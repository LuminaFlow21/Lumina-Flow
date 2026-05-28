import logging
from datetime import datetime
from flask import Blueprint, request, jsonify, session
from ..supabase_handler import get_supabase_handler
from ..stripe_handler import get_stripe_handler
from ..services.billing_logs import (
    save_webhook_log,
    is_webhook_processed,
    mark_webhook_processed,
    mark_webhook_failed,
    create_billing_audit_log,
    upsert_subscription_from_stripe,
    upsert_payment_from_invoice,
    get_user_id_from_checkout_webhook
)
from .dashboard import login_required

payments_bp = Blueprint('payments', __name__)
logger = logging.getLogger(__name__)

@payments_bp.route('/create-checkout-session', methods=['POST'])
@login_required
def create_checkout_session():
    data = request.get_json() or {}
    price_id_key = data.get('priceIdKey') or data.get('price_id_key')  # e.g., 'br_monthly'
    explicit_price_id = data.get('price_id')
    currency = data.get('currency')

    user_id = session['user_id']
    user_email = session['user_email']

    supabase = get_supabase_handler()
    profile = supabase.get_user_subscription(user_id)
    customer_id = profile.get('stripe_customer_id') if profile.get('success') else None

    stripe_handler = get_stripe_handler()
    
    # Check if customer exists in Stripe before using it
    if customer_id:
        try:
            stripe_customer = stripe_handler.stripe.Customer.retrieve(customer_id)
            if not stripe_customer:
                # Customer doesn't exist in Stripe, clear it from profile
                customer_id = None
                supabase.update_user_subscription(
                    user_id=user_id,
                    stripe_customer_id=None
                )
                logger.warning(f'Customer {customer_id} not found in Stripe, cleared from profile', extra={'user_id': user_id})
        except Exception as e:
            # Customer doesn't exist in Stripe, clear it from profile
            customer_id = None
            supabase.update_user_subscription(
                user_id=user_id,
                stripe_customer_id=None
            )
            logger.warning(f'Customer {customer_id} not found in Stripe, cleared from profile', extra={'user_id': user_id, 'error': str(e)})

    price_id = explicit_price_id
    if not price_id and price_id_key:
        price_id = stripe_handler.get_price_id_by_key(price_id_key)
        if not currency:
            currency = 'brl' if price_id_key.startswith('br_') else 'gbp'

    if not price_id:
        logger.warning('Invalid price configuration for checkout', extra={'user_id': user_id, 'price_id_key': price_id_key})
        return jsonify({'success': False, 'error': 'Invalid price configuration'}), 400

    session_result = stripe_handler.create_checkout_session(
        price_id=price_id,
        user_id=user_id,
        user_email=user_email,
        currency=currency or 'brl',
        customer_id=customer_id
    )

    if session_result.get('success'):
        logger.info('Stripe checkout session created', extra={'user_id': user_id})
        return jsonify({'success': True, 'checkout_url': session_result['checkout_url']})
    else:
        logger.error('Stripe checkout session failed', extra={'user_id': user_id, 'error': session_result.get('error')})
        return jsonify({'success': False, 'error': session_result.get('error', 'Failed to create checkout session')}), 500

@payments_bp.route('/webhook/stripe', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    
    stripe_handler = get_stripe_handler()
    event_result = stripe_handler.handle_webhook(payload, sig_header)
    
    if not event_result.get('success'):
        logger.warning('Stripe webhook rejected', extra={'error': event_result.get('error')})
        return jsonify({'error': event_result.get('error')}), 400
    
    event = event_result['event']
    event_type = event['type']
    stripe_event_id = event['id']
    
    logger.info('Stripe webhook received', extra={'event_type': event_type, 'event_id': stripe_event_id})
    
    # Check idempotency: skip if already processed
    if is_webhook_processed(stripe_event_id):
        logger.warning(
            '[IDEMPOTENCY] Webhook already processed, SKIPPING',
            extra={
                'event_type': event_type,
                'event_id': stripe_event_id,
                'reason': 'Event already marked as processed in stripe_webhook_logs'
            }
        )
        return jsonify({'status': 'success', 'message': 'Already processed'}), 200
    
    # Save webhook log before processing - convert event to dict
    event_dict = _stripe_object_to_dict(event)
    log_result = save_webhook_log(event_dict)
    if not log_result.get('success'):
        logger.error('Failed to save webhook log', extra={'stripe_event_id': stripe_event_id})
        # Continue processing even if log save fails
    
    try:
        # Process events based on type
        if event_type == 'checkout.session.completed':
            _handle_checkout_session_completed(event)
        elif event_type == 'customer.subscription.created':
            _handle_subscription_created(event)
        elif event_type == 'customer.subscription.updated':
            _handle_subscription_updated(event)
        elif event_type == 'customer.subscription.deleted':
            _handle_subscription_deleted(event)
        elif event_type == 'invoice.payment_succeeded':
            _handle_invoice_payment_succeeded(event)
        elif event_type == 'invoice.payment_failed':
            _handle_invoice_payment_failed(event)
        elif event_type == 'payment_intent.payment_failed':
            _handle_payment_intent_payment_failed(event)
        else:
            logger.info('Unhandled webhook event type', extra={'event_type': event_type})
        
        # Mark webhook as processed
        mark_webhook_processed(stripe_event_id)
        logger.info('Stripe webhook processed successfully', extra={'event_type': event_type, 'event_id': stripe_event_id})
        
        return jsonify({'status': 'success'}), 200
        
    except Exception as e:
        logger.exception('Error processing Stripe webhook', extra={'event_type': event_type, 'event_id': stripe_event_id})
        mark_webhook_failed(stripe_event_id, str(e))
        return jsonify({'error': str(e)}), 500


def _handle_checkout_session_completed(event):
    """Handle checkout.session.completed event"""
    stripe_event_id = event['id']
    session_data = _stripe_object_to_dict(event['data']['object'])
    customer_id = session_data.get('customer')
    subscription_id = session_data.get('subscription')
    metadata = session_data.get('metadata', {})
    user_id = metadata.get('user_id')
    
    logger.info(
        '[DEBUG] Checkout session completed - START',
        extra={
            'stripe_event_id': stripe_event_id,
            'customer_id': customer_id,
            'subscription_id': subscription_id,
            'user_id': user_id,
            'metadata_keys': list(metadata.keys())
        }
    )
    
    # Update profile with stripe_customer_id and stripe_subscription_id
    # This allows invoice.payment_succeeded to find the user later
    if user_id and customer_id and subscription_id:
        # Check if profile is already active (prevent downgrade)
        is_already_active = _is_profile_already_active(user_id)
        
        if is_already_active:
            logger.warning(
                '[DEBUG] Profile already active, skipping plan/status downgrade in checkout.session.completed',
                extra={
                    'user_id': user_id,
                    'reason': 'Profile already has plan=basic and subscription_status=active'
                }
            )
            # Only update Stripe IDs, not plan/status
            try:
                supabase = get_supabase_handler()
                update_result = supabase.update_user_subscription(
                    user_id=user_id,
                    plan=None,  # Don't change plan
                    subscription_status=None,  # Don't change status
                    stripe_customer_id=customer_id,
                    stripe_subscription_id=subscription_id,
                    next_billing_date=None
                )

                if update_result.get('success'):
                    logger.info(
                        '[SUCCESS] Profile Stripe IDs updated (no plan/status change)',
                        extra={
                            'user_id': user_id,
                            'stripe_customer_id': customer_id,
                            'stripe_subscription_id': subscription_id
                        }
                    )
                else:
                    logger.error(
                        '[ERROR] Failed to update profile Stripe IDs',
                        extra={
                            'user_id': user_id,
                            'error': update_result.get('error')
                        }
                    )
            except Exception as e:
                logger.exception(
                    '[ERROR] Exception updating profile Stripe IDs',
                    extra={'user_id': user_id}
                )
        else:
            logger.info(
                '[DEBUG] Preparing to update profile with Stripe IDs and free/inactive',
                extra={
                    'user_id': user_id,
                    'stripe_customer_id': customer_id,
                    'stripe_subscription_id': subscription_id,
                    'target_plan': 'free',
                    'target_status': 'inactive'
                }
            )
            try:
                supabase = get_supabase_handler()
                update_result = supabase.update_user_subscription(
                    user_id=user_id,
                    plan='free',  # Keep free until payment succeeds
                    subscription_status='inactive',  # Profile will be activated on payment success
                    stripe_customer_id=customer_id,
                    stripe_subscription_id=subscription_id,
                    next_billing_date=None
                )

                logger.info(
                    '[DEBUG] Supabase update_user_subscription result',
                    extra={
                        'update_success': update_result.get('success'),
                        'update_error': update_result.get('error'),
                        'update_data': update_result.get('data')
                    }
                )

                if update_result.get('success'):
                    logger.info(
                        '[SUCCESS] Profiles/users synced after checkout session',
                        extra={
                            'user_id': user_id,
                            'stripe_customer_id': customer_id,
                            'stripe_subscription_id': subscription_id,
                            'plan': 'free',
                            'subscription_status': 'inactive'
                        }
                    )
                else:
                    logger.error(
                        '[ERROR] Failed to sync profiles/users after checkout session',
                        extra={
                            'user_id': user_id,
                            'stripe_customer_id': customer_id,
                            'subscription_id': subscription_id,
                            'error': update_result.get('error'),
                            'full_update_result': str(update_result)
                        }
                    )
            except Exception as e:
                logger.exception(
                    '[ERROR] Exception updating profile with Stripe IDs',
                    extra={
                        'user_id': user_id,
                        'customer_id': customer_id,
                        'exception_type': type(e).__name__,
                        'exception_message': str(e)
                    }
                )
    else:
        logger.warning(
            '[DEBUG] Missing required IDs for profile update',
            extra={
                'user_id': user_id,
                'customer_id': customer_id,
                'subscription_id': subscription_id
            }
        )
    
    # Create audit log - subscription will be activated by invoice.payment_succeeded
    create_billing_audit_log(
        user_id=user_id,
        company_id=None,
        stripe_event_id=event['id'],
        event='checkout.session.completed',
        description='Checkout completed successfully',
        metadata={
            'customer_id': customer_id,
            'subscription_id': subscription_id,
            'metadata': metadata
        }
    )


def _handle_subscription_created(event):
    """Handle customer.subscription.created event"""
    subscription_data = _stripe_object_to_dict(event['data']['object'])
    stripe_subscription_id = subscription_data.get('id')
    stripe_customer_id = subscription_data.get('customer')
    status = subscription_data.get('status')
    
    logger.info(
        'Subscription created',
        extra={
            'stripe_subscription_id': stripe_subscription_id,
            'stripe_customer_id': stripe_customer_id,
            'status': status
        }
    )
    
    # Upsert subscription to billing table
    upsert_subscription_from_stripe(subscription_data)
    
    # Try to find profile by stripe_customer_id and update stripe_subscription_id
    user_id = _get_user_id_from_customer(stripe_customer_id)
    
    # Fallback: try to get user_id from checkout.session.completed webhook
    if not user_id:
        checkout_result = get_user_id_from_checkout_webhook(stripe_customer_id=stripe_customer_id)
        if checkout_result.get('success'):
            user_id = checkout_result.get('user_id')
            logger.info('Found user_id from checkout webhook fallback', extra={'user_id': user_id})
    
    if user_id:
        # Extract next_billing_date from subscription data
        next_billing_date = _get_next_billing_date_from_subscription(subscription_data)
        
        # Check if profile is already active (prevent downgrade)
        is_already_active = _is_profile_already_active(user_id)
        
        if is_already_active:
            logger.warning(
                '[DEBUG] Profile already active, skipping plan downgrade in subscription.created',
                extra={
                    'user_id': user_id,
                    'reason': 'Profile already has plan=basic and subscription_status=active'
                }
            )
            # Only update Stripe IDs, next_billing_date, and status (not plan)
            try:
                supabase = get_supabase_handler()
                update_result = supabase.update_user_subscription(
                    user_id=user_id,
                    plan=None,  # Don't change plan
                    subscription_status=status,  # Sync status from Stripe
                    stripe_customer_id=stripe_customer_id,
                    stripe_subscription_id=stripe_subscription_id,
                    next_billing_date=next_billing_date
                )
                if update_result.get('success'):
                    logger.info(
                        '[SUCCESS] Profile updated (no plan change) after subscription created',
                        extra={
                            'user_id': user_id,
                            'subscription_status': status,
                            'stripe_customer_id': stripe_customer_id,
                            'stripe_subscription_id': stripe_subscription_id,
                            'next_billing_date': next_billing_date
                        }
                    )
                else:
                    logger.error(
                        '[ERROR] Failed to update profile after subscription created',
                        extra={
                            'user_id': user_id,
                            'error': update_result.get('error')
                        }
                    )
            except Exception as e:
                logger.exception(
                    '[ERROR] Exception updating profile after subscription created',
                    extra={'user_id': user_id}
                )
        else:
            logger.info(
                '[DEBUG] Updating profile with free plan after subscription created',
                extra={
                    'user_id': user_id,
                    'subscription_status': status,
                    'next_billing_date': next_billing_date
                }
            )
            try:
                supabase = get_supabase_handler()
                update_result = supabase.update_user_subscription(
                    user_id=user_id,
                    plan='free',  # Keep free until payment
                    subscription_status=status,  # Use actual status from Stripe
                    stripe_customer_id=stripe_customer_id,
                    stripe_subscription_id=stripe_subscription_id,
                    next_billing_date=next_billing_date
                )
                if update_result.get('success'):
                    logger.info(
                        'Profiles/users synced after subscription created',
                        extra={
                            'user_id': user_id,
                            'plan': 'free',
                            'subscription_status': status,
                            'stripe_customer_id': stripe_customer_id,
                            'stripe_subscription_id': stripe_subscription_id,
                            'next_billing_date': next_billing_date
                        }
                    )
                else:
                    logger.error(
                        'Failed to sync profiles/users after subscription created',
                        extra={
                            'user_id': user_id,
                            'stripe_customer_id': stripe_customer_id,
                            'stripe_subscription_id': stripe_subscription_id,
                            'error': update_result.get('error')
                        }
                    )
            except Exception as e:
                logger.exception(
                    'Error updating profile with subscription ID',
                    extra={'user_id': user_id}
                )
    else:
        logger.warning('Could not find user_id for customer in profiles or checkout webhooks', extra={'stripe_customer_id': stripe_customer_id})
    
    # Create audit log (even with null user_id/company_id)
    create_billing_audit_log(
        user_id=user_id,
        company_id=None,
        stripe_event_id=event['id'],
        event='customer.subscription.created',
        description='Subscription created in Stripe',
        metadata={
            'stripe_subscription_id': stripe_subscription_id,
            'stripe_customer_id': stripe_customer_id,
            'status': status
        }
    )


def _handle_subscription_updated(event):
    """
    Handle customer.subscription.updated event.
    Synchronizes status, next billing date, cancel_at, current_period_start, current_period_end.
    Does NOT change plan - plan changes are event-specific.
    """
    subscription_data = _stripe_object_to_dict(event['data']['object'])
    stripe_subscription_id = subscription_data.get('id')
    stripe_customer_id = subscription_data.get('customer')
    status = subscription_data.get('status')
    cancel_at = subscription_data.get('cancel_at')
    current_period_start = subscription_data.get('current_period_start')
    current_period_end = subscription_data.get('current_period_end')
    cancel_at_period_end = subscription_data.get('cancel_at_period_end')
    
    logger.info(
        '[DEBUG] Subscription updated',
        extra={
            'stripe_subscription_id': stripe_subscription_id,
            'status': status,
            'cancel_at': cancel_at,
            'current_period_start': current_period_start,
            'current_period_end': current_period_end,
            'cancel_at_period_end': cancel_at_period_end
        }
    )
    
    # Upsert subscription to billing table
    upsert_subscription_from_stripe(subscription_data)
    
    # Update Supabase profile with new status and billing info (no plan change)
    user_id = _get_user_id_from_customer(stripe_customer_id)
    if user_id:
        # Extract next_billing_date from subscription data (no API call)
        next_billing_date = _get_next_billing_date_from_subscription(subscription_data)
        
        # Convert cancel_at timestamp to ISO date if exists
        cancel_at_date = None
        if cancel_at:
            try:
                cancel_at_date = datetime.fromtimestamp(cancel_at).isoformat()
            except Exception as e:
                logger.warning('[DEBUG] Error converting cancel_at to date', extra={'cancel_at': cancel_at, 'error': str(e)})
        
        logger.info(
            '[DEBUG] Updating profile subscription with billing dates',
            extra={
                'user_id': user_id,
                'subscription_status': status,
                'next_billing_date': next_billing_date,
                'cancel_at': cancel_at_date,
                'current_period_end': current_period_end
            }
        )
        
        update_result = _update_profile_subscription(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            subscription_status=status,
            next_billing_date=next_billing_date,
            cancel_at=cancel_at_date
        )
        if not update_result.get('success'):
            logger.error(
                '[ERROR] Failed to sync subscription update',
                extra={
                    'user_id': user_id,
                    'stripe_subscription_id': stripe_subscription_id,
                    'error': update_result.get('error')
                }
            )
    else:
        logger.warning('Could not find user_id for customer in profiles', extra={'stripe_customer_id': stripe_customer_id})
    
    # Create audit log (even with null user_id/company_id)
    create_billing_audit_log(
        user_id=user_id,
        company_id=None,
        stripe_event_id=event['id'],
        event='customer.subscription.updated',
        description=f'Subscription updated to status: {status}, cancel_at_period_end: {cancel_at_period_end}',
        metadata={
            'stripe_subscription_id': stripe_subscription_id,
            'status': status,
            'cancel_at_period_end': cancel_at_period_end
        }
    )


def _handle_subscription_deleted(event):
    """Handle customer.subscription.deleted event"""
    subscription_data = _stripe_object_to_dict(event['data']['object'])
    stripe_subscription_id = subscription_data.get('id')
    stripe_customer_id = subscription_data.get('customer')
    
    logger.info(
        'Subscription deleted',
        extra={
            'stripe_subscription_id': stripe_subscription_id,
            'stripe_customer_id': stripe_customer_id
        }
    )
    
    # Upsert subscription to billing table
    upsert_subscription_from_stripe(subscription_data)
    
    # Get user_id and update profile
    user_id = _get_user_id_from_customer(stripe_customer_id)
    if user_id:
        # Update profile: plan to free, status to canceled, clear subscription_id
        supabase = get_supabase_handler()
        try:
            update_result = supabase.update_user_subscription(
                user_id=user_id,
                plan='free',
                subscription_status='canceled',
                stripe_customer_id=stripe_customer_id,
                stripe_subscription_id=None,
                next_billing_date=None
            )

            if update_result.get('success'):
                # Update auth handler only when Supabase confirmed
                from ..auth_handler import get_auth_handler
                auth_handler = get_auth_handler()
                auth_handler.update_user_plan(user_id, 'free')

                logger.info(
                    'Profiles/users synced after subscription deleted',
                    extra={
                        'user_id': user_id,
                        'plan': 'free',
                        'subscription_status': 'canceled',
                        'stripe_customer_id': stripe_customer_id
                    }
                )
            else:
                logger.error(
                    'Failed to sync profiles/users after subscription deleted',
                    extra={
                        'user_id': user_id,
                        'stripe_customer_id': stripe_customer_id,
                        'error': update_result.get('error')
                    }
                )
        except Exception as e:
            logger.exception(
                'Error canceling subscription in Supabase',
                extra={'user_id': user_id, 'stripe_customer_id': stripe_customer_id}
            )
    else:
        logger.warning('Could not find user_id for customer in profiles', extra={'stripe_customer_id': stripe_customer_id})
    
    # Create audit log (even with null user_id/company_id)
    create_billing_audit_log(
        user_id=user_id,
        company_id=None,
        stripe_event_id=event['id'],
        event='customer.subscription.deleted',
        description='Subscription canceled/deleted',
        metadata={
            'stripe_subscription_id': stripe_subscription_id,
            'stripe_customer_id': stripe_customer_id
        }
    )


def _handle_invoice_payment_succeeded(event):
    """Handle invoice.payment_succeeded event - SOURCE OF TRUTH for plan activation"""
    stripe_event_id = event['id']
    invoice_data = _stripe_object_to_dict(event['data']['object'])
    stripe_invoice_id = invoice_data.get('id')
    stripe_customer_id = invoice_data.get('customer')
    stripe_subscription_id = invoice_data.get('subscription')
    amount_paid = invoice_data.get('amount_paid')
    currency = invoice_data.get('currency')
    
    # Log all available IDs for debugging
    logger.info(
        '[DEBUG] Invoice payment succeeded - START',
        extra={
            'stripe_event_id': stripe_event_id,
            'stripe_invoice_id': stripe_invoice_id,
            'stripe_customer_id': stripe_customer_id,
            'stripe_subscription_id_from_invoice': stripe_subscription_id,
            'amount_paid': amount_paid,
            'currency': currency,
            'invoice_data_keys': list(invoice_data.keys())
        }
    )
    
    # Try to extract subscription_id from other possible locations
    subscription_id_from_parent = None
    if 'parent' in invoice_data:
        parent = invoice_data.get('parent', {})
        if isinstance(parent, dict):
            subscription_details = parent.get('subscription_details', {})
            if isinstance(subscription_details, dict):
                subscription_id_from_parent = subscription_details.get('subscription')
    
    if subscription_id_from_parent:
        logger.info(
            '[DEBUG] Found subscription_id from invoice.parent.subscription_details',
            extra={'subscription_id_from_parent': subscription_id_from_parent}
        )
        if not stripe_subscription_id:
            stripe_subscription_id = subscription_id_from_parent
    
    # Get user_id by finding profile via stripe_customer_id
    user_id = _get_user_id_from_customer(stripe_customer_id)
    logger.info(
        '[DEBUG] user_id lookup by stripe_customer_id',
        extra={
            'stripe_customer_id': stripe_customer_id,
            'user_id_found': user_id
        }
    )
    
    # Fallback: try to get user_id from checkout.session.completed webhook
    if not user_id:
        logger.info(
            '[DEBUG] user_id not found by stripe_customer_id, trying fallback from checkout.session.completed',
            extra={
                'stripe_invoice_id': stripe_invoice_id,
                'stripe_customer_id': stripe_customer_id
            }
        )
        checkout_result = get_user_id_from_checkout_webhook(
            stripe_invoice_id=stripe_invoice_id,
            stripe_customer_id=stripe_customer_id
        )
        logger.info(
            '[DEBUG] checkout.session.completed fallback result',
            extra={
                'checkout_success': checkout_result.get('success'),
                'checkout_user_id': checkout_result.get('user_id'),
                'checkout_subscription_id': checkout_result.get('subscription_id'),
                'checkout_error': checkout_result.get('error')
            }
        )
        if checkout_result.get('success'):
            user_id = checkout_result.get('user_id')
            # Use subscription_id from checkout if not in invoice
            if not stripe_subscription_id:
                stripe_subscription_id = checkout_result.get('subscription_id')
            logger.info('[DEBUG] Found user_id from checkout webhook fallback', extra={'user_id': user_id})
    
    # If invoice.subscription is null, try to get subscription_id from profile
    if not stripe_subscription_id and user_id:
        logger.info('[DEBUG] subscription_id still null, trying to get from profile', extra={'user_id': user_id})
        try:
            supabase = get_supabase_handler()
            profile_result = supabase.get_user_subscription(user_id)
            logger.info(
                '[DEBUG] profile.get_user_subscription result',
                extra={
                    'profile_success': profile_result.get('success'),
                    'profile_stripe_subscription_id': profile_result.get('stripe_subscription_id'),
                    'profile_error': profile_result.get('error')
                }
            )
            if profile_result.get('success'):
                stripe_subscription_id = profile_result.get('stripe_subscription_id')
                logger.info(
                    '[DEBUG] Retrieved subscription_id from profile',
                    extra={'stripe_subscription_id': stripe_subscription_id}
                )
        except Exception as e:
            logger.exception('[DEBUG] Error getting subscription_id from profile', extra={'user_id': user_id})
    
    if user_id is None:
        logger.error(
            '[DEBUG] CRITICAL: Could not find user_id for customer in profiles or checkout webhooks',
            extra={
                'stripe_customer_id': stripe_customer_id,
                'stripe_invoice_id': stripe_invoice_id
            }
        )
    
    # Upsert payment to billing table with user_id if found
    payment_extra_data = None
    if user_id:
        payment_extra_data = {'user_id': user_id}
    upsert_payment_from_invoice(invoice_data, extra_data=payment_extra_data)
    
    # Update profile: activate subscription, update next_billing_date
    if user_id:
        # Extract next_billing_date from invoice data
        next_billing_date = _get_next_billing_date_from_invoice(invoice_data)
        
        logger.info(
            '[DEBUG] Preparing to update profile/users',
            extra={
                'user_id': user_id,
                'target_plan': 'basic',
                'target_status': 'active',
                'stripe_customer_id': stripe_customer_id,
                'stripe_subscription_id': stripe_subscription_id,
                'next_billing_date': next_billing_date
            }
        )
        
        try:
            supabase = get_supabase_handler()
            update_result = supabase.update_user_subscription(
                user_id=user_id,
                plan='basic',
                subscription_status='active',
                stripe_customer_id=stripe_customer_id,
                stripe_subscription_id=stripe_subscription_id,
                next_billing_date=next_billing_date
            )

            logger.info(
                '[DEBUG] Supabase update_user_subscription result',
                extra={
                    'update_success': update_result.get('success'),
                    'update_error': update_result.get('error'),
                    'update_data': update_result.get('data')
                }
            )

            if update_result.get('success'):
                # Update auth handler only when Supabase confirmed
                from ..auth_handler import get_auth_handler
                auth_handler = get_auth_handler()
                auth_result = auth_handler.update_user_plan(user_id, 'basic')
                
                logger.info(
                    '[DEBUG] Auth handler update_user_plan result',
                    extra={
                        'user_id': user_id,
                        'auth_result': str(auth_result)
                    }
                )

                logger.info(
                    '[SUCCESS] Profiles/users synced after invoice payment succeeded',
                    extra={
                        'user_id': user_id,
                        'plan': 'basic',
                        'subscription_status': 'active',
                        'next_billing_date': next_billing_date,
                        'stripe_customer_id': stripe_customer_id,
                        'stripe_subscription_id': stripe_subscription_id
                    }
                )
            else:
                logger.error(
                    '[ERROR] Failed to sync profiles/users after invoice payment succeeded',
                    extra={
                        'user_id': user_id,
                        'stripe_customer_id': stripe_customer_id,
                        'stripe_subscription_id': stripe_subscription_id,
                        'error': update_result.get('error'),
                        'full_update_result': str(update_result)
                    }
                )
        except Exception as e:
            logger.exception(
                '[ERROR] Exception activating user subscription',
                extra={
                    'user_id': user_id,
                    'stripe_customer_id': stripe_customer_id,
                    'stripe_subscription_id': stripe_subscription_id,
                    'exception_type': type(e).__name__,
                    'exception_message': str(e)
                }
            )
    
    # Create audit log (even with null user_id/company_id)
    create_billing_audit_log(
        user_id=user_id,
        company_id=None,
        stripe_event_id=event['id'],
        event='invoice.payment_succeeded',
        description=f'Payment succeeded: {amount_paid} {currency.upper()}',
        metadata={
            'stripe_invoice_id': stripe_invoice_id,
            'stripe_subscription_id': stripe_subscription_id,
            'amount_paid': amount_paid,
            'currency': currency
        }
    )


def _handle_invoice_payment_failed(event):
    """Handle invoice.payment_failed event"""
    invoice_data = _stripe_object_to_dict(event['data']['object'])
    stripe_invoice_id = invoice_data.get('id')
    stripe_customer_id = invoice_data.get('customer')
    stripe_subscription_id = invoice_data.get('subscription')
    amount_due = invoice_data.get('amount_due')
    currency = invoice_data.get('currency')
    
    logger.warning(
        'Invoice payment failed',
        extra={
            'stripe_invoice_id': stripe_invoice_id,
            'stripe_customer_id': stripe_customer_id,
            'stripe_subscription_id': stripe_subscription_id,
            'amount_due': amount_due
        }
    )
    
    # Get user_id by finding profile via stripe_customer_id
    user_id = _get_user_id_from_customer(stripe_customer_id)
    
    # If invoice.subscription is null, try to get subscription_id from profile
    if not stripe_subscription_id and user_id:
        try:
            supabase = get_supabase_handler()
            profile_result = supabase.get_user_subscription(user_id)
            if profile_result.get('success'):
                stripe_subscription_id = profile_result.get('stripe_subscription_id')
                logger.info(
                    'Retrieved subscription_id from profile',
                    extra={'stripe_subscription_id': stripe_subscription_id}
                )
        except Exception as e:
            logger.exception('Error getting subscription_id from profile', extra={'user_id': user_id})
    
    if user_id is None:
        logger.warning('Could not find user_id for customer in profiles', extra={'stripe_customer_id': stripe_customer_id})
    
    # Upsert payment to billing table with user_id if found
    payment_extra_data = None
    if user_id:
        payment_extra_data = {'user_id': user_id}
    upsert_payment_from_invoice(invoice_data, extra_data=payment_extra_data)
    
    # Update profile: mark as past_due if user found AND was previously active
    if user_id:
        # Check current profile state to determine correct action
        is_already_active = _is_profile_already_active(user_id)
        
        logger.info(
            '[DEBUG] Checking profile state for invoice payment failure',
            extra={
                'user_id': user_id,
                'is_already_active': is_already_active
            }
        )
        
        if is_already_active:
            # User was active: mark as past_due (renewal failure)
            logger.info(
                '[DEBUG] Active user invoice payment failed, marking as past_due',
                extra={'user_id': user_id}
            )
            try:
                supabase = get_supabase_handler()
                update_result = supabase.update_user_subscription(
                    user_id=user_id,
                    plan='basic',  # Keep current plan
                    subscription_status='past_due',
                    stripe_customer_id=stripe_customer_id,
                    stripe_subscription_id=stripe_subscription_id,
                    next_billing_date=None
                )
                if update_result.get('success'):
                    logger.info(
                        '[SUCCESS] Profiles/users synced after invoice payment failed',
                        extra={
                            'user_id': user_id,
                            'plan': 'basic',
                            'subscription_status': 'past_due',
                            'stripe_customer_id': stripe_customer_id,
                            'stripe_subscription_id': stripe_subscription_id
                        }
                    )
                else:
                    logger.error(
                        '[ERROR] Failed to sync profiles/users after invoice payment failed',
                        extra={
                            'user_id': user_id,
                            'stripe_customer_id': stripe_customer_id,
                            'stripe_subscription_id': stripe_subscription_id,
                            'error': update_result.get('error')
                        }
                    )
            except Exception as e:
                logger.exception(
                    '[ERROR] Error marking subscription as past_due',
                    extra={'user_id': user_id}
                )
        else:
            # User was free: keep free/inactive (first checkout failure)
            logger.info(
                '[DEBUG] Free user invoice payment failed, keeping free/inactive',
                extra={'user_id': user_id}
            )
            # No action needed - user remains free/inactive
            # Just log that we checked
    
    # Create audit log (even with null user_id/company_id)
    create_billing_audit_log(
        user_id=user_id,
        company_id=None,
        stripe_event_id=event['id'],
        event='invoice.payment_failed',
        description=f'Payment failed: {amount_due} {currency.upper()}',
        metadata={
            'stripe_invoice_id': stripe_invoice_id,
            'stripe_subscription_id': stripe_subscription_id,
            'amount_due': amount_due,
            'failure_reason': invoice_data.get('last_payment_error', {}).get('message')
        }
    )


def _handle_payment_intent_payment_failed(event):
    """
    Handle payment_intent.payment_failed event
    
    This handles payment failures in two scenarios:
    1. First checkout (user is free): keep plan=free, subscription_status=inactive
    2. Renewal (user is active): mark subscription_status=past_due, keep plan=basic
    
    Always creates audit log. Attempts to save payment record if possible.
    """
    payment_intent_data = _stripe_object_to_dict(event['data']['object'])
    payment_intent_id = payment_intent_data.get('id')
    stripe_customer_id = payment_intent_data.get('customer')
    amount = payment_intent_data.get('amount')
    currency = payment_intent_data.get('currency')
    
    # Extract failure reason
    last_payment_error = payment_intent_data.get('last_payment_error', {})
    failure_reason = last_payment_error.get('message') if last_payment_error else None
    
    logger.warning(
        '[DEBUG] Payment intent payment failed',
        extra={
            'payment_intent_id': payment_intent_id,
            'stripe_customer_id': stripe_customer_id,
            'amount': amount,
            'currency': currency,
            'failure_reason': failure_reason
        }
    )
    
    # Try to find user_id
    user_id = _get_user_id_from_customer(stripe_customer_id)
    
    # Fallback: try to get user_id from checkout.session.completed webhook
    if not user_id and stripe_customer_id:
        checkout_result = get_user_id_from_checkout_webhook(stripe_customer_id=stripe_customer_id)
        if checkout_result.get('success'):
            user_id = checkout_result.get('user_id')
            logger.info('[DEBUG] Found user_id from checkout webhook fallback', extra={'user_id': user_id})
    
    if user_id:
        # Check current profile state to determine correct action
        is_already_active = _is_profile_already_active(user_id)
        
        logger.info(
            '[DEBUG] Checking profile state for payment failure',
            extra={
                'user_id': user_id,
                'is_already_active': is_already_active
            }
        )
        
        if is_already_active:
            # User was active: mark as past_due (renewal failure)
            logger.info(
                '[DEBUG] Active user payment failed, marking as past_due',
                extra={'user_id': user_id}
            )
            try:
                supabase = get_supabase_handler()
                update_result = supabase.update_user_subscription(
                    user_id=user_id,
                    plan='basic',  # Keep current plan
                    subscription_status='past_due',
                    stripe_customer_id=stripe_customer_id,
                    stripe_subscription_id=None,  # May not have subscription in payment_intent
                    next_billing_date=None
                )
                if update_result.get('success'):
                    logger.info(
                        '[SUCCESS] Profile marked as past_due after payment failure',
                        extra={
                            'user_id': user_id,
                            'plan': 'basic',
                            'subscription_status': 'past_due'
                        }
                    )
                else:
                    logger.error(
                        '[ERROR] Failed to mark profile as past_due',
                        extra={
                            'user_id': user_id,
                            'error': update_result.get('error')
                        }
                    )
            except Exception as e:
                logger.exception(
                    '[ERROR] Exception marking profile as past_due',
                    extra={'user_id': user_id}
                )
        else:
            # User was free: keep free/inactive (first checkout failure)
            logger.info(
                '[DEBUG] Free user payment failed, keeping free/inactive',
                extra={'user_id': user_id}
            )
            # No action needed - user remains free/inactive
            # Just log that we checked
    
    # Create audit log (even with null user_id)
    currency_str = currency.upper() if currency else ''
    create_billing_audit_log(
        user_id=user_id,
        company_id=None,
        stripe_event_id=event['id'],
        event='payment_intent.payment_failed',
        description=f'Payment failed: {amount / 100:.2f} {currency_str}',
        metadata={
            'payment_intent_id': payment_intent_id,
            'stripe_customer_id': stripe_customer_id,
            'amount': amount,
            'currency': currency,
            'failure_reason': failure_reason
        }
    )
    
    # Note: We cannot save payment record directly from payment_intent
    # because upsert_payment_from_invoice expects invoice data
    # Payment records are saved when invoice events arrive


def _get_user_id_from_customer(stripe_customer_id):
    """Get user_id from Stripe customer by querying profiles table"""
    try:
        supabase = get_supabase_handler()
        response = supabase.admin_client.table('profiles') \
            .select('user_id') \
            .eq('stripe_customer_id', stripe_customer_id) \
            .execute()
        
        if response.data and len(response.data) > 0:
            return response.data[0].get('user_id')
        return None
    except Exception as e:
        logger.exception('Error getting user_id from customer', extra={'stripe_customer_id': stripe_customer_id})
        return None


def _is_profile_already_active(user_id):
    """
    Check if profile is already active (plan=basic and subscription_status=active)
    Used to prevent downgrade from later events
    
    Args:
        user_id: User ID
        
    Returns:
        True if profile is already active, False otherwise
    """
    try:
        supabase = get_supabase_handler()
        response = supabase.admin_client.table('profiles') \
            .select('plan', 'subscription_status') \
            .eq('user_id', user_id) \
            .execute()
        
        if response.data and len(response.data) > 0:
            profile = response.data[0]
            plan = profile.get('plan')
            subscription_status = profile.get('subscription_status')
            
            is_active = plan == 'basic' and subscription_status == 'active'
            logger.info(
                '[DEBUG] Profile active status check',
                extra={
                    'user_id': user_id,
                    'current_plan': plan,
                    'current_subscription_status': subscription_status,
                    'is_active': is_active
                }
            )
            return is_active
        
        return False
    except Exception as e:
        logger.exception(
            '[DEBUG] Error checking if profile is already active',
            extra={'user_id': user_id}
        )
        return False


def _update_profile_subscription(user_id, stripe_customer_id, stripe_subscription_id, subscription_status, next_billing_date=None, cancel_at=None):
    """
    Update profile subscription status, next billing date, and cancel_at.
    NOTE: Does NOT change plan automatically - plan changes are handled by specific handlers.
    
    Args:
        user_id: User ID
        stripe_customer_id: Stripe customer ID
        stripe_subscription_id: Stripe subscription ID
        subscription_status: Subscription status
        next_billing_date: Next billing date (optional, will be fetched if not provided)
        cancel_at: Cancellation date (optional)
    """
    try:
        supabase = get_supabase_handler()
        
        # Get next billing date if not provided and subscription exists
        if next_billing_date is None and stripe_subscription_id:
            next_billing_date = _get_next_billing_date(stripe_subscription_id)
        
        # Update without changing plan (plan changes are event-specific)
        update_result = supabase.update_user_subscription(
            user_id=user_id,
            plan=None,  # Don't change plan
            subscription_status=subscription_status,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            next_billing_date=next_billing_date,
            cancel_at=cancel_at
        )
        
        if update_result.get('success'):
            logger.info(
                'Profile subscription status updated',
                extra={
                    'user_id': user_id,
                    'subscription_status': subscription_status,
                    'stripe_subscription_id': stripe_subscription_id,
                    'next_billing_date': next_billing_date
                }
            )
            return {'success': True}
        else:
            logger.error(
                'Failed to update profile subscription status',
                extra={
                    'user_id': user_id,
                    'subscription_status': subscription_status,
                    'error': update_result.get('error')
                }
            )
            return {'success': False, 'error': update_result.get('error')}
        
    except Exception as e:
        logger.exception(
            'Error updating profile subscription',
            extra={'user_id': user_id}
        )
        return {'success': False, 'error': str(e)}


def _stripe_object_to_dict(obj):
    """Convert Stripe object to dict safely"""
    if obj is None:
        return {}
    if hasattr(obj, 'to_dict'):
        try:
            return obj.to_dict()
        except Exception:
            pass
    if isinstance(obj, dict):
        return obj
    try:
        return dict(obj)
    except Exception:
        return {}


def _get_next_billing_date_from_invoice(invoice_data):
    """
    Extract next billing date from invoice data
    
    Tries multiple sources in order:
    1. invoice.lines.data[0].period.end
    2. invoice.period_end
    3. subscription.current_period_end (fallback to Stripe API)
    
    Args:
        invoice_data: Invoice data as dict
        
    Returns:
        ISO format date string or None
    """
    try:
        # Try invoice.lines.data[0].period.end
        lines = invoice_data.get('lines', {})
        lines_data = lines.get('data', [])
        if lines_data and len(lines_data) > 0:
            first_line = lines_data[0]
            period = first_line.get('period', {})
            period_end = period.get('end')
            if period_end:
                logger.info(
                    '[DEBUG] Found next_billing_date from invoice.lines.data[0].period.end',
                    extra={'period_end': period_end}
                )
                return datetime.fromtimestamp(period_end).isoformat()
        
        # Try invoice.period_end
        period_end = invoice_data.get('period_end')
        if period_end:
            logger.info(
                '[DEBUG] Found next_billing_date from invoice.period_end',
                extra={'period_end': period_end}
            )
            return datetime.fromtimestamp(period_end).isoformat()
        
        # Fallback to Stripe API
        stripe_subscription_id = invoice_data.get('subscription')
        if stripe_subscription_id:
            stripe_handler = get_stripe_handler()
            return stripe_handler.get_next_billing_date(stripe_subscription_id)
        
        logger.warning(
            '[DEBUG] Could not find next_billing_date in invoice',
            extra={'invoice_data_keys': list(invoice_data.keys())}
        )
        return None
    except Exception as e:
        logger.exception(
            '[DEBUG] Error extracting next_billing_date from invoice',
            extra={'invoice_id': invoice_data.get('id')}
        )
        return None


def _get_next_billing_date_from_subscription(subscription_data):
    """
    Extract next billing date from subscription data
    
    Tries multiple sources in order:
    1. subscription.items.data[0].current_period_end
    2. subscription.current_period_end
    
    Args:
        subscription_data: Subscription data as dict
        
    Returns:
        ISO format date string or None
    """
    try:
        # Try subscription.items.data[0].current_period_end
        items = subscription_data.get('items', {})
        items_data = items.get('data', [])
        if items_data and len(items_data) > 0:
            first_item = items_data[0]
            current_period_end = first_item.get('current_period_end')
            if current_period_end:
                logger.info(
                    '[DEBUG] Found next_billing_date from subscription.items.data[0].current_period_end',
                    extra={'current_period_end': current_period_end}
                )
                return datetime.fromtimestamp(current_period_end).isoformat()
        
        # Try subscription.current_period_end
        current_period_end = subscription_data.get('current_period_end')
        if current_period_end:
            logger.info(
                '[DEBUG] Found next_billing_date from subscription.current_period_end',
                extra={'current_period_end': current_period_end}
            )
            return datetime.fromtimestamp(current_period_end).isoformat()
        
        logger.warning(
            '[DEBUG] Could not find next_billing_date in subscription',
            extra={'subscription_data_keys': list(subscription_data.keys())}
        )
        return None
    except Exception as e:
        logger.exception(
            '[DEBUG] Error extracting next_billing_date from subscription',
            extra={'subscription_id': subscription_data.get('id')}
        )
        return None


@payments_bp.route('/customer-portal', methods=['POST'])
def customer_portal():
    """
    Create a Stripe Customer Portal session for updating payment methods
    
    Requires authenticated user.
    Returns JSON with portal URL or error.
    """
    from flask_login import current_user
    from ..config import Config
    
    if not current_user.is_authenticated:
        return jsonify({'success': False, 'error': 'Authentication required'}), 401
    
    try:
        # Get user's stripe_customer_id from profile
        supabase = get_supabase_handler()
        profile_result = supabase.admin_client.table('profiles') \
            .select('stripe_customer_id') \
            .eq('user_id', current_user.id) \
            .execute()
        
        if not profile_result.data or len(profile_result.data) == 0:
            return jsonify({'success': False, 'error': 'Profile not found'}), 404
        
        stripe_customer_id = profile_result.data[0].get('stripe_customer_id')
        
        if not stripe_customer_id:
            return jsonify({'success': False, 'error': 'No Stripe customer found. Please complete checkout first.'}), 400
        
        # Create customer portal session
        stripe_handler = get_stripe_handler()
        return_url = Config.BASE_URL + '/dashboard/profile'
        portal_result = stripe_handler.create_customer_portal_session(stripe_customer_id, return_url)
        
        if portal_result.get('success'):
            return jsonify({
                'success': True,
                'url': portal_result['url']
            }), 200
        else:
            return jsonify({'success': False, 'error': portal_result.get('error')}), 500
            
    except Exception as e:
        logger.exception('Error creating customer portal session', extra={'user_id': current_user.id})
        return jsonify({'success': False, 'error': str(e)}), 500


def _get_next_billing_date(stripe_subscription_id):
    """Get next billing date from Stripe subscription"""
    try:
        stripe_handler = get_stripe_handler()
        return stripe_handler.get_next_billing_date(stripe_subscription_id)
    except Exception as e:
        logger.exception('Error getting next billing date', extra={'stripe_subscription_id': stripe_subscription_id})
        return None