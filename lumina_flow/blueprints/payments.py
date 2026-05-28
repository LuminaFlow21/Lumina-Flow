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
        logger.info(
            '[DEBUG] Preparing to update profile with Stripe IDs',
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
        try:
            supabase = get_supabase_handler()
            update_result = supabase.update_user_subscription(
                user_id=user_id,
                plan='free',  # Keep free until payment
                subscription_status=status,  # Use actual status from Stripe
                stripe_customer_id=stripe_customer_id,
                stripe_subscription_id=stripe_subscription_id,
                next_billing_date=None
            )
            if update_result.get('success'):
                logger.info(
                    'Profiles/users synced after subscription created',
                    extra={
                        'user_id': user_id,
                        'plan': 'free',
                        'subscription_status': status,
                        'stripe_customer_id': stripe_customer_id,
                        'stripe_subscription_id': stripe_subscription_id
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
    Synchronizes status, next billing date, cancel_at_period_end, current period.
    Does NOT change plan - plan changes are event-specific.
    """
    subscription_data = _stripe_object_to_dict(event['data']['object'])
    stripe_subscription_id = subscription_data.get('id')
    stripe_customer_id = subscription_data.get('customer')
    status = subscription_data.get('status')
    cancel_at_period_end = subscription_data.get('cancel_at_period_end')
    
    logger.info(
        'Subscription updated',
        extra={
            'stripe_subscription_id': stripe_subscription_id,
            'status': status,
            'cancel_at_period_end': cancel_at_period_end
        }
    )
    
    # Upsert subscription to billing table
    upsert_subscription_from_stripe(subscription_data)
    
    # Update Supabase profile with new status and billing info (no plan change)
    user_id = _get_user_id_from_customer(stripe_customer_id)
    if user_id:
        update_result = _update_profile_subscription(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            subscription_status=status
        )
        if not update_result.get('success'):
            logger.error(
                'Failed to sync subscription update',
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
        next_billing_date = None
        if stripe_subscription_id:
            next_billing_date = _get_next_billing_date(stripe_subscription_id)
        
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
    
    # Update profile: mark as past_due if user found
    if user_id:
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
                    'Profiles/users synced after invoice payment failed',
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
                    'Failed to sync profiles/users after invoice payment failed',
                    extra={
                        'user_id': user_id,
                        'stripe_customer_id': stripe_customer_id,
                        'stripe_subscription_id': stripe_subscription_id,
                        'error': update_result.get('error')
                    }
                )
        except Exception as e:
            logger.exception(
                'Error marking subscription as past_due',
                extra={'user_id': user_id}
            )
    
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


def _update_profile_subscription(user_id, stripe_customer_id, stripe_subscription_id, subscription_status):
    """
    Update profile subscription status and next billing date.
    NOTE: Does NOT change plan automatically - plan changes are handled by specific handlers.
    """
    try:
        supabase = get_supabase_handler()
        
        # Get next billing date if subscription exists
        next_billing_date = None
        if stripe_subscription_id:
            next_billing_date = _get_next_billing_date(stripe_subscription_id)
        
        # Update without changing plan (plan changes are event-specific)
        update_result = supabase.update_user_subscription(
            user_id=user_id,
            plan=None,  # Don't change plan
            subscription_status=subscription_status,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            next_billing_date=next_billing_date
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


def _get_next_billing_date(stripe_subscription_id):
    """Get next billing date from Stripe subscription"""
    try:
        stripe_handler = get_stripe_handler()
        return stripe_handler.get_next_billing_date(stripe_subscription_id)
    except Exception as e:
        logger.exception('Error getting next billing date', extra={'stripe_subscription_id': stripe_subscription_id})
        return None