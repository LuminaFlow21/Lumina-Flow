"""
Lumina Flow - Billing Logs Service
Auxiliary functions for billing and payment logging
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any
from ..supabase_handler import get_supabase_handler


logger = logging.getLogger(__name__)


def save_webhook_log(event: Any) -> Dict[str, Any]:
    """
    Save a Stripe webhook event to stripe_webhook_logs table
    
    Args:
        event: Stripe event object (from stripe.Webhook.construct_event)
        
    Returns:
        Dictionary with success status, log_id, and error if any
    """
    try:
        supabase = get_supabase_handler()
        
        # Extract event data safely
        stripe_event_id = getattr(event, 'id', None) or event.get('id') if isinstance(event, dict) else None
        event_type = getattr(event, 'type', None) or event.get('type') if isinstance(event, dict) else None
        
        if not stripe_event_id:
            logger.error("Cannot save webhook log: missing stripe_event_id")
            return {
                'success': False,
                'error': 'Missing stripe_event_id in event object'
            }
        
        # Extract customer, subscription, and invoice IDs from event data
        data = getattr(event, 'data', None) or event.get('data', {}) if isinstance(event, dict) else {}
        data_object = getattr(data, 'object', None) or data.get('object', {}) if isinstance(data, dict) else {}
        
        stripe_customer_id = (
            getattr(data_object, 'customer', None) or 
            data_object.get('customer') if isinstance(data_object, dict) else None
        )
        stripe_subscription_id = (
            getattr(data_object, 'subscription', None) or 
            data_object.get('subscription') if isinstance(data_object, dict) else None
        )
        stripe_invoice_id = (
            getattr(data_object, 'invoice', None) or 
            data_object.get('invoice') if isinstance(data_object, dict) else None
        )
        
        # Convert event to dict for JSON storage
        if hasattr(event, 'to_dict'):
            raw_payload = event.to_dict()
        elif isinstance(event, dict):
            raw_payload = event
        else:
            raw_payload = {'id': stripe_event_id, 'type': event_type}
        
        log_data = {
            'stripe_event_id': stripe_event_id,
            'event_type': event_type,
            'stripe_customer_id': stripe_customer_id,
            'stripe_subscription_id': stripe_subscription_id,
            'stripe_invoice_id': stripe_invoice_id,
            'status': 'received',
            'raw_payload': raw_payload,
            'processed': False
        }
        
        response = supabase.admin_client.table('stripe_webhook_logs').insert(log_data).execute()
        
        if response.data:
            log_id = response.data[0].get('id')
            logger.info(
                "Webhook log saved",
                extra={
                    'stripe_event_id': stripe_event_id,
                    'event_type': event_type,
                    'log_id': log_id
                }
            )
            return {
                'success': True,
                'log_id': log_id,
                'stripe_event_id': stripe_event_id
            }
        else:
            logger.error("Failed to save webhook log: no data returned")
            return {
                'success': False,
                'error': 'No data returned from insert'
            }
            
    except Exception as e:
        logger.exception("Error saving webhook log", extra={'stripe_event_id': getattr(event, 'id', 'unknown')})
        return {
            'success': False,
            'error': str(e)
        }


def mark_webhook_processed(stripe_event_id: str) -> Dict[str, Any]:
    """
    Mark a webhook log as processed
    
    Args:
        stripe_event_id: Stripe event ID
        
    Returns:
        Dictionary with success status and error if any
    """
    try:
        supabase = get_supabase_handler()
        
        response = supabase.admin_client.table('stripe_webhook_logs') \
            .update({
                'processed': True,
                'status': 'processed',
                'processed_at': datetime.now().isoformat()
            }) \
            .eq('stripe_event_id', stripe_event_id) \
            .execute()
        
        if response.data:
            logger.info("Webhook marked as processed", extra={'stripe_event_id': stripe_event_id})
            return {
                'success': True,
                'updated_rows': len(response.data)
            }
        else:
            logger.warning("No webhook log found to mark as processed", extra={'stripe_event_id': stripe_event_id})
            return {
                'success': False,
                'error': 'No webhook log found with this stripe_event_id'
            }
            
    except Exception as e:
        logger.exception("Error marking webhook as processed", extra={'stripe_event_id': stripe_event_id})
        return {
            'success': False,
            'error': str(e)
        }


def mark_webhook_failed(stripe_event_id: str, error_message: str) -> Dict[str, Any]:
    """
    Mark a webhook log as failed with error message
    
    Args:
        stripe_event_id: Stripe event ID
        error_message: Error message describing the failure
        
    Returns:
        Dictionary with success status and error if any
    """
    try:
        supabase = get_supabase_handler()
        
        response = supabase.admin_client.table('stripe_webhook_logs') \
            .update({
                'processed': True,
                'status': 'failed',
                'processing_error': error_message,
                'processed_at': datetime.now().isoformat()
            }) \
            .eq('stripe_event_id', stripe_event_id) \
            .execute()
        
        if response.data:
            logger.warning(
                "Webhook marked as failed",
                extra={
                    'stripe_event_id': stripe_event_id,
                    'error': error_message
                }
            )
            return {
                'success': True,
                'updated_rows': len(response.data)
            }
        else:
            logger.warning(
                "No webhook log found to mark as failed",
                extra={'stripe_event_id': stripe_event_id}
            )
            return {
                'success': False,
                'error': 'No webhook log found with this stripe_event_id'
            }
            
    except Exception as e:
        logger.exception(
            "Error marking webhook as failed",
            extra={'stripe_event_id': stripe_event_id}
        )
        return {
            'success': False,
            'error': str(e)
        }


def create_billing_audit_log(
    user_id: Optional[str],
    company_id: Optional[str],
    stripe_event_id: Optional[str],
    event: str,
    description: str,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create a billing audit log entry
    
    Args:
        user_id: User ID (optional)
        company_id: Company ID (optional)
        stripe_event_id: Stripe event ID (optional)
        event: Event type/name
        description: Human-readable description
        metadata: Additional metadata as dictionary (optional)
        
    Returns:
        Dictionary with success status, log_id, and error if any
    """
    try:
        supabase = get_supabase_handler()
        
        log_data = {
            'user_id': user_id,
            'company_id': company_id,
            'stripe_event_id': stripe_event_id,
            'event': event,
            'description': description,
            'metadata': metadata or {}
        }
        
        response = supabase.admin_client.table('billing_audit_logs').insert(log_data).execute()
        
        if response.data:
            log_id = response.data[0].get('id')
            logger.info(
                "Billing audit log created",
                extra={
                    'log_id': log_id,
                    'event': event,
                    'user_id': user_id,
                    'company_id': company_id
                }
            )
            return {
                'success': True,
                'log_id': log_id
            }
        else:
            logger.error("Failed to create billing audit log: no data returned")
            return {
                'success': False,
                'error': 'No data returned from insert'
            }
            
    except Exception as e:
        logger.exception(
            "Error creating billing audit log",
            extra={'event': event, 'user_id': user_id}
        )
        return {
            'success': False,
            'error': str(e)
        }


def upsert_subscription_from_stripe(
    subscription_object: Any,
    extra_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Upsert subscription data from Stripe subscription object
    
    Args:
        subscription_object: Stripe subscription object
        extra_data: Additional data to merge (user_id, company_id, etc.)
        
    Returns:
        Dictionary with success status, subscription_id, and error if any
    """
    try:
        supabase = get_supabase_handler()
        
        # Extract subscription data safely
        stripe_subscription_id = (
            getattr(subscription_object, 'id', None) or 
            subscription_object.get('id') if isinstance(subscription_object, dict) else None
        )
        
        if not stripe_subscription_id:
            logger.error("Cannot upsert subscription: missing stripe_subscription_id")
            return {
                'success': False,
                'error': 'Missing stripe_subscription_id in subscription object'
            }
        
        # Extract essential fields only
        stripe_customer_id = (
            getattr(subscription_object, 'customer', None) or 
            subscription_object.get('customer') if isinstance(subscription_object, dict) else None
        )
        
        status = (
            getattr(subscription_object, 'status', None) or 
            subscription_object.get('status') if isinstance(subscription_object, dict) else None
        )
        
        # Extract plan name from items
        items = getattr(subscription_object, 'items', None) or subscription_object.get('items', {}) if isinstance(subscription_object, dict) else {}
        items_data = getattr(items, 'data', []) or items.get('data', []) if isinstance(items, dict) else []
        
        plan_name = None
        if items_data:
            first_item = items_data[0] if isinstance(items_data, list) else items_data
            price = getattr(first_item, 'price', None) or first_item.get('price') if isinstance(first_item, dict) else None
            if price:
                plan_name = (
                    getattr(price, 'nickname', None) or 
                    price.get('nickname') if isinstance(price, dict) else None
                )
        
        # Extract period dates
        current_period_start = getattr(subscription_object, 'current_period_start', None)
        if current_period_start and hasattr(current_period_start, 'timestamp'):
            current_period_start = datetime.fromtimestamp(current_period_start).isoformat()
        elif isinstance(current_period_object := subscription_object.get('current_period_start') if isinstance(subscription_object, dict) else None, (int, float)):
            current_period_start = datetime.fromtimestamp(current_period_object).isoformat()
        
        current_period_end = getattr(subscription_object, 'current_period_end', None)
        if current_period_end and hasattr(current_period_end, 'timestamp'):
            current_period_end = datetime.fromtimestamp(current_period_end).isoformat()
        elif isinstance(current_period_end_object := subscription_object.get('current_period_end') if isinstance(subscription_object, dict) else None, (int, float)):
            current_period_end = datetime.fromtimestamp(current_period_end_object).isoformat()
        
        cancel_at = getattr(subscription_object, 'cancel_at', None)
        if cancel_at and hasattr(cancel_at, 'timestamp'):
            cancel_at = datetime.fromtimestamp(cancel_at).isoformat()
        elif isinstance(cancel_at_object := subscription_object.get('cancel_at') if isinstance(subscription_object, dict) else None, (int, float)):
            cancel_at = datetime.fromtimestamp(cancel_at_object).isoformat()
        
        canceled_at = getattr(subscription_object, 'canceled_at', None)
        if canceled_at and hasattr(canceled_at, 'timestamp'):
            canceled_at = datetime.fromtimestamp(canceled_at).isoformat()
        elif isinstance(canceled_at_object := subscription_object.get('canceled_at') if isinstance(subscription_object, dict) else None, (int, float)):
            canceled_at = datetime.fromtimestamp(canceled_at_object).isoformat()
        
        # Build subscription data with essential fields only
        subscription_data = {
            'stripe_subscription_id': stripe_subscription_id,
            'stripe_customer_id': stripe_customer_id,
            'plan_name': plan_name,
            'status': status,
            'current_period_start': current_period_start,
            'current_period_end': current_period_end,
            'cancel_at': cancel_at,
            'canceled_at': canceled_at,
            'updated_at': datetime.now().isoformat()
        }
        
        # Merge extra data (user_id, company_id, etc.)
        if extra_data:
            subscription_data.update(extra_data)
        
        # Upsert using stripe_subscription_id as conflict target
        response = supabase.admin_client.table('subscriptions') \
            .upsert(subscription_data, on_conflict='stripe_subscription_id') \
            .execute()
        
        if response.data:
            subscription_id = response.data[0].get('id')
            logger.info(
                "Subscription upserted",
                extra={
                    'subscription_id': subscription_id,
                    'stripe_subscription_id': stripe_subscription_id,
                    'status': status
                }
            )
            return {
                'success': True,
                'subscription_id': subscription_id,
                'stripe_subscription_id': stripe_subscription_id
            }
        else:
            logger.error("Failed to upsert subscription: no data returned")
            return {
                'success': False,
                'error': 'No data returned from upsert'
            }
            
    except Exception as e:
        logger.exception(
            "Error upserting subscription",
            extra={'stripe_subscription_id': getattr(subscription_object, 'id', 'unknown')}
        )
        return {
            'success': False,
            'error': str(e)
        }


def upsert_payment_from_invoice(
    invoice_object: Any,
    extra_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Upsert payment data from Stripe invoice object
    
    Args:
        invoice_object: Stripe invoice object
        extra_data: Additional data to merge (user_id, company_id, subscription_id, etc.)
        
    Returns:
        Dictionary with success status, payment_id, and error if any
    """
    try:
        supabase = get_supabase_handler()
        
        # Extract invoice data safely
        stripe_invoice_id = (
            getattr(invoice_object, 'id', None) or 
            invoice_object.get('id') if isinstance(invoice_object, dict) else None
        )
        
        if not stripe_invoice_id:
            logger.error("Cannot upsert payment: missing stripe_invoice_id")
            return {
                'success': False,
                'error': 'Missing stripe_invoice_id in invoice object'
            }
        
        # Extract essential fields only
        stripe_customer_id = (
            getattr(invoice_object, 'customer', None) or 
            invoice_object.get('customer') if isinstance(invoice_object, dict) else None
        )
        
        stripe_subscription_id = (
            getattr(invoice_object, 'subscription', None) or 
            invoice_object.get('subscription') if isinstance(invoice_object, dict) else None
        )
        
        stripe_payment_intent_id = (
            getattr(invoice_object, 'payment_intent', None) or 
            invoice_object.get('payment_intent') if isinstance(invoice_object, dict) else None
        )
        
        amount = getattr(invoice_object, 'amount_paid', None) or invoice_object.get('amount_paid') if isinstance(invoice_object, dict) else None
        currency = getattr(invoice_object, 'currency', None) or invoice_object.get('currency') if isinstance(invoice_object, dict) else None
        status = getattr(invoice_object, 'status', None) or invoice_object.get('status') if isinstance(invoice_object, dict) else None
        
        # Extract failure reason if present
        failure_reason = None
        if status == 'uncollectible' or status == 'void':
            failure_reason = getattr(invoice_object, 'reason', None) or invoice_object.get('reason') if isinstance(invoice_object, dict) else None
        
        # Extract dates
        paid_at = None
        if status == 'paid':
            paid_at = getattr(invoice_object, 'status_transitions', None)
            if paid_at:
                paid_at = getattr(paid_at, 'paid_at', None)
            if paid_at and hasattr(paid_at, 'timestamp'):
                paid_at = datetime.fromtimestamp(paid_at).isoformat()
        
        failed_at = None
        if status in ['uncollectible', 'void']:
            failed_at = datetime.now().isoformat()
        
        # Build payment data with essential fields only
        payment_data = {
            'stripe_invoice_id': stripe_invoice_id,
            'stripe_customer_id': stripe_customer_id,
            'stripe_subscription_id': stripe_subscription_id,
            'stripe_payment_intent_id': str(stripe_payment_intent_id) if stripe_payment_intent_id else None,
            'amount': amount,
            'currency': currency,
            'status': status,
            'failure_reason': failure_reason,
            'paid_at': paid_at,
            'failed_at': failed_at
        }
        
        # Merge extra data (user_id, company_id, subscription_id, etc.)
        if extra_data:
            payment_data.update(extra_data)
        
        # Upsert using stripe_invoice_id as conflict target
        response = supabase.admin_client.table('payments') \
            .upsert(payment_data, on_conflict='stripe_invoice_id') \
            .execute()
        
        if response.data:
            payment_id = response.data[0].get('id')
            logger.info(
                "Payment upserted",
                extra={
                    'payment_id': payment_id,
                    'stripe_invoice_id': stripe_invoice_id,
                    'status': status,
                    'amount': amount
                }
            )
            return {
                'success': True,
                'payment_id': payment_id,
                'stripe_invoice_id': stripe_invoice_id
            }
        else:
            logger.error("Failed to upsert payment: no data returned")
            return {
                'success': False,
                'error': 'No data returned from upsert'
            }
            
    except Exception as e:
        logger.exception(
            "Error upserting payment",
            extra={'stripe_invoice_id': getattr(invoice_object, 'id', 'unknown')}
        )
        return {
            'success': False,
            'error': str(e)
        }


def get_customer_billing_details(company_id: str) -> Dict[str, Any]:
    """
    Get billing details for a company (subscriptions and payments)
    
    Args:
        company_id: Company ID
        
    Returns:
        Dictionary with success status, subscriptions, payments, and error if any
    """
    try:
        supabase = get_supabase_handler()
        
        # Get subscriptions for company
        subscriptions_response = supabase.admin_client.table('subscriptions') \
            .select('*') \
            .eq('company_id', company_id) \
            .order('created_at', desc=True) \
            .execute()
        
        subscriptions = subscriptions_response.data if subscriptions_response.data else []
        
        # Get payments for company
        payments_response = supabase.admin_client.table('payments') \
            .select('*') \
            .eq('company_id', company_id) \
            .order('created_at', desc=True) \
            .execute()
        
        payments = payments_response.data if payments_response.data else []
        
        logger.info(
            "Retrieved customer billing details",
            extra={
                'company_id': company_id,
                'subscriptions_count': len(subscriptions),
                'payments_count': len(payments)
            }
        )
        
        return {
            'success': True,
            'subscriptions': subscriptions,
            'payments': payments,
            'subscriptions_count': len(subscriptions),
            'payments_count': len(payments)
        }
        
    except Exception as e:
        logger.exception(
            "Error getting customer billing details",
            extra={'company_id': company_id}
        )
        return {
            'success': False,
            'error': str(e),
            'subscriptions': [],
            'payments': []
        }
