"""
Authentication Blueprint - Custom Authentication with Flask-Login
"""

from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime
from ..auth_handler import get_auth_handler, User
from ..email_handler import get_email_handler

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login')
def login_page():
    """Render login page"""
    return render_template('login.html')


@auth_bp.route('/login', methods=['POST'])
def handle_login():
    """Handle login request"""
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        remember = data.get('remember', False)
        
        if not email or not password:
            return jsonify({'success': False, 'error': 'Email and password are required'}), 400
        
        auth_handler = get_auth_handler()
        result = auth_handler.authenticate_user(email, password)

        if result.get('success'):
            user_data = result['user']
            user = User(user_data)

            # Set session as permanent if remember is True
            if remember:
                session.permanent = True

            login_user(user, remember=remember)

            # Set session variables
            session['user_id'] = str(user_data['id'])
            session['user_email'] = user_data['email']
            session['user_plan'] = user_data.get('plan', 'free')

            # Set region based on email
            if '.br' in email.lower():
                session['user_region'] = 'BR'
            else:
                session['user_region'] = 'UK'

            return jsonify({'success': True, 'redirect': '/dashboard'})
        elif result.get('code') == 'email_not_verified':
            # Email not verified - return user data to show verification modal
            user_data = result.get('user', {})
            return jsonify({
                'success': False,
                'code': 'email_not_verified',
                'email': result.get('email'),
                'full_name': user_data.get('full_name'),
                'error': result.get('error')
            }), 200
        else:
            return jsonify({'success': False, 'error': result.get('error', 'Login failed')}), 401
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@auth_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    """Handle password reset request by email"""
    try:
        data = request.get_json() or {}
        email = data.get('email')

        if not email:
            return jsonify({'success': False, 'error': 'Email is required'}), 400

        auth_handler = get_auth_handler()
        token_result = auth_handler.create_password_reset_token(email)

        if not token_result.get('success'):
            code = token_result.get('code')

            # Do not reveal if email exists
            if code == 'not_found':
                return jsonify({
                    'success': True,
                    'message': 'If the email exists, a reset link will be sent.'
                })

            if code == 'unverified':
                return jsonify({
                    'success': False,
                    'error': token_result.get('error', 'Account not verified.')
                }), 400

            return jsonify({
                'success': False,
                'error': token_result.get('error', 'Unable to create reset token.')
            }), 400

        email_handler = get_email_handler()
        user = token_result.get('user') or {}
        email_response = email_handler.send_password_reset_email(
            email=email,
            reset_token=token_result.get('token'),
            user_name=user.get('full_name')
        )

        if not email_response.get('success'):
            return jsonify({
                'success': False,
                'error': email_response.get('error', 'Failed to send reset email via Brevo.')
            }), 502

        return jsonify({
            'success': True,
            'message': 'We sent instructions to reset your password.'
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@auth_bp.route('/reset-password', methods=['POST'])
def reset_password():
    """Reset password using token"""
    try:
        data = request.get_json() or {}
        token = data.get('token')
        password = data.get('password')
        confirm_password = data.get('confirm_password')

        if not token or not password or not confirm_password:
            return jsonify({'success': False, 'error': 'Token and password are required'}), 400

        if password != confirm_password:
            return jsonify({'success': False, 'error': 'Passwords do not match'}), 400

        if len(password) < 8:
            return jsonify({'success': False, 'error': 'Password must be at least 8 characters'}), 400

        auth_handler = get_auth_handler()
        result = auth_handler.reset_password(token, password)

        if result.get('success'):
            return jsonify({'success': True, 'message': 'Password updated successfully. You can now login.'})

        status_code = 400 if result.get('code') in {'invalid_token', 'expired'} else 500

        return jsonify({
            'success': False,
            'error': result.get('error', 'Unable to reset password')
        }), status_code

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@auth_bp.route('/signup', methods=['POST'])
def handle_signup():
    """Handle signup request"""
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        full_name = data.get('full_name')
        plan = data.get('plan', 'free')
        
        if not email or not password:
            return jsonify({'success': False, 'error': 'Email and password are required'}), 400
        
        auth_handler = get_auth_handler()
        result = auth_handler.create_user(email, password, plan, full_name)
        
        if result.get('success'):
            user_data = result['user']
            verification_token = result.get('verification_token')
            
            # Send verification email
            email_handler = get_email_handler()
            email_result = email_handler.send_verification_email(
                email=email,
                verification_token=verification_token,
                user_name=full_name or email.split('@')[0]
            )
            
            if email_result.get('success'):
                return jsonify({
                    'success': True,
                    'message': 'Account created. Please check your email to verify your account.'
                })
            else:
                return jsonify({
                    'success': True,
                    'message': 'Account created but email verification failed. Please contact support.',
                    'error': email_result.get('error')
                })
        else:
            return jsonify({'success': False, 'error': result.get('error', 'Signup failed')}), 401
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@auth_bp.route('/logout')
@login_required
def handle_logout():
    """Handle logout request"""
    logout_user()
    session.clear()
    return redirect(url_for('main.index'))


@auth_bp.route('/resend-verification', methods=['POST'])
def handle_resend_verification():
    """Handle resend verification code request"""
    try:
        data = request.get_json()
        email = data.get('email')
        full_name = data.get('full_name', email.split('@')[0])
        
        if not email:
            return jsonify({'success': False, 'error': 'Email is required'}), 400
        
        auth_handler = get_auth_handler()
        
        # Find user by email
        result = auth_handler.supabase.admin_client.table('users') \
            .select('*') \
            .eq('email', email) \
            .execute()
        
        if not result.data or len(result.data) == 0:
            return jsonify({'success': False, 'error': 'Email not found'}), 404
        
        user = result.data[0]
        
        # Check if already verified
        if user.get('verified'):
            return jsonify({'success': False, 'error': 'Email already verified'}), 400
        
        # Generate new verification token
        new_token = auth_handler.generate_verification_token()
        
        # Update user with new token
        auth_handler.supabase.admin_client.table('users') \
            .update({'verification_token': new_token}) \
            .eq('id', user['id']) \
            .execute()
        
        # Send verification email
        email_handler = get_email_handler()
        email_result = email_handler.send_verification_email(
            email=email,
            verification_token=new_token,
            user_name=full_name
        )
        
        if email_result.get('success'):
            return jsonify({'success': True, 'message': 'Verification code resent'})
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to send verification email'
            }), 500
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@auth_bp.route('/change-email', methods=['POST'])
def handle_change_email():
    """Handle change email request"""
    try:
        data = request.get_json()
        old_email = data.get('old_email')
        new_email = data.get('new_email')
        full_name = data.get('full_name')
        password = data.get('password')
        
        if not old_email or not new_email or not password:
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        
        auth_handler = get_auth_handler()
        
        # Find user by old email
        result = auth_handler.supabase.admin_client.table('users') \
            .select('*') \
            .eq('email', old_email) \
            .execute()
        
        if not result.data or len(result.data) == 0:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        user = result.data[0]
        
        # Verify password
        if not auth_handler.verify_password(password, user['password_hash']):
            return jsonify({'success': False, 'error': 'Invalid password'}), 401
        
        # Check if new email already exists
        existing = auth_handler.supabase.admin_client.table('users') \
            .select('id') \
            .eq('email', new_email) \
            .execute()
        
        if existing.data and len(existing.data) > 0:
            return jsonify({'success': False, 'error': 'Email already registered'}), 400
        
        # Generate new verification token
        new_token = auth_handler.generate_verification_token()
        
        # Update user with new email and new token
        auth_handler.supabase.admin_client.table('users') \
            .update({
                'email': new_email,
                'verification_token': new_token,
                'verified': False,
                'updated_at': datetime.now().isoformat()
            }) \
            .eq('id', user['id']) \
            .execute()
        
        # Send verification email to new email
        email_handler = get_email_handler()
        email_result = email_handler.send_verification_email(
            email=new_email,
            verification_token=new_token,
            user_name=full_name
        )
        
        if email_result.get('success'):
            return jsonify({'success': True, 'message': 'Email updated. Please verify new email.'})
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to send verification email'
            }), 500
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
