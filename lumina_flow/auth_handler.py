"""
Custom Authentication Handler for Lumina Flow
Uses bcrypt for password hashing and PostgreSQL for user storage
"""

import logging
import bcrypt
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict
from flask_login import UserMixin
from .supabase_handler import get_supabase_handler


logger = logging.getLogger(__name__)


class User(UserMixin):
    """User class for Flask-Login"""
    
    def __init__(self, user_data: Dict):
        self.id = user_data['id']
        self.email = user_data['email']
        self.verified = user_data.get('verified', False)
        self.plan = user_data.get('plan', 'free')
        self.created_at = user_data.get('created_at')
    
    def get_id(self):
        return str(self.id)
    
    def is_authenticated(self):
        return True
    
    def is_active(self):
        return self.verified


class AuthHandler:
    """Handles user authentication with bcrypt and PostgreSQL"""
    
    def __init__(self):
        self.supabase = get_supabase_handler()
    
    def hash_password(self, password: str) -> str:
        """Hash a password using bcrypt"""
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    
    def verify_password(self, password: str, hashed: str) -> bool:
        """Verify a password against a hash"""
        try:
            return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
        except:
            return False
    
    def generate_verification_token(self) -> str:
        """Generate a secure random token for email verification"""
        return secrets.token_urlsafe(32)

    def generate_reset_token(self) -> str:
        """Generate a secure token for password resets"""
        return secrets.token_urlsafe(48)
    
    def create_user(self, email: str, password: str, plan: str = 'free', full_name: str = None) -> Dict:
        """
        Create a new user account
        
        Args:
            email: User email
            password: User password (will be hashed)
            plan: Subscription plan (default: free)
            full_name: User's full name (optional)
        
        Returns:
            Dictionary with success status and user data or error
        """
        try:
            # Check if email already exists
            existing = self.supabase.admin_client.table('users') \
                .select('id') \
                .eq('email', email) \
                .execute()
            
            if existing.data and len(existing.data) > 0:
                return {
                    'success': False,
                    'error': 'Email already registered'
                }
            
            # Hash password
            password_hash = self.hash_password(password)
            
            # Generate verification token
            verification_token = self.generate_verification_token()
            
            # Create user
            user_data = {
                'email': email,
                'password_hash': password_hash,
                'verified': False,
                'verification_token': verification_token,
                'plan': plan,
                'full_name': full_name,
                'created_at': datetime.now().isoformat()
            }
            
            response = self.supabase.admin_client.table('users') \
                .insert(user_data) \
                .execute()
            
            if response.data and len(response.data) > 0:
                user = response.data[0]
                
                return {
                    'success': True,
                    'user': user,
                    'verification_token': verification_token
                }
            else:
                return {
                    'success': False,
                    'error': 'Failed to create user'
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def verify_email(self, token: str) -> Dict:
        """
        Verify user email using token
        
        Args:
            token: Verification token sent to user's email
        
        Returns:
            Dictionary with success status
        """
        try:
            logger.info('[Auth] Verifying email token')
            
            # Find user by verification token
            response = self.supabase.admin_client.table('users') \
                .select('*') \
                .eq('verification_token', token) \
                .execute()
            
            logger.debug('[Auth] User lookup result', extra={'count': len(response.data) if response.data else 0})
            
            if not response.data or len(response.data) == 0:
                logger.warning('[Auth] Invalid verification token')
                return {
                    'success': False,
                    'error': 'Invalid or expired verification token'
                }
            
            user = response.data[0]
            logger.debug('[Auth] User found for verification', extra={'email': user['email'], 'verified': user.get('verified')})
            
            # Check if already verified
            if user.get('verified'):
                logger.info('[Auth] User already verified', extra={'email': user['email']})
                return {
                    'success': False,
                    'error': 'Email already verified'
                }
            
            # Mark user as verified
            update_result = self.supabase.admin_client.table('users') \
                .update({
                    'verified': True,
                    'verification_token': None,
                    'updated_at': datetime.now().isoformat()
                }) \
                .eq('id', user['id']) \
                .execute()
            
            logger.info('[Auth] User verified successfully', extra={'user_id': str(user['id'])})
            
            return {
                'success': True,
                'user': user
            }
            
        except Exception as e:
            logger.exception('[Auth] Exception in verify_email')
            return {
                'success': False,
                'error': str(e)
            }
    
    def authenticate_user(self, email: str, password: str) -> Dict:
        """
        Authenticate a user with email and password
        
        Args:
            email: User email
            password: User password
        
        Returns:
            Dictionary with success status and user data or error
        """
        try:
            logger.info('[Auth] Authenticating user', extra={'email': email})
            
            # Find user by email
            response = self.supabase.admin_client.table('users') \
                .select('*') \
                .eq('email', email) \
                .execute()
            
            logger.debug('[Auth] Lookup result', extra={'email': email, 'count': len(response.data) if response.data else 0})
            
            if not response.data or len(response.data) == 0:
                logger.warning('[Auth] User not found during authentication', extra={'email': email})
                return {
                    'success': False,
                    'error': 'Invalid email or password'
                }
            
            user = response.data[0]
            logger.debug('[Auth] User record fetched', extra={'email': user['email'], 'verified': user.get('verified')})
            
            # Check if email is verified
            if not user.get('verified'):
                logger.warning('[Auth] Email not verified', extra={'email': user['email']})
                return {
                    'success': False,
                    'error': 'Please verify your email before logging in',
                    'code': 'email_not_verified',
                    'email': email,
                    'user': user
                }
            
            # Verify password
            if not self.verify_password(password, user['password_hash']):
                logger.warning('[Auth] Password verification failed', extra={'email': user['email']})
                return {
                    'success': False,
                    'error': 'Invalid email or password'
                }
            
            logger.info('[Auth] Authentication successful', extra={'user_id': str(user['id'])})
            return {
                'success': True,
                'user': user
            }
            
        except Exception as e:
            logger.exception('[Auth] Exception in authenticate_user', extra={'email': email})
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_user_by_id(self, user_id: str) -> Dict:
        """
        Get user by ID
        
        Args:
            user_id: User ID
        
        Returns:
            Dictionary with success status and user data or error
        """
        try:
            response = self.supabase.admin_client.table('users') \
                .select('*') \
                .eq('id', user_id) \
                .execute()
            
            if response.data and len(response.data) > 0:
                return {
                    'success': True,
                    'user': response.data[0]
                }
            else:
                return {
                    'success': False,
                    'error': 'User not found'
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def update_user_plan(self, user_id: str, plan: str) -> Dict:
        """
        Update user subscription plan
        
        Args:
            user_id: User ID
            plan: New plan (free, basic, pro, enterprise)
        
        Returns:
            Dictionary with success status
        """
        try:
            self.supabase.admin_client.table('users') \
                .update({
                    'plan': plan,
                    'updated_at': datetime.now().isoformat()
                }) \
                .eq('id', user_id) \
                .execute()
            
            return {
                'success': True
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def create_password_reset_token(self, email: str) -> Dict:
        """Create and persist a password reset token for the given email"""
        try:
            logger.info('[Auth] Generating password reset token', extra={'email': email})

            response = self.supabase.admin_client.table('users') \
                .select('*') \
                .eq('email', email) \
                .execute()

            if not response.data:
                logger.warning('[Auth] Password reset requested for unknown email', extra={'email': email})
                return {
                    'success': False,
                    'error': 'If the email exists, a reset link will be sent.',
                    'code': 'not_found'
                }

            user = response.data[0]

            if not user.get('verified'):
                logger.warning('[Auth] Password reset requested for unverified account', extra={'email': email})
                return {
                    'success': False,
                    'error': 'Please verify your email before requesting a password reset.',
                    'code': 'unverified'
                }

            reset_token = self.generate_reset_token()
            expires_at_dt = datetime.now(timezone.utc) + timedelta(hours=1)
            expires_at = expires_at_dt.isoformat()

            self.supabase.admin_client.table('users') \
                .update({
                    'reset_token': reset_token,
                    'reset_token_expires_at': expires_at,
                    'updated_at': datetime.now(timezone.utc).isoformat()
                }) \
                .eq('id', user['id']) \
                .execute()

            logger.info('[Auth] Password reset token stored', extra={'user_id': str(user['id'])})

            return {
                'success': True,
                'token': reset_token,
                'user': user,
                'expires_at': expires_at
            }

        except Exception as e:
            logger.exception('[Auth] Exception creating password reset token', extra={'email': email})
            return {
                'success': False,
                'error': str(e)
            }

    def reset_password(self, token: str, new_password: str) -> Dict:
        """Reset the password for a user via a valid reset token"""
        try:
            logger.info('[Auth] Resetting password via token')

            response = self.supabase.admin_client.table('users') \
                .select('*') \
                .eq('reset_token', token) \
                .execute()

            if not response.data:
                logger.warning('[Auth] Invalid password reset token')
                return {
                    'success': False,
                    'error': 'Invalid or expired reset token.',
                    'code': 'invalid_token'
                }

            user = response.data[0]
            expires_at = user.get('reset_token_expires_at')

            if not expires_at:
                logger.warning('[Auth] Reset token without expiry', extra={'user_id': str(user['id'])})
                return {
                    'success': False,
                    'error': 'Invalid or expired reset token.',
                    'code': 'invalid_token'
                }

            try:
                if isinstance(expires_at, str):
                    expires_dt = datetime.fromisoformat(expires_at.replace('Z', '+00:00') if 'Z' in expires_at else expires_at)
                else:
                    expires_dt = expires_at
                if expires_dt.tzinfo is None:
                    expires_dt = expires_dt.replace(tzinfo=timezone.utc)
            except Exception:
                logger.exception('[Auth] Failed parsing reset token expiry', extra={'user_id': str(user['id'])})
                return {
                    'success': False,
                    'error': 'Invalid or expired reset token.',
                    'code': 'invalid_token'
                }

            if expires_dt < datetime.now(timezone.utc):
                logger.warning('[Auth] Reset token expired', extra={'user_id': str(user['id'])})
                return {
                    'success': False,
                    'error': 'Reset token has expired. Request a new one.',
                    'code': 'expired'
                }

            password_hash = self.hash_password(new_password)

            self.supabase.admin_client.table('users') \
                .update({
                    'password_hash': password_hash,
                    'reset_token': None,
                    'reset_token_expires_at': None,
                    'updated_at': datetime.now(timezone.utc).isoformat()
                }) \
                .eq('id', user['id']) \
                .execute()

            logger.info('[Auth] Password reset successful', extra={'user_id': str(user['id'])})

            return {
                'success': True
            }

        except Exception as e:
            logger.exception('[Auth] Exception resetting password')
            return {
                'success': False,
                'error': str(e)
            }


def is_admin_user(email: str) -> bool:
    """
    Check if a user email is in the admin list
    
    Args:
        email: User email to check
        
    Returns:
        True if email is in ADMIN_EMAILS, False otherwise
    """
    from .config import Config
    admin_emails = [e.strip().lower() for e in Config.ADMIN_EMAILS if e.strip()]
    return email.lower() in admin_emails


# Singleton instance
_auth_handler = None

def get_auth_handler():
    """Get the singleton AuthHandler instance"""
    global _auth_handler
    if _auth_handler is None:
        _auth_handler = AuthHandler()
    return _auth_handler

