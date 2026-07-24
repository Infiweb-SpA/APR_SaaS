"""
Blueprint Módulo 5: Toma de Lecturas en Terreno.
Rutas HTML + API JSON para DataTables / Captura Mobile / Sync Offline.
"""

from datetime import date
from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, jsonify, current_app
)
from flask_login import login_required, current_user

from app import db
from app.models.reading import Reading, ReadingStatus
from app.models.partner import Partner, Meter, Sector, PartnerStatus, MeterStatus
from app.services.reading_service import (
    capture_reading, sync_offline_readings, search_readings,
    get_reading_by_id, validate_reading, reject_reading,
    validate_batch, get_lecturas_stats, get_readings_for_capture,
    get_consumption_history, get_partner_readings_summary,
    ValidationError, BusinessRuleError, NotFoundError, ReadingServiceError,
)
from app.services.partner_service import (
    get_sectores_activos, get_partner_by_id,
)
from app.services.auth_service import permission_required


# ──────────────────────────────────────────────────────────────
# BLUEPRINT
# ──────────────────────────────────────────────────────────────
bp = Blueprint('readings', __name__, url_prefix='/readings')


# ══════════════════════════════════════════════════════════════
# LISTADO PRINCIPAL (HTML + DataTables AJAX)
# ══════════════════════════════════════════════════════════════

@bp.route('/')
@login_required
@permission_required('readings', 1)
def index():
    """Vista principal: Tabla de Lecturas (DataTables server-side)."""
    sectores = get_sectores_activos()
    estados = [(s.value, s.name.capitalize()) for s in ReadingStatus]

    # Periodos disponibles (últimos 12 meses)
    periodos = _get_available_periodos()

    return render_template(
        'readings/index.html',
        sectores=sectores,
        estados=estados,
        periodos=periodos,
    )


@bp.route('/api/list')
@login_required
@permission_required('readings', 1)
def api_list():
    """Endpoint DataTables: JSON paginado/filtrado."""
    draw = request.args.get('draw', 1, type=int)
    start = request.args.get('start', 0, type=int)
    length = request.args.get('length', 25, type=int)
    search_value = request.args.get('search[value]', '', type=str)

    periodo = request.args.get('periodo', '', type=str)
    status = request.args.get('status', '', type=str)
    sector_id = request.args.get('sector_id', 0, type=int)

    page = (start // length) + 1 if length else 1
    per_page = length

    status_enum = ReadingStatus(status) if status else None
    sector_id_f = sector_id if sector_id != 0 else None

    try:
        readings, total = search_readings(
            term=search_value if search_value else None,
            periodo=periodo if periodo else None,
            status=status_enum,
            sector_id=sector_id_f,
            page=page,
            per_page=per_page,
            order_by='fecha',
            order_dir='desc',
        )
    except Exception as e:
        current_app.logger.error(f"Error api_list readings: {e}")
        return jsonify({
            'draw': draw, 'recordsTotal': 0,
            'recordsFiltered': 0, 'data': [], 'error': str(e),
        }), 500

    data = []
    for r in readings:
        data.append({
            'id': r.id,
            'periodo': r.periodo,
            'periodo_display': r.periodo_display,
            'fecha': r.fecha.strftime('%d/%m/%Y') if r.fecha else '-',
            'partner_nombre': r.partner.nombre if r.partner else '-',
            'partner_rut': r.partner.rut if r.partner else '-',
            'sector': r.sector.nombre if r.sector else '-',
            'meter_serie': r.meter.numero_serie if r.meter else '-',
            'lectura_anterior': r.lectura_anterior,
            'lectura_actual': r.lectura_actual,
            'consumo': r.consumo,
            'consumo_real': r.consumo_real,
            'multiplicador': r.multiplicador,
            'status': r.status.name.capitalize(),
            'status_raw': r.status.value,
            'origen': r.origen,
            'observaciones': r.observaciones or '',
        })

    return jsonify({
        'draw': draw,
        'recordsTotal': total,
        'recordsFiltered': total,
        'data': data,
    })


# ══════════════════════════════════════════════════════════════
# CAPTURA EN TERRENO (Mobile-First)
# ══════════════════════════════════════════════════════════════

@bp.route('/capture')
@login_required
@permission_required('readings', 2)
def capture():
    """Interfaz de captura mobile-first por sector/ruta."""
    sectores = get_sectores_activos()
    periodo = request.args.get('periodo', date.today().strftime('%Y-%m'))
    sector_id = request.args.get('sector_id', 0, type=int)

    # Obtener lista de medidores para captura
    items = get_readings_for_capture(
        sector_id=sector_id if sector_id != 0 else None,
        periodo=periodo,
    )

    return render_template(
        'readings/capture.html',
        sectores=sectores,
        periodo=periodo,
        sector_id=sector_id,
        items=items,
    )


@bp.route('/api/capture', methods=['POST'])
@login_required
@permission_required('readings', 2)
def api_capture():
    """API: Captura individual de lectura (AJAX desde vista capture)."""
    data = request.get_json() if request.is_json else request.form.to_dict()

    try:
        reading = capture_reading(data, current_user.id)
        return jsonify({
            'success': True,
            'message': f'Lectura registrada: {reading.consumo} m³ '
                       f'({reading.meter.numero_serie}).',
            'reading': reading.to_dict(),
        })
    except ValidationError as e:
        return jsonify({'success': False, 'error': e.message, 'field': e.field}), 400
    except BusinessRuleError as e:
        return jsonify({'success': False, 'error': e.message}), 400
    except NotFoundError as e:
        return jsonify({'success': False, 'error': e.message}), 404
    except ReadingServiceError as e:
        return jsonify({'success': False, 'error': e.message}), 400
    except Exception as e:
        current_app.logger.exception("Error en api_capture")
        return jsonify({'success': False, 'error': 'Error interno del servidor.'}), 500


@bp.route('/api/validate-consumption', methods=['POST'])
@login_required
@permission_required('readings', 1)
def api_validate_consumption():
    """API: Validación en tiempo real del consumo (llamado desde JS)."""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Sin datos'}), 400

    meter_id = data.get('meter_id')
    lectura_actual = data.get('lectura_actual')
    lectura_anterior = data.get('lectura_anterior')

    if not meter_id or lectura_actual is None or lectura_anterior is None:
        return jsonify({'success': False, 'error': 'Campos requeridos faltantes'}), 400

    try:
        from app.services.reading_service import validate_consumption_rules
        result = validate_consumption_rules(
            int(meter_id), int(lectura_actual), int(lectura_anterior)
        )
        return jsonify({'success': True, **result})
    except Exception as e:
        current_app.logger.exception("Error en api_validate_consumption")
        return jsonify({'success': False, 'error': str(e)}), 500


# ══════════════════════════════════════════════════════════════
# SINCRONIZACIÓN OFFLINE (BATCH)
# ══════════════════════════════════════════════════════════════

@bp.route('/api/sync', methods=['POST'])
@login_required
@permission_required('readings', 2)
def api_sync():
    """
    API: Sincronización batch de lecturas offline.
    Acepta JSON array de lecturas.
    """
    data = request.get_json()
    if not data or not isinstance(data, list):
        return jsonify({
            'success': False,
            'error': 'Se esperaba un array JSON de lecturas.',
        }), 400

    try:
        result = sync_offline_readings(data, current_user.id)
        return jsonify({
            'success': True,
            'message': f'Sincronizadas: {result["synced"]}, '
                       f'Omitidas: {result["skipped"]}, '
                       f'Errores: {len(result["errors"])}.',
            **result,
        })
    except Exception as e:
        current_app.logger.exception("Error en api_sync")
        return jsonify({'success': False, 'error': f'Error en sincronización: {str(e)}'}), 500


@bp.route('/api/sync/status')
@login_required
@permission_required('readings', 1)
def api_sync_status():
    """API: Estado de sincronización del periodo actual."""
    periodo = request.args.get('periodo', date.today().strftime('%Y-%m'))

    total_offline = Reading.query.filter(
        Reading.periodo == periodo,
        Reading.sincronizado == False,
    ).count()

    total_pending = Reading.query.filter(
        Reading.periodo == periodo,
        Reading.status == ReadingStatus.PENDIENTE,
    ).count()

    return jsonify({
        'success': True,
        'periodo': periodo,
        'offline_pending': total_offline,
        'readings_pending': total_pending,
    })


# ══════════════════════════════════════════════════════════════
# VALIDACIÓN / APROBACIÓN / RECHAZO (Admin)
# ══════════════════════════════════════════════════════════════

@bp.route('/<int:reading_id>/validate', methods=['POST'])
@login_required
@permission_required('readings', 2)
def validate_route(reading_id):
    """Aprueba una lectura pendiente."""
    try:
        reading = validate_reading(reading_id, current_user.id)

        if request.is_json:
            return jsonify({
                'success': True,
                'message': f'Lectura {reading.periodo_display} aprobada. '
                           f'Consumo: {reading.consumo} m³.',
            })

        flash(f'Lectura aprobada.', 'success')
    except BusinessRuleError as e:
        if request.is_json:
            return jsonify({'success': False, 'error': e.message}), 400
        flash(f'Error: {e.message}', 'danger')
    except ReadingServiceError as e:
        if request.is_json:
            return jsonify({'success': False, 'error': e.message}), 400
        flash(f'Error: {e.message}', 'danger')
    except Exception as e:
        current_app.logger.exception("Error validando lectura")
        if request.is_json:
            return jsonify({'success': False, 'error': 'Error interno'}), 500
        flash('Error interno del servidor.', 'danger')

    return redirect(url_for('readings.index'))


@bp.route('/<int:reading_id>/reject', methods=['POST'])
@login_required
@permission_required('readings', 2)
def reject_route(reading_id):
    """Rechaza una lectura con motivo."""
    data = request.get_json() if request.is_json else request.form.to_dict()
    motivo = data.get('motivo_rechazo', '').strip()

    try:
        reading = reject_reading(reading_id, motivo, current_user.id)

        if request.is_json:
            return jsonify({
                'success': True,
                'message': f'Lectura rechazada.',
            })

        flash('Lectura rechazada.', 'warning')
    except (ValidationError, BusinessRuleError) as e:
        if request.is_json:
            return jsonify({'success': False, 'error': e.message}), 400
        flash(f'Error: {e.message}', 'danger')
    except ReadingServiceError as e:
        if request.is_json:
            return jsonify({'success': False, 'error': e.message}), 400
        flash(f'Error: {e.message}', 'danger')
    except Exception as e:
        current_app.logger.exception("Error rechazando lectura")
        if request.is_json:
            return jsonify({'success': False, 'error': 'Error interno'}), 500
        flash('Error interno del servidor.', 'danger')

    return redirect(url_for('readings.index'))


@bp.route('/api/validate-batch', methods=['POST'])
@login_required
@permission_required('readings', 2)
def api_validate_batch():
    """API: Aprobación masiva de lecturas pendientes."""
    data = request.get_json()
    reading_ids = data.get('reading_ids', []) if data else []

    if not reading_ids:
        return jsonify({
            'success': False,
            'error': 'No se seleccionaron lecturas.',
        }), 400

    try:
        result = validate_batch(reading_ids, current_user.id)
        return jsonify({
            'success': True,
            'message': f'Aprobadas: {result["validated"]}, '
                       f'Errores: {result["errors"]}.',
            **result,
        })
    except Exception as e:
        current_app.logger.exception("Error en validate_batch")
        return jsonify({'success': False, 'error': str(e)}), 500


# ══════════════════════════════════════════════════════════════
# DETALLE DE LECTURA
# ══════════════════════════════════════════════════════════════

@bp.route('/<int:reading_id>')
@login_required
@permission_required('readings', 1)
def detail(reading_id):
    """Detalle de una lectura individual."""
    reading = get_reading_by_id(reading_id)

    # Historial del medidor para contexto
    history = get_consumption_history(reading.meter_id, months=6)

    return render_template(
        'readings/detail.html',
        reading=reading,
        history=history,
    )


# ══════════════════════════════════════════════════════════════
# API AUXILIARES
# ══════════════════════════════════════════════════════════════

@bp.route('/api/stats')
@login_required
@permission_required('readings', 1)
def api_stats():
    """API: Estadísticas de lecturas para dashboard."""
    periodo = request.args.get('periodo', None)
    try:
        stats = get_lecturas_stats(periodo)
        return jsonify({'success': True, **stats})
    except Exception as e:
        current_app.logger.error(f"Error api_stats: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/api/history/<int:meter_id>')
@login_required
@permission_required('readings', 1)
def api_consumption_history(meter_id):
    """API: Historial de consumo de un medidor (para Chart.js)."""
    months = request.args.get('months', 12, type=int)
    try:
        history = get_consumption_history(meter_id, months=months)
        return jsonify({
            'success': True,
            'meter_id': meter_id,
            'history': history,
            'labels': [h['label'] for h in history],
            'data': [h['consumo'] for h in history],
        })
    except Exception as e:
        current_app.logger.error(f"Error api_consumption_history: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/api/partner/<int:partner_id>/summary')
@login_required
@permission_required('readings', 1)
def api_partner_summary(partner_id):
    """API: Resumen de lecturas de un socio (para ficha partners/detail)."""
    try:
        summary = get_partner_readings_summary(partner_id)
        return jsonify({'success': True, **summary})
    except NotFoundError as e:
        return jsonify({'success': False, 'error': e.message}), 404
    except Exception as e:
        current_app.logger.error(f"Error api_partner_summary: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ══════════════════════════════════════════════════════════════
# HELPERS PRIVADOS
# ══════════════════════════════════════════════════════════════

def _get_available_periodos() -> list:
    """
    Genera lista de periodos (últimos 12 meses + actual)
    para el filtro dropdown del listado.
    """
    from datetime import datetime
    periodos = []
    today = date.today()

    for i in range(12):
        # Mes actual y 11 anteriores
        year = today.year
        month = today.month - i

        while month <= 0:
            month += 12
            year -= 1

        periodo_str = f"{year}-{month:02d}"
        months_es = [
            'Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
            'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic',
        ]
        label = f"{months_es[month - 1]} {year}"
        periodos.append((periodo_str, label))

    return periodos