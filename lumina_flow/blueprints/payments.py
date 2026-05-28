import logging
from datetime import datetime
from flask import Blueprint, request, jsonify, session
from ..supabase_handler import get_supabase_handler
from ..stripe_handler import get_stripe_handler
from ..services.billing_logs import (
    save_webhook_log,
    mark_webhook_processed,
    mark_webhook_failed,
    create_billing_audit_log,
    upsert_subscription_from_stripe,
    upsert_payment_from_invoice
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
    
    # Save webhook log before processing
    log_result = save_webhook_log(event)
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
    session_data = event['data']['object']
    customer_id = session_data.get('customer')
    subscription_id = session_data.get('subscription')
    metadata = session_data.get('metadata', {})
    user_id = metadata.get('user_id')
    
    logger.info(
        'Checkout session completed',
        extra={
            'customer_id': customer_id,
            'subscription_id': subscription_id,
            'user_id': user_id
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
    subscription_data = event['data']['object']
    stripe_subscription_id = subscription_data.get('id')
    stripe_customer_id = subscription_data.get('customer')
    
    logger.info(
        'Subscription created',
        extra={
            'stripe_subscription_id': stripe_subscription_id,
            'stripe_customer_id': stripe_customer_id
        }
    )
    
    # Upsert subscription to billing table
    upsert_subscription_from_stripe(subscription_data)
    
    # Try to get user_id from customer metadata (if available)
    user_id = _get_user_id_from_customer(stripe_customer_id)
    
    # Create audit log
    create_billing_audit_log(
        user_id=user_id,
        company_id=None,
        stripe_event_id=event['id'],
        event='customer.subscription.created',
        description='Subscription created in Stripe',
        metadata={
            'stripe_subscription_id': stripe_subscription_id,
            'stripe_customer_id': stripe_customer_id
        }
    )


def _handle_subscription_updated(event):
    """Handle customer.subscription.updated event"""
    subscription_data = event['data']['object']
    stripe_subscription_id = subscription_data.get('id')
    stripe_customer_id = subscription_data.get('customer')
    status = subscription_data.get('status')
    
    logger.info(
        'Subscription updated',
        extra={
            'stripe_subscription_id': stripe_subscription_id,
            'status': status
        }
    )
    
    # Upsert subscription to billing table
    upsert_subscription_from_stripe(subscription_data)
    
    # Update Supabase profile with new status
    user_id = _get_user_id_from_customer(stripe_customer_id)
    if user_id:
        _update_profile_subscription(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            subscription_status=status
        )
    
    # Create audit log
    create_billing_audit_log(
        user_id=user_id,
        company_id=None,
        stripe_event_id=event['id'],
        event='customer.subscription.updated',
        description=f'Subscription updated to status: {status}',
        metadata={
            'stripe_subscription_id': stripe_subscription_id,
            'status': status
        }
    )


def _handle_subscription_deleted(event):
    """Handle customer.subscription.deleted event"""
    subscription_data = event['data']['object']
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
        supabase.update_user_subscription(
            user_id=user_id,
            plan='free',
            subscription_status='canceled',
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=None,
            next_billing_date=None
        )
        
        # Update auth handler
        from ..auth_handler import get_auth_handler
        auth_handler = get_auth_handler()
        auth_handler.update_user_plan(user_id, 'free')
    
    # Create audit log
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
    """Handle invoice.payment_succeeded event"""
    invoice_data = event['data']['object']
    stripe_invoice_id = invoice_data.get('id')
    stripe_customer_id = invoice_data.get('customer')
    stripe_subscription_id = invoice_data.get('subscription')
    amount_paid = invoice_data.get('amount_paid')
    currency = invoice_data.get('currency')
    
    logger.info(
        'Invoice payment succeeded',
        extra={
            'stripe_invoice_id': stripe_invoice_id,
            'stripe_subscription_id': stripe_subscription_id,
            'amount_paid': amount_paid,
            'currency': currency
        }
    )
    
    # Upsert payment to billing table
    upsert_payment_from_invoice(invoice_data)
    
    # Get user_id
    user_id = _get_user_id_from_customer(stripe_customer_id)
    
    # Update profile: activate subscription, update next_billing_date
    if user_id and stripe_subscription_id:
        # Get next billing date from subscription
        next_billing_date = _get_next_billing_date(stripe_subscription_id)
        
        supabase = get_supabase_handler()
        supabase.update_user_subscription(
            user_id=user_id,
            plan='basic',  # TODO: Determine plan from price/metadata
            subscription_status='active',
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            next_billing_date=next_billing_date
        )
        
        # Update auth handler
        from ..auth_handler import get_auth_handler
        auth_handler = get_auth_handler()
        auth_handler.update_user_plan(user_id, 'basic')
    
    # Create audit log
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
    invoice_data = event['data']['object']
    stripe_invoice_id = invoice_data.get('id')
    stripe_customer_id = invoice_data.get('customer')
    stripe_subscription_id = invoice_data.get('subscription')
    amount_due = invoice_data.get('amount_due')
    currency = invoice_data.get('currency')
    
    logger.warning(
        'Invoice payment failed',
        extra={
            'stripe_invoice_id': stripe_invoice_id,
            'stripe_subscription_id': stripe_subscription_id,
            'amount_due': amount_due
        }
    )
    
    # Upsert payment to billing table
    upsert_payment_from_invoice(invoice_data)
    
    # Get user_id and update profile
    user_id = _get_user_id_from_customer(stripe_customer_id)
    if user_id and stripe_subscription_id:
        # Update profile: mark as past_due
        supabase = get_supabase_handler()
        supabase.update_user_subscription(
            user_id=user_id,
            plan='basic',  # Keep current plan
            subscription_status='past_due',
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            next_billing_date=None
        )
    
    # Create audit log
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
    """Update profile subscription status"""
    try:
        supabase = get_supabase_handler()
        # Determine plan based on status
        plan = 'basic' if subscription_status in ['active', 'trialing'] else 'free'
        
        supabase.update_user_subscription(
            user_id=user_id,
            plan=plan,
            subscription_status=subscription_status,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            next_billing_date=None
        )
        
        # Update auth handler
        from ..auth_handler import get_auth_handler
        auth_handler = get_auth_handler()
        auth_handler.update_user_plan(user_id, plan)
        
    except Exception as e:
        logger.exception('Error updating profile subscription', extra={'user_id': user_id})


def _get_next_billing_date(stripe_subscription_id):
    """Get next billing date from Stripe subscription"""
    try:
        stripe_handler = get_stripe_handler()
        return stripe_handler.get_next_billing_date(stripe_subscription_id)
    except Exception as e:
        logger.exception('Error getting next billing date', extra={'stripe_subscription_id': stripe_subscription_id})
        return None