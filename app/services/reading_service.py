"""
Capa de Servicio – Lógica de Negocio para Lecturas de Consumo.
Orquesta captura, validación, sincronización offline, reglas de negocio
y consultas para dashboard (Módulo 3) y facturación (Módulo 6).
"""

from datetime import date, datetime, timedelta
from typing import Optional, List, Tuple, Dict, Any
from sqlalchemy import func, desc, asc, and_, or_, extract
from sqlalchemy.orm import Query, joinedload
from app import db
from app.models.reading import Reading, ReadingStatus
from app.models.partner import Partner, Meter, Sector, PartnerStatus, MeterStatus


# ══════════════════════════════════════════════════════════════
# EXCEPCIONES PERSONALIZADAS
# ══════════════════════════════════════════════════════════════

class ReadingServiceError(Exception):
    """Excepción base para errores de negocio en Lecturas."""
    def __init__(self, message: str, code: str = 'READING_ERROR', field: str = None):
        self.message = message
        self.code = code
        self.field = field
        super().__init__(message)


class ValidationError(ReadingServiceError):
    def __init__(self, message: str, field: str = None):
        super().__init__(message, code='VALIDATION_ERROR', field=field)


class BusinessRuleError(ReadingServiceError):
    def __init__(self, message: str, code: str = 'BUSINESS_RULE_VIOLATION'):
        super().__init__(message, code=code)


class NotFoundError(ReadingServiceError):
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


def _generate_periodo(fecha: date) -> str:
    """Genera el string periodo YYYY-MM a partir de una fecha."""
    return fecha.strftime('%Y-%m')


def _get_current_periodo() -> str:
    """Periodo actual (mes en curso)."""
    return date.today().strftime('%Y-%m')


def _get_reading_query() -> Query:
    """Query base con eager loading estándar."""
    return Reading.query.options(
        joinedload(Reading.meter),
        joinedload(Reading.partner),
        joinedload(Reading.sector),
    )


# ══════════════════════════════════════════════════════════════
# REGLAS DE NEGOCIO – VALIDACIONES DE CONSUMO
# ══════════════════════════════════════════════════════════════

def _get_last_readings(meter_id: int, limit: int = 3) -> List[Reading]:
    """Obtiene las últimas N lecturas VALIDADAS de un medidor (orden descendente)."""
    return Reading.query.filter(
        Reading.meter_id == meter_id,
        Reading.status.in_([ReadingStatus.VALIDADA, ReadingStatus.PENDIENTE]),
    ).order_by(desc(Reading.fecha)).limit(limit).all()


def _calc_avg_consumption(meter_id: int, months: int = 3) -> float:
    """Calcula el consumo promedio de los últimos N meses de un medidor."""
    last = _get_last_readings(meter_id, limit=months)
    if not last:
        return 0.0
    consumos = [r.consumo for r in last if r.consumo is not None]
    if not consumos:
        return 0.0
    return sum(consumos) / len(consumos)


def validate_consumption_rules(meter_id: int, lectura_actual: int, lectura_anterior: int) -> Dict[str, Any]:
    """
    Aplica reglas de validación de consumo.
    Retorna dict con warnings/errors para el frontend.

    Reglas:
    1. Lectura actual >= lectura anterior (no puede retroceder).
    2. Consumo no puede exceder 100% del promedio de los últimos 3 meses.
    3. Consumo negativo → error.
    """
    warnings = []
    errors = []

    consumo = lectura_actual - lectura_anterior

    # Regla 1: Lectura retrocedida
    if lectura_actual < lectura_anterior:
        errors.append(
            f"La lectura ({lectura_actual}) es menor a la anterior ({lectura_anterior}). "
            f"Verifique si el medidor fue cambiado o reiniciado."
        )

    # Regla 2: Consumo > 100% del promedio
    if consumo > 0:
        avg = _calc_avg_consumption(meter_id, months=3)
        if avg > 0 and consumo > avg * 2:
            warnings.append(
                f"Consumo ({consumo} m³) supera el 100% del promedio "
                f"de los últimos 3 meses ({avg:.1f} m³). "
                f"Verifique la lectura en terreno."
            )

    # Regla 3: Consumo negativo (redundante si regla 1 pasa, pero defensivo)
    if consumo < 0:
        errors.append(f"Consumo negativo ({consumo} m³). Revise las lecturas.")

    return {
        'consumo': max(0, consumo),
        'warnings': warnings,
        'errors': errors,
        'avg_consumption': _calc_avg_consumption(meter_id, months=3),
        'is_valid': len(errors) == 0,
    }


# ══════════════════════════════════════════════════════════════
# CAPTURA INDIVIDUAL DE LECTURA
# ══════════════════════════════════════════════════════════════

def get_reading_by_id(reading_id: int) -> Reading:
    reading = _get_reading_query().get(reading_id)
    if not reading:
        raise NotFoundError("Lectura", reading_id)
    return reading


def capture_reading(data: dict, user_id: int) -> Reading:
    """
    Captura una lectura individual desde terreno u oficina.

    data esperado:
        - meter_id (int): ID del medidor
        - lectura_actual (int): Valor del contador
        - fecha (str|date): Fecha de toma (YYYY-MM-DD o DD/MM/YYYY)
        - observaciones (str, opcional)
        - latitud/longitud (float, opcional): GPS
        - offline_id (str, opcional): ID local para sync offline
    """
    # 1. Validar medidor
    meter_id = _to_int(data.get('meter_id'))
    if not meter_id:
        raise ValidationError("El medidor es obligatorio", field='meter_id')

    meter = Meter.query.get(meter_id)
    if not meter:
        raise NotFoundError("Medidor", meter_id)
    if not meter.es_actual or meter.estado != MeterStatus.INSTALADO:
        raise BusinessRuleError(
            f"El medidor {meter.numero_serie} no está instalado actualmente."
        )

    # 2. Validar socio
    partner = meter.partner
    if not partner:
        raise BusinessRuleError(
            f"El medidor {meter.numero_serie} no tiene socio asignado."
        )
    if partner.estado not in (PartnerStatus.ACTIVO, PartnerStatus.CORTADO):
        raise BusinessRuleError(
            f"El socio {partner.nombre} está en estado '{partner.estado.value}' "
            f"y no admite lecturas."
        )

    # 3. Parsear datos
    lectura_actual = _to_int(data.get('lectura_actual'))
    if lectura_actual is None:
        raise ValidationError("La lectura actual es obligatoria", field='lectura_actual')
    if lectura_actual < 0:
        raise ValidationError("La lectura no puede ser negativa", field='lectura_actual')

    fecha = _to_date(data.get('fecha'))
    periodo = _generate_periodo(fecha)

    # 4. Lectura anterior (cache en Meter o última reading)
    lectura_anterior = meter.ultima_lectura_valor
    if lectura_anterior is None:
        lectura_anterior = meter.lectura_instalacion or 0

    # 5. Calcular consumo
    consumo = max(0, lectura_actual - lectura_anterior)

    # 6. Validar unicidad: no puede haber dos lecturas del mismo medidor
    #    en el mismo periodo (salvo anuladas)
    existing = Reading.query.filter(
        Reading.meter_id == meter_id,
        Reading.periodo == periodo,
        Reading.status != ReadingStatus.ANULADA,
    ).first()
    if existing:
        raise BusinessRuleError(
            f"Ya existe una lectura para el medidor {meter.numero_serie} "
            f"en el periodo {periodo}. "
            f"Estado: {existing.status.value}."
        )

    # 7. Verificar reglas de negocio (warnings para el usuario)
    rules = validate_consumption_rules(meter_id, lectura_actual, lectura_anterior)
    if rules['errors']:
        raise BusinessRuleError(rules['errors'][0])

    # 8. Crear Reading
    reading = Reading(
        meter_id=meter.id,
        partner_id=partner.id,
        sector_id=partner.sector_id,
        periodo=periodo,
        fecha=fecha,
        lectura_actual=lectura_actual,
        lectura_anterior=lectura_anterior,
        consumo=consumo,
        multiplicador=meter.multiplicador or 1,
        status=ReadingStatus.PENDIENTE,
        origen=data.get('origen', 'terreno'),
        latitud=_to_float(data.get('latitud')),
        longitud=_to_float(data.get('longitud')),
        observaciones=data.get('observaciones', '').strip() or None,
        offline_id=data.get('offline_id'),
        sincronizado=True,
        es_lectura_inicial=(lectura_anterior == meter.lectura_instalacion),
        created_by_id=user_id,
        updated_by_id=user_id,
    )

    db.session.add(reading)
    db.session.commit()

    return reading


# ══════════════════════════════════════════════════════════════
# SINCRONIZACIÓN OFFLINE (BATCH)
# ══════════════════════════════════════════════════════════════

def sync_offline_readings(readings_data: List[dict], user_id: int) -> Dict[str, Any]:
    """
    Procesa un lote de lecturas capturadas offline.

    readings_data: Lista de dicts con los mismos campos que capture_reading().

    Retorna:
        {
            'synced': int,          # Cantidad sincronizadas OK
            'skipped': int,         # Cantidad omitidas (duplicadas)
            'errors': list,         # Lista de errores por lectura
            'readings': list        # Objetos creados serializados
        }
    """
    synced = 0
    skipped = 0
    errors = []
    created_readings = []

    for i, item in enumerate(readings_data):
        # Skip si ya fue sincronizada (por offline_id)
        offline_id = item.get('offline_id')
        if offline_id:
            exists = Reading.query.filter_by(offline_id=offline_id).first()
            if exists:
                skipped += 1
                continue

        try:
            item['sincronizado'] = True
            reading = capture_reading(item, user_id)
            synced += 1
            created_readings.append(reading.to_dict())
        except BusinessRuleError as e:
            # Duplicado de periodo → skip silencioso
            if 'Ya existe una lectura' in e.message:
                skipped += 1
            else:
                errors.append({
                    'index': i,
                    'offline_id': offline_id,
                    'error': e.message,
                })
        except (ValidationError, NotFoundError) as e:
            errors.append({
                'index': i,
                'offline_id': offline_id,
                'error': e.message,
                'field': getattr(e, 'field', None),
            })
        except Exception as e:
            errors.append({
                'index': i,
                'offline_id': offline_id,
                'error': f'Error inesperado: {str(e)}',
            })

    return {
        'synced': synced,
        'skipped': skipped,
        'errors': errors,
        'readings': created_readings,
    }


# ══════════════════════════════════════════════════════════════
# LISTADO Y CONSULTAS (DataTables + Filtros)
# ══════════════════════════════════════════════════════════════

def search_readings(
    term: str = None,
    periodo: str = None,
    status: ReadingStatus = None,
    sector_id: int = None,
    page: int = 1,
    per_page: int = 25,
    order_by: str = 'fecha',
    order_dir: str = 'desc',
) -> Tuple[List[Reading], int]:
    """Búsqueda paginada de lecturas con filtros combinados."""
    query = _get_reading_query()

    if term:
        term_clean = f"%{term.strip()}%"
        query = query.join(Meter, Reading.meter_id == Meter.id).outerjoin(
            Partner, Reading.partner_id == Partner.id
        ).filter(or_(
            Partner.nombre.ilike(term_clean),
            Partner.rut.ilike(term_clean),
            Meter.numero_serie.ilike(term_clean),
        )).distinct()

    if periodo:
        query = query.filter(Reading.periodo == periodo)

    if status:
        query = query.filter(Reading.status == status)

    if sector_id:
        query = query.filter(Reading.sector_id == sector_id)

    # Ordenamiento
    order_map = {
        'fecha': Reading.fecha,
        'periodo': Reading.periodo,
        'consumo': Reading.consumo,
        'created_at': Reading.created_at,
    }
    order_col = order_map.get(order_by, Reading.fecha)
    query = query.order_by(desc(order_col) if order_dir == 'desc' else asc(order_col))

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return pagination.items, pagination.total


def get_readings_for_capture(
    sector_id: int = None,
    periodo: str = None,
) -> List[Dict[str, Any]]:
    """
    Genera la lista de medidores para captura en terreno,
    ordenada por sector/orden de lectura.

    Retorna lista de dicts con datos del socio, medidor,
    última lectura, y estado de captura para el periodo.
    """
    from sqlalchemy.orm import contains_eager

    periodo = periodo or _get_current_periodo()

    # Base: medidores instalados activos con socio asignado
    query = Meter.query.filter(
        Meter.es_actual == True,
        Meter.estado == MeterStatus.INSTALADO,
        Meter.partner_id.isnot(None),
    )

    # JOIN único a Partner y Sector (evita duplicados)
    query = query.join(Meter.partner)
    query = query.join(Partner.sector_rel, isouter=True)

    if sector_id:
        query = query.filter(Partner.sector_id == sector_id)

    # Ordenar por sector → orden_lectura → nombre socio
    query = query.order_by(
        Sector.orden_lectura.asc().nullslast(),
        Partner.nombre.asc(),
    )

    # Indicar al ORM que el JOIN ya existe, use los datos directamente
    query = query.options(
        contains_eager(Meter.partner).contains_eager(Partner.sector_rel),
    )

    meters = query.all()
    result = []

    for meter in meters:
        partner = meter.partner
        if not partner:
            continue

        # Verificar si ya tiene lectura para este periodo
        existing = Reading.query.filter(
            Reading.meter_id == meter.id,
            Reading.periodo == periodo,
            Reading.status != ReadingStatus.ANULADA,
        ).first()

        lectura_anterior = meter.ultima_lectura_valor or meter.lectura_instalacion or 0

        result.append({
            'meter_id': meter.id,
            'partner_id': partner.id,
            'partner_nombre': partner.nombre,
            'partner_rut': partner.rut,
            'direccion': partner.direccion_completa,
            'sector': partner.sector_rel.nombre if partner.sector_rel else 'Sin sector',
            'sector_id': partner.sector_id,
            'orden_lectura': partner.sector_rel.orden_lectura if partner.sector_rel else 0,
            'meter_serie': meter.numero_serie,
            'lectura_anterior': lectura_anterior,
            'lectura_actual': existing.lectura_actual if existing else None,
            'consumo': existing.consumo if existing else None,
            'status': existing.status.value if existing else None,
            'reading_id': existing.id if existing else None,
            'capturado': existing is not None,
        })

    return result


# ══════════════════════════════════════════════════════════════
# VALIDACIÓN / APROBACIÓN / RECHAZO (Admin)
# ══════════════════════════════════════════════════════════════

def validate_reading(reading_id: int, user_id: int) -> Reading:
    """Aprueba una lectura pendiente y actualiza cache en Meter."""
    reading = get_reading_by_id(reading_id)

    if reading.status != ReadingStatus.PENDIENTE:
        raise BusinessRuleError(
            f"Solo se pueden validar lecturas pendientes. "
            f"Estado actual: {reading.status.value}."
        )

    reading.validar(user_id=user_id)
    db.session.commit()
    return reading


def reject_reading(reading_id: int, motivo: str, user_id: int) -> Reading:
    """Rechaza una lectura con motivo obligatorio."""
    reading = get_reading_by_id(reading_id)

    if reading.status not in (ReadingStatus.PENDIENTE, ReadingStatus.VALIDADA):
        raise BusinessRuleError(
            f"No se puede rechazar una lectura en estado '{reading.status.value}'."
        )

    if not motivo or not motivo.strip():
        raise ValidationError("El motivo de rechazo es obligatorio", field='motivo_rechazo')

    reading.rechazar(motivo=motivo.strip(), user_id=user_id)
    db.session.commit()
    return reading


def validate_batch(reading_ids: List[int], user_id: int) -> Dict[str, int]:
    """Aprueba un lote de lecturas pendientes."""
    validated = 0
    errors = 0

    for rid in reading_ids:
        try:
            validate_reading(rid, user_id)
            validated += 1
        except Exception:
            errors += 1

    return {'validated': validated, 'errors': errors}


# ══════════════════════════════════════════════════════════════
# ESTADÍSTICAS PARA DASHBOARD (Módulo 3)
# ══════════════════════════════════════════════════════════════

def get_lecturas_stats(periodo: str = None) -> Dict[str, Any]:
    """
    Calcula estadísticas de lecturas para el dashboard admin.
    Compatible con el contrato de datos de get_admin_stats() en partner_service.
    """
    periodo = periodo or _get_current_periodo()

    # Total medidores instalados (deberían tener lectura)
    total_medidores = Meter.query.filter(
        Meter.es_actual == True,
        Meter.estado == MeterStatus.INSTALADO,
    ).count()

    # Lecturas capturadas este periodo
    lecturas_capturadas = Reading.query.filter(
        Reading.periodo == periodo,
        Reading.status != ReadingStatus.ANULADA,
    ).count()

    # Lecturas validadas
    lecturas_validadas = Reading.query.filter(
        Reading.periodo == periodo,
        Reading.status == ReadingStatus.VALIDADA,
    ).count()

    # Lecturas pendientes
    lecturas_pendientes = Reading.query.filter(
        Reading.periodo == periodo,
        Reading.status == ReadingStatus.PENDIENTE,
    ).count()

    # Lecturas rechazadas
    lecturas_rechazadas = Reading.query.filter(
        Reading.periodo == periodo,
        Reading.status == ReadingStatus.RECHAZADA,
    ).count()

    # Porcentaje de avance
    pct = round((lecturas_capturadas / total_medidores * 100), 1) if total_medidores > 0 else 0

    # Consumo promedio del periodo
    avg_consumo = db.session.query(func.avg(Reading.consumo)).filter(
        Reading.periodo == periodo,
        Reading.status.in_([ReadingStatus.VALIDADA, ReadingStatus.PENDIENTE]),
    ).scalar() or 0

    return {
        'periodo': periodo,
        'total_medidores': total_medidores,
        'lecturas_tomadas': lecturas_capturadas,
        'lecturas_validadas': lecturas_validadas,
        'lecturas_pendientes': lecturas_pendientes,
        'lecturas_rechazadas': lecturas_rechazadas,
        'pct_lecturas': pct,
        'consumo_promedio': round(float(avg_consumo), 1),
    }


# ══════════════════════════════════════════════════════════════
# HISTORIAL DE CONSUMO PARA PORTAL SOCIO (Módulo 3)
# ══════════════════════════════════════════════════════════════

def get_consumption_history(meter_id: int, months: int = 12) -> List[Dict[str, Any]]:
    """
    Historial de consumo de un medidor para el gráfico del Portal Socio.
    Retorna lista de dicts compatible con Chart.js (labels + data).
    """
    readings = Reading.query.filter(
        Reading.meter_id == meter_id,
        Reading.status.in_([ReadingStatus.VALIDADA, ReadingStatus.PENDIENTE]),
    ).order_by(desc(Reading.fecha)).limit(months).all()

    # Invertir para orden cronológico
    readings.reverse()

    return [{
        'periodo': r.periodo,
        'label': r.periodo_display,
        'consumo': r.consumo,
        'consumo_real': r.consumo_real,
        'lectura': r.lectura_actual,
        'fecha': r.fecha.isoformat() if r.fecha else None,
    } for r in readings]


def get_partner_readings_summary(partner_id: int) -> Dict[str, Any]:
    """Resumen de lecturas de un socio para la ficha detail (Módulo 4)."""
    partner = Partner.query.get(partner_id)
    if not partner:
        raise NotFoundError("Socio", partner_id)

    meter = partner.medidor_activo
    if not meter:
        return {
            'lecturas_count': 0,
            'consumo_total': 0,
            'consumo_promedio': 0,
            'ultima_lectura': None,
            'history': [],
        }

    total_readings = Reading.query.filter(
        Reading.meter_id == meter.id,
        Reading.status != ReadingStatus.ANULADA,
    ).count()

    # Consumo total acumulado
    total_consumo = db.session.query(func.sum(Reading.consumo)).filter(
        Reading.meter_id == meter.id,
        Reading.status.in_([ReadingStatus.VALIDADA, ReadingStatus.PENDIENTE]),
    ).scalar() or 0

    # Últimas 12 lecturas para historial
    history = get_consumption_history(meter.id, months=12)

    avg = round(total_consumo / total_readings, 1) if total_readings > 0 else 0

    ultima = Reading.query.filter(
        Reading.meter_id == meter.id,
        Reading.status != ReadingStatus.ANULADA,
    ).order_by(desc(Reading.fecha)).first()

    return {
        'lecturas_count': total_readings,
        'consumo_total': total_consumo,
        'consumo_promedio': avg,
        'ultima_lectura': ultima.to_dict() if ultima else None,
        'history': history,
    }


# ══════════════════════════════════════════════════════════════
# ACTUALIZACIÓN DE CONTRATOS (Módulo 3 – partner_service)
# ══════════════════════════════════════════════════════════════

def get_consumption_history_for_portal(meter_id: int, months: int = 12) -> List[Dict[str, Any]]:
    """
    Versión simplificada para get_socio_portal_data() en partner_service.
    Retorna formato compatible con Chart.js del socio_portal.html.
    """
    raw = get_consumption_history(meter_id, months)
    return [{'month': r['label'], 'consumption': r['consumo']} for r in raw]