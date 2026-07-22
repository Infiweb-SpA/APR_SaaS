"""
Módulo 3 – Panel Principal Interno / Portal Socio.
Workspace administrativo post-login adaptado al nivel de acceso del usuario.
"""

from flask import Blueprint, render_template
from flask_login import login_required, current_user
from app.services.auth_service import permission_required

main_bp = Blueprint('main', __name__, template_folder='../templates/main')


@main_bp.route('/panel')
@login_required
def panel():
    """
    Panel principal post-login.
    Redirige según el rol del usuario a la vista correspondiente.
    """
    if current_user.has_permission('auth', 2):
        return _render_admin_dashboard()
    return _render_socio_portal()


@main_bp.route('/panel/admin')
@login_required
@permission_required('auth', 1)
def admin_dashboard():
    """Vista de resumen ejecutivo para staff administrativo."""
    return _render_admin_dashboard()


@main_bp.route('/panel/socio')
@login_required
def socio_portal():
    """Vista personal del socio / cliente."""
    return _render_socio_portal()


# ── Helpers privados ───────────────────────────────────────

def _render_admin_dashboard():
    """Renderiza el dashboard de staff con datos de ejemplo."""

    # Datos de ejemplo — se reemplazarán con consultas reales
    # cuando los módulos 4, 5, 6 y 8 estén desarrollados.
    stats = {
        'total_socios': 0,
        'socios_activos': 0,
        'total_recaudado': 0,
        'meta_recaudacion': 0,
        'pct_lecturas': 0,
        'lecturas_tomadas': 0,
        'lecturas_total': 0,
        'deudores_mora': 0,
        'monto_mora': 0,
        'consumo_promedio': 0,
    }

    # Alertas de ejemplo
    alerts = []

    # Actividad reciente de ejemplo
    recent_activity = []

    return render_template(
        'main/admin_dashboard.html',
        stats=stats,
        alerts=alerts,
        recent_activity=recent_activity,
    )


def _render_socio_portal():
    """Renderiza el portal personal del socio."""

    # Datos de ejemplo — se reemplazarán con consultas reales
    # cuando los módulos 4, 5, 6 y 8 estén desarrollados.
    socio_data = {
        'nombre': current_user.nombre,
        'rut': current_user.rut,
        'direccion': 'Sin datos aún',
        'sector': 'Sin datos aún',
        'medidor': 'Sin datos aún',
        'estado': 'Al día',
        'saldo_pendiente': 0,
        'ultima_boleta': None,
        'consumo_actual': 0,
        'consumo_promedio': 0,
    }

    # Historial de consumo (últimos 12 meses) — vacío hasta módulo 5
    consumption_history = []

    # Boletas recientes — vacío hasta módulo 6
    recent_bills = []

    return render_template(
        'main/socio_portal.html',
        socio=socio_data,
        consumption_history=consumption_history,
        recent_bills=recent_bills,
    )