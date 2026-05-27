"""
Email Handler for Lumina Flow
Uses Brevo API for sending transactional emails
"""

import logging
import requests
from typing import Dict, Optional
from flask import current_app


logger = logging.getLogger(__name__)


class EmailHandler:
    """Handles email sending via Brevo API"""
    
    def __init__(self):
        self.api_key = current_app.config.get('BREVO_API_KEY')
        self.base_url = 'https://api.brevo.com/v3'
    
    def send_verification_email(self, email: str, verification_token: str, user_name: str = None) -> Dict:
        """
        Send email verification link to user
        
        Args:
            email: User email address
            verification_token: Verification token
            user_name: Optional user name for personalization
        
        Returns:
            Dictionary with success status
        """
        try:
            logger.info('[Email] Sending verification email', extra={'email': email})
            logger.debug('[Email] API key configured', extra={'has_key': bool(self.api_key)})
            
            # Build verification URL
            verification_url = f"{current_app.config.get('BASE_URL', 'http://localhost:5000')}/verify/{verification_token}"
            logger.debug('[Email] Verification URL built', extra={'email': email})
            
            # Prepare email data
            email_data = {
                "sender": {
                    "name": "Lumina Flow",
                    "email": current_app.config.get('BREVO_SENDER_EMAIL', 'noreply@luminaflow.com')
                },
                "to": [
                    {
                        "email": email,
                        "name": user_name or email.split('@')[0]
                    }
                ],
                "subject": "Verify your Lumina Flow account",
                "htmlContent": f"""
                <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                        <h2 style="color: #1e40af;">Welcome to Lumina Flow!</h2>
                        <p>Thank you for signing up. Please verify your email address to activate your account.</p>
                        
                        <div style="text-align: center; margin: 30px 0;">
                            <a href="{verification_url}" 
                               style="background-color: #1e40af; color: white; padding: 12px 30px; 
                                      text-decoration: none; border-radius: 5px; font-weight: bold;">
                                Verify Email
                            </a>
                        </div>
                        
                        <p style="font-size: 12px; color: #666;">
                            If the button doesn't work, copy and paste this link into your browser:<br>
                            <a href="{verification_url}" style="color: #1e40af;">{verification_url}</a>
                        </p>
                        
                        <p style="font-size: 12px; color: #999;">
                            This link will expire in 24 hours.<br>
                            If you didn't create an account, please ignore this email.
                        </p>
                    </div>
                </body>
                </html>
                """,
                "textContent": f"""
Welcome to Lumina Flow!

Thank you for signing up. Please verify your email address to activate your account.

Click the link below to verify your email:
{verification_url}

This link will expire in 24 hours.
If you didn't create an account, please ignore this email.
                """
            }
            
            logger.debug('[Email] Email payload prepared', extra={'email': email})
            
            # Send email via Brevo API
            headers = {
                'accept': 'application/json',
                'content-type': 'application/json',
                'api-key': self.api_key
            }
            
            response = requests.post(
                f'{self.base_url}/smtp/email',
                json=email_data,
                headers=headers
            )
            
            logger.info('[Email] Brevo API response', extra={'status': response.status_code})
            
            if response.status_code in [200, 201, 202]:
                return {
                    'success': True,
                    'message': 'Verification email sent'
                }
            else:
                return {
                    'success': False,
                    'error': f'Brevo API error: {response.status_code} - {response.text}'
                }
                
        except Exception as e:
            logger.exception('[Email] Exception sending verification email', extra={'email': email})
            return {
                'success': False,
                'error': str(e)
            }

    def send_password_reset_email(self, email: str, reset_token: str, user_name: Optional[str] = None) -> Dict:
        """Send password reset email with a secure link"""
        try:
            logger.info('[Email] Sending password reset email', extra={'email': email})

            reset_url = f"{current_app.config.get('BASE_URL', 'http://localhost:5000')}/auth/login?reset_token={reset_token}"

            email_data = {
                "sender": {
                    "name": "Lumina Flow",
                    "email": current_app.config.get('BREVO_SENDER_EMAIL', 'noreply@luminaflow.com')
                },
                "to": [
                    {
                        "email": email,
                        "name": user_name or email.split('@')[0]
                    }
                ],
                "subject": "Reset your Lumina Flow password",
                "htmlContent": f"""
                <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                        <h2 style="color: #1e40af;">Reset your password</h2>
                        <p>We received a request to reset your Lumina Flow password.</p>
                        <p>If you made this request, click the button below to choose a new password.</p>

                        <div style="text-align: center; margin: 30px 0;">
                            <a href="{reset_url}"
                               style="background-color: #1e40af; color: white; padding: 12px 30px;
                                      text-decoration: none; border-radius: 5px; font-weight: bold;">
                                Reset password
                            </a>
                        </div>

                        <p style="font-size: 12px; color: #666;">
                            If the button doesn't work, copy and paste this link into your browser:<br>
                            <a href="{reset_url}" style="color: #1e40af;">{reset_url}</a>
                        </p>

                        <p style="font-size: 12px; color: #999;">
                            This link will expire in 1 hour for your security.<br>
                            If you didn't request a password reset, you can safely ignore this email.
                        </p>
                    </div>
                </body>
                </html>
                """,
                "textContent": f"""
We received a request to reset your Lumina Flow password.

If you made this request, use the link below to choose a new password:
{reset_url}

This link will expire in 1 hour. If you didn't request a password reset, you can ignore this email.
                """
            }

            headers = {
                'accept': 'application/json',
                'content-type': 'application/json',
                'api-key': self.api_key
            }

            response = requests.post(
                f'{self.base_url}/smtp/email',
                json=email_data,
                headers=headers
            )

            logger.info('[Email] Password reset email response', extra={'status': response.status_code})

            if response.status_code in [200, 201, 202]:
                return {
                    'success': True,
                    'message': 'Password reset email sent'
                }
            else:
                return {
                    'success': False,
                    'error': f'Brevo API error: {response.status_code} - {response.text}'
                }

        except Exception as e:
            logger.exception('[Email] Exception sending password reset email', extra={'email': email})
            return {
                'success': False,
                'error': str(e)
            }
    
    def send_welcome_email(self, email: str, user_name: str = None) -> Dict:
        """
        Send welcome email after verification
        
        Args:
            email: User email address
            user_name: Optional user name for personalization
        
        Returns:
            Dictionary with success status
        """
        try:
            email_data = {
                "sender": {
                    "name": "Lumina Flow",
                    "email": current_app.config.get('BREVO_SENDER_EMAIL', 'noreply@luminaflow.com')
                },
                "to": [
                    {
                        "email": email,
                        "name": user_name or email.split('@')[0]
                    }
                ],
                "subject": "Welcome to Lumina Flow!",
                "htmlContent": f"""
                <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                        <h2 style="color: #1e40af;">Welcome to Lumina Flow!</h2>
                        <p>Your account has been successfully verified.</p>
                        <p>You can now start creating quotations and managing your business.</p>
                        
                        <div style="text-align: center; margin: 30px 0;">
                            <a href="{current_app.config.get('BASE_URL', 'http://localhost:5000')}/dashboard" 
                               style="background-color: #1e40af; color: white; padding: 12px 30px; 
                                      text-decoration: none; border-radius: 5px; font-weight: bold;">
                                Go to Dashboard
                            </a>
                        </div>
                        
                        <p style="font-size: 12px; color: #999;">
                            If you have any questions, feel free to contact us.
                        </p>
                    </div>
                </body>
                </html>
                """
            }
            
            headers = {
                'accept': 'application/json',
                'content-type': 'application/json',
                'api-key': self.api_key
            }
            
            response = requests.post(
                f'{self.base_url}/smtp/email',
                json=email_data,
                headers=headers
            )
            
            logger.info('[Email] Welcome email response', extra={'status': response.status_code})

            if response.status_code in [200, 201, 202]:
                return {
                    'success': True,
                    'message': 'Welcome email sent'
                }
            else:
                return {
                    'success': False,
                    'error': f'Brevo API error: {response.status_code} - {response.text}'
                }
                
        except Exception as e:
            logger.exception('[Email] Exception sending welcome email', extra={'email': email})
            return {
                'success': False,
                'error': str(e)
            }


# Singleton instance
_email_handler = None

def get_email_handler():
    """Get the singleton EmailHandler instance"""
    global _email_handler
    if _email_handler is None:
        _email_handler = EmailHandler()
    return _email_handler
