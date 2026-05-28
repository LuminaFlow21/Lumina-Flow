"""
Lumina Flow - Configuration
Central configuration management for environment variables and app settings
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Base configuration class"""
    
    # Flask
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    DEBUG = os.getenv('DEBUG', 'True').lower() == 'true'
    TESTING = os.getenv('TESTING', 'False').lower() == 'true'
    
    # App
    APP_NAME = 'Lumina Flow'
    APP_VERSION = '1.0.0'

    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
    LOG_JSON = os.getenv('LOG_JSON', 'False').lower() == 'true'
    LOG_TO_FILE = os.getenv('LOG_TO_FILE', 'True').lower() == 'true'
    LOG_DIR = os.getenv('LOG_DIR') or os.path.join(os.path.dirname(__file__), '..', 'logs')
    LOG_MAX_BYTES = int(os.getenv('LOG_MAX_BYTES', 5 * 1024 * 1024))
    LOG_BACKUP_COUNT = int(os.getenv('LOG_BACKUP_COUNT', 5))
    
    # Supabase
    SUPABASE_URL = os.getenv('SUPABASE_URL')
    SUPABASE_KEY = os.getenv('SUPABASE_KEY')
    SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
    
    # Stripe
    STRIPE_PUBLIC_KEY = os.getenv('STRIPE_PUBLIC_KEY')
    STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')
    STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
    
    # Stripe Price IDs
    STRIPE_PRICE_ID_BR_MONTHLY = os.getenv('STRIPE_PRICE_ID_BR_MONTHLY')
    STRIPE_PRICE_ID_BR_YEARLY = os.getenv('STRIPE_PRICE_ID_BR_YEARLY')
    STRIPE_PRICE_ID_UK_MONTHLY = os.getenv('STRIPE_PRICE_ID_UK_MONTHLY')
    STRIPE_PRICE_ID_UK_YEARLY = os.getenv('STRIPE_PRICE_ID_UK_YEARLY')
    
    # Brevo API (Email)
    BREVO_API_KEY = os.getenv('BREVO_API_KEY')
    
    # Admin
    ADMIN_EMAILS = os.getenv('ADMIN_EMAILS', '').split(',') if os.getenv('ADMIN_EMAILS') else []
    BREVO_SENDER_EMAIL = os.getenv('BREVO_SENDER_EMAIL', 'noreply@luminaflow.com')
    
    # URLs
    BASE_URL = os.getenv('BASE_URL', 'http://localhost:5000')
    SUCCESS_URL = f'{BASE_URL}/dashboard?session_id={{CHECKOUT_SESSION_ID}}'
    CANCEL_URL = f'{BASE_URL}/pricing'
    LINKS_HOME_URL = os.getenv('LINKS_HOME_URL', '/')
    LINKS_WHATSAPP_URL = os.getenv('LINKS_WHATSAPP_URL', 'https://wa.me/5511999999999')
    LINKS_INSTAGRAM_URL = os.getenv('LINKS_INSTAGRAM_URL', 'https://instagram.com/luminaflow')
    
    # Session
    SESSION_COOKIE_SECURE = os.getenv('SESSION_COOKIE_SECURE', 'False').lower() == 'true'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 86400  # 24 hours


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    SESSION_COOKIE_SECURE = True


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    WTF_CSRF_ENABLED = False


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}


def get_config(env=None):
    """Get configuration based on environment"""
    if env is None:
        env = os.getenv('FLASK_ENV', 'development')
    return config.get(env, DevelopmentConfig)
