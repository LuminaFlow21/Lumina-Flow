"""
Email Handler for Lumina Flow
Uses Brevo API for sending transactional emails
"""

import requests
from typing import Dict, Optional
from flask import current_app


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
            print(f'[Email] Sending verification email to: {email}')
            print(f'[Email] API Key configured: {bool(self.api_key)}')
            
            # Build verification URL
            verification_url = f"{current_app.config.get('BASE_URL', 'http://localhost:5000')}/verify/{verification_token}"
            print(f'[Email] Verification URL: {verification_url}')
            
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
            
            print(f'[Email] Email data prepared, sending to Brevo API...')
            
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
            
            print(f'[Email] Brevo API response status: {response.status_code}')
            print(f'[Email] Brevo API response body: {response.text}')
            
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
            print(f'[Email] Exception: {str(e)}')
            import traceback
            traceback.print_exc()
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
