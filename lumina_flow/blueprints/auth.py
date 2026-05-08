
from flask import Blueprint, request, jsonify, session, redirect, url_for, render_template
from ..supabase_handler import get_supabase_handler

# Criação do Blueprint de autenticação
auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET'])
def login_page():
    """Renderiza a página de login/signup."""
    if 'user_id' in session:
        return redirect(url_for('dashboard.dashboard_view'))
    return render_template('login.html')

@auth_bp.route('/login', methods=['POST'])
def handle_login():
    """Lida com a requisição de login via API."""
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    
    if not email or not password:
        return jsonify({'success': False, 'error': 'Email and password are required'}), 400
    
    supabase = get_supabase_handler()
    result = supabase.sign_in(email, password)
    
    if result.get('success'):
        session['user_id'] = result['user'].id
        session['user_email'] = result['user'].email
        session['access_token'] = result['session'].access_token
        
        # Heurística simples para definir a região do usuário
        if '.br' in email.lower():
            session['user_region'] = 'BR'
        else:
            session['user_region'] = 'UK'
            
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': result.get('error', 'Login failed')}), 401

@auth_bp.route('/signup', methods=['POST'])
def handle_signup():
    """Lida com a requisição de signup via API."""
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    
    if not email or not password:
        return jsonify({'success': False, 'error': 'Email and password are required'}), 400
    
    supabase = get_supabase_handler()
    result = supabase.sign_up(email, password)
    
    if result.get('success'):
        # Cria o perfil do usuário na nossa tabela 'profiles'
        profile_result = supabase.create_user_profile(result['user'].id, email)
        
        if profile_result.get('success'):
            # Loga o usuário automaticamente após o signup
            session['user_id'] = result['user'].id
            session['user_email'] = result['user'].email
            session['access_token'] = result['session'].access_token
            
            if '.br' in email.lower():
                session['user_region'] = 'BR'
            else:
                session['user_region'] = 'UK'
            
            return jsonify({'success': True})
        else:
            # Em um cenário real, poderíamos tentar deletar o usuário criado no Auth
            # para evitar inconsistência, mas por enquanto retornamos o erro.
            return jsonify({'success': False, 'error': 'Failed to create user profile'}), 500
    else:
        return jsonify({'success': False, 'error': result.get('error', 'Signup failed')}), 401

@auth_bp.route('/logout')
def logout():
    """Lida com o logout do usuário."""
    supabase = get_supabase_handler()
    access_token = session.get('access_token')
    
    if access_token:
        supabase.sign_out(access_token)
    
    session.clear()
    return redirect(url_for('main.index'))