from flask import Blueprint, request, jsonify, session
from ..supabase_handler import get_supabase_handler
from ..stripe_handler import get_stripe_handler
from .dashboard import login_required

payments_bp = Blueprint('payments', __name__)

@payments_bp.route('/create-checkout-session', methods=['POST'])
@login_required
def create_checkout_session():
    data = request.get_json()
    price_id_key = data.get('priceIdKey')  # e.g., 'br_monthly'
    
    user_id = session['user_id']
    user_email = session['user_email']

    supabase = get_supabase_handler()
    profile = supabase.get_user_subscription(user_id)
    customer_id = profile.get('stripe_customer_id') if profile.get('success') else None

    stripe_handler = get_stripe_handler()
    price_id = stripe_handler.get_price_id_by_key(price_id_key)

    if not price_id:
        return jsonify({'success': False, 'error': 'Invalid price configuration'}), 400

    session_result = stripe_handler.create_checkout_session(
        price_id=price_id,
        user_id=user_id,
        user_email=user_email,
        customer_id=customer_id
    )

    if session_result.get('success'):
        return jsonify({'success': True, 'checkout_url': session_result['checkout_url']})
    else:
        return jsonify({'success': False, 'error': session_result.get('error', 'Failed to create checkout session')}), 500

@payments_bp.route('/webhook/stripe', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    
    stripe_handler = get_stripe_handler()
    event_result = stripe_handler.handle_webhook(payload, sig_header)
    
    if not event_result.get('success'):
        return jsonify({'error': event_result.get('error')}), 400
    
    event = event_result['event']
    
    # Lógica de manipulação de eventos será adicionada aqui
    
    return jsonify({'status': 'success'}), 200