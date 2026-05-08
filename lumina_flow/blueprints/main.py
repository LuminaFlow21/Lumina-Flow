import json
import os
from flask import Blueprint, render_template, session, jsonify, request

main_bp = Blueprint('main', __name__)

PRICING = {
    'free': {'br_monthly': 'R$ 0', 'uk_monthly': '£0', 'br_annual': 'R$ 0', 'uk_annual': '£0'},
    'pro': {
        'br_monthly': 'R$ 49', 'uk_monthly': '£19', 'br_annual': 'R$ 89', 'uk_annual': '£29',
        'price_id_br_monthly': os.getenv('STRIPE_PRICE_ID_BR_MONTHLY'),
        'price_id_uk_monthly': os.getenv('STRIPE_PRICE_ID_UK_MONTHLY'),
        'price_id_br_annual': os.getenv('STRIPE_PRICE_ID_BR_YEARLY'),
        'price_id_uk_annual': os.getenv('STRIPE_PRICE_ID_UK_YEARLY'),
    },
    'enterprise': {
        'br_monthly': 'R$ 159', 'uk_monthly': '£69', 'br_annual': 'R$ 199', 'uk_annual': '£99',
        'price_id_br_monthly': os.getenv('STRIPE_PRICE_ID_BR_ENT_MONTHLY'),
        'price_id_uk_monthly': os.getenv('STRIPE_PRICE_ID_UK_ENT_MONTHLY'),
        'price_id_br_annual': os.getenv('STRIPE_PRICE_ID_BR_ENT_YEARLY'),
        'price_id_uk_annual': os.getenv('STRIPE_PRICE_ID_UK_ENT_YEARLY'),
    },
}

@main_bp.route('/')
def index():
    if 'user_region' not in session:
        session['user_region'] = 'UK'
    return render_template('index.html', pricing=PRICING)

@main_bp.route('/translations.json')
def translations():
    translations_path = os.path.join(os.path.dirname(__file__), '..', 'translations.json')
    with open(translations_path, 'r', encoding='utf-8') as f:
        return jsonify(json.load(f))

@main_bp.route('/set-region', methods=['POST'])
def set_region():
    data = request.get_json()
    region = data.get('region', 'UK')
    if region in ['BR', 'UK']:
        session['user_region'] = region
        return jsonify({'success': True, 'region': region})
    return jsonify({'success': False, 'error': 'Invalid region'}), 400

@main_bp.app_errorhandler(404)
def not_found(error):
    return render_template('index.html', pricing=PRICING), 404

@main_bp.app_errorhandler(500)
def internal_error(error):
    return render_template('index.html', pricing=PRICING), 500