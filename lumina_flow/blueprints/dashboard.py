from flask import Blueprint, render_template, session, redirect, url_for, request, jsonify, abort
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from collections import Counter, defaultdict
import json
from ..supabase_handler import get_supabase_handler
from ..stripe_handler import get_stripe_handler
from ..auth_handler import get_auth_handler
from ..services.billing_logs import get_user_id_from_checkout_webhook
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
CURRENCY_SYMBOLS = {
    'BRL': 'R$',
    'GBP': '£',
    'USD': '$',
    'EUR': '€'
}
VALUE_BUCKETS = [
    (0, 300),
    (300, 800),
    (800, 2000),
    (2000, 5000),
    (5000, None)
]


def format_decimal_value(value: Decimal, region: str = 'UK', places: int = 2) -> str:
    quantize_pattern = '0' if places == 0 else '0.' + ('0' * places)
    try:
        quantized = value.quantize(Decimal(quantize_pattern), rounding=ROUND_HALF_UP)
    except (InvalidOperation, AttributeError):
        quantized = Decimal('0').quantize(Decimal(quantize_pattern))

    formatted = f"{quantized:,.{places}f}"
    if region == 'BR':
        formatted = formatted.replace(',', 'TEMP').replace('.', ',').replace('TEMP', '.')
    return formatted


def format_integer(value: int, region: str = 'UK') -> str:
    formatted = f"{value:,}"
    if region == 'BR':
        formatted = formatted.replace(',', '.')
    return formatted


def parse_datetime(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    text = text.replace('Z', '+00:00')
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    fallback_formats = [
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%dT%H:%M',
        '%Y-%m-%d %H:%M'
    ]
    for fmt in fallback_formats:
        try:
            return datetime.strptime(text[:len(fmt)], fmt)
        except ValueError:
            continue
    try:
        timestamp = float(text)
        return datetime.fromtimestamp(timestamp)
    except (ValueError, TypeError):
        return None


def bucket_label(lower: int | float, upper: int | float | None, symbol: str, region: str) -> str:
    lower_text = format_decimal_value(Decimal(lower), region, 0)
    if upper is None:
        return f"{symbol} {lower_text}+"
    upper_text = format_decimal_value(Decimal(upper), region, 0)
    return f"{symbol} {lower_text} – {upper_text}"


def compute_trend(current_value: float | int, previous_value: float | int, suffix: str = '', decimals: int = 0) -> dict:
    diff = current_value - previous_value
    direction = 'up' if diff > 0 else 'down' if diff < 0 else 'flat'
    if decimals == 0:
        diff_display = f"{diff:+.0f}{suffix}"
    else:
        diff_display = f"{diff:+.{decimals}f}{suffix}"
    return {
        'current': current_value,
        'previous': previous_value,
        'diff': diff,
        'diff_display': diff_display,
        'direction': direction
    }


def average_days(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 1)


def calculate_results_metrics(quotations: list, region: str = 'UK', period_key: str = '30') -> dict:
    today = datetime.utcnow().date()
    period_alias = str(period_key or '30').lower()
    period_map = {'3': 3, '7': 7, '30': 30, 'all': None}
    period_days = period_map.get(period_alias, 30)

    created_dates = []
    for quotation in quotations:
        created_dt = parse_datetime(quotation.get('created_at'))
        if created_dt:
            created_dates.append(created_dt.date())

    if period_days is None:
        if created_dates:
            current_start = min(created_dates)
        else:
            current_start = today - timedelta(days=29)
        period_days = max((today - current_start).days + 1, 1)
    else:
        period_days = max(int(period_days), 1)
        current_start = today - timedelta(days=period_days - 1)

    default_currency = REGION_TO_CURRENCY.get(region, 'GBP')
    currency_symbol = CURRENCY_SYMBOLS.get(default_currency, default_currency)

    counts = {'total': 0, 'accepted': 0, 'rejected': 0, 'pending': 0}
    financial_totals = {
        'total_value': Decimal('0'),
        'closed_value': Decimal('0'),
        'lost_value': Decimal('0')
    }
    accepted_amounts: list[Decimal] = []
    ticket_by_date: dict[str, list[Decimal]] = defaultdict(list)
    closed_by_date: dict[str, Decimal] = defaultdict(lambda: Decimal('0'))
    bucket_stats = {(lower, upper): {'total': 0, 'accepted': 0} for lower, upper in VALUE_BUCKETS}
    template_stats = defaultdict(lambda: {'total': 0, 'accepted': 0})
    accepted_services = Counter()
    accepted_items = Counter()
    rejected_services = Counter()

    for quotation in quotations:
        created_dt = parse_datetime(quotation.get('created_at'))
        if not created_dt:
            continue
        created_date = created_dt.date()
        in_period = period_alias == 'all' or current_start <= created_date <= today
        if not in_period:
            continue

        status = (quotation.get('status') or 'pending').lower()
        if status not in {'accepted', 'rejected', 'pending', 'expired'}:
            status = 'pending'

        counts['total'] += 1
        if status in counts:
            counts[status] += 1

        raw_value = quotation.get('value') or quotation.get('total_value') or 0
        try:
            amount = Decimal(str(raw_value))
        except (InvalidOperation, TypeError, ValueError):
            amount = Decimal('0')

        currency_code = (quotation.get('currency') or '').upper() or default_currency
        decision_dt = parse_datetime(quotation.get('status_updated_at') or quotation.get('decision_date') or quotation.get('updated_at'))
        effective_date = decision_dt.date() if decision_dt else created_date

        if currency_code == default_currency:
            financial_totals['total_value'] += amount
            if status == 'accepted':
                financial_totals['closed_value'] += amount
                accepted_amounts.append(amount)
                ticket_by_date[effective_date.isoformat()].append(amount)
                closed_by_date[effective_date.isoformat()] += amount
            elif status == 'rejected':
                financial_totals['lost_value'] += amount

            try:
                numeric_amount = float(amount)
            except (TypeError, ValueError, InvalidOperation):
                numeric_amount = 0.0

            bucket_key = VALUE_BUCKETS[-1]
            for candidate in VALUE_BUCKETS:
                lower, upper = candidate
                if upper is None and numeric_amount >= lower:
                    bucket_key = candidate
                    break
                if upper is not None and lower <= numeric_amount < upper:
                    bucket_key = candidate
                    break
            bucket_stats[bucket_key]['total'] += 1
            if status == 'accepted':
                bucket_stats[bucket_key]['accepted'] += 1

        template_code = (quotation.get('template') or '').strip()
        if template_code:
            template_stats[template_code]['total'] += 1
            if status == 'accepted':
                template_stats[template_code]['accepted'] += 1

        if status == 'accepted':
            service_description = (quotation.get('service_description') or '').strip()
            items = quotation.get('items')

            if service_description:
                accepted_services[service_description] += 1

            if isinstance(items, list):
                for item in items:
                    name = (item or {}).get('name')
                    if not name:
                        continue
                    label = str(name).strip()
                    if not label:
                        continue
                    accepted_items[label] += 1
                    if not service_description:
                        accepted_services[label] += 1
            elif not service_description:
                fallback_service = (quotation.get('title') or '').strip()
                if fallback_service:
                    accepted_services[fallback_service] += 1

        if status == 'rejected':
            service_description = (quotation.get('service_description') or '').strip()
            items = quotation.get('items')

            if service_description:
                rejected_services[service_description] += 1

            if isinstance(items, list):
                for item in items:
                    name = (item or {}).get('name')
                    if not name:
                        continue
                    label = str(name).strip()
                    if not label:
                        continue
                    if not service_description:
                        rejected_services[label] += 1
            elif not service_description:
                fallback_service = (quotation.get('title') or '').strip()
                if fallback_service:
                    rejected_services[fallback_service] += 1

    total_count = counts['total']
    approval_rate = round((counts['accepted'] / total_count) * 100, 2) if total_count else 0.0
    rejection_rate = round((counts['rejected'] / total_count) * 100, 2) if total_count else 0.0

    average_ticket = Decimal('0')
    if accepted_amounts:
        average_ticket = sum(accepted_amounts, Decimal('0')) / len(accepted_amounts)

    counts_display = {key: format_integer(value, region) for key, value in counts.items()}
    financial_display = {
        'total_value': f"{currency_symbol} {format_decimal_value(financial_totals['total_value'], region)}",
        'closed_value': f"{currency_symbol} {format_decimal_value(financial_totals['closed_value'], region)}",
        'lost_value': f"{currency_symbol} {format_decimal_value(financial_totals['lost_value'], region)}",
        'average_ticket': f"{currency_symbol} {format_decimal_value(average_ticket, region)}"
    }

    def format_rate(value: float) -> str:
        text = f"{value:.1f}"
        if region == 'BR':
            text = text.replace('.', ',')
        return f"{text}%"

    conversion_chart = {'labels': [], 'values': []}
    for lower, upper in VALUE_BUCKETS:
        stats = bucket_stats[(lower, upper)]
        total_bucket = stats['total']
        rate = round((stats['accepted'] / total_bucket) * 100, 1) if total_bucket else 0.0
        conversion_chart['labels'].append(bucket_label(lower, upper, currency_symbol, region))
        conversion_chart['values'].append(rate)

    def build_series(series_dict, average: bool = False):
        labels = sorted(series_dict.keys())
        values = []
        for label in labels:
            data = series_dict[label]
            if average:
                if data:
                    total_values = sum(data, Decimal('0'))
                    avg = total_values / len(data)
                else:
                    avg = Decimal('0')
                values.append(float(avg))
            else:
                values.append(float(data))
        return {'labels': labels, 'values': values}

    ticket_chart = build_series(ticket_by_date, average=True)
    closed_chart = build_series(dict(closed_by_date))

    def build_counter(counter_obj: Counter, limit: int = 6) -> dict:
        items = counter_obj.most_common(limit)
        return {
            'labels': [label for label, _ in items],
            'values': [count for _, count in items]
        }

    accepted_services_chart = build_counter(accepted_services)
    accepted_items_chart = build_counter(accepted_items)
    rejected_services_chart = build_counter(rejected_services)

    template_chart_data = []
    for template_code, stats in template_stats.items():
        total_template = stats['total']
        if total_template == 0:
            continue
        rate = round((stats['accepted'] / total_template) * 100, 1)
        template_name = ALL_TEMPLATES.get(template_code, {}).get('name', template_code)
        template_chart_data.append({'label': template_name, 'value': rate})
    template_chart_data.sort(key=lambda entry: entry['value'], reverse=True)
    template_chart_data = template_chart_data[:6]

    charts = {
        'conversion_by_value': conversion_chart,
        'ticket_over_time': ticket_chart,
        'closed_value_over_time': closed_chart,
        'templates_conversion': {
            'labels': [item['label'] for item in template_chart_data],
            'values': [item['value'] for item in template_chart_data]
        },
        'accepted_services': accepted_services_chart,
        'accepted_items': accepted_items_chart,
        'rejected_services': rejected_services_chart
    }

    return {
        'period': {
            'key': period_alias,
            'start': current_start.isoformat(),
            'end': today.isoformat(),
            'days': period_days
        },
        'counts': counts,
        'counts_display': counts_display,
        'financial_display': financial_display,
        'rates': {
            'approval': approval_rate,
            'rejection': rejection_rate
        },
        'rates_display': {
            'approval': format_rate(approval_rate),
            'rejection': format_rate(rejection_rate)
        },
        'currency': {
            'code': default_currency,
            'symbol': currency_symbol
        },
        'charts': charts
    }

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


def _safe_float(value, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    try:
        text = str(value).strip()
    except Exception:
        return default
    if not text:
        return default
    try:
        normalized = text.replace(',', '.')
        return float(normalized)
    except (TypeError, ValueError):
        return default

def can_create_quotation(user_id: str, plan: str) -> bool:
    normalized_plan = (plan or 'free').lower()
    if normalized_plan in ('basic', 'pro', 'enterprise'):
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
    supabase = get_supabase_handler()

    # Get unified billing display state
    from ..services.billing_logs import get_billing_display_state
    billing_state = get_billing_display_state(user_id, supabase)
    
    subscription = {
        'plan': billing_state.get('plan'),
        'status': billing_state.get('subscription_status'),
        'next_billing': billing_state.get('next_billing_date')
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
        profile_data=profile_data,
        billing_state=billing_state
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
    
    # Get unified billing display state
    from ..services.billing_logs import get_billing_display_state, get_subscription_visual_state
    billing_state = get_billing_display_state(user_id, supabase)
    
    # Get visual state for subscription
    visual_state = get_subscription_visual_state(billing_state)
    
    # Check if profile is complete
    profile_result = supabase.get_user_profile(user_id)
    profile_data = profile_result.get('data', {}) if profile_result.get('success') else {}
    profile_complete = bool(profile_data.get('profile_photo_url') and profile_data.get('whatsapp'))
    
    return render_template(
        'profile.html',
        billing_state=billing_state,
        visual_state=visual_state,
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
        can_delete_quotations=can_delete_quotation(current_user.plan),
        active_view='history'
    )


@dashboard_bp.route('/history/results')
@login_required
def history_results():
    user_id = current_user.id
    supabase = get_supabase_handler()
    quotations = get_user_quotations(user_id)

    user_region = session.get('user_region', 'UK')
    period_key = request.args.get('period', '30')
    active_tab = request.args.get('tab', 'basic')
    if active_tab not in {'basic', 'advanced'}:
        active_tab = 'basic'

    metrics = calculate_results_metrics(quotations, region=user_region, period_key=period_key)

    sub_result = supabase.get_user_subscription(user_id)
    subscription = {
        'plan': current_user.plan,
        'status': sub_result.get('subscription_status', 'inactive') if sub_result.get('success') else 'inactive'
    }

    profile_result = supabase.get_user_profile(user_id)
    profile_data = profile_result.get('data', {}) if profile_result.get('success') else {}

    has_period_data = metrics['counts']['total'] > 0

    return render_template(
        'history_results.html',
        subscription=subscription,
        profile_data=profile_data,
        metrics=metrics,
        quotations_count=len(quotations),
        has_quotations=len(quotations) > 0,
        has_period_data=has_period_data,
        active_view='results',
        active_tab=active_tab,
        period_key=metrics['period']['key'],
        user_region=user_region
    )

@dashboard_bp.route('/quotation/edit/<quotation_id>', methods=['POST'])
@login_required
def edit_quotation(quotation_id):
    user_id = current_user.id
    supabase = get_supabase_handler()
    
    data = request.get_json()
    raw_value = data.get('value')
    raw_discount = data.get('discount')
    raw_items = data.get('items')

    items_payload = None
    items_total = 0.0
    if isinstance(raw_items, list):
        items_payload = []
        for item in raw_items:
            name = (item or {}).get('name') or ''
            quantity = _safe_float((item or {}).get('quantity'), 0.0)
            value = _safe_float((item or {}).get('value'), 0.0)

            if not name.strip() and quantity == 0 and value == 0:
                continue

            normalized = {
                'name': name.strip(),
                'quantity': quantity,
                'value': value,
            }
            items_payload.append(normalized)
            items_total += quantity * value

    discount_value = _safe_float(raw_discount, 0.0) if raw_discount is not None else None
    recalculated_value = None
    if items_payload is not None:
        effective_discount = discount_value if discount_value is not None else 0.0
        recalculated_value = max(items_total - effective_discount, 0.0)

    update_fields = {
        'client_name': data.get('client_name'),
        'phone': data.get('phone'),
        'address': data.get('address'),
        'service_description': data.get('service_description'),
        'value': _safe_float(raw_value, 0.0) if raw_value is not None else None,
        'expiry_date': data.get('expiry_date'),
        'notes': data.get('notes'),
        'discount': discount_value,
        'items': items_payload,
    }

    if recalculated_value is not None:
        update_fields['value'] = recalculated_value

    update_data = {k: v for k, v in update_fields.items() if v is not None}

    result = supabase.update_quotation(
        user_id=user_id,
        quotation_id=str(quotation_id),
        update_data=update_data
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
        return jsonify({'success': False, 'error': 'Free plan limit reached. Upgrade to Basic.'}), 403
    
    _, currency = resolve_region_and_currency(data)
    
    result = supabase.create_quotation(
        user_id=user_id,
        client_name=data.get('client_name'),
        service_description=data.get('service_description'),
        value=_safe_float(data.get('value'), 0.0),
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
            return jsonify({'success': False, 'error': 'Free plan limit reached. Upgrade to Basic.'}), 403

        _, currency = resolve_region_and_currency(data)

        # Calculate total from items
        items = data.get('items', [])
        total = sum(
            _safe_float(item.get('quantity'), 0.0) * _safe_float(item.get('value'), 0.0)
            for item in items
        )
        discount = _safe_float(data.get('discount'), 0.0)
        final_value = max(total - discount, 0.0)

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
        return jsonify({'success': False, 'error': 'Free plan limit reached. Upgrade to Basic.'}), 403
    
    _, currency = resolve_region_and_currency(data)
    
    result = supabase.create_quotation(
        user_id=user_id,
        client_name=data.get('client_name'),
        service_description=data.get('service_description'),
        value=_safe_float(data.get('value'), 0.0),
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

    # Fallback: recover subscription_id from checkout webhook logs if missing
    if not subscription_id and customer_id:
        checkout_lookup = get_user_id_from_checkout_webhook(stripe_customer_id=customer_id)
        if checkout_lookup.get('success'):
            recovered_subscription_id = checkout_lookup.get('subscription_id')
            recovered_customer_id = checkout_lookup.get('customer_id') or customer_id
            if recovered_subscription_id:
                subscription_id = recovered_subscription_id
                customer_id = recovered_customer_id
                plan_value = profile_data.get('plan') or current_user.plan or 'basic'
                status_value = profile_data.get('subscription_status') or 'active'
                next_billing_value = profile_data.get('next_billing_date')
                try:
                    supabase.update_user_subscription(
                        user_id=user_id,
                        plan=plan_value,
                        subscription_status=status_value,
                        stripe_customer_id=customer_id,
                        stripe_subscription_id=subscription_id,
                        next_billing_date=next_billing_value
                    )
                    profile_data['stripe_subscription_id'] = subscription_id
                    profile_data['stripe_customer_id'] = customer_id
                except Exception:
                    logger.exception(
                        'Failed to persist recovered Stripe identifiers before cancellation',
                        extra={'user_id': user_id}
                    )

    if not subscription_id:
        return jsonify({'success': False, 'error': 'Nenhuma assinatura ativa foi encontrada.'}), 400

    # Get subscription status from Stripe to check if it can be canceled
    try:
        subscription = stripe_handler.stripe.Subscription.retrieve(subscription_id)
        subscription_status = subscription.get('status', '')
        
        # Cannot cancel incomplete, incomplete_expired, or canceled subscriptions
        if subscription_status in ['incomplete', 'incomplete_expired', 'canceled']:
            return jsonify({
                'success': False,
                'error': f'Não é possível cancelar uma assinatura com status "{subscription_status}". A assinatura já está finalizada ou não foi completada.'
            }), 400
    except Exception as e:
        logger.warning('Failed to retrieve subscription status from Stripe', extra={'subscription_id': subscription_id, 'error': str(e)})
        # Continue with attempt to modify subscription anyway

    # Use modify_subscription with cancel_at_period_end=True to cancel at end of period
    modify_result = stripe_handler.modify_subscription(subscription_id, cancel_at_period_end=True)
    if not modify_result.get('success'):
        return jsonify({'success': False, 'error': modify_result.get('error', 'Falha ao cancelar a assinatura no Stripe.')}), 500

    # If cancel_at_period_end is set, Stripe will handle cancellation at period end
    # We update subscription_status to indicate pending cancellation
    cancel_at_period_end = modify_result.get('cancel_at_period_end', False)
    cancel_at_date = modify_result.get('cancel_at')  # Get cancel_at from Stripe response
    if cancel_at_period_end:
        # Mark as will cancel at period end - user keeps access until then
        supabase.update_user_subscription(
            user_id=user_id,
            plan='basic',  # Keep basic until period ends
            subscription_status='active',  # Still active until period ends
            stripe_customer_id=customer_id,
            stripe_subscription_id=subscription_id,
            next_billing_date=None,  # Clear next billing date
            cancel_at=cancel_at_date  # Save cancel_at date
        )
        
        # Also update subscriptions table with user_id and cancel_at
        try:
            supabase.admin_client.table('subscriptions') \
                .update({
                    'user_id': user_id,
                    'cancel_at': cancel_at_date,
                    'updated_at': datetime.now().isoformat()
                }) \
                .eq('stripe_subscription_id', subscription_id) \
                .execute()
            logger.info('Updated subscriptions table with user_id and cancel_at', extra={'user_id': user_id, 'subscription_id': subscription_id})
        except Exception as e:
            logger.warning('Failed to update subscriptions table', extra={'user_id': user_id, 'error': str(e)})
        
        logger.info(
            'Subscription set to cancel at period end',
            extra={
                'user_id': user_id,
                'subscription_id': subscription_id,
                'cancel_at_period_end': True,
                'cancel_at': cancel_at_date
            }
        )
    else:
        # Immediate cancellation (fallback)
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
        logger.info(
            'Subscription canceled immediately',
            extra={
                'user_id': user_id,
                'subscription_id': subscription_id
            }
        )

    return jsonify({'success': True, 'cancel_at_period_end': cancel_at_period_end})


@dashboard_bp.route('/api/subscription/reactivate', methods=['POST'])
@login_required
def reactivate_subscription():
    """Reactivate a subscription that was set to cancel at period end"""
    user_id = current_user.id
    supabase = get_supabase_handler()
    stripe_handler = get_stripe_handler()

    profile_result = supabase.get_user_profile(user_id)
    if not profile_result.get('success'):
        return jsonify({'success': False, 'error': 'Não foi possível localizar o perfil do usuário.'}), 400

    profile_data = profile_result.get('data') or {}
    subscription_id = profile_data.get('stripe_subscription_id')
    customer_id = profile_data.get('stripe_customer_id')

    if not subscription_id:
        return jsonify({'success': False, 'error': 'Nenhuma assinatura foi encontrada.'}), 400

    # Get subscription status from Stripe to check if it can be reactivated
    try:
        subscription = stripe_handler.stripe.Subscription.retrieve(subscription_id)
        subscription_status = subscription.get('status', '')
        
        # Cannot reactivate incomplete, incomplete_expired, or canceled subscriptions
        if subscription_status in ['incomplete', 'incomplete_expired', 'canceled']:
            return jsonify({
                'success': False,
                'error': f'Não é possível reativar uma assinatura com status "{subscription_status}". Por favor, faça um novo checkout para assinar novamente.',
                'requires_new_checkout': True
            }), 400
    except Exception as e:
        logger.warning('Failed to retrieve subscription status from Stripe', extra={'subscription_id': subscription_id, 'error': str(e)})
        # Continue with attempt to modify subscription anyway
    
    # Use modify_subscription with cancel_at_period_end=False to reactivate
    modify_result = stripe_handler.modify_subscription(subscription_id, cancel_at_period_end=False)
    if not modify_result.get('success'):
        return jsonify({'success': False, 'error': modify_result.get('error', 'Falha ao reativar a assinatura no Stripe.')}), 500

    # Update profile to remove cancel_at and keep subscription active
    supabase.update_user_subscription(
        user_id=user_id,
        plan='basic',
        subscription_status='active',
        stripe_customer_id=customer_id,
        stripe_subscription_id=subscription_id,
        next_billing_date=None,
        cancel_at=None
    )
    
    # Also update subscriptions table with user_id and clear cancel_at
    try:
        supabase.admin_client.table('subscriptions') \
            .update({
                'user_id': user_id,
                'cancel_at': None,
                'canceled_at': None,
                'updated_at': datetime.now().isoformat()
            }) \
            .eq('stripe_subscription_id', subscription_id) \
            .execute()
        logger.info('Updated subscriptions table with user_id and cleared cancel_at', extra={'user_id': user_id, 'subscription_id': subscription_id})
    except Exception as e:
        logger.warning('Failed to update subscriptions table', extra={'user_id': user_id, 'error': str(e)})

    logger.info(
        'Subscription reactivated',
        extra={
            'user_id': user_id,
            'subscription_id': subscription_id
        }
    )

    return jsonify({'success': True})


@dashboard_bp.route('/quotation/public/<quotation_id>')
def quotation_public_view(quotation_id):
    supabase = get_supabase_handler()
    result = supabase.get_public_quotation(str(quotation_id))

    if not result.get('success') or not result.get('data'):
        abort(404)

    quotation = result['data']
    owner_id = quotation.get('user_id')

    profile_data = {}
    generator_name = None
    if owner_id:
        profile_result = supabase.get_user_profile(owner_id)
        if profile_result.get('success'):
            profile_data = profile_result.get('data') or {}
            generator_name = profile_data.get('full_name') or profile_data.get('company_name')

    if not generator_name:
        generator_name = quotation.get('client_name') or 'Lumina Flow'

    currency_code = quotation.get('currency') or ('BRL' if session.get('user_region', 'UK') == 'BR' else 'GBP')
    if isinstance(currency_code, str):
        currency_code = currency_code.upper()

    currency_map = {
        'BRL': 'R$',
        'GBP': '£',
        'USD': '$',
        'EUR': '€'
    }
    currency_symbol = currency_map.get(currency_code, currency_code)

    template = quotation.get('template', 'quotation_detail.html')

    return render_template(
        template,
        quotation=quotation,
        user_name=generator_name,
        profile_data=profile_data,
        currency_symbol=currency_symbol,
        currency_code=currency_code,
        generator_name=generator_name,
        public_view=True
    )

