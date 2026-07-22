"""
Módulo 2 – Modelo de Usuarios, Roles y Permisos.
Implementa RBAC con niveles numéricos (0, 1, 2) por módulo.
"""

from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db


# ── Configuración de Roles y Permisos por Defecto ──────────

ROLE_DEFAULTS = {
    'socio': {
        'auth': 2, 'portal_socio': 2, 'partners': 0,
        'readings': 0, 'billing': 0, 'pos': 0, 'reports': 0,
    },
    'operario': {
        'auth': 1, 'portal_socio': 0, 'partners': 1,
        'readings': 2, 'billing': 0, 'pos': 0, 'reports': 2,
    },
    'secretaria': {
        'auth': 1, 'portal_socio': 0, 'partners': 2,
        'readings': 1, 'billing': 1, 'pos': 2, 'reports': 0,
    },
    'dirigente': {
        'auth': 2, 'portal_socio': 2, 'partners': 2,
        'readings': 2, 'billing': 2, 'pos': 2, 'reports': 2,
    },
}

ROLE_LABELS = {
    'socio':       'Socio / Cliente',
    'operario':    'Operario de Terreno',
    'secretaria':  'Secretaria / Caja',
    'dirigente':   'Dirigente / Administrador',
}

ALL_MODULES = [
    'auth', 'portal_socio', 'partners',
    'readings', 'billing', 'pos', 'reports',
]

MODULE_LABELS = {
    'auth':         'Autenticación / Usuarios',
    'portal_socio': 'Portal Socio',
    'partners':     'Socios / Medidores',
    'readings':     'Lecturas',
    'billing':      'Facturación',
    'pos':          'Caja / Cobranza',
    'reports':      'Reportes SISS',
}


# ── Modelo de Usuario ──────────────────────────────────────

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    rut = db.Column(db.String(12), unique=True, nullable=False, index=True)
    nombre = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='socio')
    permissions = db.Column(db.JSON, nullable=False, default=lambda: ROLE_DEFAULTS['socio'].copy())
    _is_active = db.Column('is_active', db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # ── Password ────────────────────────────────────────────

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    # ── Permisos ────────────────────────────────────────────

    def has_permission(self, module: str, min_level: int = 1) -> bool:
        """Verifica si el usuario tiene al menos min_level en el módulo."""
        if not self.permissions:
            return False
        return self.permissions.get(module, 0) >= min_level

    def get_permission_level(self, module: str) -> int:
        """Retorna el nivel de permiso numérico para un módulo."""
        if not self.permissions:
            return 0
        return self.permissions.get(module, 0)

    def apply_role_defaults(self):
        """Aplica los permisos por defecto según el rol asignado."""
        self.permissions = ROLE_DEFAULTS.get(
            self.role, ROLE_DEFAULTS['socio']
        ).copy()

    # ── Flask-Login: is_active ──────────────────────────────

    @property
    def is_active(self):
        return self._is_active

    @is_active.setter
    def is_active(self, value):
        self._is_active = value

    # ── Representación ──────────────────────────────────────

    def __repr__(self):
        return f'<User {self.rut} ({self.role})>'