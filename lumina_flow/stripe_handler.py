"""
Lumina Flow - Stripe Handler
Isolated logic for Stripe payment processing
"""

import os
import stripe
from datetime import datetime, timedelta
from .config import Config


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
            raise ValueError(f"No price ID found for {currency} {billing}")
        
        return price_id
    
    def create_checkout_session(self, price_id: str, user_id: str, user_email: str, currency: str, customer_id: str = None) -> dict:
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
            locale_code = 'pt-BR' if currency.lower() == 'brl' else 'en-GB'

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
            
            session = stripe.checkout.Session.create(**session_params)
            
            return {
                'success': True,
                'checkout_url': session.url,
                'session_id': session.id,
                'customer_id': session.customer
            }
        except Exception as e:
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
            
            return {
                'success': True,
                'customer_id': customer.id,
                'customer': customer
            }
        except Exception as e:
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
            return {
                'success': True,
                'customer': customer
            }
        except Exception as e:
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
            
            return {
                'success': True,
                'subscription': subscription,
                'status': subscription.status,
                'plan_id': subscription.items.data[0].price.id if subscription.items.data else None,
                'current_period_end': subscription.current_period_end
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def cancel_subscription(self, subscription_id: str) -> dict:
        """
        Cancel a subscription
        
        Args:
            subscription_id: Stripe subscription ID
            
        Returns:
            Dictionary with success status or error
        """
        try:
            subscription = stripe.Subscription.delete(subscription_id)
            return {
                'success': True,
                'subscription': subscription
            }
        except Exception as e:
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
            
            return {
                'success': True,
                'event': event,
                'event_type': event.type,
                'event_data': event.data
            }
        except ValueError as e:
            return {
                'success': False,
                'error': f'Invalid payload: {str(e)}'
            }
        except stripe.error.SignatureVerificationError as e:
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
