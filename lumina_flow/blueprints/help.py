"""
Help Blueprint for Lumy Chatbot API
"""

from flask import Blueprint, request, jsonify, session
from flask_login import login_required
from ..help_handler import get_help_handler

help_bp = Blueprint('help', __name__)


@help_bp.route('/api/help/search', methods=['POST'])
def search_help():
    """Search help articles by query"""
    try:
        data = request.get_json()
        query = data.get('query', '')
        
        if not query:
            return jsonify({'success': False, 'error': 'Query is required'}), 400
        
        help_handler = get_help_handler()
        result = help_handler.search_help_articles(query)
        
        # Log the search if user is authenticated
        if session.get('user_id'):
            matched_article_id = result['results'][0]['id'] if result.get('results') else None
            found_result = len(result.get('results', [])) > 0
            help_handler.log_help_search(
                user_id=session['user_id'],
                query=query,
                matched_article_id=matched_article_id,
                found_result=found_result
            )
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@help_bp.route('/api/help/categories', methods=['GET'])
def get_categories():
    """Get all help article categories"""
    try:
        help_handler = get_help_handler()
        result = help_handler.get_categories()
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@help_bp.route('/api/help/popular', methods=['GET'])
def get_popular_articles():
    """Get most searched help articles"""
    try:
        help_handler = get_help_handler()
        result = help_handler.get_popular_articles(limit=10)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@help_bp.route('/api/help/article/<article_id>', methods=['GET'])
def get_article(article_id):
    """Get a specific help article by ID"""
    try:
        help_handler = get_help_handler()
        response = help_handler.supabase.admin_client.table('help_articles') \
            .select('*') \
            .eq('id', article_id) \
            .eq('is_active', True) \
            .execute()
        
        if not response.data:
            return jsonify({'success': False, 'error': 'Article not found'}), 404
        
        return jsonify({'success': True, 'article': response.data[0]})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@help_bp.route('/api/help/feedback', methods=['POST'])
@login_required
def submit_feedback():
    """Submit feedback for an article"""
    try:
        data = request.get_json()
        article_id = data.get('article_id')
        helpful = data.get('helpful')
        
        if not article_id or helpful is None:
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        
        help_handler = get_help_handler()
        result = help_handler.submit_feedback(
            user_id=session.get('user_id'),
            article_id=article_id,
            helpful=helpful
        )
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@help_bp.route('/api/help/analytics', methods=['GET'])
@login_required
def get_analytics():
    """Get analytics data for Lumy (admin only)"""
    try:
        # Check if user is admin
        from ..auth_handler import is_admin_user
        from flask_login import current_user
        
        if not current_user.is_authenticated or not is_admin_user(current_user.email):
            return jsonify({'success': False, 'error': 'Admin access required'}), 403
        
        help_handler = get_help_handler()
        result = help_handler.get_analytics()
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@help_bp.route('/api/help/suggest-category', methods=['POST'])
def suggest_category():
    """Suggest category based on keywords"""
    try:
        data = request.get_json()
        keywords = data.get('keywords', [])
        
        if not keywords:
            return jsonify({'success': False, 'error': 'Keywords are required'}), 400
        
        help_handler = get_help_handler()
        result = help_handler.suggest_category(keywords)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@help_bp.route('/api/help/related/<article_id>', methods=['GET'])
def get_related_articles(article_id):
    """Get related articles for a given article"""
    try:
        help_handler = get_help_handler()
        result = help_handler.get_related_articles(article_id)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
