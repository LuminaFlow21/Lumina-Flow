"""
Admin Blueprint - Billing Dashboard
Read-only admin panel for monitoring payments, subscriptions, webhooks and errors
"""

import logging
from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from ..auth_handler import is_admin_user
from ..services.billing_logs import (
    get_admin_billing_summary,
    get_admin_customer_billing_details,
    search_admin_billing_customers,
    format_datetime_br,
    format_date_br,
    format_money,
    get_status_label,
    get_status_badge_class,
    get_plan_badge_class,
    get_subscription_visual_state,
    get_billing_timeline,
    get_last_stripe_event,
    get_webhooks_with_error_count
)
from ..supabase_handler import get_supabase_handler

logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def admin_required(f):
    """Decorator to require admin access"""
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'error': 'Authentication required'}), 401
        if not is_admin_user(current_user.email):
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper


@admin_bp.route('/billing')
@login_required
@admin_required
def billing_dashboard():
    """Admin billing dashboard with summary cards, search, filters and customer table"""
    try:
        # Get query params
        q = request.args.get('q', '').strip()
        status_filter = request.args.get('status', '').strip()
        plan_filter = request.args.get('plan', '').strip()
        has_failed_payment = request.args.get('has_failed_payment', '').strip() == 'true'
        canceling = request.args.get('canceling', '').strip() == 'true'
        
        # Build filters
        filters = {}
        if status_filter:
            filters['status'] = status_filter
        if plan_filter:
            filters['plan'] = plan_filter
        if has_failed_payment:
            filters['has_failed_payment'] = True
        if canceling:
            filters['canceling'] = True
        
        # Get billing summary (without filters for overview)
        summary_result = get_admin_billing_summary()
        
        # Get customers with search and filters
        customers_result = search_admin_billing_customers(
            q=q if q else None,
            filters=filters if filters else None,
            limit=50
        )
        
        customers = customers_result.get('data', []) if customers_result.get('success') else []
        
        # Get webhooks with error count
        webhooks_error_count = get_webhooks_with_error_count()
        
        # Prepare customer data for display
        customers_display = []
        for customer in customers:
            profile = customer.get('profile', {})
            user = customer.get('user', {})
            last_payment = customer.get('last_payment')
            billing_state = customer.get('billing_state', {})
            
            # Get visual state for subscription
            visual_state = get_subscription_visual_state(billing_state)
            
            customers_display.append({
                'user_id': profile.get('user_id'),
                'name': profile.get('full_name') or user.get('email', '-') if user else '-',
                'email': user.get('email', '-') if user else '-',
                'plan': billing_state.get('plan', '-'),
                'subscription_status': billing_state.get('subscription_status', '-'),
                'status_label': visual_state.get('label'),
                'status_badge_class': visual_state.get('color_class'),
                'status_icon': visual_state.get('icon'),
                'status_description': visual_state.get('description'),
                'next_billing_date': billing_state.get('next_billing_date'),
                'cancel_at': billing_state.get('cancel_at'),
                'canceled_at': billing_state.get('canceled_at'),
                'is_canceling': billing_state.get('is_canceling', False),
                'access_until': billing_state.get('access_until'),
                'stripe_customer_id': billing_state.get('stripe_customer_id'),
                'stripe_subscription_id': billing_state.get('stripe_subscription_id'),
                'last_payment_date': last_payment.get('created_at') if last_payment else None,
                'last_payment_amount': last_payment.get('amount') if last_payment else None,
                'last_payment_currency': last_payment.get('currency') if last_payment else None,
                'last_payment_status': last_payment.get('status') if last_payment else None,
                'created_at': profile.get('created_at'),
                'updated_at': profile.get('updated_at')
            })
        
        return render_template(
            'admin_billing.html',
            summary=summary_result.get('data') if summary_result.get('success') else None,
            customers=customers_display,
            q=q,
            filters={
                'status': status_filter,
                'plan': plan_filter,
                'has_failed_payment': has_failed_payment,
                'canceling': canceling
            },
            webhooks_error_count=webhooks_error_count
        )
    except Exception as e:
        logger.exception('[ADMIN] Error loading billing dashboard')
        return render_template('admin_billing.html', summary=None, customers=[], error=str(e))


@admin_bp.route('/billing/customer/<user_id>')
@login_required
@admin_required
def customer_billing_details(user_id):
    """Admin customer billing details page with tabs"""
    try:
        details_result = get_admin_customer_billing_details(user_id)
        
        if not details_result.get('success'):
            return render_template('admin_billing_customer.html', error=details_result.get('error'))
        
        data = details_result.get('data', {})
        
        # Get billing timeline
        timeline = get_billing_timeline(user_id, limit=50)
        
        # Get visual state for subscription
        billing_state = data.get('billing_state', {})
        visual_state = get_subscription_visual_state(billing_state)
        
        # Get last Stripe event
        last_stripe_event = get_last_stripe_event(user_id)
        
        return render_template(
            'admin_billing_customer.html',
            data=data,
            user_id=user_id,
            timeline=timeline,
            visual_state=visual_state,
            last_stripe_event=last_stripe_event
        )
    except Exception as e:
        logger.exception('[ADMIN] Error loading customer billing details', extra={'user_id': user_id})
        return render_template('admin_billing_customer.html', error=str(e))
