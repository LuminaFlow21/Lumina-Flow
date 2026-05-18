"""
Authentication Blueprint - Custom Authentication with Flask-Login
"""

from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
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
        else:
            return jsonify({'success': False, 'error': result.get('error', 'Login failed')}), 401
            
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
