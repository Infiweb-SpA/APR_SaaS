"""
Capa de Servicio – Motor de Facturación, Tarifas y Subsidios.
Orquesta configuración de tarifas, cierre de mes masivo, generación
de boletas respetando Ley 20.998 y Dec. Sup. N° 171.
Provee datos para partner_service (Módulo 3: Dashboard y Portal Socio).
"""

from datetime import date, datetime, timedelta
from typing import Optional, List, Tuple, Dict, Any
from sqlalchemy import func, desc, asc, and_, or_
from sqlalchemy.orm import Query, joinedload
from app import db
from app.models.billing import Bill, BillStatus, TariffConfig
from app.models.reading import Reading, ReadingStatus
from app.models.partner import Partner, Meter, Sector, PartnerStatus, MeterStatus


# ══════════════════════════════════════════════════════════════
# EXCEPCIONES PERSONALIZADAS
# ══════════════════════════════════════════════════════════════

class BillingServiceError(Exception):
    """Excepción base para errores de negocio en Facturación."""
    def __init__(self, message: str, code: str = 'BILLING_ERROR', field: str = None):
        self.message = message
        self.code = code
        self.field = field
        super().__init__(message)


class ValidationError(BillingServiceError):
    def __init__(self, message: str, field: str = None):
        super().__init__(message, code='VALIDATION_ERROR', field=field)


class BusinessRuleError(BillingServiceError):
    def __init__(self, message: str, code: str = 'BUSINESS_RULE_VIOLATION'):
        super().__init__(message, code=code)


class NotFoundError(BillingServiceError):
    def __init__(self, entity: str, identifier: Any):
        super().__init__(f"{entity} no encontrado: {identifier}", code='NOT_FOUND')


# ══════════════════════════════════════════════════════════════
# HELPERS PRIVADOS
# ══════════════════════════════════════════════════════════════

def _to_int(val) -> Optional[int]:
    if val in (None, '', 'None'):
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _to_float(val) -> Optional[float]:
    if val in (None, '', 'None'):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _to_date(val) -> date:
    if not val or val in ('', 'None'):
        return date.today()
    try:
        if isinstance(val, date):
            return val
        if '/' in str(val):
            day, month, year = map(int, str(val).split('/'))
            return date(year, month, day)
        return date.fromisoformat(str(val))
    except (ValueError, TypeError):
        return date.today()


def _get_current_periodo() -> str:
    """Periodo actual (mes en curso)."""
    return date.today().strftime('%Y-%m')


def _get_bill_query() -> Query:
    """Query base con eager loading estándar para boletas."""
    return Bill.query.options(
        joinedload(Bill.partner),
        joinedload(Bill.reading),
    )


def _partner_tiene_mora(partner_id: int) -> bool:
    """Verifica si un socio tiene boletas vencidas sin pagar."""
    count = Bill.query.filter(
        Bill.partner_id == partner_id,
        Bill.status == BillStatus.VENCIDA,
    ).count()
    return count > 0


# ══════════════════════════════════════════════════════════════
# CONFIGURACIÓN DE TARIFAS
# ══════════════════════════════════════════════════════════════

def get_active_tariff() -> Optional[TariffConfig]:
    """Retorna la tarifa activa actual. None si no hay ninguna configurada."""
    return TariffConfig.query.filter_by(activo=True).first()


def get_tariff_history() -> List[TariffConfig]:
    """Historial completo de configuraciones de tarifas, más reciente primero."""
    return TariffConfig.query.order_by(desc(TariffConfig.created_at)).all()


def get_tariff_by_id(tariff_id: int) -> TariffConfig:
    tariff = TariffConfig.query.get(tariff_id)
    if not tariff:
        raise NotFoundError("Configuración de tarifa", tariff_id)
    return tariff


def create_tariff(data: dict, user_id: int) -> TariffConfig:
    """Crea una nueva configuración de tarifa y desactiva la anterior.

    Reglas:
    - Desactiva cualquier TariffConfig con activo=True.
    - El nuevo registro queda como activo=True.
    - Valida que los montos no sean negativos (además del CheckConstraint en BD).
    """
    # Validaciones de negocio (CheckConstraints son la red de seguridad)
    cargo_fijo = _to_float(data.get('cargo_fijo'))
    if cargo_fijo is None or cargo_fijo < 0:
        raise ValidationError("El cargo fijo debe ser un valor positivo", field='cargo_fijo')

    valor_m3_base = _to_float(data.get('valor_m3_base'))
    if valor_m3_base is None or valor_m3_base < 0:
        raise ValidationError("El valor por m³ base debe ser positivo", field='valor_m3_base')

    valor_m3_sobreconsumo = _to_float(data.get('valor_m3_sobreconsumo'))
    if valor_m3_sobreconsumo is None or valor_m3_sobreconsumo < 0:
        raise ValidationError("El valor por m³ de sobreconsumo debe ser positivo", field='valor_m3_sobreconsumo')

    limite_sobreconsumo = _to_int(data.get('limite_sobreconsumo'))
    if limite_sobreconsumo is None or limite_sobreconsumo < 0:
        raise ValidationError("El límite de sobreconsumo debe ser positivo", field='limite_sobreconsumo')

    multa_mora = _to_float(data.get('multa_mora'))
    if multa_mora is None or multa_mora < 0:
        raise ValidationError("La multa por mora debe ser positiva", field='multa_mora')

    porcentaje_subsidio = _to_float(data.get('porcentaje_subsidio'))
    if porcentaje_subsidio is not None:
        if porcentaje_subsidio < 0 or porcentaje_subsidio > 1:
            raise ValidationError(
                "El porcentaje de subsidio debe estar entre 0.0 y 1.0",
                field='porcentaje_subsidio'
            )

    tope_subsidio_m3 = _to_int(data.get('tope_subsidio_m3'))
    if tope_subsidio_m3 is None or tope_subsidio_m3 < 0:
        raise ValidationError("El tope de subsidio debe ser positivo", field='tope_subsidio_m3')

    vigente_desde = _to_date(data.get('vigente_desde'))

    # Desactivar tarifa anterior
    anterior = TariffConfig.query.filter_by(activo=True).first()
    if anterior:
        anterior.activo = False
        anterior.updated_by_id = user_id

    # Crear nueva tarifa activa
    tariff = TariffConfig(
        cargo_fijo=cargo_fijo,
        valor_m3_base=valor_m3_base,
        limite_sobreconsumo=limite_sobreconsumo,
        valor_m3_sobreconsumo=valor_m3_sobreconsumo,
        multa_mora=multa_mora,
        porcentaje_subsidio=porcentaje_subsidio,
        tope_subsidio_m3=tope_subsidio_m3,
        activo=True,
        vigente_desde=vigente_desde,
        observaciones=data.get('observaciones', '').strip() or None,
        created_by_id=user_id,
        updated_by_id=user_id,
    )

    db.session.add(tariff)
    db.session.commit()
    return tariff


def update_tariff(tariff_id: int, data: dict, user_id: int) -> TariffConfig:
    """Actualiza campos de una tarifa existente.

    Regla: solo se puede editar si es la activa. Si se necesita
    cambiar valores históricos, crear una nueva configuración.
    """
    tariff = get_tariff_by_id(tariff_id)

    if not tariff.activo:
        raise BusinessRuleError(
            "Solo se puede editar la configuración de tarifa activa. "
            "Para cambiar valores, cree una nueva configuración."
        )

    updatable = [
        'cargo_fijo', 'valor_m3_base', 'limite_sobreconsumo',
        'valor_m3_sobreconsumo', 'multa_mora', 'tope_subsidio_m3',
        'observaciones',
    ]

    for field in updatable:
        if field in data:
            val = data[field]
            if field == 'observaciones':
                val = val.strip() if isinstance(val, str) else val
            setattr(tariff, field, val)

    if 'porcentaje_subsidio' in data:
        val = _to_float(data['porcentaje_subsidio'])
        if val is not None and (val < 0 or val > 1):
            raise ValidationError("Porcentaje de subsidio debe estar entre 0.0 y 1.0", field='porcentaje_subsidio')
        tariff.porcentaje_subsidio = val

    if 'vigente_desde' in data:
        tariff.vigente_desde = _to_date(data['vigente_desde'])

    tariff.updated_by_id = user_id
    db.session.commit()
    return tariff


# ══════════════════════════════════════════════════════════════
# CONSULTA DE BOLETAS (DataTables + Detalle)
# ══════════════════════════════════════════════════════════════

def get_bill_by_id(bill_id: int) -> Bill:
    bill = _get_bill_query().get(bill_id)
    if not bill:
        raise NotFoundError("Boleta", bill_id)
    return bill


def search_bills(
    term: str = None,
    periodo: str = None,
    status: BillStatus = None,
    partner_id: int = None,
    page: int = 1,
    per_page: int = 25,
    order_by: str = 'periodo',
    order_dir: str = 'desc',
) -> Tuple[List[Bill], int]:
    """Búsqueda paginada de boletas con filtros combinados. Para DataTables."""
    query = _get_bill_query()

    if term:
        term_clean = f"%{term.strip()}%"
        query = query.join(Partner, Bill.partner_id == Partner.id).filter(or_(
            Partner.nombre.ilike(term_clean),
            Partner.rut.ilike(term_clean),
        )).distinct()

    if periodo:
        query = query.filter(Bill.periodo == periodo)

    if status:
        query = query.filter(Bill.status == status)

    if partner_id:
        query = query.filter(Bill.partner_id == partner_id)

    order_map = {
        'periodo': Bill.periodo,
        'fecha_emision': Bill.fecha_emision,
        'monto_total': Bill.monto_total,
        'fecha_vencimiento': Bill.fecha_vencimiento,
        'created_at': Bill.created_at,
    }
    order_col = order_map.get(order_by, Bill.periodo)
    query = query.order_by(desc(order_col) if order_dir == 'desc' else asc(order_col))

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return pagination.items, pagination.total


def get_bills_for_partner(partner_id: int, limit: int = 6) -> List[Bill]:
    """Últimas boletas de un socio (para detalle/ficha y portal)."""
    return Bill.query.filter(
        Bill.partner_id == partner_id,
        Bill.status != BillStatus.ANULADA,
    ).order_by(desc(Bill.periodo)).limit(limit).all()


def get_partner_outstanding_balance(partner_id: int) -> int:
    """Saldo pendiente total de un socio (suma de boletas no pagadas, CLP)."""
    result = db.session.query(func.coalesce(func.sum(Bill.monto_total), 0)).filter(
        Bill.partner_id == partner_id,
        Bill.status.in_([BillStatus.EMITIDA, BillStatus.VENCIDA]),
    ).scalar()
    return int(result)


# ══════════════════════════════════════════════════════════════
# PREVISUALIZACIÓN DE CIERRE DE MES
# ══════════════════════════════════════════════════════════════

def get_billing_preview(periodo: str) -> Dict[str, Any]:
    """Genera un preview de lo que produciría el cierre de mes.

    Retorna:
        - Resumen de tarifa activa.
        - Socios con lectura lista para facturar.
        - Socios sin lectura (warnings).
        - Monto estimado total.
        - Si el periodo ya tiene boletas emitidas.
    """
    tariff = get_active_tariff()
    if not tariff:
        raise BusinessRuleError(
            "No hay configuración de tarifa activa. "
            "Configure tarifas antes de ejecutar el cierre."
        )

    # Socios facturables
    partners = Partner.query.filter(
        Partner.estado.in_([PartnerStatus.ACTIVO, PartnerStatus.CORTADO])
    ).all()

    # Lecturas del periodo (VALIDADA o PENDIENTE)
    readings_map = {}
    readings = Reading.query.filter(
        Reading.periodo == periodo,
        Reading.status.in_([ReadingStatus.VALIDADA, ReadingStatus.PENDIENTE]),
    ).all()
    for r in readings:
        readings_map[r.partner_id] = r

    # Boletas ya emitidas para este periodo
    existing_count = Bill.query.filter(
        Bill.periodo == periodo,
        Bill.status != BillStatus.ANULADA,
    ).count()

    # Clasificar
    con_lectura = []
    sin_lectura = []
    estimated_total = 0.0

    for p in partners:
        reading = readings_map.get(p.id)
        if reading:
            # Simular cálculo
            consumo = reading.consumo_real
            consumo_basico = min(consumo, tariff.limite_sobreconsumo)
            consumo_exc = max(0, consumo - tariff.limite_sobreconsumo)
            monto_fijo = tariff.cargo_fijo
            monto_basico = round(consumo_basico * tariff.valor_m3_base)
            monto_sobre = round(consumo_exc * tariff.valor_m3_sobreconsumo)

            subsidio_pct = tariff.porcentaje_subsidio or 0
            monto_sub = 0
            if subsidio_pct > 0 and consumo > 0:
                m3_sub = min(consumo, tariff.tope_subsidio_m3)
                monto_sub = round(m3_sub * tariff.valor_m3_base * subsidio_pct)

            # Verificar mora
            incluir_mora = _partner_tiene_mora(p.id)
            mora = tariff.multa_mora if incluir_mora else 0

            total = max(0, round(monto_fijo + monto_basico + monto_sobre - monto_sub + mora))
            estimated_total += total

            con_lectura.append({
                'partner_id': p.id,
                'nombre': p.nombre,
                'rut': p.rut,
                'consumo_m3': consumo,
                'monto_estimado': total,
                'reading_status': reading.status.value,
                'tiene_mora': incluir_mora,
            })
        else:
            sin_lectura.append({
                'partner_id': p.id,
                'nombre': p.nombre,
                'rut': p.rut,
                'estado': p.estado.value,
            })

    return {
        'periodo': periodo,
        'tarifa': tariff.to_dict(),
        'total_partners': len(partners),
        'partners_con_lectura': len(con_lectura),
        'partners_sin_lectura': len(sin_lectura),
        'detalle_con_lectura': con_lectura,
        'detalle_sin_lectura': sin_lectura,
        'estimated_total': estimated_total,
        'existing_bills': existing_count,
    }


# ══════════════════════════════════════════════════════════════
# MOTOR DE CIERRE DE MES (La operación crítica)
# ══════════════════════════════════════════════════════════════

def execute_monthly_billing(
    periodo: str,
    fecha_emision: date,
    fecha_vencimiento: date,
    user_id: int,
) -> Dict[str, Any]:
    """Ejecuta el cierre de mes: genera boletas masivamente.

    Flujo:
    1. Valida que no existan boletas para el periodo (o las anula si se fuerza).
    2. Obtiene tarifa activa.
    3. Para cada socio facturable (ACTIVO/CORTADO):
       a. Busca lectura VALIDADA o PENDIENTE del periodo.
       b. Si PENDIENTE → la valida automáticamente (admin ejecuta cierre).
       c. Si no hay lectura → agrega a omitidos.
       d. Calcula boleta con snapshot de tarifa.
       e. Verifica mora (boletas vencidas anteriores).
    4. Commit atómico.
    5. Retorna resumen con creadas, omitidas, warnings.

    Args:
        periodo: Mes a facturar (YYYY-MM).
        fecha_emision: Fecha de emisión de las boletas.
        fecha_vencimiento: Fecha límite de pago.
        user_id: Usuario que ejecuta el cierre.

    Returns:
        Dict con resumen del proceso.
    """
    # 1. Verificar si ya existen boletas para este periodo
    existing = Bill.query.filter(
        Bill.periodo == periodo,
        Bill.status != BillStatus.ANULADA,
    ).count()
    if existing > 0:
        raise BusinessRuleError(
            f"Ya existen {existing} boletas emitidas para el periodo {periodo}. "
            f"Anule las existentes primero si desea regenerar."
        )

    # 2. Obtener tarifa activa
    tariff = get_active_tariff()
    if not tariff:
        raise BusinessRuleError(
            "No hay configuración de tarifa activa. "
            "Configure tarifas antes de ejecutar el cierre."
        )

    # 3. Obtener socios facturables
    partners = Partner.query.filter(
        Partner.estado.in_([PartnerStatus.ACTIVO, PartnerStatus.CORTADO])
    ).all()

    # 4. Obtener lecturas del periodo indexadas por partner_id
    readings = Reading.query.filter(
        Reading.periodo == periodo,
        Reading.status.in_([ReadingStatus.VALIDADA, ReadingStatus.PENDIENTE]),
    ).all()
    readings_map = {r.partner_id: r for r in readings}

    # 5. Generar boletas
    creadas = 0
    omitidos = []
    warnings = []
    lecturas_validadas = 0

    try:
        for partner in partners:
            reading = readings_map.get(partner.id)

            if not reading:
                omitidos.append({
                    'partner_id': partner.id,
                    'nombre': partner.nombre,
                    'rut': partner.rut,
                    'razon': 'Sin lectura para el periodo',
                })
                continue

            # Auto-validar lecturas pendientes
            if reading.status == ReadingStatus.PENDIENTE:
                reading.validar(user_id=user_id)
                lecturas_validadas += 1
                warnings.append(
                    f"Lectura pendiente de {partner.nombre} "
                    f"auto-validada durante el cierre."
                )

            # Consumo real (aplica multiplicador del medidor)
            consumo_m3 = reading.consumo_real

            # Verificar mora (boletas vencidas previas)
            incluir_mora = _partner_tiene_mora(partner.id)

            # Obtener lectura anterior para el snapshot
            lectura_anterior = reading.lectura_anterior

            # Crear boleta
            bill = Bill(
                partner_id=partner.id,
                reading_id=reading.id,
                periodo=periodo,
                lectura_anterior=lectura_anterior,
                lectura_actual=reading.lectura_actual,
                consumo_m3=consumo_m3,
                fecha_emision=fecha_emision,
                fecha_vencimiento=fecha_vencimiento,
                status=BillStatus.EMITIDA,
                created_by_id=user_id,
                updated_by_id=user_id,
            )

            # Calcular montos usando el motor del modelo
            bill.calcular_desde_tarifa(
                tarifa=tariff,
                consumo_m3=consumo_m3,
                incluir_mora=incluir_mora,
            )

            db.session.add(bill)
            creadas += 1

        db.session.commit()

    except Exception as e:
        db.session.rollback()
        raise BusinessRuleError(f"Error durante el cierre de mes: {str(e)}")

    return {
        'periodo': periodo,
        'boletas_creadas': creadas,
        'omitidos': omitidos,
        'omitidos_count': len(omitidos),
        'lecturas_auto_validadas': lecturas_validadas,
        'warnings': warnings,
        'tarifa_aplicada': tariff.to_dict(),
    }


# ══════════════════════════════════════════════════════════════
# CICLO DE VIDA DE BOLETAS
# ══════════════════════════════════════════════════════════════

def mark_bill_as_paid(bill_id: int, user_id: int) -> Bill:
    """Registra pago de una boleta individual."""
    bill = get_bill_by_id(bill_id)

    if bill.status == BillStatus.PAGADA:
        raise BusinessRuleError("La boleta ya está pagada.")

    if bill.status == BillStatus.ANULADA:
        raise BusinessRuleError("No se puede pagar una boleta anulada.")

    bill.marcar_pagada(user_id=user_id)
    db.session.commit()
    return bill


def mark_overdue_bills(user_id: int) -> int:
    """Marca como VENCIDA todas las boletas EMITIDA cuya fecha de vencimiento pasó.

    Ejecutar periódicamente (cron job, comando CLI, o al acceder al dashboard).
    Retorna la cantidad de boletas marcadas.
    """
    today = date.today()
    overdue = Bill.query.filter(
        Bill.status == BillStatus.EMITIDA,
        Bill.fecha_vencimiento < today,
    ).all()

    count = 0
    for bill in overdue:
        bill.marcar_vencida(user_id=user_id)
        count += 1

    if count > 0:
        db.session.commit()

    return count


def anular_bill(bill_id: int, motivo: str, user_id: int) -> Bill:
    """Anula una boleta con motivo obligatorio."""
    bill = get_bill_by_id(bill_id)

    if bill.status == BillStatus.ANULADA:
        raise BusinessRuleError("La boleta ya está anulada.")

    if bill.status == BillStatus.PAGADA:
        raise BusinessRuleError(
            "No se puede anular una boleta pagada. "
            "Registre una nota de crédito en su lugar."
        )

    if not motivo or not motivo.strip():
        raise ValidationError("El motivo de anulación es obligatorio", field='motivo')

    bill.anular(user_id=user_id, motivo=motivo.strip())
    db.session.commit()
    return bill


# ══════════════════════════════════════════════════════════════
# ESTADÍSTICAS PARA DASHBOARD (Contrato con partner_service)
# ══════════════════════════════════════════════════════════════

def get_billing_stats(periodo: str = None) -> Dict[str, Any]:
    """Estadísticas de facturación para el Admin Dashboard (Módulo 3).

    Compatible con el contrato de datos de get_admin_stats() en partner_service.
    Retorna: total_recaudado, meta_recaudacion, deudores_mora, monto_mora.
    """
    periodo = periodo or _get_current_periodo()

    # Total recaudado este periodo (pagadas)
    total_recaudado = db.session.query(
        func.coalesce(func.sum(Bill.monto_total), 0)
    ).filter(
        Bill.periodo == periodo,
        Bill.status == BillStatus.PAGADA,
    ).scalar()

    # Meta de recaudación (total emitido, incluye pagadas y pendientes)
    meta_recaudacion = db.session.query(
        func.coalesce(func.sum(Bill.monto_total), 0)
    ).filter(
        Bill.periodo == periodo,
        Bill.status != BillStatus.ANULADA,
    ).scalar()

    # Deudores en mora (socios con al menos una boleta vencida)
    deudores_mora = db.session.query(
        func.count(func.distinct(Bill.partner_id))
    ).filter(
        Bill.status == BillStatus.VENCIDA,
    ).scalar()

    # Monto total en mora
    monto_mora = db.session.query(
        func.coalesce(func.sum(Bill.monto_total), 0)
    ).filter(
        Bill.status == BillStatus.VENCIDA,
    ).scalar()

    return {
        'total_recaudado': int(total_recaudado),
        'meta_recaudacion': int(meta_recaudacion),
        'deudores_mora': int(deudores_mora),
        'monto_mora': int(monto_mora),
    }


# ══════════════════════════════════════════════════════════════
# DATOS PARA PORTAL SOCIO (Contrato con partner_service)
# ══════════════════════════════════════════════════════════════

def get_bills_for_socio_portal(partner_id: int, limit: int = 6) -> List[Dict[str, Any]]:
    """Últimas boletas de un socio para el Portal 'MI APR' (Módulo 3).

    Formato compatible con la sección 'recent_bills' de socio_portal.html.
    """
    bills = Bill.query.filter(
        Bill.partner_id == partner_id,
        Bill.status != BillStatus.ANULADA,
    ).order_by(desc(Bill.periodo)).limit(limit).all()

    return [{
        'periodo': b.periodo_display,
        'consumption': b.consumo_m3,
        'amount': b.monto_total,
        'due_date': b.fecha_vencimiento.isoformat() if b.fecha_vencimiento else None,
        'status': b.status.value,
    } for b in bills]


def get_socio_saldo_pendiente(partner_id: int) -> int:
    """Saldo pendiente de un socio para el Portal (CLP)."""
    return get_partner_outstanding_balance(partner_id)


def get_socio_ultima_boleta(partner_id: int) -> Optional[date]:
    """Fecha de la última boleta emitida de un socio."""
    bill = Bill.query.filter(
        Bill.partner_id == partner_id,
        Bill.status != BillStatus.ANULADA,
    ).order_by(desc(Bill.fecha_emision)).first()
    return bill.fecha_emision if bill else None