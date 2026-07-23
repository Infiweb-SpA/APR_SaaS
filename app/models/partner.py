# app/models/partner.py
"""
Modelos de Catastro: Socios (Partner), Medidores (Meter) y Sectores.
Relación: Sector 1:N Partner 1:N Meter.
Integración: Partner 1:1 User (opcional, para portal socio).
"""

import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Date, Float, Boolean,
    ForeignKey, Enum as SQLEnum, Index, UniqueConstraint, CheckConstraint
)
from sqlalchemy.orm import relationship, validates, declared_attr
from sqlalchemy.ext.hybrid import hybrid_property

from app import db
from app.services.rut_validator import clean_rut, format_rut, validate_rut


# ══════════════════════════════════════════════════════════════
# ENUMS DE ESTADO (Tipados para DB y Python)
# ══════════════════════════════════════════════════════════════

class PartnerStatus(str, enum.Enum):
    """Estados del Socio en el Catastro."""
    ACTIVO = 'activo'           # Servicio normal, facturable
    CORTADO = 'cortado'         # Corte por mora (gestión POS)
    BAJA = 'baja'               # Desconexión definitiva / Renuncia
    SIN_CONEXION = 'sin_conexion' # Empalme pagado, pendiente instalación


class MeterStatus(str, enum.Enum):
    """Estados físicos/administrativos del Medidor."""
    BODEGA = 'bodega'           # Stock, sin instalar
    INSTALADO = 'instalado'     # Funcionando en terreno (es_actual=True)
    RETIRADO = 'retirado'       # Sacado de terreno, pendiente revisión
    REPARACION = 'reparacion'   # En taller proveedor
    BAJA = 'baja'               # Dado de baja definitiva (vida útil agotada)


# ══════════════════════════════════════════════════════════════
# MODELO SECTOR (Catastro Geográfico/Administrativo)
# ══════════════════════════════════════════════════════════════

class Sector(db.Model):
    """Sectores/Zonas de lectura y facturación. Normaliza 'sector' en Partner."""
    __tablename__ = 'sectors'
    __table_args__ = (
        Index('ix_sector_codigo', 'codigo', unique=True),
    )

    id = Column(Integer, primary_key=True)
    codigo = Column(String(10), nullable=False, unique=True, comment="Código corto ej: 'SEC-01', 'URB-05'")
    nombre = Column(String(100), nullable=False, comment="Nombre legible ej: 'Sector Centro', 'Villa Los Andes'")
    descripcion = Column(Text, nullable=True)
    orden_lectura = Column(Integer, default=0, comment="Orden en ruta de operario")
    activo = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relación inversa
    partners = relationship('Partner', back_populates='sector_rel', lazy='dynamic')

    def __repr__(self):
        return f"<Sector {self.codigo}: {self.nombre}>"

    def to_dict(self):
        return {'id': self.id, 'codigo': self.codigo, 'nombre': self.nombre, 'activo': self.activo}


# ══════════════════════════════════════════════════════════════
# MODELO PARTNER (Ficha Única del Socio)
# ══════════════════════════════════════════════════════════════

class Partner(db.Model):
    """Catastro maestro de socios / conexiones."""
    __tablename__ = 'partners'
    __table_args__ = (
        Index('ix_partner_rut', 'rut', unique=True),
        Index('ix_partner_estado', 'estado'),
        Index('ix_partner_sector', 'sector_id'),
        CheckConstraint("length(rut) >= 8", name='ck_partner_rut_len'),
    )

    # ── PK & Auditoría ──────────────────────────────────────
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by_id = Column(Integer, ForeignKey('users.id'), nullable=True)  # User creador
    updated_by_id = Column(Integer, ForeignKey('users.id'), nullable=True)  # User último editor

    # ── Identificación ──────────────────────────────────────
    rut = Column(String(12), nullable=False, unique=True, comment="Formato canónico XX.XXX.XXX-K")
    nombre = Column(String(150), nullable=False, index=True)
    nombre_fantasia = Column(String(150), nullable=True, comment="Para personas jurídicas")

    # ── Ubicación ───────────────────────────────────────────
    direccion = Column(String(250), nullable=False)
    numero = Column(String(10), nullable=True)
    complemento = Column(String(100), nullable=True, comment="Depto, Block, Casa 2, etc.")
    sector_id = Column(Integer, ForeignKey('sectors.id'), nullable=True, index=True)
    latitud = Column(Float, nullable=True, comment="WGS84 GPS")
    longitud = Column(Float, nullable=True)
    referencia_ubicacion = Column(Text, nullable=True, comment="Cercano a..., color portón, etc.")

    # ── Contacto ────────────────────────────────────────────
    telefono = Column(String(20), nullable=True)
    celular = Column(String(20), nullable=True, index=True)
    email = Column(String(120), nullable=True)

    # ── Estado y Clasificación ──────────────────────────────
    estado = Column(SQLEnum(PartnerStatus), default=PartnerStatus.ACTIVO, nullable=False, index=True)
    fecha_ingreso = Column(Date, nullable=True, default=datetime.utcnow)
    fecha_baja = Column(Date, nullable=True)
    motivo_baja = Column(Text, nullable=True)
    tipo_conexion = Column(String(30), default='domiciliaria', nullable=False, comment="domiciliaria, industrial, publica, agricola")
    diametro_empalme = Column(String(10), nullable=True, comment="1/2\", 3/4\", 1\"" )

    # ── Vinculación Usuario Portal (Módulo 2) ───────────────
    user_id = Column(Integer, ForeignKey('users.id'), unique=True, nullable=True, index=True)

    # ── Observaciones ───────────────────────────────────────
    observaciones = Column(Text, nullable=True)

    # ── RELACIONES ──────────────────────────────────────────
    sector_rel = relationship('Sector', back_populates='partners', lazy='joined')
    user = relationship('User', backref='partner_profile', lazy='joined', foreign_keys=[user_id])
    meters = relationship('Meter', back_populates='partner', lazy='dynamic', order_by='desc(Meter.fecha_instalacion)')
    
    # Relaciones auditoría (opcional, requiere User model cargado)
    created_by = relationship('User', foreign_keys=[created_by_id], lazy='selectin')
    updated_by = relationship('User', foreign_keys=[updated_by_id], lazy='selectin')

    # ── VALIDADORES / SETTERS ───────────────────────────────
    @validates('rut')
    def _validate_rut(self, key, value):
        if not value:
            raise ValueError("RUT es obligatorio")
        cleaned = clean_rut(value)
        if not validate_rut(cleaned):
            raise ValueError(f"RUT inválido: {value}")
        # Guardamos SIEMPRE formato canónico
        return format_rut(cleaned)

    @validates('email')
    def _validate_email(self, key, value):
        if value and '@' not in value:
            raise ValueError("Email inválido")
        return value.lower().strip() if value else None

    # ── PROPIEDADES HÍBRIDAS / HELPERS ──────────────────────

    @hybrid_property
    def medidor_activo(self):
        """Retorna el Meter con es_actual=True (o el más reciente instalado)."""
        # Usamos la relación dinámica filtrada
        return self.meters.filter_by(es_actual=True).first()

    @hybrid_property
    def lectura_actual(self):
        """Lectura base del medidor actual para cálculo de consumo."""
        m = self.medidor_activo
        return m.lectura_instalacion if m else 0

    @property
    def direccion_completa(self):
        """Formato legible para boletas/impresión."""
        parts = [self.direccion]
        if self.numero: parts.append(self.numero)
        if self.complemento: parts.append(self.complemento)
        if self.sector_rel: parts.append(f"({self.sector_rel.nombre})")
        return ", ".join(parts)

    @property
    def esta_activo_para_facturar(self):
        """Regla de negocio: ¿Genera boleta este mes?"""
        return self.estado in (PartnerStatus.ACTIVO, PartnerStatus.CORTADO)

    @property
    def iniciales_nombre(self):
        """Para avatar en UI."""
        return "".join([n[0].upper() for n in self.nombre.split() if n][:2])

    # ── MÉTODOS DE INSTANCIA ────────────────────────────────

    def activar(self, user_id=None):
        self.estado = PartnerStatus.ACTIVO
        self.fecha_baja = None
        self.motivo_baja = None
        if user_id: self.updated_by_id = user_id

    def dar_baja(self, motivo, user_id=None):
        self.estado = PartnerStatus.BAJA
        self.fecha_baja = datetime.utcnow().date()
        self.motivo_baja = motivo
        if user_id: self.updated_by_id = user_id
        # Desactivar medidor actual si existe
        if self.medidor_activo:
            self.medidor_activo.retirar(lectura_retiro=0, user_id=user_id) # Lectura 0 por defecto, service la sobrescribe

    def cortar_suministro(self, user_id=None):
        if self.esta_activo_para_facturar:
            self.estado = PartnerStatus.CORTADO
            if user_id: self.updated_by_id = user_id

    def reconectar(self, user_id=None):
        if self.estado == PartnerStatus.CORTADO:
            self.estado = PartnerStatus.ACTIVO
            if user_id: self.updated_by_id = user_id

    def to_dict(self, include_meters=False):
        """Serialización para API/JS."""
        data = {
            'id': self.id,
            'rut': self.rut,
            'nombre': self.nombre,
            'nombre_fantasia': self.nombre_fantasia,
            'direccion': self.direccion_completa,
            'direccion_raw': self.direccion,
            'numero': self.numero,
            'complemento': self.complemento,
            'sector': self.sector_rel.to_dict() if self.sector_rel else None,
            'coordenadas': {'lat': self.latitud, 'lng': self.longitud} if self.latitud and self.longitud else None,
            'telefono': self.telefono,
            'celular': self.celular,
            'email': self.email,
            'estado': self.estado.value,
            'estado_label': self.estado.name.capitalize(),
            'fecha_ingreso': self.fecha_ingreso.isoformat() if self.fecha_ingreso else None,
            'tipo_conexion': self.tipo_conexion,
            'diametro_empalme': self.diametro_empalme,
            'medidor_activo': self.medidor_activo.to_dict() if self.medidor_activo else None,
            'user_id': self.user_id,
            'observaciones': self.observaciones,
        }
        if include_meters:
            data['medidores_historial'] = [m.to_dict() for m in self.meters]
        return data

    def __repr__(self):
        return f"<Partner {self.rut} - {self.nombre} ({self.estado.value})>"


# ══════════════════════════════════════════════════════════════
# MODELO METER (Historial de Medidores del Socio)
# ══════════════════════════════════════════════════════════════

class Meter(db.Model):
    """Medidor de agua. Un socio tiene historial 1:N. Solo uno con es_actual=True."""
    __tablename__ = 'meters'
    __table_args__ = (
        Index('ix_meter_serie', 'numero_serie', unique=True),
        Index('ix_meter_partner_actual', 'partner_id', 'es_actual'),
        CheckConstraint('lectura_retiro IS NULL OR lectura_retiro >= lectura_instalacion', name='ck_meter_lecturas_validas'),
    )

    # ── PK & Auditoría ──────────────────────────────────────
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    updated_by_id = Column(Integer, ForeignKey('users.id'), nullable=True)

    # ── Identificación Física ───────────────────────────────
    numero_serie = Column(String(30), nullable=False, unique=True, index=True, comment="Nº Serie físico del fabricante")
    marca = Column(String(50), nullable=True)
    modelo = Column(String(50), nullable=True)
    diametro = Column(String(10), nullable=True, comment="Ej: 1/2\", 3/4\"")
    multiplicador = Column(Integer, default=1, nullable=False, comment="Factor multiplicador (ej: 1, 10, 100)")

    # ── Estado y Ubicación Lógica ───────────────────────────
    estado = Column(SQLEnum(MeterStatus), default=MeterStatus.BODEGA, nullable=False, index=True)
    es_actual = Column(Boolean, default=False, nullable=False, index=True, comment="Indica si está instalado y facturando AHORA")
    partner_id = Column(Integer, ForeignKey('partners.id'), nullable=True, index=True, comment="NULL si está en bodega")

    # ── Fechas y Lecturas de Ciclo de Vida ──────────────────
    fecha_instalacion = Column(Date, nullable=True)
    lectura_instalacion = Column(Integer, default=0, nullable=False, comment="Lectura índice al instalar")
    fecha_retiro = Column(Date, nullable=True)
    lectura_retiro = Column(Integer, nullable=True, comment="Lectura índice al retirar")
    fecha_ultima_lectura = Column(Date, nullable=True, comment="Cache: última reading registrada (Módulo 5)")
    ultima_lectura_valor = Column(Integer, nullable=True, comment="Cache: valor última reading")

    # ── Observaciones ───────────────────────────────────────
    observaciones = Column(Text, nullable=True)
    observaciones_instalacion = Column(Text, nullable=True)
    observaciones_retiro = Column(Text, nullable=True)

    # ── RELACIONES ──────────────────────────────────────────
    partner = relationship('Partner', back_populates='meters', lazy='joined')
    created_by = relationship('User', foreign_keys=[created_by_id], lazy='selectin')
    updated_by = relationship('User', foreign_keys=[updated_by_id], lazy='selectin')
    # readings = relationship('Reading', back_populates='meter', lazy='dynamic') # Módulo 5

    # ── VALIDADORES ─────────────────────────────────────────
    @validates('numero_serie')
    def _validate_serie(self, key, value):
        if not value:
            raise ValueError("Nº Serie es obligatorio")
        return value.strip().upper()

    @validates('lectura_instalacion', 'lectura_retiro')
    def _validate_lecturas(self, key, value):
        if value is not None and value < 0:
            raise ValueError("Lectura no puede ser negativa")
        return value

    # ── PROPIEDADES ─────────────────────────────────────────
    @hybrid_property
    def consumo_acumulado_actual(self):
        """Consumo desde instalación hasta hoy (o retiro)."""
        if self.ultima_lectura_valor is not None:
            return self.ultima_lectura_valor - self.lectura_instalacion
        if self.lectura_retiro is not None:
            return self.lectura_retiro - self.lectura_instalacion
        return 0

    @property
    def esta_en_terreno(self):
        return self.estado == MeterStatus.INSTALADO and self.es_actual

    # ── MÉTODOS DE CICLO DE VIDA (Llamados desde Service) ───

    def instalar(self, partner: Partner, lectura_inicial: int, fecha=None, user_id=None, obs=None):
        """Instala este medidor en un socio."""
        # NOTA: La capa de servicio (install_first_meter / change_meter) se encarga
        # de validar que NO haya medidor activo, o de retirarlo ANTES de llamar aquí.
        # Por eso no necesitamos desactivar nada desde el modelo.

        self.partner_id = partner.id
        self.estado = MeterStatus.INSTALADO
        self.es_actual = True
        self.fecha_instalacion = fecha or datetime.utcnow().date()
        self.lectura_instalacion = lectura_inicial
        self.observaciones_instalacion = obs
        self.updated_by_id = user_id
        partner.updated_by_id = user_id
        
    def retirar(self, lectura_retiro: int, fecha=None, user_id=None, obs=None):
        """Retira medidor de terreno (cambio, baja, reparación)."""
        if not self.es_actual:
            raise ValueError("Solo se puede retirar un medidor actual (es_actual=True)")
        
        self.es_actual = False
        self.estado = MeterStatus.RETIRADO
        self.fecha_retiro = fecha or datetime.utcnow().date()
        self.lectura_retiro = lectura_retiro
        self.observaciones_retiro = obs
        self.updated_by_id = user_id
        
        if self.partner:
            self.partner.updated_by_id = user_id

    def enviar_reparacion(self, user_id=None, obs=None):
        if self.es_actual:
            raise ValueError("Debe retirar el medidor antes de enviarlo a reparación")
        self.estado = MeterStatus.REPARACION
        self.observaciones = obs
        self.updated_by_id = user_id

    def dar_baja_definitiva(self, user_id=None, obs=None):
        self.estado = MeterStatus.BAJA
        self.observaciones = obs
        self.updated_by_id = user_id

    def recibir_de_reparacion(self, user_id=None):
        self.estado = MeterStatus.BODEGA
        self.updated_by_id = user_id

    def to_dict(self):
        return {
            'id': self.id,
            'numero_serie': self.numero_serie,
            'marca': self.marca,
            'modelo': self.modelo,
            'diametro': self.diametro,
            'multiplicador': self.multiplicador,
            'estado': self.estado.value,
            'estado_label': self.estado.name.capitalize(),
            'es_actual': self.es_actual,
            'partner_id': self.partner_id,
            'partner_nombre': self.partner.nombre if self.partner else None,
            'fecha_instalacion': self.fecha_instalacion.isoformat() if self.fecha_instalacion else None,
            'lectura_instalacion': self.lectura_instalacion,
            'fecha_retiro': self.fecha_retiro.isoformat() if self.fecha_retiro else None,
            'lectura_retiro': self.lectura_retiro,
            'consumo_acumulado': self.consumo_acumulado_actual,
            'fecha_ultima_lectura': self.fecha_ultima_lectura.isoformat() if self.fecha_ultima_lectura else None,
            'ultima_lectura_valor': self.ultima_lectura_valor,
            'observaciones': self.observaciones,
        }

    def __repr__(self):
        return f"<Meter {self.numero_serie} ({self.estado.value}) {'ACTUAL' if self.es_actual else ''}>"