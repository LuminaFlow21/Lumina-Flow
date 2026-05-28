import os
from flask import Flask, session
from flask_talisman import Talisman
from flask_login import LoginManager

from .config import get_config
from .auth_handler import User
from .logging_config import setup_logging, register_request_logging

def create_app(config_name=None):
    """
    Application Factory: Cria e configura a aplicação Flask.
    """
    app = Flask(__name__, instance_relative_config=True)
    
    # Carrega a configuração apropriada (dev, prod, test)
    config_obj = get_config(config_name)
    app.config.from_object(config_obj)

    setup_logging(app.config)
    register_request_logging(app)

    # Inicializa extensões de segurança
    # O CSP é desabilitado por padrão para não interferir com scripts inline/externos
    # durante o desenvolvimento. Pode ser ajustado para produção.
    if not app.config['DEBUG']:
        Talisman(app, content_security_policy=None, frame_options='SAMEORIGIN')

    # Inicializa Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login_page'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.session_protection = 'strong'

    @login_manager.user_loader
    def load_user(user_id):
        from .auth_handler import get_auth_handler
        auth_handler = get_auth_handler()
        result = auth_handler.get_user_by_id(user_id)
        if result.get('success'):
            return User(result['user'])
        return None

    # --- Registra os Blueprints ---
    # As importações são feitas aqui para evitar importações circulares
    from .blueprints.main import main_bp
    from .blueprints.auth import auth_bp
    from .blueprints.dashboard import dashboard_bp
    from .blueprints.payments import payments_bp
    from .blueprints.admin import admin_bp
    from .blueprints.help import help_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(dashboard_bp, url_prefix='/dashboard')
    app.register_blueprint(payments_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(help_bp)

    # --- Registra o Context Processor ---
    # Injeta variáveis em todos os templates
    @app.context_processor
    def inject_template_vars():
        user_region = session.get('user_region', 'UK')
        return {
            'user_region': user_region,
            'app_name': app.config['APP_NAME'],
            'app_version': app.config['APP_VERSION'],
            'whatsapp_url': app.config.get('LINKS_WHATSAPP_URL')
        }

    return app