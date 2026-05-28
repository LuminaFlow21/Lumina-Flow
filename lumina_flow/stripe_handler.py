"""
Lumina Flow - Stripe Handler
Isolated logic for Stripe payment processing
"""

import os
import logging
import stripe
from datetime import datetime, timedelta
from .config import Config


logger = logging.getLogger(__name__)


class StripeHandler:
    """Handler for Stripe operations"""
    
    def __init__(self):
        """Initialize Stripe client"""
        stripe.api_key = Config.STRIPE_SECRET_KEY
        
        if not Config.STRIPE_SECRET_KEY:
            raise ValueError("STRIPE_SECRET_KEY must be set in environment variables")
        
        # Price IDs
        self.price_ids = {
            'br_monthly': Config.STRIPE_PRICE_ID_BR_MONTHLY,
            'br_yearly': Config.STRIPE_PRICE_ID_BR_YEARLY,
            'uk_monthly': Config.STRIPE_PRICE_ID_UK_MONTHLY,
            'uk_yearly': Config.STRIPE_PRICE_ID_UK_YEARLY
        }
    
    def get_price_id(self, currency: str, billing: str = 'monthly') -> str:
        """
        Get Stripe price ID based on currency and billing period
        
        Args:
            currency: Currency code (brl or gbp)
            billing: Billing period (monthly or yearly)
            
        Returns:
            Stripe price ID
        """
        key = f"{currency.replace('gbp', 'uk')}_{billing}"
        price_id = self.price_ids.get(key)

        if not price_id:
            logger.error("Missing Stripe price ID", extra={'currency': currency, 'billing': billing, 'key': key})
            raise ValueError(f"No price ID found for {currency} {billing}")

        return price_id
    
    def create_checkout_session(self, price_id: str, user_id: str, user_email: str, currency: str = 'brl', customer_id: str = None) -> dict:
        """
        Create a Stripe checkout session
        
        Args:
            price_id: Stripe price ID
            user_id: User ID
            user_email: User email
            currency: Currency code (brl or gbp)
            customer_id: Existing Stripe customer ID (optional)
            
        Returns:
            Dictionary with checkout session URL or error
        """
        try:
            # Determine locale based on currency for Stripe Checkout UI
            locale_code = 'pt-BR' if (currency or '').lower() == 'brl' else 'en-GB'

            session_params = {
                'payment_method_types': ['card'],
                'line_items': [{
                    'price': price_id,
                    'quantity': 1,
                }],
                'mode': 'subscription',
                'success_url': Config.SUCCESS_URL,
                'cancel_url': Config.CANCEL_URL,
                'locale': locale_code,
                'customer_email': user_email if not customer_id else None,
                'metadata': {
                    'user_id': user_id,
                    'user_email': user_email,
                    'price_id': price_id,
                    'currency': currency
                }
            }
            
            # Add customer_id if exists
            if customer_id:
                session_params['customer'] = customer_id
                session_params.pop('customer_email', None)
            
            logger.info(
                "Creating Stripe checkout session",
                extra={'user_id': user_id, 'price_id': price_id, 'currency': currency, 'customer_id': customer_id}
            )

            session = stripe.checkout.Session.create(**session_params)

            logger.info(
                "Stripe checkout session created",
                extra={'user_id': user_id, 'session_id': session.id, 'customer_id': session.customer}
            )

            return {
                'success': True,
                'checkout_url': session.url,
                'session_id': session.id,
                'customer_id': session.customer
            }
        except Exception as e:
            logger.exception(
                "Failed to create checkout session",
                extra={'user_id': user_id, 'price_id': price_id, 'currency': currency}
            )
            return {
                'success': False,
                'error': str(e)
            }
    
    def create_customer(self, email: str, name: str = None) -> dict:
        """
        Create a Stripe customer
        
        Args:
            email: Customer email
            name: Customer name (optional)
            
        Returns:
            Dictionary with customer data or error
        """
        try:
            customer_params = {
                'email': email,
            }
            
            if name:
                customer_params['name'] = name
            
            customer = stripe.Customer.create(**customer_params)

            logger.info("Stripe customer created", extra={'customer_id': customer.id, 'email': email})

            return {
                'success': True,
                'customer_id': customer.id,
                'customer': customer
            }
        except Exception as e:
            logger.exception("Failed to create Stripe customer", extra={'email': email})
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_customer(self, customer_id: str) -> dict:
        """
        Get customer information
        
        Args:
            customer_id: Stripe customer ID
            
        Returns:
            Dictionary with customer data or error
        """
        try:
            customer = stripe.Customer.retrieve(customer_id)
            logger.debug("Retrieved Stripe customer", extra={'customer_id': customer_id})
            return {
                'success': True,
                'customer': customer
            }
        except Exception as e:
            logger.exception("Failed to retrieve Stripe customer", extra={'customer_id': customer_id})
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_subscription(self, subscription_id: str) -> dict:
        """
        Get subscription information
        
        Args:
            subscription_id: Stripe subscription ID
            
        Returns:
            Dictionary with subscription data or error
        """
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)

            logger.debug(
                "Retrieved Stripe subscription",
                extra={'subscription_id': subscription_id, 'status': subscription.status}
            )

            return {
                'success': True,
                'subscription': subscription,
                'status': subscription.status,
                'plan_id': subscription.items.data[0].price.id if subscription.items.data else None,
                'current_period_end': subscription.current_period_end
            }
        except Exception as e:
            logger.exception("Failed to retrieve subscription", extra={'subscription_id': subscription_id})
            return {
                'success': False,
                'error': str(e)
            }
    
    def cancel_subscription(self, subscription_id: str) -> dict:
        """
        Cancel a subscription immediately (legacy method - use modify_subscription for cancel_at_period_end)
        
        Args:
            subscription_id: Stripe subscription ID
            
        Returns:
            Dictionary with success status or error
        """
        try:
            subscription = stripe.Subscription.delete(subscription_id)
            logger.info("Cancelled Stripe subscription immediately", extra={'subscription_id': subscription_id})
            return {
                'success': True,
                'subscription': subscription
            }
        except Exception as e:
            logger.exception("Failed to cancel subscription", extra={'subscription_id': subscription_id})
            return {
                'success': False,
                'error': str(e)
            }
    
    def modify_subscription(self, subscription_id: str, cancel_at_period_end: bool = False) -> dict:
        """
        Modify a subscription (e.g., set cancel_at_period_end)
        
        Args:
            subscription_id: Stripe subscription ID
            cancel_at_period_end: If True, cancel at end of current period
            
        Returns:
            Dictionary with success status or error
        """
        try:
            subscription = stripe.Subscription.modify(
                subscription_id,
                cancel_at_period_end=cancel_at_period_end
            )
            logger.info(
                "Modified Stripe subscription",
                extra={
                    'subscription_id': subscription_id,
                    'cancel_at_period_end': cancel_at_period_end
                }
            )
            return {
                'success': True,
                'subscription': subscription,
                'cancel_at_period_end': subscription.get('cancel_at_period_end', False)
            }
        except Exception as e:
            logger.exception(
                "Failed to modify subscription",
                extra={'subscription_id': subscription_id, 'cancel_at_period_end': cancel_at_period_end}
            )
            return {
                'success': False,
                'error': str(e)
            }
    
    def handle_webhook(self, payload: str, sig_header: str) -> dict:
        """
        Handle Stripe webhook events
        
        Args:
            payload: Request payload
            sig_header: Stripe signature header
            
        Returns:
            Dictionary with event data or error
        """
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, Config.STRIPE_WEBHOOK_SECRET
            )

            logger.info("Stripe webhook received", extra={'event_type': event.type, 'event_id': event.id})

            return {
                'success': True,
                'event': event,
                'event_type': event.type,
                'event_data': event.data
            }
        except ValueError as e:
            logger.warning("Invalid Stripe webhook payload", extra={'error': str(e)})
            return {
                'success': False,
                'error': f'Invalid payload: {str(e)}'
            }
        except stripe.error.SignatureVerificationError as e:
            logger.warning("Invalid Stripe webhook signature", extra={'error': str(e)})
            return {
                'success': False,
                'error': f'Invalid signature: {str(e)}'
            }
    
    def get_next_billing_date(self, subscription_id: str) -> str:
        """
        Get next billing date for a subscription
        
        Args:
            subscription_id: Stripe subscription ID
            
        Returns:
            ISO format date string or None
        """
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
            timestamp = subscription.current_period_end
            return datetime.fromtimestamp(timestamp).isoformat()
        except Exception:
            logger.exception("Failed to fetch next billing date", extra={'subscription_id': subscription_id})
            return None

    def get_price_id_by_key(self, key: str) -> str:
        """
        Get Stripe price ID based on a composite key (e.g., 'br_monthly').
        """
        return self.price_ids.get(key)


# Singleton instance
_stripe_handler = None


def get_stripe_handler():
    """Get or create Stripe handler instance"""
    global _stripe_handler
    if _stripe_handler is None:
        _stripe_handler = StripeHandler()
    return _stripe_handler
