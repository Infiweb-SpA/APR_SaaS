import os
from dotenv import load_dotenv

load_dotenv()

# Ruta base del proyecto (donde está este archivo)
basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    """Configuración base compartida entre entornos."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'apr-dev-secret-key')

    # Ruta absoluta al archivo SQLite
    _db_path = os.path.join(basedir, 'instance', 'apr_database.sqlite')
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'sqlite:///' + _db_path
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config_map = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig,
}