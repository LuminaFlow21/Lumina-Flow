from flask import Blueprint, render_template, session, redirect, url_for, request, jsonify
from functools import wraps
from datetime import datetime
from ..supabase_handler import get_supabase_handler

dashboard_bp = Blueprint('dashboard', __name__)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login_page'))
        return f(*args, **kwargs)
    return decorated_function

def get_user_quotations(user_id: str) -> list:
    supabase = get_supabase_handler()
    result = supabase.get_user_quotations(user_id)
    return result.get('data', []) if result.get('success') else []

def can_create_quotation(user_id: str, plan: str) -> bool:
    if plan == 'pro':
        return True
    supabase = get_supabase_handler()
    count_result = supabase.count_user_quotations(user_id)
    if count_result.get('success'):
        return count_result.get('count', 0) < 3
    return False

@dashboard_bp.route('/test-dashboard')
def test_dashboard():
    """Test dashboard with mock data for UI testing"""
    test_email = 'test@luminaflow.com'
    test_password = 'testpassword123'

    # Create or get test user via Supabase Auth
    supabase = get_supabase_handler()

    # Try to sign in first (user might already exist)
    sign_in_result = supabase.sign_in(test_email, test_password)

    if sign_in_result.get('success'):
        # User is a Supabase User object, not a dict
        user = sign_in_result['user']
        test_user_id = user.id
        session['user_email'] = user.email
    else:
        # User doesn't exist, create via signup
        sign_up_result = supabase.sign_up(test_email, test_password)
        if sign_up_result.get('success'):
            # User is a Supabase User object, not a dict
            user = sign_up_result['user']
            test_user_id = user.id
            session['user_email'] = user.email
            # Update profile with test data
            supabase.update_user_profile(test_user_id, full_name='Test User')
            supabase.update_user_subscription(test_user_id, plan='pro', subscription_status='active')
        else:
            # Fallback - use a placeholder (will fail for quotations but dashboard will work)
            test_user_id = '11111111-1111-1111-1111-111111111111'
            session['user_email'] = test_email

    # Get real subscription data from Supabase
    sub_result = supabase.get_user_subscription(test_user_id)
    subscription = {
        'plan': sub_result.get('plan', 'pro') if sub_result.get('success') else 'pro',
        'status': sub_result.get('subscription_status', 'active') if sub_result.get('success') else 'active',
        'next_billing': '2026-06-06'
    }

    # Get real quotations from database
    quotations = get_user_quotations(test_user_id)

    session['user_id'] = test_user_id
    session['user_email'] = test_email
    return render_template(
        'dashboard.html',
        subscription=subscription,
        quotations=quotations,
        quotation_count=len(quotations),
        can_create=True
    )

@dashboard_bp.route('/dashboard')
@login_required
def dashboard_view():
    user_id = session.get('user_id')
    supabase = get_supabase_handler()
    
    subscription_result = supabase.get_user_subscription(user_id)
    subscription = {
        'plan': 'free',
        'status': 'inactive',
        'next_billing': None
    }
    if subscription_result.get('success'):
        subscription['plan'] = subscription_result.get('plan', 'free')
        subscription['status'] = subscription_result.get('subscription_status', 'inactive')
        subscription['next_billing'] = subscription_result.get('next_billing_date')
    
    quotations = get_user_quotations(user_id)
    quotation_count = len(quotations)
    can_create_new = can_create_quotation(user_id, subscription['plan'])
    
    return render_template(
        'dashboard.html', 
        subscription=subscription, 
        quotations=quotations, 
        quotation_count=quotation_count, 
        can_create=can_create_new
    )

@dashboard_bp.route('/quotation/<uuid:quotation_id>')
@login_required
def quotation_detail(quotation_id):
    user_id = session.get('user_id')
    supabase = get_supabase_handler()
    result = supabase.get_quotation_by_id(user_id, str(quotation_id))

    if result.get('success') and result.get('data'):
        return render_template('quotation_detail.html', quotation=result['data'])
    
    return redirect(url_for('dashboard.dashboard_view'))

@dashboard_bp.route('/profile')
@login_required
def profile():
    user_id = session.get('user_id')
    supabase = get_supabase_handler()
    
    sub_result = supabase.get_user_subscription(user_id)
    subscription = {
        'plan': sub_result.get('plan', 'free') if sub_result.get('success') else 'free',
        'status': sub_result.get('subscription_status', 'inactive') if sub_result.get('success') else 'inactive'
    }
    
    return render_template('profile.html', subscription=subscription, user_email=session.get('user_email'))

@dashboard_bp.route('/api/quotations', methods=['POST'])
@login_required
def create_quotation():
    user_id = session.get('user_id')
    data = request.get_json()
    
    supabase = get_supabase_handler()
    sub_result = supabase.get_user_subscription(user_id)
    plan = sub_result.get('plan', 'free') if sub_result.get('success') else 'free'
    
    if not can_create_quotation(user_id, plan):
        return jsonify({'success': False, 'error': 'Free plan limit reached. Upgrade to Pro.'}), 403
    
    region = session.get('user_region', 'UK')
    currency = 'BRL' if region == 'BR' else 'GBP'
    
    result = supabase.create_quotation(
        user_id=user_id,
        client_name=data.get('client_name'),
        service_description=data.get('service_description'),
        value=float(data.get('value', 0)),
        currency=currency,
        expiry_date=data.get('expiry_date')
    )
    
    if result.get('success'):
        return jsonify({'success': True, 'quotation': result.get('data')})
    else:
        return jsonify({'success': False, 'error': result.get('error', 'Failed to create quotation')}), 400

@dashboard_bp.route('/api/profile', methods=['PUT'])
@login_required
def update_profile():
    user_id = session.get('user_id')
    data = request.get_json()
    
    supabase = get_supabase_handler()
    result = supabase.update_user_profile(user_id, full_name=data.get('full_name'))
    
    if result.get('success'):
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': result.get('error')}), 400