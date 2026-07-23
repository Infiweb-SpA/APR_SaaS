# app/services/partner_service.py
"""
Capa de Servicio - Lógica de Negocio para Catastro (Socios, Medidores, Sectores).
Orquesta transacciones, validaciones cruzadas y reglas de negocio complejas.
Versión corregida: helpers de tipado, validación RUT robusta, transacciones atómicas.
"""

from datetime import date, datetime
from typing import Optional, List, Tuple, Dict, Any
from sqlalchemy import or_, func, desc, asc
from sqlalchemy.orm import Query, joinedload
from app import db
from app.models.partner import Partner, Meter, Sector, PartnerStatus, MeterStatus
from app.models.user import User
from app.services.rut_validator import clean_rut, format_rut, validate_rut


# ══════════════════════════════════════════════════════════════
# EXCEPCIONES PERSONALIZADAS
# ══════════════════════════════════════════════════════════════

class PartnerServiceError(Exception):
    """Excepción base para errores de negocio en Partners."""
    def __init__(self, message: str, code: str = 'PARTNER_ERROR', field: str = None):
        self.message = message
        self.code = code
        self.field = field
        super().__init__(message)


class ValidationError(PartnerServiceError):
    def __init__(self, message: str, field: str = None):
        super().__init__(message, code='VALIDATION_ERROR', field=field)


class BusinessRuleError(PartnerServiceError):
    def __init__(self, message: str, code: str = 'BUSINESS_RULE_VIOLATION'):
        super().__init__(message, code=code)


class NotFoundError(PartnerServiceError):
    def __init__(self, entity: str, identifier: Any):
        super().__init__(f"{entity} no encontrado: {identifier}", code='NOT_FOUND')


# ══════════════════════════════════════════════════════════════
# HELPERS PRIVADOS DE TIPADO Y VALIDACIÓN
# ══════════════════════════════════════════════════════════════

def _to_float(val) -> Optional[float]:
    """Convierte a float de forma segura. Retorna None si vacío o inválido."""
    if val in (None, '', 'None'):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _to_int(val) -> Optional[int]:
    """Convierte a int de forma segura. Retorna None si vacío o inválido."""
    if val in (None, '', 'None'):
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _to_date(val) -> date:
    """Convierte a date (ISO 'YYYY-MM-DD' o 'DD/MM/YYYY'). Default: hoy."""
    if not val or val in ('', 'None'):
        return date.today()
    try:
        if '/' in val:
            # Formato DD/MM/YYYY
            day, month, year = map(int, val.split('/'))
            return date(year, month, day)
        # Formato ISO YYYY-MM-DD
        return date.fromisoformat(val)
    except (ValueError, TypeError):
        return date.today()


def _get_partner_query() -> Query:
    """Query base con eager loading estándar para evitar N+1."""
    return Partner.query.options(
        joinedload(Partner.sector_rel),
        joinedload(Partner.user),
        # joinedload(Partner.meters).joinedload(Meter.partner)  # Descomentar si se necesitan medidores siempre
    )


def _get_meter_query() -> Query:
    return Meter.query.options(joinedload(Meter.partner))


def _validate_unique_rut(rut: str, exclude_id: int = None) -> str:
    """Normaliza, valida DV y chequea unicidad en BD. Retorna RUT formateado."""
    cleaned = clean_rut(rut)
    if not validate_rut(cleaned):
        raise ValidationError("El RUT ingresado no es válido (dígito verificador incorrecto)", field='rut')
    
    formatted = format_rut(cleaned)
    query = Partner.query.filter(Partner.rut == formatted)
    if exclude_id:
        query = query.filter(Partner.id != exclude_id)
    
    if query.first():
        raise ValidationError(f"El RUT {formatted} ya está registrado en otro socio", field='rut')
    
    return formatted


def _validate_unique_meter_serie(serie: str, exclude_id: int = None) -> str:
    serie_clean = serie.strip().upper()
    query = Meter.query.filter(Meter.numero_serie == serie_clean)
    if exclude_id:
        query = query.filter(Meter.id != exclude_id)
    if query.first():
        raise ValidationError(f"El Nº Serie {serie_clean} ya existe en catastro de medidores", field='numero_serie')
    return serie_clean


# ══════════════════════════════════════════════════════════════
# SECTORES (Catastro simple)
# ══════════════════════════════════════════════════════════════

def get_sectores_activos() -> List[Sector]:
    return Sector.query.filter_by(activo=True).order_by(Sector.orden_lectura, Sector.nombre).all()


def get_sector_by_id(sector_id: int) -> Sector:
    sector = Sector.query.get(sector_id)
    if not sector:
        raise NotFoundError("Sector", sector_id)
    return sector


def create_sector(data: dict, user_id: int) -> Sector:
    sector = Sector(
        codigo=data['codigo'].strip().upper(),
        nombre=data['nombre'].strip(),
        descripcion=data.get('descripcion'),
        orden_lectura=data.get('orden_lectura', 0),
        activo=True
    )
    db.session.add(sector)
    db.session.commit()
    return sector


# ══════════════════════════════════════════════════════════════
# SOCIOS (PARTNERS) - CRUD Y REGLAS
# ══════════════════════════════════════════════════════════════

def get_partner_by_id(partner_id: int, with_meters: bool = True) -> Partner:
    q = _get_partner_query() if with_meters else Partner.query
    partner = q.get(partner_id)
    if not partner:
        raise NotFoundError("Socio", partner_id)
    return partner


def get_partner_by_rut(rut: str) -> Optional[Partner]:
    formatted = format_rut(clean_rut(rut))
    return Partner.query.filter_by(rut=formatted).first()


def search_partners(
    term: str = None, 
    estado: PartnerStatus = None, 
    sector_id: int = None,
    page: int = 1, 
    per_page: int = 25,
    order_by: str = 'nombre',
    order_dir: str = 'asc'
) -> Tuple[List[Partner], int]:
    """Búsqueda paginada para Listado/DataTables."""
    query = _get_partner_query()
    
    if term:
        term_clean = f"%{term.strip()}%"
        query = query.outerjoin(Meter).filter(or_(
            Partner.rut.ilike(term_clean),
            Partner.nombre.ilike(term_clean),
            Partner.direccion.ilike(term_clean),
            Meter.numero_serie.ilike(term_clean)
        )).distinct()
    
    if estado:
        query = query.filter(Partner.estado == estado)
    
    if sector_id:
        query = query.filter(Partner.sector_id == sector_id)
    
    order_col = getattr(Partner, order_by, Partner.nombre)
    query = query.order_by(desc(order_col) if order_dir == 'desc' else asc(order_col))
    
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return pagination.items, pagination.total


def create_partner(data: dict, user_id: int) -> Partner:
    """
    Crea un nuevo socio con validaciones robustas.
    data: dict plano (request.form.to_dict() o similar)
    """
    from sqlalchemy.exc import IntegrityError
    
    # 1. Validar y normalizar RUT (único)
    rut = _validate_unique_rut(data['rut'])
    
    # 2. Validar sector si se proporciona
    sector_id = _to_int(data.get('sector_id'))
    if sector_id:
        get_sector_by_id(sector_id)  # Lanza NotFoundError si no existe

    # 3. Construir objeto Partner usando helpers seguros
    partner = Partner(
        rut=rut,
        nombre=data.get('nombre', '').strip(),
        nombre_fantasia=data.get('nombre_fantasia', '').strip() or None,
        direccion=data.get('direccion', '').strip(),
        numero=data.get('numero', '').strip() or None,
        complemento=data.get('complemento', '').strip() or None,
        sector_id=sector_id,
        latitud=_to_float(data.get('latitud')),
        longitud=_to_float(data.get('longitud')),
        referencia_ubicacion=data.get('referencia_ubicacion', '').strip() or None,
        telefono=data.get('telefono', '').strip() or None,
        celular=data.get('celular', '').strip() or None,
        email=data.get('email', '').strip().lower() or None,
        estado=PartnerStatus(data.get('estado', 'activo')),
        fecha_ingreso=_to_date(data.get('fecha_ingreso')),
        tipo_conexion=data.get('tipo_conexion', 'domiciliaria'),
        diametro_empalme=data.get('diametro_empalme'),
        observaciones=data.get('observaciones', '').strip() or None,
        created_by_id=user_id,
        updated_by_id=user_id,
    )
    
    # 4. Vincular User existente (opcional)
    user_id_link = _to_int(data.get('user_id'))
    if user_id_link:
        user = User.query.get(user_id_link)
        if not user:
            raise ValidationError("Usuario a vincular no existe", field='user_id')
        # user.partner_profile es dynamic relationship -> .first() para check existencia
        if user.partner_profile.first():
            raise ValidationError("Ese usuario ya tiene un socio asociado", field='user_id')
        if not user.is_active:
            raise ValidationError("Usuario no está activo", field='user_id')
        partner.user_id = user.id
    
    # 5. Persistir
    db.session.add(partner)
    try:
        db.session.commit()
        return partner
    except IntegrityError as e:
        db.session.rollback()
        # Log real en producción: current_app.logger.error(...)
        raise ValidationError("Error de integridad en base de datos (RUT duplicado?)")
    except Exception as e:
        db.session.rollback()
        raise


def update_partner(partner_id: int, data: dict, user_id: int) -> Partner:
    partner = get_partner_by_id(partner_id, with_meters=False)
    
    # Cambio de RUT (validar unicidad)
    if 'rut' in data and data['rut'] != partner.rut:
        partner.rut = _validate_unique_rut(data['rut'], exclude_id=partner_id)
    
    # Campos actualizables directos (strings -> strip or None)
    updatable_fields = [
        'nombre', 'nombre_fantasia', 'direccion', 'numero', 'complemento',
        'referencia_ubicacion', 'telefono', 'celular', 'email',
        'tipo_conexion', 'diametro_empalme', 'observaciones',
    ]
    for field in updatable_fields:
        if field in data:
            val = data[field]
            if isinstance(val, str):
                val = val.strip() or None
            setattr(partner, field, val)
    
    # Coordenadas (float seguro)
    if 'latitud' in data:
        partner.latitud = _to_float(data['latitud'])
    if 'longitud' in data:
        partner.longitud = _to_float(data['longitud'])
    
    # Sector (validar existencia)
    if 'sector_id' in data:
        new_sector_id = _to_int(data['sector_id'])
        partner.sector_id = new_sector_id
        if new_sector_id:
            get_sector_by_id(new_sector_id)
    
    # Cambio de Estado (reglas de negocio)
    if 'estado' in data:
        new_status = PartnerStatus(data['estado'])
        _apply_status_change(partner, new_status, user_id, data)
    
    partner.updated_by_id = user_id
    db.session.commit()
    return partner


def _apply_status_change(partner: Partner, new_status: PartnerStatus, user_id: int, data: dict):
    """Reglas de transición de estado con side-effects."""
    current = partner.estado
    
    if current == new_status:
        return
    
    if new_status == PartnerStatus.BAJA:
        motivo = data.get('motivo_baja', 'Baja administrativa')
        partner.dar_baja(motivo=motivo, user_id=user_id)
        
    elif new_status == PartnerStatus.CORTADO:
        partner.cortar_suministro(user_id=user_id)
        
    elif new_status == PartnerStatus.ACTIVO:
        partner.activar(user_id=user_id)
        
    elif new_status == PartnerStatus.SIN_CONEXION:
        partner.estado = PartnerStatus.SIN_CONEXION
        partner.updated_by_id = user_id
        
    else:
        partner.estado = new_status
        partner.updated_by_id = user_id


# ══════════════════════════════════════════════════════════════
# MEDIDORES (METERS) - GESTIÓN Y CAMBIO (CORE)
# ══════════════════════════════════════════════════════════════

def get_meter_by_id(meter_id: int) -> Meter:
    meter = _get_meter_query().get(meter_id)
    if not meter:
        raise NotFoundError("Medidor", meter_id)
    return meter


def get_meters_available_for_install() -> List[Meter]:
    """Medidores en bodega listos para instalar."""
    return Meter.query.filter(
        Meter.estado.in_([MeterStatus.BODEGA]),
        Meter.partner_id.is_(None)
    ).order_by(Meter.marca, Meter.numero_serie).all()


def create_meter(data: dict, user_id: int) -> Meter:
    """Ingresa medidor a bodega (stock)."""
    serie = _validate_unique_meter_serie(data['numero_serie'])
    
    meter = Meter(
        numero_serie=serie,
        marca=data.get('marca', '').strip().upper() or None,
        modelo=data.get('modelo', '').strip().upper() or None,
        diametro=data.get('diametro'),
        multiplicador=data.get('multiplicador', 1),
        estado=MeterStatus.BODEGA,
        es_actual=False,
        observaciones=data.get('observaciones', '').strip() or None,
        created_by_id=user_id,
        updated_by_id=user_id,
    )
    db.session.add(meter)
    db.session.commit()
    return meter


def update_meter(meter_id: int, data: dict, user_id: int) -> Meter:
    meter = get_meter_by_id(meter_id)
    
    if meter.es_actual:
        raise BusinessRuleError("No se puede editar un medidor actualmente instalado. Retírelo primero.")
    
    if 'numero_serie' in data and data['numero_serie'] != meter.numero_serie:
        meter.numero_serie = _validate_unique_meter_serie(data['numero_serie'], exclude_id=meter_id)
    
    for field in ['marca', 'modelo', 'diametro', 'multiplicador', 'observaciones']:
        if field in data:
            val = data[field]
            if isinstance(val, str):
                val = val.strip().upper() or None
            setattr(meter, field, val)
    
    meter.updated_by_id = user_id
    db.session.commit()
    return meter


# ══════════════════════════════════════════════════════════════
# CAMBIO DE MEDIDOR - LA OPERACIÓN CRÍTICA
# ══════════════════════════════════════════════════════════════

def change_meter(
    partner_id: int,
    new_meter_serie: str,
    lectura_salida_antiguo: int,
    lectura_entrada_nuevo: int,
    fecha_cambio: date,
    user_id: int,
    observaciones: str = None
) -> Tuple[Meter, Meter]:
    """
    Transacción atómica: Retira medidor actual + Instala nuevo.
    Valida coherencia de lecturas.
    Retorna (medidor_retirado, medidor_instalado).
    """
    partner = get_partner_by_id(partner_id)
    old_meter = partner.medidor_activo
    
    if not old_meter:
        raise BusinessRuleError("El socio no tiene medidor actual instalado para cambiar.")
    
    new_meter = Meter.query.filter_by(numero_serie=new_meter_serie.strip().upper()).first()
    if not new_meter:
        raise NotFoundError("Medidor nuevo (Nº Serie)", new_meter_serie)
    if new_meter.estado != MeterStatus.BODEGA or new_meter.partner_id is not None:
        raise BusinessRuleError(f"Medidor {new_meter_serie} no está disponible en bodega (Estado: {new_meter.estado.value})")
    
    if lectura_salida_antiguo < old_meter.lectura_instalacion:
        raise ValidationError(
            f"Lectura de salida ({lectura_salida_antiguo}) no puede ser menor a la de instalación del medidor actual ({old_meter.lectura_instalacion})",
            field='lectura_salida'
        )
    
    try:
        # A. Retirar antiguo
        old_meter.retirar(
            lectura_retiro=lectura_salida_antiguo,
            fecha=fecha_cambio,
            user_id=user_id,
            obs=f"Cambio a medidor {new_meter_serie}. {observaciones or ''}"
        )
        old_meter.estado = MeterStatus.RETIRADO
        
        # B. Instalar nuevo
        new_meter.instalar(
            partner=partner,
            lectura_inicial=lectura_entrada_nuevo,
            fecha=fecha_cambio,
            user_id=user_id,
            obs=f"Cambio desde medidor {old_meter.numero_serie}. {observaciones or ''}"
        )
        
        db.session.commit()
        return old_meter, new_meter
    
    except Exception as e:
        db.session.rollback()
        raise BusinessRuleError(f"Error en transacción de cambio: {str(e)}")


def remove_meter(partner_id: int, lectura_retiro: int, fecha: date, user_id: int, motivo: str) -> Meter:
    """Retira medidor sin instalar uno nuevo (Baja definitiva)."""
    partner = get_partner_by_id(partner_id)
    meter = partner.medidor_activo
    if not meter:
        raise BusinessRuleError("No hay medidor instalado para retirar.")
    
    meter.retirar(lectura_retiro, fecha, user_id, motivo)
    partner.dar_baja(motivo, user_id)
    db.session.commit()
    return meter


# ══════════════════════════════════════════════════════════════
# CONSULTAS ESPECIALES PARA DASHBOARD / PORTAL (Módulo 3)
# ══════════════════════════════════════════════════════════════

def get_admin_stats() -> Dict[str, Any]:
    total = Partner.query.count()
    activos = Partner.query.filter(Partner.estado == PartnerStatus.ACTIVO).count()
    cortados = Partner.query.filter(Partner.estado == PartnerStatus.CORTADO).count()
    sin_conexion = Partner.query.filter(Partner.estado == PartnerStatus.SIN_CONEXION).count()
    
    medidores_instalados = Meter.query.filter_by(es_actual=True).count()
    medidores_bodega = Meter.query.filter_by(estado=MeterStatus.BODEGA, partner_id=None).count()
    
    return {
        'total_socios': total,
        'socios_activos': activos,
        'socios_cortados': cortados,
        'socios_sin_conexion': sin_conexion,
        'medidores_instalados': medidores_instalados,
        'medidores_bodega': medidores_bodega,
        'total_recaudado': 0,
        'meta_recaudacion': 0,
        'pct_lecturas': 0,
        'lecturas_tomadas': 0,
        'lecturas_total': medidores_instalados,
        'deudores_mora': 0,
        'monto_mora': 0,
        'consumo_promedio': 0,
    }


def get_socio_portal_data(user: User) -> Dict[str, Any]:
    if not user.partner_profile.first():
        return {
            'socio': _empty_socio_data(user),
            'consumption_history': [],
            'recent_bills': [],
        }
    
    partner = user.partner_profile.first()
    meter = partner.medidor_activo
    
    socio_data = {
        'nombre': partner.nombre,
        'rut': partner.rut,
        'direccion': partner.direccion_completa,
        'sector': partner.sector_rel.nombre if partner.sector_rel else 'Sin sector',
        'medidor': meter.numero_serie if meter else 'Sin medidor',
        'estado': partner.estado.name.capitalize(),
        'saldo_pendiente': 0,
        'ultima_boleta': None,
        'consumo_actual': 0,
        'consumo_promedio': 0,
    }
    
    if meter and meter.ultima_lectura_valor is not None:
        socio_data['consumo_actual'] = meter.ultima_lectura_valor - meter.lectura_instalacion
    
    return {
        'socio': socio_data,
        'consumption_history': [],
        'recent_bills': [],
    }


def _empty_socio_data(user: User) -> dict:
    return {
        'nombre': user.nombre, 'rut': user.rut,
        'direccion': 'Sin datos aún', 'sector': 'Sin datos aún',
        'medidor': 'Sin datos aún', 'estado': 'Sin conexión',
        'saldo_pendiente': 0, 'ultima_boleta': None,
        'consumo_actual': 0, 'consumo_promedio': 0,
    }