# app/services/__init__.py
# ─────────────────────────────────────────────────────────────
# SOLO utilidades base (sin partner_service para evitar ciclo)
# ─────────────────────────────────────────────────────────────
from flask_login import login_required

from app.services.auth_service import permission_required
from app.services.rut_validator import clean_rut, format_rut, validate_rut, calculate_dv

# ❌ ELIMINA: from app.services.partner_service import ...

__all__ = [
    'login_required',
    'permission_required',
    'clean_rut', 'format_rut', 'validate_rut', 'calculate_dv',
    # partner_service NO va aquí
]