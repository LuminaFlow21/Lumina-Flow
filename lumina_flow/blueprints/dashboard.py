from flask import Blueprint, render_template, session, redirect, url_for, request, jsonify, abort
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from ..supabase_handler import get_supabase_handler
from ..stripe_handler import get_stripe_handler
from ..auth_handler import get_auth_handler
from .main import PRICING
import os
import base64
import uuid
import logging
from werkzeug.utils import secure_filename

dashboard_bp = Blueprint('dashboard', __name__)
logger = logging.getLogger(__name__)

def check_and_update_expired_quotations(quotations: list, user_id: str) -> list:
    """Check if quotations have expired and update status to 'expired'"""
    supabase = get_supabase_handler()
    today = datetime.now().date()

    for quotation in quotations:
        if quotation.get('status') in ['pending', 'accepted'] and quotation.get('expiry_date'):
            try:
                expiry_date = datetime.strptime(quotation['expiry_date'][:10], '%Y-%m-%d').date()
                if expiry_date < today:
                    # Update status to expired
                    supabase.update_quotation_status(user_id, quotation['id'], 'expired')
                    quotation['status'] = 'expired'
            except (ValueError, KeyError):
                pass

    return quotations

def get_user_quotations(user_id: str, access_token: str = None) -> list:
    supabase = get_supabase_handler()
    result = supabase.get_user_quotations(user_id, access_token)
    quotations = result.get('data', []) if result.get('success') else []
    return check_and_update_expired_quotations(quotations, user_id)

ALLOWED_DELETE_PLANS = {'basic', 'pro', 'enterprise'}
REGION_TO_CURRENCY = {'BR': 'BRL', 'UK': 'GBP'}

TEMPLATE_PALETTES = {
    'quick_modern_v2.html': ['#eef3ff', '#1565ff', '#29d6ff', '#e0e7ff'],
    'quick_classic.html': ['#f4f1ea', '#b45309', '#d97706', '#fef3c7'],
    'quick_bold.html': ['#fff1f2', '#be185d', '#f97316', '#ffe4e6'],
    'quick_elegant.html': ['#f4f4f5', '#78350f', '#ea580c', '#fef0c7'],
    'quick_vibrant.html': ['#fff7ed', '#ec4899', '#f97316', '#ffe4e6'],
    'quick_clean.html': ['#f0fdfa', '#0f766e', '#14b8a6', '#ccfbf1'],
    'quick_creative.html': ['#faf5ff', '#a855f7', '#6366f1', '#ede9fe'],
    'quick_luxury.html': ['#0b1120', '#facc15', '#f59e0b', '#4c1d95'],
    'quick_tech.html': ['#020617', '#38bdf8', '#22d3ee', '#0ea5e9'],
    'quick_premium.html': ['#ecfccb', '#15803d', '#34d399', '#dcfce7'],
    'detailed_premium.html': ['#ecfccb', '#15803d', '#34d399', '#dcfce7'],
    'detailed_modern.html': ['#ecf1ff', '#4f46e5', '#0ea5e9', '#e0e7ff'],
    'detailed_classic.html': ['#f5f1ea', '#b45309', '#d97706', '#fef3c7'],
    'detailed_bold.html': ['#fff1f2', '#be123c', '#f97316', '#ffe4e6'],
    'detailed_elegant.html': ['#f4f4f5', '#78350f', '#ea580c', '#fef0c7'],
    'detailed_clean.html': ['#f0fdfa', '#0f766e', '#14b8a6', '#ccfbf1'],
    'detailed_creative.html': ['#fdf2ff', '#a855f7', '#6366f1', '#f3e8ff'],
    'detailed_luxury.html': ['#0b1120', '#facc15', '#f59e0b', '#4c1d95'],
    'detailed_tech.html': ['#0f172a', '#38bdf8', '#22d3ee', '#0ea5e9'],
    'detailed_vibrant.html': ['#fff7ed', '#ec4899', '#f97316', '#ffe4e6'],
}

TEMPLATE_CATALOG = {
    'quick': [
        {'name': 'Moderno Clássico', 'template_file': 'quick_modern_v2.html', 'preview_image': None},
        {'name': 'Clássico Profissional', 'template_file': 'quick_classic.html', 'preview_image': None},
        {'name': 'Bold Impactante', 'template_file': 'quick_bold.html', 'preview_image': None},
        {'name': 'Elegante Sofisticado', 'template_file': 'quick_elegant.html', 'preview_image': None},
        {'name': 'Vibrante Energético', 'template_file': 'quick_vibrant.html', 'preview_image': None},
        {'name': 'Limpo Minimalista', 'template_file': 'quick_clean.html', 'preview_image': None},
        {'name': 'Criativo Colorido', 'template_file': 'quick_creative.html', 'preview_image': None},
        {'name': 'Luxo Premium', 'template_file': 'quick_luxury.html', 'preview_image': None},
        {'name': 'Tech Moderno', 'template_file': 'quick_tech.html', 'preview_image': None},
        {'name': 'Premium Dark', 'template_file': 'quick_premium.html', 'preview_image': None},
    ],
    'detailed': [
        {'name': 'Premium Dark', 'template_file': 'detailed_premium.html', 'preview_image': None},
        {'name': 'Moderno Minimalista', 'template_file': 'detailed_modern.html', 'preview_image': None},
        {'name': 'Clássico Profissional', 'template_file': 'detailed_classic.html', 'preview_image': None},
        {'name': 'Bold Impactante', 'template_file': 'detailed_bold.html', 'preview_image': None},
        {'name': 'Elegante Sofisticado', 'template_file': 'detailed_elegant.html', 'preview_image': None},
        {'name': 'Limpo Minimalista', 'template_file': 'detailed_clean.html', 'preview_image': None},
        {'name': 'Criativo Colorido', 'template_file': 'detailed_creative.html', 'preview_image': None},
        {'name': 'Luxo Premium', 'template_file': 'detailed_luxury.html', 'preview_image': None},
        {'name': 'Tech Moderno', 'template_file': 'detailed_tech.html', 'preview_image': None},
        {'name': 'Vibrante Energético', 'template_file': 'detailed_vibrant.html', 'preview_image': None},
    ],
}

for group in TEMPLATE_CATALOG.values():
    for entry in group:
        entry['palette'] = TEMPLATE_PALETTES.get(entry['template_file'], [])

ALL_TEMPLATES = {
    entry['template_file']: entry
    for group in TEMPLATE_CATALOG.values()
    for entry in group
}


def can_create_quotation(user_id: str, plan: str) -> bool:
    normalized_plan = (plan or 'free').lower()
    if normalized_plan in ('basic', 'pro'):
        return True
    supabase = get_supabase_handler()
    count_result = supabase.count_user_quotations(user_id)
    if count_result.get('success'):
        return count_result.get('count', 0) < 3
    return False


def can_delete_quotation(plan: str) -> bool:
    normalized_plan = (plan or 'free').lower()
    return normalized_plan in ALLOWED_DELETE_PLANS


def resolve_region_and_currency(payload=None):
    payload = payload or {}
    region = str(payload.get('region', '')).upper()

    if region not in REGION_TO_CURRENCY:
        region = session.get('user_region', 'UK')
    else:
        session['user_region'] = region

    currency = REGION_TO_CURRENCY.get(region, 'GBP')
    return region, currency

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
            supabase.update_user_subscription(test_user_id, plan='basic', subscription_status='active')
        else:
            # Fallback - use a placeholder (will fail for quotations but dashboard will work)
            test_user_id = '11111111-1111-1111-1111-111111111111'
            session['user_email'] = test_email

    # Get real subscription data from Supabase
    sub_result = supabase.get_user_subscription(test_user_id)
    subscription = {
        'plan': sub_result.get('plan', 'basic') if sub_result.get('success') else 'basic',
        'status': sub_result.get('subscription_status', 'active') if sub_result.get('success') else 'active',
        'next_billing': '2026-06-06'
    }

    # Get real quotations from database
    quotations = get_user_quotations(test_user_id)
    recent_quotations = quotations[:5]

    session['user_id'] = test_user_id
    session['user_email'] = test_email
    return render_template(
        'dashboard.html',
        subscription=subscription,
        quotations=quotations,
        recent_quotations=recent_quotations,
        quotation_count=len(quotations),
        can_create=True
    )

@dashboard_bp.route('/')
@login_required
def dashboard_view():
    user_id = current_user.id
    user_plan = current_user.plan
    supabase = get_supabase_handler()

    subscription_result = supabase.get_user_subscription(user_id)
    subscription = {
        'plan': user_plan,
        'status': subscription_result.get('subscription_status', 'inactive') if subscription_result.get('success') else 'inactive',
        'next_billing': subscription_result.get('next_billing_date') if subscription_result.get('success') else None
    }

    quotations = get_user_quotations(user_id)
    quotation_count = len(quotations)
    recent_quotations = quotations[:5]
    can_create_new = can_create_quotation(user_id, subscription['plan'])

    # Check if profile is complete
    profile_result = supabase.get_user_profile(user_id)
    profile_data = profile_result.get('data', {}) if profile_result.get('success') else {}
    profile_complete = bool(profile_data.get('profile_photo_url') and profile_data.get('whatsapp'))

    return render_template(
        'dashboard.html',
        subscription=subscription,
        quotations=quotations,
        recent_quotations=recent_quotations,
        quotation_count=quotation_count, 
        can_create=can_create_new,
        profile_complete=profile_complete,
        profile_data=profile_data
    )

@dashboard_bp.route('/quotation/select-type')
@login_required
def select_quotation_type():
    user_id = current_user.id
    supabase = get_supabase_handler()
    
    # Get profile data
    profile_result = supabase.get_user_profile(user_id)
    profile_data = profile_result.get('data', {}) if profile_result.get('success') else {}
    
    # Get subscription data
    sub_result = supabase.get_user_subscription(user_id)
    subscription = {
        'plan': current_user.plan,
        'status': sub_result.get('subscription_status', 'inactive') if sub_result.get('success') else 'inactive'
    }
    
    return render_template('select_quotation_type.html', profile_data=profile_data, subscription=subscription)

@dashboard_bp.route('/quotation/select-template/<quotation_type>')
@login_required
def select_template(quotation_type):
    user_id = current_user.id
    supabase = get_supabase_handler()
    
    # Get subscription data
    sub_result = supabase.get_user_subscription(user_id)
    subscription = {
        'plan': current_user.plan,
        'status': sub_result.get('subscription_status', 'inactive') if sub_result.get('success') else 'inactive'
    }
    
    # Get profile data
    profile_result = supabase.get_user_profile(user_id)
    profile_data = profile_result.get('data', {}) if profile_result.get('success') else {}
    
    templates = TEMPLATE_CATALOG.get(quotation_type)
    if templates is None:
        abort(404)

    return render_template('select_template.html', templates=templates, quotation_type=quotation_type, profile_data=profile_data, subscription=subscription)

@dashboard_bp.route('/api/templates')
@login_required
def get_templates_api():
    """API endpoint to get all templates for SPA"""
    all_templates = TEMPLATE_CATALOG['quick'] + TEMPLATE_CATALOG['detailed']

    return jsonify({'templates': all_templates})


@dashboard_bp.route('/quotation/template-preview/<template_file>')
@login_required
def quotation_template_preview(template_file):
    template_entry = ALL_TEMPLATES.get(template_file)
    if not template_entry:
        abort(404)

    supabase = get_supabase_handler()
    profile_result = supabase.get_user_profile(current_user.id)
    profile_data = profile_result.get('data', {}) if profile_result.get('success') else {}

    region = session.get('user_region', 'UK')
    currency_code = REGION_TO_CURRENCY.get(region, 'GBP')
    currency_symbol = 'R$' if currency_code == 'BRL' else '£'

    sample_items = [
        {'name': 'Consultoria Estratégica', 'quantity': 1, 'value': 1800.0},
        {'name': 'Design de Interface', 'quantity': 2, 'value': 850.0},
        {'name': 'Implementação', 'quantity': 1, 'value': 1200.0},
    ]
    subtotal = sum(item['quantity'] * item['value'] for item in sample_items)
    discount = 250.0
    total_value = max(subtotal - discount, 0)

    quotation = {
        'id': f"PREVIEW-{template_file.replace('.html', '').upper()[:6]}",
        'user_id': str(current_user.id),
        'client_name': 'Cliente Exemplo',
        'phone': '(11) 99999-9999',
        'address': 'Rua Exemplo, 123 - São Paulo/SP',
        'email': 'cliente@exemplo.com',
        'service_description': 'Pacote completo de branding, identidade visual e desenvolvimento.',
        'items': sample_items,
        'discount': discount,
        'value': total_value,
        'currency': currency_code,
        'created_at': datetime.utcnow().isoformat(),
        'expiry_date': (datetime.utcnow() + timedelta(days=7)).date().isoformat(),
        'notes': 'Esta é uma prévia interativa automática para visualizar o layout do template.',
        'template': template_file,
    }

    profile_data = profile_data or {}
    profile_data.setdefault('company_name', 'Lumina Flow Studio')
    user_name = profile_data.get('full_name') or profile_data.get('company_name')
    if not user_name:
        email = getattr(current_user, 'email', 'lumina@flow.com')
        user_name = email.split('@')[0].replace('.', ' ').title()

    return render_template(
        template_file,
        quotation=quotation,
        profile_data=profile_data,
        user_name=user_name,
        currency_symbol=currency_symbol,
        preview_mode=True,
        generator_name=user_name,
    )

@dashboard_bp.route('/quotation/spa')
@login_required
def quotation_spa():
    """SPA page for quotation creation flow"""
    user_id = current_user.id
    supabase = get_supabase_handler()

    profile_result = supabase.get_user_profile(user_id)
    profile_data = profile_result.get('data', {}) if profile_result.get('success') else {}

    sub_result = supabase.get_user_subscription(user_id)
    subscription = {
        'plan': current_user.plan,
        'status': sub_result.get('subscription_status', 'inactive') if sub_result.get('success') else 'inactive'
    }

    return render_template('quotation_spa.html', profile_data=profile_data, subscription=subscription)

@dashboard_bp.route('/quotation/create/<quotation_type>')
@login_required
def create_quotation_form(quotation_type):
    user_id = current_user.id
    supabase = get_supabase_handler()
    
    # Get profile data
    profile_result = supabase.get_user_profile(user_id)
    profile_data = profile_result.get('data', {}) if profile_result.get('success') else {}
    
    # Get subscription data
    sub_result = supabase.get_user_subscription(user_id)
    subscription = {
        'plan': current_user.plan,
        'status': sub_result.get('subscription_status', 'inactive') if sub_result.get('success') else 'inactive'
    }
    
    template = request.args.get('template', 'quick_modern_v2.html')
    
    if quotation_type == 'quick':
        return render_template('create_quick_quotation.html', template=template, profile_data=profile_data, subscription=subscription)
    else:
        return render_template('create_detailed_quotation.html', template=template, profile_data=profile_data, subscription=subscription)

@dashboard_bp.route('/quotation/view/<quotation_id>')
@login_required
def quotation_detail(quotation_id):
    user_id = current_user.id
    supabase = get_supabase_handler()
    result = supabase.get_quotation_by_id(user_id, str(quotation_id))

    if result.get('success') and result.get('data'):
        quotation = result['data']
        
        # Get user profile data
        profile_result = supabase.get_user_profile(user_id)
        profile_data = profile_result.get('data', {}) if profile_result.get('success') else {}
        
        # Use user name or email as company name
        company_name = profile_data.get('full_name') or profile_data.get('company_name') or current_user.email.split('@')[0].capitalize()
        
        template = quotation.get('template', 'quotation_detail.html')

        currency_code = (quotation.get('currency') or ('BRL' if session.get('user_region', 'UK') == 'BR' else 'GBP'))
        if isinstance(currency_code, str):
            currency_code = currency_code.upper()

        currency_map = {
            'BRL': 'R$',
            'GBP': '£',
            'USD': '$',
            'EUR': '€'
        }
        currency_symbol = currency_map.get(currency_code, currency_code)

        return render_template(
            template,
            quotation=quotation,
            user_name=company_name,
            user_email=current_user.email,
            profile_data=profile_data,
            currency_symbol=currency_symbol,
            currency_code=currency_code
        )
    
    return redirect(url_for('dashboard.dashboard_view'))

@dashboard_bp.route('/profile')
@login_required
def profile():
    user_id = current_user.id
    supabase = get_supabase_handler()
    
    sub_result = supabase.get_user_subscription(user_id)
    subscription = {
        'plan': current_user.plan,
        'status': sub_result.get('subscription_status', 'inactive') if sub_result.get('success') else 'inactive'
    }
    
    # Check if profile is complete
    profile_result = supabase.get_user_profile(user_id)
    profile_data = profile_result.get('data', {}) if profile_result.get('success') else {}
    profile_complete = bool(profile_data.get('profile_photo_url') and profile_data.get('whatsapp'))
    
    subscription.update({
        'stripe_customer_id': sub_result.get('stripe_customer_id') if sub_result.get('success') else None,
        'stripe_subscription_id': sub_result.get('stripe_subscription_id') if sub_result.get('success') else None,
        'next_billing': sub_result.get('next_billing_date') if sub_result.get('success') else None
    })
    
    return render_template(
        'profile.html',
        subscription=subscription,
        user_email=current_user.email,
        profile_complete=profile_complete,
        profile_data=profile_data,
        pricing=PRICING,
        user_region=session.get('user_region', 'BR')
    )

@dashboard_bp.route('/history')
@login_required
def history():
    user_id = current_user.id
    supabase = get_supabase_handler()
    quotations = get_user_quotations(user_id)
    
    # Get subscription info
    sub_result = supabase.get_user_subscription(user_id)
    subscription = {
        'plan': current_user.plan,
        'status': sub_result.get('subscription_status', 'inactive') if sub_result.get('success') else 'inactive'
    }
    
    # Get profile data
    profile_result = supabase.get_user_profile(user_id)
    profile_data = profile_result.get('data', {}) if profile_result.get('success') else {}
    
    return render_template(
        'history.html',
        quotations=quotations,
        subscription=subscription,
        profile_data=profile_data,
        can_delete_quotations=can_delete_quotation(current_user.plan)
    )

@dashboard_bp.route('/quotation/edit/<quotation_id>', methods=['POST'])
@login_required
def edit_quotation(quotation_id):
    user_id = current_user.id
    supabase = get_supabase_handler()
    
    data = request.get_json()
    result = supabase.update_quotation(
        user_id=user_id,
        quotation_id=str(quotation_id),
        client_name=data.get('client_name'),
        service_description=data.get('service_description'),
        value=float(data.get('value', 0)),
        expiry_date=data.get('expiry_date')
    )
    
    if result.get('success'):
        return jsonify({'success': True, 'quotation': result.get('data')})
    else:
        return jsonify({'success': False, 'error': result.get('error', 'Failed to update quotation')}), 400

@dashboard_bp.route('/quotation/delete/<quotation_id>', methods=['DELETE'])
@login_required
def delete_quotation(quotation_id):
    user_id = current_user.id
    supabase = get_supabase_handler()
    plan = (current_user.plan or 'free').lower()

    if not can_delete_quotation(plan):
        logger.warning(
            '[delete_quotation] User without delete permission attempted action',
            extra={'user_id': user_id, 'plan': plan, 'quotation_id': quotation_id}
        )
        return jsonify({'success': False, 'error': 'Somente planos Pro ou Enterprise podem excluir or�amentos.'}, 403)

    result = supabase.delete_quotation(user_id, str(quotation_id))
    
    if result.get('success'):
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': result.get('error', 'Failed to delete quotation')}), 400

@dashboard_bp.route('/quotation/<quotation_id>/status', methods=['POST'])
@login_required
def update_quotation_status(quotation_id):
    user_id = current_user.id
    supabase = get_supabase_handler()
    data = request.get_json()
    status = data.get('status')
    
    if status not in ['pending', 'accepted', 'rejected', 'expired']:
        return jsonify({'success': False, 'error': 'Invalid status'}), 400
    
    result = supabase.update_quotation_status(user_id, str(quotation_id), status)
    
    if result.get('success'):
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': result.get('error', 'Failed to update status')}), 400

@dashboard_bp.route('/quotation/<quotation_id>/reactivate', methods=['POST'])
@login_required
def reactivate_quotation(quotation_id):
    user_id = current_user.id
    supabase = get_supabase_handler()
    data = request.get_json()
    new_expiry_date = data.get('expiry_date')
    
    if not new_expiry_date:
        return jsonify({'success': False, 'error': 'Expiry date is required'}), 400
    
    result = supabase.update_quotation_expiry(user_id, str(quotation_id), new_expiry_date)
    
    if result.get('success'):
        # Also update status to pending
        supabase.update_quotation_status(user_id, str(quotation_id), 'pending')
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': result.get('error', 'Failed to reactivate quotation')}), 400

@dashboard_bp.route('/quotation/<quotation_id>/edit', methods=['POST'])
@login_required
def edit_quotation_basic(quotation_id):
    user_id = current_user.id
    supabase = get_supabase_handler()
    data = request.get_json()
    
    client_name = data.get('client_name')
    service_description = data.get('service_description')
    value = data.get('value')
    expiry_date = data.get('expiry_date')
    notes = data.get('notes')
    items = data.get('items')
    
    update_data = {}
    if client_name:
        update_data['client_name'] = client_name
    if service_description:
        update_data['service_description'] = service_description
    if value:
        update_data['value'] = float(value)
    if expiry_date:
        update_data['expiry_date'] = expiry_date
    if notes is not None:
        update_data['notes'] = notes
    if items is not None:
        update_data['items'] = items
    
    if not update_data:
        return jsonify({'success': False, 'error': 'No data to update'}), 400
    
    result = supabase.update_quotation(user_id, str(quotation_id), update_data)
    
    if result.get('success'):
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': result.get('error', 'Failed to update quotation')}), 400

@dashboard_bp.route('/quotation/update-currency', methods=['POST'])
@login_required
def update_quotation_currency():
    """Update currency of all user's quotations based on current region"""
    user_id = current_user.id
    payload = request.get_json(silent=True) or {}
    _, currency = resolve_region_and_currency(payload)
    
    supabase = get_supabase_handler()
    result = supabase.update_user_quotation_currency(user_id, currency)
    
    if result.get('success'):
        return jsonify({'success': True, 'currency': currency})
    else:
        return jsonify({'success': False, 'error': result.get('error', 'Failed to update currency')}), 400

@dashboard_bp.route('/api/quotations/quick', methods=['POST'])
@login_required
def create_quick_quotation():
    user_id = current_user.id
    data = request.get_json()
    
    supabase = get_supabase_handler()
    plan = current_user.plan
    
    if not can_create_quotation(user_id, plan):
        return jsonify({'success': False, 'error': 'Free plan limit reached. Upgrade to Pro.'}), 403
    
    _, currency = resolve_region_and_currency(data)
    
    result = supabase.create_quotation(
        user_id=user_id,
        client_name=data.get('client_name'),
        service_description=data.get('service_description'),
        value=float(data.get('value', 0)),
        currency=currency,
        expiry_date=data.get('expiry_date'),
        quotation_type='quick',
        phone=data.get('phone'),
        template=data.get('template', 'quick_modern_v2.html')
    )
    
    if result.get('success'):
        return jsonify({'success': True, 'quotation': result.get('data')})
    else:
        return jsonify({'success': False, 'error': result.get('error', 'Failed to create quotation')}), 400

@dashboard_bp.route('/api/quotations/detailed', methods=['POST'])
@login_required
def create_detailed_quotation():
    try:
        user_id = current_user.id
        data = request.get_json()

        supabase = get_supabase_handler()
        plan = current_user.plan

        if not can_create_quotation(user_id, plan):
            return jsonify({'success': False, 'error': 'Free plan limit reached. Upgrade to Pro.'}), 403

        _, currency = resolve_region_and_currency(data)

        # Calculate total from items
        items = data.get('items', [])
        total = sum(float(item['quantity']) * float(item['value']) for item in items)
        discount = float(data.get('discount', 0))
        final_value = total - discount

        result = supabase.create_quotation(
            user_id=user_id,
            client_name=data.get('client_name'),
            service_description='Orçamento detalhado com ' + str(len(items)) + ' itens',
            value=final_value,
            currency=currency,
            expiry_date=data.get('expiry_date'),
            quotation_type='detailed',
            phone=data.get('phone'),
            address=data.get('address'),
            items=items,
            discount=discount,
            notes=data.get('notes'),
            template=data.get('template', 'detailed_professional.html')
        )

        if result.get('success'):
            return jsonify({'success': True, 'quotation': result.get('data')})
        else:
            return jsonify({'success': False, 'error': result.get('error', 'Failed to create quotation')}), 400
    except Exception as e:
        logger.exception('Error creating detailed quotation', extra={'user_id': getattr(current_user, 'id', None)})
        return jsonify({'success': False, 'error': str(e)}), 500

@dashboard_bp.route('/api/quotations', methods=['POST'])
@login_required
def create_quotation():
    user_id = current_user.id
    data = request.get_json()
    
    supabase = get_supabase_handler()
    plan = current_user.plan
    
    if not can_create_quotation(user_id, plan):
        return jsonify({'success': False, 'error': 'Free plan limit reached. Upgrade to Pro.'}), 403
    
    _, currency = resolve_region_and_currency(data)
    
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
    user_id = current_user.id
    data = request.get_json()
    
    supabase = get_supabase_handler()
    
    profile_data = {}

    # Save WhatsApp to the database
    if data.get('whatsapp'):
        profile_data['whatsapp'] = data.get('whatsapp')
        logger.info('[Dashboard API] Updating WhatsApp', extra={'user_id': user_id})

    # Save Full Name to the database
    if data.get('full_name'):
        profile_data['full_name'] = data.get('full_name')
        logger.info('[Dashboard API] Updating full name', extra={'user_id': user_id})

    # Handle profile photo upload to Supabase Storage
    profile_photo_url = None
    # Check if base64 image data is provided in the request
    photo_key = 'profile_photo' if 'profile_photo' in data else 'profile_photo_url_data'
    if data.get(photo_key):
        base64_image_string = data[photo_key]
        try:
            # Extract base64 part (remove data URL prefix if present)
            if ',' in base64_image_string:
                header, base64_data = base64_image_string.split(',', 1)
            else:
                base64_data = base64_image_string

            # Decode base64 string to bytes
            file_content = base64.b64decode(base64_data)

            # Generate a unique filename. Determine file extension (defaulting to jpg).
            # A more robust solution might parse the MIME type from the header.
            file_extension = "jpg"
            filename = f"{uuid.uuid4()}.{file_extension}"

            logger.info('[Dashboard API] Uploading profile image', extra={'user_id': user_id, 'filename': filename})

            # Upload to Supabase Storage using the handler's method
            uploaded_url = supabase.upload_file_to_storage(file_content, filename, bucket_name='avatars')

            if uploaded_url:
                profile_photo_url = uploaded_url
                profile_data['profile_photo_url'] = profile_photo_url
                logger.info('[Dashboard API] Profile image uploaded', extra={'user_id': user_id})
            else:
                logger.error('[Dashboard API] Failed to upload profile image', extra={'user_id': user_id})

        except Exception as e:
            logger.exception('[Dashboard API] Error processing profile photo upload', extra={'user_id': user_id})
            # Optionally return an error
            # return jsonify({'success': False, 'error': 'Error processing profile photo'}), 500

    # Update the profile in the database if there's any data to update
    if profile_data:
        # update_user_profile expects kwargs like full_name, whatsapp, profile_photo_url
        result = supabase.update_user_profile(user_id, **profile_data)

        if result.get('success'):
            logger.info('[Dashboard API] Profile updated successfully', extra={'user_id': user_id})
            return jsonify({'success': True})
        else:
            logger.error('[Dashboard API] Failed to update profile in database', extra={'user_id': user_id, 'error': result.get('error')})
            return jsonify({'success': False, 'error': result.get('error', 'Failed to update profile')}), 400
    else:
        # No data to update
        logger.warning('[Dashboard API] No profile data provided for update', extra={'user_id': user_id})
        return jsonify({'success': False, 'error': 'No data to update'}), 400


@dashboard_bp.route('/api/subscription/cancel', methods=['POST'])
@login_required
def cancel_subscription():
    user_id = current_user.id
    supabase = get_supabase_handler()
    stripe_handler = get_stripe_handler()
    auth_handler = get_auth_handler()

    profile_result = supabase.get_user_profile(user_id)
    if not profile_result.get('success'):
        return jsonify({'success': False, 'error': 'Não foi possível localizar o perfil do usuário.'}), 400

    profile_data = profile_result.get('data') or {}
    subscription_id = profile_data.get('stripe_subscription_id')
    customer_id = profile_data.get('stripe_customer_id')

    if not subscription_id:
        return jsonify({'success': False, 'error': 'Nenhuma assinatura ativa foi encontrada.'}), 400

    cancel_result = stripe_handler.cancel_subscription(subscription_id)
    if not cancel_result.get('success'):
        return jsonify({'success': False, 'error': cancel_result.get('error', 'Falha ao cancelar a assinatura no Stripe.')}), 500

    supabase.update_user_subscription(
        user_id=user_id,
        plan='free',
        subscription_status='canceled',
        stripe_customer_id=customer_id,
        stripe_subscription_id=None,
        next_billing_date=None
    )

    auth_handler.update_user_plan(user_id, 'free')
    current_user.plan = 'free'

    return jsonify({'success': True})


