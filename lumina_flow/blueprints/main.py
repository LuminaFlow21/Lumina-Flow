import json
import os
import logging
from flask import Blueprint, render_template, session, jsonify, request, redirect, url_for, flash, current_app
from flask_login import login_user
from ..auth_handler import get_auth_handler, User

main_bp = Blueprint('main', __name__)
logger = logging.getLogger(__name__)

SALES_CONTACT_URL = os.getenv('SALES_CONTACT_URL', os.getenv('LINKS_WHATSAPP_URL', 'https://wa.me/5511999999999'))

PRICING = {
    'free': {
        'br_monthly': 'R$ 0',
        'uk_monthly': '£0',
        'br_annual': 'R$ 0',
        'uk_annual': '£0'
    },
    'basic': {
        'br_monthly': 'R$ 49',
        'uk_monthly': '£19',
        'br_annual': 'R$ 89',
        'uk_annual': '£29',
        'price_id_br_monthly': os.getenv('STRIPE_PRICE_ID_BR_MONTHLY'),
        'price_id_uk_monthly': os.getenv('STRIPE_PRICE_ID_UK_MONTHLY'),
        'price_id_br_annual': os.getenv('STRIPE_PRICE_ID_BR_YEARLY'),
        'price_id_uk_annual': os.getenv('STRIPE_PRICE_ID_UK_YEARLY'),
    },
    'pro': {
        'label': {
            'pt': 'Pro Corporativo',
            'en': 'Pro Enterprise'
        },
        'description': {
            'pt': 'Implantações customizadas para equipes com alto volume.',
            'en': 'Custom deployments for high-volume teams.'
        },
        'cta_label': {
            'pt': 'Fale conosco',
            'en': 'Talk to us'
        },
        'cta_url': SALES_CONTACT_URL
    }
}

@main_bp.route('/')
def index():
    if 'user_region' not in session:
        session['user_region'] = 'UK'
    return render_template('index.html', pricing=PRICING)


@main_bp.route('/links')
def links_page():
    links = {
        'home': current_app.config.get('LINKS_HOME_URL', '/'),
        'whatsapp': current_app.config.get('LINKS_WHATSAPP_URL', 'https://wa.me/5511999999999'),
        'instagram': current_app.config.get('LINKS_INSTAGRAM_URL', 'https://instagram.com/luminaflow')
    }
    return render_template('links.html', links=links)

@main_bp.route('/translations.json')
def translations():
    try:
        # Get absolute path to translations.json in project root
        current_dir = os.path.dirname(os.path.abspath(__file__))
        translations_path = os.path.normpath(os.path.join(current_dir, '..', '..', 'translations.json'))
        logger.debug('Loading translations', extra={'path': translations_path})

        if not os.path.exists(translations_path):
            logger.error('Translations file not found', extra={'path': translations_path})
            return jsonify({'error': 'Translations file not found'}), 500

        with open(translations_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            logger.info('Translations loaded', extra={'languages': len(data)})
            return jsonify(data)
    except Exception as e:
        logger.exception('Failed to load translations')
        return jsonify({'error': str(e)}), 500

@main_bp.route('/set-region', methods=['POST'])
def set_region():
    from flask_login import current_user
    from ..supabase_handler import get_supabase_handler
    
    data = request.get_json()
    region = data.get('region', 'UK')
    if region in ['BR', 'UK']:
        session['user_region'] = region
        
        # Update currency of existing quotations if user is logged in
        if current_user.is_authenticated:
            try:
                supabase = get_supabase_handler()
                currency = 'BRL' if region == 'BR' else 'GBP'
                supabase.update_user_quotation_currency(current_user.id, currency)
            except Exception as e:
                logger.exception('[set-region] Error updating quotation currency', extra={'user_id': current_user.id})
        
        return jsonify({'success': True, 'region': region})
    return jsonify({'success': False, 'error': 'Invalid region'}), 400

@main_bp.route('/verify/<token>')
def verify_email(token):
    """Verify email with token"""
    try:
        auth_handler = get_auth_handler()
        result = auth_handler.verify_email(token)
        
        if result.get('success'):
            user_data = result['user']
            user = User(user_data)
            login_user(user)
            
            # Set session variables
            session['user_id'] = str(user_data['id'])
            session['user_email'] = user_data['email']
            session['user_plan'] = user_data.get('plan', 'free')
            
            # Set region based on email
            if '.br' in user_data['email'].lower():
                session['user_region'] = 'BR'
            else:
                session['user_region'] = 'UK'
            
            flash('Email verified successfully! Welcome to Lumina Flow.')
            return redirect(url_for('dashboard.dashboard_view'))
        else:
            flash(result.get('error', 'Invalid or expired verification token'))
            return redirect(url_for('auth.login_page'))
            
    except Exception as e:
        flash(f'Error verifying email: {str(e)}')
        return redirect(url_for('auth.login_page'))

@main_bp.app_errorhandler(404)
def not_found(error):
    return render_template('index.html', pricing=PRICING), 404

@main_bp.app_errorhandler(500)
def internal_error(error):
    return render_template('index.html', pricing=PRICING), 500