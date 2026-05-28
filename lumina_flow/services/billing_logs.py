"""
Lumina Flow - Billing Logs Service
Auxiliary functions for billing and payment logging
"""

import logging
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, Dict, Any
from ..supabase_handler import get_supabase_handler


logger = logging.getLogger(__name__)


def get_subscription_visual_state(billing_state: dict) -> dict:
    """
    Get visual state for subscription with professional badges.
    
    Returns consistent visual representation across the system.
    
    Args:
        billing_state: Billing state dict from get_billing_display_state()
    
    Returns:
        dict with:
        - label: Human-readable label
        - color_class: CSS class for color
        - icon: Emoji icon
        - description: Detailed explanation
        - state_key: Internal state key (active, canceling, past_due, canceled, free)
    """
    is_canceling = billing_state.get('is_canceling', False)
    subscription_status = billing_state.get('subscription_status', '').lower()
    plan = billing_state.get('plan', '').lower()
    
    # Priority: canceling > subscription_status > plan
    if is_canceling:
        return {
            'label': 'Cancelamento agendado',
            'color_class': 'warning',
            'icon': '🟡',
            'description': 'O plano foi cancelado mas mantém acesso até a data final do período.',
            'state_key': 'canceling'
        }
    elif subscription_status == 'active':
        return {
            'label': 'Ativo',
            'color_class': 'success',
            'icon': '🟢',
            'description': 'Plano ativo e em dia.',
            'state_key': 'active'
        }
    elif subscription_status == 'past_due':
        return {
            'label': 'Pagamento pendente',
            'color_class': 'danger',
            'icon': '🟠',
            'description': 'A última cobrança falhou. O plano continua ativo temporariamente.',
            'state_key': 'past_due'
        }
    elif subscription_status in ('canceled', 'incomplete_expired'):
        return {
            'label': 'Cancelado',
            'color_class': 'neutral',
            'icon': '🔴',
            'description': 'O plano foi cancelado e o acesso expirou.',
            'state_key': 'canceled'
        }
    elif plan == 'free':
        return {
            'label': 'Free',
            'color_class': 'neutral',
            'icon': '⚪',
            'description': 'Plano gratuito.',
            'state_key': 'free'
        }
    else:
        # Default to inactive
        return {
            'label': 'Inativo',
            'color_class': 'neutral',
            'icon': '⚪',
            'description': 'Sem assinatura ativa.',
            'state_key': 'inactive'
        }


def get_billing_timeline(user_id: str, limit: int = 50) -> list:
    """
    Get billing timeline events for a user.
    
    Combines events from:
    - billing_audit_logs
    - stripe_webhook_logs
    - payments
    - subscriptions
    
    Args:
        user_id: User ID
        limit: Maximum number of events to return
    
    Returns:
        List of timeline events sorted by date descending
    """
    try:
        supabase = get_supabase_handler()
        events = []
        
        # Get profile for stripe_customer_id
        profile_response = supabase.admin_client.table('profiles') \
            .select('stripe_customer_id') \
            .eq('user_id', user_id) \
            .execute()
        
        profile = profile_response.data[0] if profile_response.data else None
        stripe_customer_id = profile.get('stripe_customer_id') if profile else None
        
        # Get audit logs
        audit_logs_response = supabase.admin_client.table('billing_audit_logs') \
            .select('*') \
            .eq('user_id', user_id) \
            .order('created_at', desc=True) \
            .limit(limit) \
            .execute()
        
        for log in audit_logs_response.data or []:
            events.append({
                'type': 'audit',
                'event_type': log.get('event_type'),
                'description': log.get('description', log.get('event_type')),
                'created_at': log.get('created_at'),
                'icon': '📋',
                'color': 'blue'
            })
        
        # Get webhooks
        if stripe_customer_id:
            webhooks_response = supabase.admin_client.table('stripe_webhook_logs') \
                .select('*') \
                .eq('stripe_customer_id', stripe_customer_id) \
                .order('created_at', desc=True) \
                .limit(limit) \
                .execute()
            
            for webhook in webhooks_response.data or []:
                event_type = webhook.get('event_type', 'unknown')
                processing_error = webhook.get('processing_error')
                
                # Determine icon and color
                if 'payment_succeeded' in event_type:
                    icon = '✅'
                    color = 'green'
                elif 'payment_failed' in event_type:
                    icon = '❌'
                    color = 'red'
                elif 'cancel' in event_type.lower():
                    icon = '🟡'
                    color = 'yellow'
                elif processing_error:
                    icon = '⚠️'
                    color = 'orange'
                else:
                    icon = '🔔'
                    color = 'blue'
                
                events.append({
                    'type': 'webhook',
                    'event_type': event_type,
                    'description': f'Webhook: {event_type}',
                    'created_at': webhook.get('created_at'),
                    'processing_error': processing_error,
                    'icon': icon,
                    'color': color
                })
        
        # Get payments
        payments_response = supabase.admin_client.table('payments') \
            .select('*') \
            .eq('user_id', user_id) \
            .order('created_at', desc=True) \
            .limit(limit) \
            .execute()
        
        for payment in payments_response.data or []:
            status = payment.get('status')
            if status == 'paid':
                icon = '💰'
                color = 'green'
                description = f'Pagamento aprovado: R$ {payment.get("amount", 0) / 100:.2f}'
            elif status == 'failed':
                icon = '❌'
                color = 'red'
                description = f'Pagamento falhou: R$ {payment.get("amount", 0) / 100:.2f}'
            else:
                icon = '💳'
                color = 'blue'
                description = f'Pagamento: {status}'
            
            events.append({
                'type': 'payment',
                'event_type': f'payment_{status}',
                'description': description,
                'created_at': payment.get('created_at'),
                'icon': icon,
                'color': color
            })
        
        # Get subscription events
        subscription_response = supabase.admin_client.table('subscriptions') \
            .select('*') \
            .eq('user_id', user_id) \
            .order('created_at', desc=True) \
            .limit(limit) \
            .execute()
        
        for subscription in subscription_response.data or []:
            status = subscription.get('status')
            cancel_at = subscription.get('cancel_at')
            
            if cancel_at:
                icon = '🟡'
                color = 'yellow'
                description = f'Cancelamento agendado para {cancel_at[:10]}'
            elif status == 'active':
                icon = '✅'
                color = 'green'
                description = 'Assinatura ativada'
            else:
                icon = '📝'
                color = 'blue'
                description = f'Assinatura: {status}'
            
            events.append({
                'type': 'subscription',
                'event_type': f'subscription_{status}',
                'description': description,
                'created_at': subscription.get('created_at'),
                'icon': icon,
                'color': color
            })
        
        # Sort by date descending
        events.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        # Limit results
        return events[:limit]
    
    except Exception as e:
        logger.exception('[BILLING] Error getting billing timeline', extra={'user_id': user_id})
        return []


def get_last_stripe_event(user_id: str) -> dict:
    """
    Get the last Stripe webhook event for a user.
    
    Args:
        user_id: User ID
    
    Returns:
        Dict with event data or None if not found
    """
    try:
        supabase = get_supabase_handler()
        
        # Get profile for stripe_customer_id
        profile_response = supabase.admin_client.table('profiles') \
            .select('stripe_customer_id') \
            .eq('user_id', user_id) \
            .execute()
        
        profile = profile_response.data[0] if profile_response.data else None
        stripe_customer_id = profile.get('stripe_customer_id') if profile else None
        
        if not stripe_customer_id:
            return None
        
        # Get last webhook
        webhook_response = supabase.admin_client.table('stripe_webhook_logs') \
            .select('*') \
            .eq('stripe_customer_id', stripe_customer_id) \
            .order('created_at', desc=True) \
            .limit(1) \
            .execute()
        
        if webhook_response.data and len(webhook_response.data) > 0:
            webhook = webhook_response.data[0]
            return {
                'event_type': webhook.get('event_type'),
                'created_at': webhook.get('created_at'),
                'processed': webhook.get('processed'),
                'processing_error': webhook.get('processing_error'),
                'stripe_event_id': webhook.get('stripe_event_id')
            }
        
        return None
    
    except Exception as e:
        logger.exception('[BILLING] Error getting last stripe event', extra={'user_id': user_id})
        return None


def get_webhooks_with_error_count() -> int:
    """
    Get count of webhooks with processing errors.
    
    Returns:
        Number of webhooks with processing_error not null
    """
    try:
        supabase = get_supabase_handler()
        
        # Count webhooks with processing_error
        response = supabase.admin_client.table('stripe_webhook_logs') \
            .select('*', count='exact') \
            .not_.is_('processing_error', 'null') \
            .execute()
        
        return response.count if response.count else 0
    
    except Exception as e:
        logger.exception('[BILLING] Error getting webhooks with error count')
        return 0


def _serialize_for_json(obj: Any) -> Any:
    """
    Convert object to JSON-serializable format.
    
    Handles:
    - Decimal -> float
    - datetime/date -> ISO string
    - StripeObject -> dict
    - Recursive conversion for nested structures
    """
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _serialize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize_for_json(item) for item in obj]
    if hasattr(obj, 'to_dict'):
        try:
            return _serialize_for_json(obj.to_dict())
        except Exception:
            pass
    try:
        return _serialize_for_json(dict(obj))
    except Exception:
        return str(obj)


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
        
        # Convert event to dict for JSON storage (handle Decimal, datetime, etc.)
        if hasattr(event, 'to_dict'):
            raw_payload = _serialize_for_json(event.to_dict())
        elif isinstance(event, dict):
            raw_payload = _serialize_for_json(event)
        else:
            raw_payload = _serialize_for_json({'id': stripe_event_id, 'type': event_type})
        
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


def is_webhook_processed(stripe_event_id: str) -> bool:
    """
    Check if a webhook event has already been processed
    
    Args:
        stripe_event_id: Stripe event ID
        
    Returns:
        True if already processed, False otherwise
    """
    try:
        supabase = get_supabase_handler()
        
        response = supabase.admin_client.table('stripe_webhook_logs') \
            .select('processed') \
            .eq('stripe_event_id', stripe_event_id) \
            .execute()
        
        if response.data and len(response.data) > 0:
            return response.data[0].get('processed', False)
        return False
    except Exception as e:
        logger.exception("Error checking webhook processed status", extra={'stripe_event_id': stripe_event_id})
        return False


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
            'metadata': _serialize_for_json(metadata or {})
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
        
        # Build payment data with essential fields only (stripe_customer_id and stripe_subscription_id not in payments table)
        payment_data = {
            'stripe_invoice_id': stripe_invoice_id,
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


def get_user_id_from_checkout_webhook(stripe_invoice_id: str = None, stripe_customer_id: str = None) -> Dict[str, Any]:
    """
    Fallback: Get user_id from checkout.session.completed webhook log
    
    Args:
        stripe_invoice_id: Stripe invoice ID to match
        stripe_customer_id: Stripe customer ID to match
        
    Returns:
        Dictionary with success status, user_id, customer_id, subscription_id, and error if any
    """
    logger.info(
        '[DEBUG] get_user_id_from_checkout_webhook called',
        extra={
            'stripe_invoice_id': stripe_invoice_id,
            'stripe_customer_id': stripe_customer_id
        }
    )
    
    try:
        supabase = get_supabase_handler()
        
        # Build query
        query = supabase.admin_client.table('stripe_webhook_logs') \
            .select('raw_payload') \
            .eq('event_type', 'checkout.session.completed')
        
        if stripe_invoice_id:
            query = query.eq('stripe_invoice_id', stripe_invoice_id)
            logger.info('[DEBUG] Querying by stripe_invoice_id', extra={'stripe_invoice_id': stripe_invoice_id})
        elif stripe_customer_id:
            query = query.eq('stripe_customer_id', stripe_customer_id)
            logger.info('[DEBUG] Querying by stripe_customer_id', extra={'stripe_customer_id': stripe_customer_id})
        else:
            logger.warning('[DEBUG] No search criteria provided')
            return {
                'success': False,
                'error': 'Either stripe_invoice_id or stripe_customer_id is required'
            }
        
        response = query.order('created_at', desc=True).limit(1).execute()
        
        logger.info(
            '[DEBUG] Query result from stripe_webhook_logs',
            extra={
                'results_count': len(response.data) if response.data else 0,
                'has_data': bool(response.data)
            }
        )
        
        if not response.data or len(response.data) == 0:
            logger.warning(
                '[DEBUG] No checkout.session.completed found in stripe_webhook_logs',
                extra={
                    'stripe_invoice_id': stripe_invoice_id,
                    'stripe_customer_id': stripe_customer_id
                }
            )
            return {
                'success': False,
                'error': 'No checkout.session.completed found'
            }
        
        # Extract user_id from raw_payload
        raw_payload = response.data[0].get('raw_payload', {})
        if not raw_payload:
            logger.warning('[DEBUG] No raw_payload in webhook log')
            return {
                'success': False,
                'error': 'No raw_payload in webhook log'
            }
        
        # Navigate to nested structure
        data_object = raw_payload.get('data', {}).get('object', {})
        metadata = data_object.get('metadata', {})
        user_id = metadata.get('user_id')
        customer_id = data_object.get('customer')
        subscription_id = data_object.get('subscription')
        
        logger.info(
            '[DEBUG] Extracted data from raw_payload',
            extra={
                'user_id': user_id,
                'customer_id': customer_id,
                'subscription_id': subscription_id,
                'metadata_keys': list(metadata.keys()) if metadata else []
            }
        )
        
        if not user_id:
            logger.warning('[DEBUG] No user_id in checkout metadata', extra={'metadata': metadata})
            return {
                'success': False,
                'error': 'No user_id in checkout metadata'
            }
        
        logger.info(
            '[SUCCESS] Found user_id from checkout webhook',
            extra={
                'user_id': user_id,
                'customer_id': customer_id,
                'subscription_id': subscription_id
            }
        )
        
        return {
            'success': True,
            'user_id': user_id,
            'customer_id': customer_id,
            'subscription_id': subscription_id
        }
        
    except Exception as e:
        logger.exception(
            'Error getting user_id from checkout webhook',
            extra={'stripe_invoice_id': stripe_invoice_id, 'stripe_customer_id': stripe_customer_id}
        )
        return {
            'success': False,
            'error': str(e)
        }


def get_admin_billing_summary(filters: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Get billing summary for admin dashboard
    
    Args:
        filters: Optional filters to apply (status, plan, etc.)
    
    Returns:
        Dictionary with:
        - active_subscriptions: count
        - past_due_subscriptions: count
        - canceled_subscriptions: count
        - failed_payments: count (recent)
        - estimated_monthly_revenue: total based on basic plans
        - scheduled_cancellations: count
    """
    try:
        supabase = get_supabase_handler()
        filters = filters or {}
        
        # Build query with filters
        query = supabase.admin_client.table('profiles').select('*')
        
        if filters.get('status'):
            query = query.eq('subscription_status', filters['status'])
        
        if filters.get('plan'):
            query = query.eq('plan', filters['plan'])
        
        profiles_response = query.execute()
        
        # Count subscriptions by status
        active_count = 0
        past_due_count = 0
        canceled_count = 0
        scheduled_cancellations = 0
        estimated_monthly_revenue = 0
        
        if profiles_response.data:
            for profile in profiles_response.data:
                status = profile.get('subscription_status')
                plan = profile.get('plan')
                cancel_at = profile.get('cancel_at')
                
                if status == 'active':
                    active_count += 1
                    if cancel_at:
                        scheduled_cancellations += 1
                elif status == 'past_due':
                    past_due_count += 1
                elif status == 'canceled':
                    canceled_count += 1
                
                # Estimate revenue (basic plans)
                if plan == 'basic' and status in ['active', 'past_due']:
                    estimated_monthly_revenue += 69  # Basic price in BRL
        
        # Count failed payments (recent)
        failed_payments_query = supabase.admin_client.table('payments') \
            .select('id') \
            .eq('status', 'failed') \
            .gte('created_at', datetime.now() - timedelta(days=30))
        
        if filters.get('has_failed_payment'):
            # Get customer IDs with failed payments
            failed_customers = supabase.admin_client.table('payments') \
                .select('user_id') \
                .eq('status', 'failed') \
                .gte('created_at', datetime.now() - timedelta(days=30)) \
                .execute()
            
            if failed_customers.data:
                customer_ids = list(set(p.get('user_id') for p in failed_customers.data if p.get('user_id')))
                if customer_ids:
                    profiles_response = supabase.admin_client.table('profiles') \
                        .select('*') \
                        .in_('user_id', customer_ids) \
                        .execute()
        
        failed_payments_response = failed_payments_query.execute()
        failed_payments_count = len(failed_payments_response.data) if failed_payments_response.data else 0
        
        # Estimate monthly revenue (basic plan = R$ 29.90 or similar)
        basic_plan_count = 0
        if profiles_response.data:
            basic_plan_count = sum(1 for p in profiles_response.data if p.get('plan') == 'basic')
        
        estimated_monthly_revenue = basic_plan_count * 29.90  # Assuming R$ 29.90 per month
        
        logger.info(
            '[ADMIN] Billing summary fetched',
            extra={
                'active_subscriptions': active_count,
                'past_due_subscriptions': past_due_count,
                'canceled_subscriptions': canceled_count,
                'failed_payments': failed_payments_count,
                'estimated_monthly_revenue': estimated_monthly_revenue,
                'scheduled_cancellations': scheduled_cancellations
            }
        )
        
        return {
            'success': True,
            'data': {
                'active_subscriptions': active_count,
                'past_due_subscriptions': past_due_count,
                'canceled_subscriptions': canceled_count,
                'failed_payments': failed_payments_count,
                'estimated_monthly_revenue': estimated_monthly_revenue,
                'scheduled_cancellations': scheduled_cancellations
            }
        }
    except Exception as e:
        logger.exception('[ADMIN] Error fetching billing summary')
        return {
            'success': False,
            'error': str(e)
        }


def get_admin_customer_billing_details(user_id: str) -> Dict[str, Any]:
    """
    Get detailed billing information for a specific customer
    
    Args:
        user_id: User ID
        
    Returns:
        Dictionary with:
        - profile: user profile data
        - payments: list of payments
        - webhooks: list of webhooks
        - audit_logs: list of audit logs
        - subscription: subscription details
    """
    try:
        supabase = get_supabase_handler()
        
        # Get profile data
        profile_response = supabase.admin_client.table('profiles') \
            .select('*') \
            .eq('user_id', user_id) \
            .execute()
        
        profile = profile_response.data[0] if profile_response.data else None
        
        # Get unified billing display state
        billing_state = get_billing_display_state(user_id, supabase)
        
        # Get user data
        user_response = supabase.admin_client.table('users') \
            .select('id', 'email', 'plan', 'created_at') \
            .eq('id', user_id) \
            .execute()
        
        user = user_response.data[0] if user_response.data else None
        
        # Get payments
        payments_response = supabase.admin_client.table('payments') \
            .select('*') \
            .eq('user_id', user_id) \
            .order('created_at', desc=True) \
            .limit(50) \
            .execute()
        
        payments = payments_response.data if payments_response.data else []
        
        # Calculate total paid amount and failed payment count
        total_paid = sum(p.get('amount', 0) for p in payments if p.get('status') == 'paid')
        failed_payment_count = sum(1 for p in payments if p.get('status') == 'failed')
        
        # Get webhooks
        webhooks_response = supabase.admin_client.table('stripe_webhook_logs') \
            .select('*') \
            .eq('stripe_customer_id', profile.get('stripe_customer_id') if profile else None) \
            .order('created_at', desc=True) \
            .limit(50) \
            .execute()
        
        webhooks = webhooks_response.data if webhooks_response.data else []
        
        # Get audit logs
        audit_logs_response = supabase.admin_client.table('billing_audit_logs') \
            .select('*') \
            .eq('user_id', user_id) \
            .order('created_at', desc=True) \
            .limit(50) \
            .execute()
        
        audit_logs = audit_logs_response.data if audit_logs_response.data else []
        
        # Get subscription details
        subscription = None
        cancel_at = None
        canceled_at = None
        is_canceling = False
        
        if profile and profile.get('stripe_subscription_id'):
            subscription_response = supabase.admin_client.table('subscriptions') \
                .select('*') \
                .eq('stripe_subscription_id', profile.get('stripe_subscription_id')) \
                .execute()
            
            subscription = subscription_response.data[0] if subscription_response.data else None
            
            if subscription:
                cancel_at = subscription.get('cancel_at')
                canceled_at = subscription.get('canceled_at')
                
                # Calculate is_canceling: cancel_at exists and is in the future
                if cancel_at:
                    try:
                        cancel_date = datetime.fromisoformat(cancel_at.replace('Z', '+00:00'))
                        is_canceling = cancel_date > datetime.now()
                    except Exception:
                        is_canceling = False
        
        # Add canceling info to profile data
        if profile:
            profile['is_canceling'] = is_canceling
            profile['cancel_at'] = cancel_at or profile.get('cancel_at')
            profile['canceled_at'] = canceled_at
        
        logger.info(
            '[ADMIN] Customer billing details fetched',
            extra={'user_id': user_id}
        )
        
        return {
            'success': True,
            'data': {
                'profile': profile,
                'user': user,
                'payments': payments,
                'total_paid': total_paid,
                'failed_payment_count': failed_payment_count,
                'webhooks': webhooks,
                'audit_logs': audit_logs,
                'subscription': subscription,
                'billing_state': billing_state
            }
        }
    except Exception as e:
        logger.exception('[ADMIN] Error fetching customer billing details', extra={'user_id': user_id})
        return {
            'success': False,
            'error': str(e)
        }


def get_billing_display_state(user_id: str, supabase: 'SupabaseHandler' = None) -> dict:
    """
    Get unified billing display state for a user.
    
    This function consolidates billing state from profiles and subscriptions tables
    to provide a consistent display state across the entire system.
    
    Returns:
        dict with keys:
            - plan: current plan (free, basic, etc)
            - subscription_status: raw subscription status from profile
            - subscription_status_raw: raw status from subscriptions table
            - stripe_subscription_id: Stripe subscription ID
            - stripe_customer_id: Stripe customer ID
            - next_billing_date: next billing date from profile
            - cancel_at: cancel_at from subscriptions table
            - canceled_at: canceled_at from subscriptions table
            - is_active: bool, subscription is active and not canceling
            - is_canceling: bool, subscription is scheduled to cancel
            - is_past_due: bool, subscription is past_due
            - is_canceled: bool, subscription is canceled
            - is_free: bool, user is on free plan
            - access_until: date until user has access (cancel_at or next_billing_date)
            - billing_message: human-readable message about billing state
            - primary_action: suggested action for user
            - status_label: display label for status
            - status_badge_class: CSS class for status badge
    """
    from datetime import datetime
    
    if supabase is None:
        supabase = get_supabase_handler()
    
    # Get profile
    profile_response = supabase.admin_client.table('profiles') \
        .select('*') \
        .eq('user_id', user_id) \
        .execute()
    
    profile = profile_response.data[0] if profile_response.data else {}
    
    # Get subscription data
    subscription = None
    cancel_at = None
    canceled_at = None
    subscription_status_raw = None
    subscription_exists_in_stripe = False
    
    stripe_subscription_id = profile.get('stripe_subscription_id')
    if stripe_subscription_id:
        # First check if subscription exists in Stripe
        try:
            from ..stripe_handler import get_stripe_handler
            stripe_handler = get_stripe_handler()
            stripe_subscription = stripe_handler.stripe.Subscription.retrieve(stripe_subscription_id)
            subscription_exists_in_stripe = stripe_subscription is not None
        except Exception as e:
            # Subscription doesn't exist in Stripe (was deleted)
            logger.warning(f'Subscription {stripe_subscription_id} not found in Stripe', extra={'error': str(e)})
            subscription_exists_in_stripe = False
        
        # Get subscription data from local database
        subscription_response = supabase.admin_client.table('subscriptions') \
            .select('*') \
            .eq('stripe_subscription_id', stripe_subscription_id) \
            .execute()
        
        subscription = subscription_response.data[0] if subscription_response.data else None
    
    if subscription:
        cancel_at = subscription.get('cancel_at')
        canceled_at = subscription.get('canceled_at')
        subscription_status_raw = subscription.get('status')
    
    # Calculate state
    plan = profile.get('plan', 'free')
    subscription_status = profile.get('subscription_status', 'inactive')
    next_billing_date = profile.get('next_billing_date')
    
    # Only override to free if subscription doesn't exist in Stripe AND status is not active
    # This handles cases where users manually deleted Stripe resources but still have active subscriptions
    if stripe_subscription_id and not subscription_exists_in_stripe:
        if subscription_status != 'active':
            plan = 'free'
            subscription_status = 'inactive'
    
    # Calculate is_canceling: cancel_at exists and is in the future
    is_canceling = False
    if cancel_at:
        try:
            # Remove timezone info from cancel_at for comparison
            # Format: 2026-06-28T03:02:29+00:00 -> 2026-06-28T03:02:29
            if '+' in cancel_at:
                cancel_date_str = cancel_at.split('+')[0]
            else:
                cancel_date_str = cancel_at.replace('Z', '')
            cancel_date = datetime.fromisoformat(cancel_date_str)
            now = datetime.now()
            is_canceling = cancel_date > now
        except Exception as e:
            logger.warning(f'Error calculating is_canceling: {type(e).__name__}: {e}')
            is_canceling = False
    
    # Calculate other states
    is_active = (subscription_status == 'active' and not is_canceling and plan == 'basic')
    is_past_due = (subscription_status == 'past_due')
    is_canceled = (subscription_status == 'canceled')
    is_free = (plan == 'free')
    
    # Calculate access_until
    access_until = None
    if is_canceling and cancel_at:
        access_until = cancel_at
    elif next_billing_date:
        access_until = next_billing_date
    
    # Determine display state
    if is_canceling:
        status_label = 'Cancelamento agendado'
        status_badge_class = 'canceling'
        billing_message = f'Seu plano foi cancelado e ficará ativo até {format_date_br(access_until) if access_until else "o fim do período atual"}.'
        primary_action = 'reactivate'
    elif is_past_due:
        status_label = 'Pagamento pendente'
        status_badge_class = 'past_due'
        billing_message = 'Não conseguimos processar seu pagamento. Atualize sua forma de pagamento.'
        primary_action = 'update_payment'
    elif is_canceled:
        status_label = 'Cancelado'
        status_badge_class = 'canceled'
        billing_message = 'Seu plano está cancelado.'
        primary_action = 'resubscribe'
    elif is_free:
        status_label = 'Free'
        status_badge_class = 'free'
        billing_message = 'Você está no plano gratuito.'
        primary_action = 'upgrade'
    elif is_active:
        status_label = 'Ativo'
        status_badge_class = 'active'
        billing_message = 'Seu plano está ativo.'
        primary_action = 'cancel'
    else:
        status_label = 'Inativo'
        status_badge_class = 'inactive'
        billing_message = 'Sua assinatura está inativa.'
        primary_action = 'upgrade'
    
    return {
        'plan': plan,
        'subscription_status': subscription_status,
        'subscription_status_raw': subscription_status_raw,
        'stripe_subscription_id': stripe_subscription_id,
        'stripe_customer_id': profile.get('stripe_customer_id'),
        'next_billing_date': next_billing_date,
        'cancel_at': cancel_at,
        'canceled_at': canceled_at,
        'is_active': is_active,
        'is_canceling': is_canceling,
        'is_past_due': is_past_due,
        'is_canceled': is_canceled,
        'is_free': is_free,
        'access_until': access_until,
        'billing_message': billing_message,
        'primary_action': primary_action,
        'status_label': status_label,
        'status_badge_class': status_badge_class
    }


def search_admin_billing_customers(q: str = None, filters: Dict[str, Any] = None, limit: int = 50) -> Dict[str, Any]:
    """
    Search customers by query string and filters
    
    Args:
        q: Search query (name, email, user_id, stripe_customer_id, stripe_subscription_id)
        filters: Optional filters (status, plan, has_failed_payment, canceling)
        limit: Maximum number of results
    
    Returns:
        Dictionary with success status and list of customers
    """
    try:
        supabase = get_supabase_handler()
        filters = filters or {}
        
        # Build query with basic filters that can be applied at DB level
        query = supabase.admin_client.table('profiles').select('*')
        
        # Only apply DB-level filters for plan (since it's in profiles)
        # Don't apply status or canceling filters at DB level since they depend on billing_state
        if filters.get('plan'):
            query = query.eq('plan', filters['plan'])
        
        # Execute query with smaller limit to improve performance
        profiles_response = query.order('created_at', desc=True).limit(limit * 2).execute()
        profiles = profiles_response.data if profiles_response.data else []
        
        # Simple cache for billing states to avoid duplicate calculations
        billing_state_cache = {}
        
        # Get billing state and user data for each profile
        customers = []
        for profile in profiles:
            user_id = profile.get('user_id')
            
            # Check cache first
            if user_id in billing_state_cache:
                billing_state = billing_state_cache[user_id]
            else:
                # Get billing display state for this user
                billing_state = get_billing_display_state(user_id, supabase)
                billing_state_cache[user_id] = billing_state
            
            # Get user data
            user_response = supabase.admin_client.table('users') \
                .select('*') \
                .eq('id', user_id) \
                .execute()
            
            user = user_response.data[0] if user_response.data else None
            
            # Get last payment only if needed for has_failed_payment filter
            last_payment = None
            if filters.get('has_failed_payment'):
                payment_response = supabase.admin_client.table('payments') \
                    .select('*') \
                    .eq('user_id', user_id) \
                    .order('created_at', desc=True) \
                    .limit(1) \
                    .execute()
                last_payment = payment_response.data[0] if payment_response.data else None
            
            customers.append({
                'profile': profile,
                'user': user,
                'last_payment': last_payment,
                'billing_state': billing_state
            })
        
        # Apply filters based on billing_state
        if filters:
            filtered_customers = []
            for customer in customers:
                billing_state = customer.get('billing_state', {})
                
                # Filter by status
                if filters.get('status'):
                    if billing_state.get('subscription_status') != filters['status']:
                        continue
                
                # Filter by canceling
                if filters.get('canceling'):
                    if not billing_state.get('is_canceling'):
                        continue
                
                # Filter by has_failed_payment
                if filters.get('has_failed_payment'):
                    last_payment = customer.get('last_payment')
                    if not last_payment or last_payment.get('status') != 'failed':
                        continue
                
                filtered_customers.append(customer)
            
            customers = filtered_customers
        
        # Filter by search query if provided
        if q:
            q_lower = q.lower()
            filtered_customers = []
            for customer in customers:
                profile = customer.get('profile', {})
                user = customer.get('user', {})
                billing_state = customer.get('billing_state', {})
                
                # Search in multiple fields
                searchable_text = ' '.join(filter(None, [
                    str(profile.get('full_name', '')),
                    str(profile.get('user_id', '')),
                    str(user.get('email', '')),
                    str(billing_state.get('stripe_customer_id', '')),
                    str(billing_state.get('stripe_subscription_id', ''))
                ])).lower()
                
                if q_lower in searchable_text:
                    filtered_customers.append(customer)
            
            customers = filtered_customers[:limit]
        else:
            customers = customers[:limit]
        
        logger.info(
            '[ADMIN] Customer search completed',
            extra={'q': q, 'filters': filters, 'count': len(customers)}
        )
        
        return {
            'success': True,
            'data': customers
        }
    except Exception as e:
        logger.exception('[ADMIN] Error searching customers')
        return {
            'success': False,
            'error': str(e)
        }


def format_money(amount: float, currency: str = 'BRL') -> str:
    """
    Format amount as money string
    
    Args:
        amount: Amount to format
        currency: Currency code (BRL, GBP, USD)
    
    Returns:
        Formatted money string
    """
    if currency == 'BRL':
        return f'R$ {amount:.2f}'.replace('.', ',')
    elif currency == 'GBP':
        return f'£{amount:.2f}'
    elif currency == 'USD':
        return f'${amount:.2f}'
    else:
        return f'{amount:.2f} {currency}'


def format_datetime_br(dt: str) -> str:
    """
    Format datetime to Brazilian format (DD/MM/YYYY HH:MM)
    
    Args:
        dt: Datetime string (ISO format)
    
    Returns:
        Formatted datetime string
    """
    if not dt:
        return '-'
    
    try:
        dt_obj = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        return dt_obj.strftime('%d/%m/%Y %H:%M')
    except Exception:
        return dt


def format_date_br(dt: str) -> str:
    """
    Format date to Brazilian format (DD/MM/YYYY)
    
    Args:
        dt: Date string (ISO format)
    
    Returns:
        Formatted date string
    """
    if not dt:
        return '-'
    
    try:
        dt_obj = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        return dt_obj.strftime('%d/%m/%Y')
    except Exception:
        return dt


def get_status_label(status: str) -> str:
    """
    Get human-readable status label
    
    Args:
        status: Status code (active, past_due, canceled, inactive)
    
    Returns:
        Human-readable status label
    """
    status_labels = {
        'active': 'Ativo',
        'past_due': 'Pagamento pendente',
        'canceled': 'Cancelado',
        'inactive': 'Inativo',
        'trial': 'Teste'
    }
    return status_labels.get(status, status)


def get_status_badge_class(status: str) -> str:
    """
    Get CSS badge class for status
    
    Args:
        status: Status code
    
    Returns:
        CSS class name
    """
    badge_classes = {
        'active': 'admin-badge--active',
        'past_due': 'admin-badge--past-due',
        'canceled': 'admin-badge--canceled',
        'inactive': 'admin-badge--inactive',
        'trial': 'admin-badge--active'
    }
    return badge_classes.get(status, 'admin-badge--inactive')


def get_plan_badge_class(plan: str) -> str:
    """
    Get CSS badge class for plan
    
    Args:
        plan: Plan code
    
    Returns:
        CSS class name
    """
    badge_classes = {
        'basic': 'admin-badge--basic',
        'pro': 'admin-badge--basic',
        'enterprise': 'admin-badge--basic',
        'free': 'admin-badge--free'
    }
    return badge_classes.get(plan, 'admin-badge--free')
