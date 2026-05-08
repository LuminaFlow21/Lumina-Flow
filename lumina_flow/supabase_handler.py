"""
Lumina Flow - Supabase Handler
Isolated logic for Supabase authentication and database operations
"""

import os
from supabase import create_client, Client
from .config import Config


class SupabaseHandler:
    """Handler for Supabase operations"""
    
    def __init__(self):
        """Initialize Supabase client"""
        self.supabase_url = Config.SUPABASE_URL
        self.supabase_key = Config.SUPABASE_KEY
        self.supabase_service_key = Config.SUPABASE_SERVICE_ROLE_KEY
        
        if not self.supabase_url or not self.supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment variables")
        
        self.client: Client = create_client(self.supabase_url, self.supabase_key)
        self.admin_client: Client = create_client(self.supabase_url, self.supabase_service_key)
    
    def create_test_profile(self, user_id: str, email: str, full_name: str = 'Test User', plan: str = 'pro') -> dict:
        """
        Create a test user in Supabase Auth and profile (for testing purposes)

        Args:
            user_id: UUID for the test user
            email: Email address
            full_name: User's full name
            plan: Subscription plan

        Returns:
            Dictionary with success status
        """
        try:
            # First, try to create the user in Supabase Auth using admin API
            try:
                # Create user in auth.users (requires service role)
                auth_response = self.admin_client.auth.admin.create_user({
                    'email': email,
                    'password': 'testpassword123',
                    'email_confirm': True,
                    'user_metadata': {'full_name': full_name}
                })

                if auth_response.user:
                    user_id = auth_response.user.id  # Use the actual UUID from Supabase
            except Exception as auth_error:
                # User might already exist, that's OK
                print(f"Auth user creation (may already exist): {auth_error}")

            # Check if profile already exists
            response = self.admin_client.table('profiles') \
                .select('id') \
                .eq('id', user_id) \
                .execute()

            if response.data and len(response.data) > 0:
                return {'success': True, 'user_id': user_id, 'message': 'Profile already exists'}

            # Create profile directly
            from datetime import datetime
            profile_data = {
                'id': user_id,
                'email': email,
                'full_name': full_name,
                'plan': plan,
                'subscription_status': 'active',
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }

            self.admin_client.table('profiles').insert(profile_data).execute()
            return {'success': True, 'user_id': user_id, 'message': 'Test profile created'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def sign_up(self, email: str, password: str) -> dict:
        """
        Sign up a new user
        
        Args:
            email: User email
            password: User password
            
        Returns:
            Dictionary with user data or error
        """
        try:
            response = self.client.auth.sign_up({
                "email": email,
                "password": password
            })
            return {
                'success': True,
                'user': response.user,
                'session': response.session
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def sign_in(self, email: str, password: str) -> dict:
        """
        Sign in a user
        
        Args:
            email: User email
            password: User password
            
        Returns:
            Dictionary with user data or error
        """
        try:
            response = self.client.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            return {
                'success': True,
                'user': response.user,
                'session': response.session,
                'access_token': response.session.access_token
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def sign_out(self, access_token: str) -> dict:
        """
        Sign out a user
        
        Args:
            access_token: User access token
            
        Returns:
            Dictionary with success status or error
        """
        try:
            self.client.auth.sign_out()
            return {'success': True}
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_user(self, access_token: str) -> dict:
        """
        Get user information
        
        Args:
            access_token: User access token
            
        Returns:
            Dictionary with user data or error
        """
        try:
            response = self.client.auth.get_user(access_token)
            return {
                'success': True,
                'user': response.user
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    

    
    def get_user_subscription(self, user_id: str) -> dict:
        """
        Get user subscription information
        
        Args:
            user_id: User ID
            
        Returns:
            Dictionary with subscription data or error
        """
        try:
            response = self.admin_client.table('profiles').select('*').eq('user_id', user_id).execute()
            
            if response.data:
                profile = response.data[0]
                return {
                    'success': True,
                    'plan': profile.get('plan', 'free'),
                    'subscription_status': profile.get('subscription_status', 'inactive'),
                    'stripe_customer_id': profile.get('stripe_customer_id'),
                    'stripe_subscription_id': profile.get('stripe_subscription_id'),
                    'next_billing_date': profile.get('next_billing_date')
                }
            else:
                return {
                    'success': False,
                    'error': 'Profile not found'
                }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def update_user_subscription(self, user_id: str, plan: str, subscription_status: str, 
                                   stripe_customer_id: str = None, stripe_subscription_id: str = None,
                                   next_billing_date: str = None) -> dict:
        """
        Update user subscription information
        
        Args:
            user_id: User ID
            plan: Plan type (free, pro, enterprise)
            subscription_status: Subscription status (active, inactive, trial)
            stripe_customer_id: Stripe customer ID
            stripe_subscription_id: Stripe subscription ID
            next_billing_date: Next billing date
            
        Returns:
            Dictionary with success status or error
        """
        try:
            update_data = {
                'plan': plan,
                'subscription_status': subscription_status
            }
            
            if stripe_customer_id:
                update_data['stripe_customer_id'] = stripe_customer_id
            if stripe_subscription_id:
                update_data['stripe_subscription_id'] = stripe_subscription_id
            if next_billing_date:
                update_data['next_billing_date'] = next_billing_date
            
            response = self.admin_client.table('profiles').update(update_data).eq('user_id', user_id).execute()
            return {
                'success': True,
                'data': response.data
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def update_user_profile(self, user_id: str, full_name: str = None) -> dict:
        """
        Update user profile (name)
        
        Args:
            user_id: User ID
            full_name: User full name
            
        Returns:
            Dictionary with success status or error
        """
        try:
            update_data = {}
            if full_name:
                update_data['full_name'] = full_name
            
            response = self.admin_client.table('profiles').update(update_data).eq('user_id', user_id).execute()
            return {
                'success': True,
                'data': response.data
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def create_quotation(self, user_id: str, client_name: str, service_description: str,
                         value: float, currency: str = 'BRL', expiry_date: str = None) -> dict:
        """
        Create a new quotation
        
        Args:
            user_id: User ID
            client_name: Client name
            service_description: Service description
            value: Quotation value
            currency: Currency code
            expiry_date: Expiry date (YYYY-MM-DD)
            
        Returns:
            Dictionary with created quotation or error
        """
        try:
            data = {
                'user_id': user_id,
                'client_name': client_name,
                'service_description': service_description,
                'value': value,
                'currency': currency,
                'status': 'pending'
            }
            if expiry_date:
                data['expiry_date'] = expiry_date
            
            response = self.admin_client.table('quotations').insert(data).execute()
            return {
                'success': True,
                'data': response.data[0] if response.data else None
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_user_quotations(self, user_id: str) -> dict:
        """
        Get all quotations for a user
        
        Args:
            user_id: User ID
            
        Returns:
            Dictionary with list of quotations or error
        """
        try:
            response = self.admin_client.table('quotations') \
                .select('*') \
                .eq('user_id', user_id) \
                .order('created_at', desc=True) \
                .execute()
            return {
                'success': True,
                'data': response.data
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def count_user_quotations(self, user_id: str) -> dict:
        """
        Count user quotations
        
        Args:
            user_id: User ID
            
        Returns:
            Dictionary with count or error
        """
        try:
            response = self.admin_client.table('quotations') \
                .select('id', count='exact') \
                .eq('user_id', user_id) \
                .execute()
            return {
                'success': True,
                'count': len(response.data) if response.data else 0
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def get_quotation_by_id(self, user_id: str, quotation_id: str) -> dict:
        """
        Get a specific quotation by ID

        Args:
            user_id: User ID
            quotation_id: Quotation ID

        Returns:
            Dictionary with quotation data or error
        """
        try:
            response = self.admin_client.table('quotations') \
                .select('*') \
                .eq('id', quotation_id) \
                .eq('user_id', user_id) \
                .execute()

            if response.data and len(response.data) > 0:
                return {
                    'success': True,
                    'data': response.data[0]
                }
            else:
                return {
                    'success': False,
                    'error': 'Quotation not found'
                }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def is_pro_user(self, user_id: str) -> bool:
        """
        Check if user is a Pro subscriber
        
        Args:
            user_id: User ID
            
        Returns:
            Boolean indicating if user is Pro
        """
        subscription = self.get_user_subscription(user_id)
        if subscription.get('success'):
            return subscription.get('plan') == 'pro' and subscription.get('subscription_status') == 'active'
        return False


# Singleton instance
_supabase_handler = None


def get_supabase_handler():
    """Get or create Supabase handler instance"""
    global _supabase_handler
    if _supabase_handler is None:
        _supabase_handler = SupabaseHandler()
    return _supabase_handler
