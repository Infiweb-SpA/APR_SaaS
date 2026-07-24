"""
Modelo de Lecturas de Consumo.
Relación: Meter 1:N Reading.
Integración: Actualiza cache en Meter (ultima_lectura_valor, fecha_ultima_lectura).
"""

import enum
from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Date, Float,Boolean,
    ForeignKey, Enum as SQLEnum, Index, CheckConstraint,
)
from sqlalchemy.orm import relationship, validates
from sqlalchemy.ext.hybrid import hybrid_property

from app import db


# ══════════════════════════════════════════════════════════════
# ENUMS DE ESTADO DE LECTURA
# ══════════════════════════════════════════════════════════════

class ReadingStatus(str, enum.Enum):
    """Estados de una lectura en el flujo de trabajo."""
    PENDIENTE = 'pendiente'         # Capturada en terreno, no revisada
    VALIDADA = 'validada'           # Revisada y aprobada por admin/secretaria
    RECHAZADA = 'rechazada'         # Rechazada por datos incoherentes
    ANULADA = 'anulada'             # Anulada por error humano o duplicada


# ══════════════════════════════════════════════════════════════
# MODELO READING (Lectura de Consumo Mensual)
# ══════════════════════════════════════════════════════════════

class Reading(db.Model):
    """Registro de lectura mensual de un medidor.

    Almacena el valor del contador en una fecha específica,
    calcula el consumo respecto a la lectura anterior,
    y mantiene el ciclo de vida de validación.
    """
    __tablename__ = 'readings'
    __table_args__ = (
        Index('ix_reading_meter_periodo', 'meter_id', 'periodo', unique=True),
        Index('ix_reading_periodo', 'periodo'),
        Index('ix_reading_status', 'status'),
        Index('ix_reading_ruta', 'sector_id', 'fecha'),  # Para captura por ruta
        CheckConstraint('lectura_actual >= 0', name='ck_reading_lectura_no_negativa'),
        CheckConstraint('consumo >= 0', name='ck_reading_consumo_no_negativo'),
    )

    # ── PK & Auditoría ──────────────────────────────────────
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    updated_by_id = Column(Integer, ForeignKey('users.id'), nullable=True)

    # ── Relación con Medidor ────────────────────────────────
    meter_id = Column(Integer, ForeignKey('meters.id'), nullable=False, index=True)
    partner_id = Column(Integer, ForeignKey('partners.id'), nullable=False, index=True)
    sector_id = Column(Integer, ForeignKey('sectors.id'), nullable=True, index=True)

    # ── Datos de Lectura ────────────────────────────────────
    periodo = Column(String(7), nullable=False, comment="Formato YYYY-MM, periodo de facturación")
    fecha = Column(Date, nullable=False, comment="Fecha real de toma de lectura en terreno")
    lectura_actual = Column(Integer, nullable=False, comment="Valor actual del contador (índice)")
    lectura_anterior = Column(Integer, nullable=False, comment="Valor del contador en periodo anterior (cache)")

    # ── Cálculos y Estado ───────────────────────────────────
    consumo = Column(Integer, nullable=False, comment="Consumo calculado: lectura_actual - lectura_anterior (m³)")
    consumo_estimado = Column(Integer, nullable=True, comment="Consumo estimado si es lectura aproximada")
    multiplicador = Column(Integer, default=1, nullable=False, comment="Factor multiplicador del medidor (copiado al crear)")

    status = Column(SQLEnum(ReadingStatus), default=ReadingStatus.PENDIENTE, nullable=False, index=True)
    origen = Column(String(20), default='terreno', nullable=False, comment="terreno, oficina, estimada, ajuste")

    # ── Datos de Terreno (Mobile-First) ─────────────────────
    latitud = Column(Float, nullable=True, comment="WGS84 GPS en punto de lectura")
    longitud = Column(Float, nullable=True)
    foto_url = Column(String(500), nullable=True, comment="URL/ruta foto del medidor (futuro)")

    # ── Observaciones y Metadatos ───────────────────────────
    observaciones = Column(Text, nullable=True)
    motivo_rechazo = Column(Text, nullable=True, comment="Razón si status=RECHAZADA")
    es_lectura_inicial = Column(Boolean, default=False, comment="True si es la primera lectura post-instalación")

    # ── Metadatos Offline/Sincronización ────────────────────
    offline_id = Column(String(50), nullable=True, comment="ID local para sincronización offline")
    sincronizado = Column(Boolean, default=True, nullable=False, comment="False si capturado offline")

    # ── RELACIONES ──────────────────────────────────────────
    meter = relationship('Meter', back_populates='readings', lazy='joined')
    partner = relationship('Partner', lazy='joined')
    sector = relationship('Sector', lazy='joined')

    # Relaciones auditoría (opcional, requiere User model cargado)
    created_by = relationship('User', foreign_keys=[created_by_id], lazy='selectin')
    updated_by = relationship('User', foreign_keys=[updated_by_id], lazy='selectin')

    # ── VALIDADORES ─────────────────────────────────────────
    @validates('lectura_actual', 'lectura_anterior')
    def _validate_lectura(self, key, value):
        if value is not None and value < 0:
            raise ValueError("La lectura no puede ser negativa")
        return value

    @validates('periodo')
    def _validate_periodo(self, key, value):
        if value and len(value) == 7 and value[4] == '-':
            return value
        raise ValueError("Periodo debe tener formato YYYY-MM")

    # ── PROPIEDADES HÍBRIDAS ────────────────────────────────
    @hybrid_property
    def consumo_real(self):
        """Consumo neto aplicando multiplicador."""
        return self.consumo * self.multiplicador

    @hybrid_property
    def porcentaje_variacion(self):
        """Variación porcentual respecto al consumo anterior (últimas 3 lecturas)."""
        # Esta propiedad se calculará en el service layer con query histórica
        return None  # Placeholder, se implementará en reading_service

    @property
    def fecha_formateada(self):
        return self.fecha.strftime('%d/%m/%Y') if self.fecha else '-'

    @property
    def periodo_display(self):
        """Formato legible del periodo (Ene 2025)."""
        if not self.periodo:
            return '-'
        year, month = self.periodo.split('-')
        months = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
                  'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
        try:
            return f"{months[int(month)-1]} {year}"
        except (ValueError, IndexError):
            return self.periodo

    @property
    def badge_status(self):
        """Para UI: clase CSS según estado."""
        mapping = {
            ReadingStatus.PENDIENTE: 'badge-pending',
            ReadingStatus.VALIDADA: 'badge-success',
            ReadingStatus.RECHAZADA: 'badge-danger',
            ReadingStatus.ANULADA: 'badge-muted',
        }
        return mapping.get(self.status, 'badge-pending')

    # ── MÉTODOS DE INSTANCIA ────────────────────────────────
    def validar(self, user_id=None):
        """Aprueba la lectura y actualiza cache en Meter."""
        self.status = ReadingStatus.VALIDADA
        self.updated_by_id = user_id

        # Actualizar cache en Meter (propagación)
        if self.meter:
            self.meter.ultima_lectura_valor = self.lectura_actual
            self.meter.fecha_ultima_lectura = self.fecha
            self.meter.updated_by_id = user_id

    def rechazar(self, motivo, user_id=None):
        """Rechaza la lectura con motivo."""
        self.status = ReadingStatus.RECHAZADA
        self.motivo_rechazo = motivo
        self.updated_by_id = user_id

    def anular(self, user_id=None):
        """Anula la lectura (no afecta cálculos)."""
        self.status = ReadingStatus.ANULADA
        self.updated_by_id = user_id

    def calcular_consumo(self):
        """Recalcula consumo basado en lecturas."""
        if self.lectura_actual is not None and self.lectura_anterior is not None:
            self.consumo = max(0, self.lectura_actual - self.lectura_anterior)
        else:
            self.consumo = 0

    def to_dict(self):
        """Serialización para API/JS."""
        return {
            'id': self.id,
            'meter_id': self.meter_id,
            'partner_id': self.partner_id,
            'sector_id': self.sector_id,
            'partner_nombre': self.partner.nombre if self.partner else None,
            'meter_serie': self.meter.numero_serie if self.meter else None,
            'periodo': self.periodo,
            'periodo_display': self.periodo_display,
            'fecha': self.fecha.isoformat() if self.fecha else None,
            'fecha_display': self.fecha_formateada,
            'lectura_actual': self.lectura_actual,
            'lectura_anterior': self.lectura_anterior,
            'consumo': self.consumo,
            'consumo_real': self.consumo_real,
            'multiplicador': self.multiplicador,
            'status': self.status.value,
            'status_label': self.status.name.capitalize(),
            'origen': self.origen,
            'observaciones': self.observaciones,
            'motivo_rechazo': self.motivo_rechazo,
            'created_by': self.created_by.nombre if self.created_by else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'sincronizado': self.sincronizado,
            'offline_id': self.offline_id,
        }

    def __repr__(self):
        return (f"<Reading {self.periodo} - Meter:{self.meter_id} "
                f"Lect:{self.lectura_actual} Cons:{self.consumo} ({self.status.value})>")