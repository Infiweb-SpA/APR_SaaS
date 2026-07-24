from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import config_map
from flask_migrate import Migrate
from flask_wtf import CSRFProtect 

db = SQLAlchemy()
csrf = CSRFProtect()  # ← NUEVO

login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Debe iniciar sesión para acceder a esta página.'
login_manager.login_message_category = 'warning'


def create_app(config_name: str = 'default') -> Flask:
    """
    Application Factory.
    Crea y configura la instancia de Flask, inicializa extensiones
    y registra blueprints.
    """
    app = Flask(
        __name__,
        template_folder='templates',
        static_folder='static',
        static_url_path='/static',
    )
    app.config.from_object(config_map[config_name])

    # ── Inicializar extensiones ─────────────────────────────
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)  # ← NUEVO: habilita csrf_token() global en Jinja2
    # +++ 2. INICIALIZAR MIGRATE (registra comando 'flask db')
    migrate = Migrate(app, db)

    # ── User loader para Flask-Login ────────────────────────
    @login_manager.user_loader
    def load_user(user_id):
        from app.models.user import User
        return User.query.get(int(user_id))

    # ── Registro de Blueprints ──────────────────────────────
    from app.blueprints.dashboard import dashboard_bp
    app.register_blueprint(dashboard_bp)

    from app.blueprints.auth import auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from app.blueprints.main import main_bp
    app.register_blueprint(main_bp)

    # app/__init__.py (dentro de create_app)
    from app.blueprints.partners import bp as partners_bp
    app.register_blueprint(partners_bp)

    from app.blueprints.readings import bp as readings_bp
    app.register_blueprint(readings_bp)
    
    # ── Crear tablas en BD ──────────────────────────────────
    with app.app_context():
        from app.models import user  # noqa: F401
        db.create_all()

    # ── Comandos CLI ────────────────────────────────────────
    _register_commands(app)

    return app


def _register_commands(app):
    """Registra comandos Flask CLI personalizados."""

    @app.cli.command('seed-admin')
    def seed_admin():
        """Crea el usuario administrador inicial (rol: dirigente)."""
        from app.models.user import User, ROLE_DEFAULTS
        from app.services.rut_validator import format_rut

        # Siempre almacenar RUT en formato normalizado: XX.XXX.XXX-K
        rut_formatted = format_rut('111111111')

        if User.query.filter_by(rut=rut_formatted).first():
            print(f'Ya existe un usuario con RUT {rut_formatted}')
            return

        admin = User(
            rut=rut_formatted,
            nombre='Administrador General',
            email='admin@apr.cl',
            role='dirigente',
            permissions=ROLE_DEFAULTS['dirigente'],
        )
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
        print('-' * 50)
        print('  Usuario administrador creado exitosamente')
        print(f'  RUT:   {rut_formatted}')
        print('  Clave: admin123')
        print('-' * 50)