"""
Blueprint de Facturación – Rutas y controladores.
Gestiona listado de boletas, configuración de tarifas,
motor de cierre de mes y ciclo de vida de boletas.
"""

from datetime import date, datetime
from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, jsonify, abort,
)
from flask_login import login_required, current_user

from app import db
from app.services.auth_service import permission_required
from app.services.billing_service import (
    # Tarifas
    get_active_tariff, get_tariff_history, create_tariff, update_tariff,
    # Boletas
    search_bills, get_bill_by_id, get_bills_for_partner,
    get_partner_outstanding_balance,
    # Cierre de mes
    get_billing_preview, execute_monthly_billing,
    # Ciclo de vida
    mark_bill_as_paid, mark_overdue_bills, anular_bill,
    # Estadísticas
    get_billing_stats,
    # Excepciones
    BillingServiceError, ValidationError, BusinessRuleError, NotFoundError,
)
from app.models.billing import BillStatus
from app.models.partner import PartnerStatus


bp = Blueprint('billing', __name__, url_prefix='/billing')


# ══════════════════════════════════════════════════════════════
# VISTA PRINCIPAL – Listado de Boletas
# ══════════════════════════════════════════════════════════════

@bp.route('/')
@login_required
@permission_required('billing', 1)
def index():
    """Listado de boletas emitidas con DataTables server-side."""
    # Periodos disponibles (últimos 12 meses para filtro)
    today = date.today()
    periodos = []
    for i in range(12):
        y = today.year
        m = today.month - i
        while m <= 0:
            m += 12
            y -= 1
        periodos.append(f"{y}-{m:02d}")

    # Estados para filtro
    estados = [(e.value, e.name.capitalize()) for e in BillStatus]

    return render_template(
        'billing/index.html',
        periodos=periodos,
        estados=estados,
    )


# ══════════════════════════════════════════════════════════════
# API DataTables – Listado de Boletas (JSON)
# ══════════════════════════════════════════════════════════════

@bp.route('/api/list')
@login_required
@permission_required('billing', 1)
def api_list():
    """Endpoint JSON para DataTables server-side."""
    # Parámetros DataTables
    draw = request.args.get('draw', 1, type=int)
    start = request.args.get('start', 0, type=int)
    length = request.args.get('length', 25, type=int)
    search_value = request.args.get('search[value]', '', type=str)

    # Filtros custom
    periodo = request.args.get('periodo', '', type=str).strip()
    status_raw = request.args.get('status', '', type=str).strip()

    # Mapear status
    status = None
    if status_raw:
        try:
            status = BillStatus(status_raw)
        except ValueError:
            pass

    # Calcular página
    page = (start // length) + 1

    # Buscar
    bills, total = search_bills(
        term=search_value if search_value else None,
        periodo=periodo if periodo else None,
        status=status,
        page=page,
        per_page=length,
    )

    # Serializar
    data = [bill.to_dict() for bill in bills]

    return jsonify({
        'draw': draw,
        'recordsTotal': total,
        'recordsFiltered': total,
        'data': data,
    })


# ══════════════════════════════════════════════════════════════
# CONFIGURACIÓN DE TARIFAS
# ══════════════════════════════════════════════════════════════

@bp.route('/config')
@login_required
@permission_required('billing', 2)
def config():
    """Vista de configuración de tarifas activa e historial."""
    tarifa_activa = get_active_tariff()
    historial = get_tariff_history()

    return render_template(
        'billing/config.html',
        tarifa=tarifa_activa,
        historial=historial,
    )


@bp.route('/config/save', methods=['POST'])
@login_required
@permission_required('billing', 2)
def config_save():
    """Crea o actualiza la configuración de tarifa.

    Si se envía 'tariff_id', actualiza la existente (solo si es activa).
    Si no, crea una nueva configuración (desactiva la anterior).
    """
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    try:
        data = request.form.to_dict()
        tariff_id = data.get('tariff_id')

        if tariff_id:
            tariff = update_tariff(int(tariff_id), data, current_user.id)
            msg = 'Configuración de tarifa actualizada exitosamente.'
        else:
            tariff = create_tariff(data, current_user.id)
            msg = 'Nueva configuración de tarifa creada y activada.'

        if is_ajax:
            return jsonify({
                'success': True,
                'message': msg,
                'tariff': tariff.to_dict(),
            })

        flash(msg, 'success')
        return redirect(url_for('billing.config'))

    except ValidationError as e:
        if is_ajax:
            return jsonify({'success': False, 'error': e.message, 'field': e.field}), 400
        flash(e.message, 'error')
        return redirect(url_for('billing.config'))

    except BusinessRuleError as e:
        if is_ajax:
            return jsonify({'success': False, 'error': e.message}), 400
        flash(e.message, 'error')
        return redirect(url_for('billing.config'))

    except Exception as e:
        db.session.rollback()
        if is_ajax:
            return jsonify({'success': False, 'error': f'Error inesperado: {str(e)}'}), 500
        flash(f'Error inesperado: {str(e)}', 'error')
        return redirect(url_for('billing.config'))


# ══════════════════════════════════════════════════════════════
# API TARIFA ACTIVA (JSON)
# ══════════════════════════════════════════════════════════════

@bp.route('/api/tariff')
@login_required
@permission_required('billing', 1)
def api_tariff():
    """Retorna la tarifa activa como JSON (para preview en process)."""
    tariff = get_active_tariff()
    if not tariff:
        return jsonify({'success': False, 'error': 'No hay tarifa activa configurada.'}), 404
    return jsonify({'success': True, 'tariff': tariff.to_dict()})


# ══════════════════════════════════════════════════════════════
# MOTOR DE CIERRE DE MES
# ══════════════════════════════════════════════════════════════

@bp.route('/process')
@login_required
@permission_required('billing', 2)
def process():
    """Vista de previsualización y ejecución de cierre de mes."""
    # Periodo sugerido: mes actual
    today = date.today()
    periodo_default = today.strftime('%Y-%m')

    # Intentar preview (si hay tarifa activa)
    preview = None
    try:
        preview = get_billing_preview(periodo_default)
    except BusinessRuleError:
        pass  # No hay tarifa activa, la vista mostrará aviso

    # Historial de cierres: periodos con boletas emitidas
    from sqlalchemy import func
    from app.models.billing import Bill
    periodos_cerrados = db.session.query(
        Bill.periodo, func.count(Bill.id)
    ).filter(
        Bill.status != BillStatus.ANULADA,
    ).group_by(Bill.periodo).order_by(Bill.periodo.desc()).limit(12).all()

    return render_template(
        'billing/process.html',
        preview=preview,
        periodo_default=periodo_default,
        periodos_cerrados=periodos_cerrados,
    )


@bp.route('/process/preview', methods=['POST'])
@login_required
@permission_required('billing', 2)
def process_preview():
    """AJAX: Previsualiza el cierre para un periodo específico."""
    periodo = request.form.get('periodo', '').strip()
    if not periodo or len(periodo) != 7:
        return jsonify({'success': False, 'error': 'Periodo inválido (formato YYYY-MM).'}), 400

    try:
        preview = get_billing_preview(periodo)
        return jsonify({'success': True, 'preview': preview})
    except BusinessRuleError as e:
        return jsonify({'success': False, 'error': e.message}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': f'Error: {str(e)}'}), 500


@bp.route('/process/execute', methods=['POST'])
@login_required
@permission_required('billing', 2)
def process_execute():
    """AJAX: Ejecuta el cierre de mes definitivo."""
    periodo = request.form.get('periodo', '').strip()
    if not periodo or len(periodo) != 7:
        return jsonify({'success': False, 'error': 'Periodo inválido (formato YYYY-MM).'}), 400

    # Fechas de emisión y vencimiento
    fecha_emision_str = request.form.get('fecha_emision', '').strip()
    fecha_vencimiento_str = request.form.get('fecha_vencimiento', '').strip()

    today = date.today()
    try:
        if fecha_emision_str:
            fecha_emision = date.fromisoformat(fecha_emision_str)
        else:
            fecha_emision = today
    except ValueError:
        fecha_emision = today

    try:
        if fecha_vencimiento_str:
            fecha_vencimiento = date.fromisoformat(fecha_vencimiento_str)
        else:
            # Default: 20 días desde emisión
            fecha_vencimiento = today.replace(day=28) if today.day <= 28 else today
    except ValueError:
        fecha_vencimiento = today.replace(day=28) if today.day <= 28 else today

    try:
        resultado = execute_monthly_billing(
            periodo=periodo,
            fecha_emision=fecha_emision,
            fecha_vencimiento=fecha_vencimiento,
            user_id=current_user.id,
        )
        return jsonify({
            'success': True,
            'message': (
                f"Cierre de {periodo} completado: "
                f"{resultado['boletas_creadas']} boletas generadas."
            ),
            'resultado': resultado,
        })
    except BusinessRuleError as e:
        return jsonify({'success': False, 'error': e.message}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Error inesperado: {str(e)}'}), 500


# ══════════════════════════════════════════════════════════════
# ACCIONES SOBRE BOLETAS (AJAX)
# ══════════════════════════════════════════════════════════════

@bp.route('/<int:bill_id>/pay', methods=['POST'])
@login_required
@permission_required('billing', 2)
def mark_paid(bill_id):
    """AJAX: Marca una boleta como pagada."""
    try:
        bill = mark_bill_as_paid(bill_id, current_user.id)
        return jsonify({
            'success': True,
            'message': f'Boleta {bill.periodo_display} marcada como pagada.',
            'bill': bill.to_dict(),
        })
    except BusinessRuleError as e:
        return jsonify({'success': False, 'error': e.message}), 400
    except NotFoundError as e:
        return jsonify({'success': False, 'error': e.message}), 404
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Error: {str(e)}'}), 500


@bp.route('/<int:bill_id>/anular', methods=['POST'])
@login_required
@permission_required('billing', 2)
def anular(bill_id):
    """AJAX: Anula una boleta con motivo."""
    motivo = request.form.get('motivo', '').strip()
    try:
        bill = anular_bill(bill_id, motivo, current_user.id)
        return jsonify({
            'success': True,
            'message': f'Boleta {bill.periodo_display} anulada.',
            'bill': bill.to_dict(),
        })
    except (BusinessRuleError, ValidationError) as e:
        return jsonify({'success': False, 'error': e.message}), 400
    except NotFoundError as e:
        return jsonify({'success': False, 'error': e.message}), 404
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Error: {str(e)}'}), 500


@bp.route('/overdue/mark', methods=['POST'])
@login_required
@permission_required('billing', 2)
def mark_overdue():
    """AJAX: Marca como vencidas todas las boletas emitidas fuera de plazo."""
    try:
        count = mark_overdue_bills(user_id=current_user.id)
        return jsonify({
            'success': True,
            'message': f'{count} boleta(s) marcada(s) como vencida(s).',
            'count': count,
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Error: {str(e)}'}), 500


# ══════════════════════════════════════════════════════════════
# API ESTADÍSTICAS (Para dashboard / widgets)
# ══════════════════════════════════════════════════════════════

@bp.route('/api/stats')
@login_required
@permission_required('billing', 1)
def api_stats():
    """Retorna estadísticas de facturación como JSON."""
    periodo = request.args.get('periodo', '').strip() or None
    try:
        stats = get_billing_stats(periodo)
        return jsonify({'success': True, 'stats': stats})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500