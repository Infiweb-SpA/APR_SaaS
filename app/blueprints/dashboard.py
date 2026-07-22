"""
Módulo 1 – Dashboard de Presentación (Landing Pública).
Portal institucional público del comité APR.
Acceso: público (sin autenticación).
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash

dashboard_bp = Blueprint('dashboard', __name__)


# ── Rutas Públicas ──────────────────────────────────────────

@dashboard_bp.route('/')
def index():
    """Hero Section / Página de inicio."""
    return render_template('dashboard/index.html')


@dashboard_bp.route('/servicios')
def servicios():
    """Información de empalmes, factibilidad y tarifas públicas."""
    return render_template('dashboard/servicios.html')


@dashboard_bp.route('/quienes-somos')
def quienes_somos():
    """Historia, directiva y reglamento interno."""
    return render_template('dashboard/quienes_somos.html')


@dashboard_bp.route('/obras')
def obras():
    """Noticias de proyectos, cortes programados y mejoras de red."""
    return render_template('dashboard/obras.html')


@dashboard_bp.route('/info-util')
def info_util():
    """Ahorro de agua, fechas de pago y protocolos."""
    return render_template('dashboard/info_util.html')


@dashboard_bp.route('/directivos')
def directivos():
    """Organigrama del comité."""
    return render_template('dashboard/directivos.html')


@dashboard_bp.route('/contacto', methods=['GET', 'POST'])
def contacto():
    """Formulario de consultas y teléfonos de emergencia."""
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        email = request.form.get('email', '').strip()
        asunto = request.form.get('asunto', '').strip()
        mensaje = request.form.get('mensaje', '').strip()

        if not all([nombre, email, asunto, mensaje]):
            flash('Todos los campos son obligatorios.', 'error')
        else:
            # TODO: integrar envío de correo o persistencia en DB
            flash(
                'Su consulta ha sido enviada. Nos contactaremos a la brevedad.',
                'success',
            )
            return redirect(url_for('dashboard.contacto'))

    return render_template('dashboard/contacto.html')