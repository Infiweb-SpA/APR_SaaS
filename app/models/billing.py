"""
Motor de Facturación: Tarifas, Boletas y Subsidios.
Relación: TariffConfig (vigente) → Bill 1:1 Reading.
Integración: Bill calcula montos respetando Ley 20.998 y Dec. Sup. N° 171.
Actualiza contratos: partner_service.get_admin_stats() y get_socio_portal_data().
"""

import enum
from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Date, Float, Boolean,
    ForeignKey, Enum as SQLEnum, Index, CheckConstraint,
)
from sqlalchemy.orm import relationship, validates
from sqlalchemy.ext.hybrid import hybrid_property

from app import db


# ══════════════════════════════════════════════════════════════
# ENUMS DE ESTADO DE BOLETA
# ══════════════════════════════════════════════════════════════

class BillStatus(str, enum.Enum):
    """Estados de una boleta en el flujo de facturación."""
    EMITIDA = 'emitida'       # Generada, pendiente de pago
    PAGADA = 'pagada'         # Pagada por el socio
    VENCIDA = 'vencida'       # Vencida sin pago (candidata a corte)
    ANULADA = 'anulada'       # Anulada por error administrativo


# ══════════════════════════════════════════════════════════════
# MODELO TARIFF CONFIG (Configuración de Tarifas Vigentes)
# ══════════════════════════════════════════════════════════════

class TariffConfig(db.Model):
    """Configuración de tarifas, subsidios y multas del APR.

    Registra los valores vigentes para el cálculo de boletas.
    La tabla guarda historial: cada cambio crea un nuevo registro.
    Solo UNO debe tener activo=True a la vez.
    """
    __tablename__ = 'tariff_configs'
    __table_args__ = (
        CheckConstraint('cargo_fijo >= 0', name='ck_tariff_cargo_fijo_positivo'),
        CheckConstraint('valor_m3_base >= 0', name='ck_tariff_valor_m3_positivo'),
        CheckConstraint('valor_m3_sobreconsumo >= 0', name='ck_tariff_sobreconsumo_positivo'),
        CheckConstraint('multa_mora >= 0', name='ck_tariff_mora_positiva'),
        CheckConstraint(
            'porcentaje_subsidio IS NULL OR (porcentaje_subsidio >= 0 AND porcentaje_subsidio <= 1)',
            name='ck_tariff_subsidio_pct'
        ),
        CheckConstraint('tope_subsidio_m3 >= 0', name='ck_tariff_tope_subsidio_positivo'),
        CheckConstraint('limite_sobreconsumo >= 0', name='ck_tariff_limite_positivo'),
    )

    # ─── PK & Auditoría ───────────────────────────────────
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    updated_by_id = Column(Integer, ForeignKey('users.id'), nullable=True)

    # ─── Tarifas de Consumo ───────────────────────────────
    cargo_fijo = Column(Float, nullable=False, default=0, comment="Cargo fijo mensual por conexión (CLP)")
    valor_m3_base = Column(Float, nullable=False, default=0, comment="Precio por m³ consumo base (CLP)")
    limite_sobreconsumo = Column(Integer, nullable=False, default=15, comment="Umbral m³ para tarifa de sobreconsumo")
    valor_m3_sobreconsumo = Column(Float, nullable=False, default=0, comment="Precio por m³ en sobreconsumo (CLP)")
    multa_mora = Column(Float, nullable=False, default=0, comment="Multa fija por pago fuera de plazo (CLP)")

    # ─── Subsidios Estatales (Ley 20.998 / Dec. Sup. N° 171) ──
    porcentaje_subsidio = Column(Float, nullable=True, default=0, comment="Fracción subsidio estatal (0.0 a 1.0, ej: 0.85 = 85%)")
    tope_subsidio_m3 = Column(Integer, nullable=False, default=15, comment="Tope máximo legal de m³ subsidiados por socio")

    # ─── Vigencia ─────────────────────────────────────────
    activo = Column(Boolean, default=True, nullable=False, index=True, comment="Solo una config debe estar activa")
    vigente_desde = Column(Date, nullable=False, default=datetime.utcnow, comment="Fecha inicio de vigencia")
    observaciones = Column(Text, nullable=True)

    # ─── RELACIONES ───────────────────────────────────────
    created_by = relationship('User', foreign_keys=[created_by_id], lazy='selectin')
    updated_by = relationship('User', foreign_keys=[updated_by_id], lazy='selectin')

    # ─── VALIDADORES ──────────────────────────────────────
    @validates('porcentaje_subsidio')
    def _validate_subsidio_pct(self, key, value):
        if value is not None and (value < 0 or value > 1):
            raise ValueError("El porcentaje de subsidio debe estar entre 0.0 y 1.0")
        return value

    # ─── PROPIEDADES ──────────────────────────────────────
    @property
    def porcentaje_subsidio_display(self):
        """Formato legible: 0.85 → '85%'."""
        if self.porcentaje_subsidio is not None:
            return f"{self.porcentaje_subsidio * 100:.0f}%"
        return "0%"

    # ─── MÉTODOS ──────────────────────────────────────────
    def to_dict(self):
        return {
            'id': self.id,
            'cargo_fijo': self.cargo_fijo,
            'valor_m3_base': self.valor_m3_base,
            'limite_sobreconsumo': self.limite_sobreconsumo,
            'valor_m3_sobreconsumo': self.valor_m3_sobreconsumo,
            'multa_mora': self.multa_mora,
            'porcentaje_subsidio': self.porcentaje_subsidio,
            'porcentaje_subsidio_display': self.porcentaje_subsidio_display,
            'tope_subsidio_m3': self.tope_subsidio_m3,
            'activo': self.activo,
            'vigente_desde': self.vigente_desde.isoformat() if self.vigente_desde else None,
            'observaciones': self.observaciones,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<TariffConfig #{self.id} ${self.cargo_fijo}+${self.valor_m3_base}/m3 {'ACTIVA' if self.activo else ''}>"


# ══════════════════════════════════════════════════════════════
# MODELO BILL (Boleta de Cobro Mensual)
# ══════════════════════════════════════════════════════════════

class Bill(db.Model):
    """Boleta de cobro mensual generada por el motor de facturación.

    Almacena un snapshot completo de la lectura, tarifa aplicada
    y montos calculados. Garantiza trazabilidad total aunque las
    tarifas cambien en el futuro.
    """
    __tablename__ = 'bills'
    __table_args__ = (
        Index('ix_bill_partner_periodo', 'partner_id', 'periodo', unique=True),
        Index('ix_bill_periodo', 'periodo'),
        Index('ix_bill_status', 'status'),
        Index('ix_bill_vencimiento', 'fecha_vencimiento'),
        CheckConstraint('consumo_m3 >= 0', name='ck_bill_consumo_no_negativo'),
        CheckConstraint('monto_total >= 0', name='ck_bill_total_no_negativo'),
    )

    # ─── PK & Auditoría ───────────────────────────────────
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    updated_by_id = Column(Integer, ForeignKey('users.id'), nullable=True)

    # ─── Relaciones Principales ───────────────────────────
    partner_id = Column(Integer, ForeignKey('partners.id'), nullable=False, index=True)
    reading_id = Column(Integer, ForeignKey('readings.id'), nullable=True, index=True,
                        comment="Lectura origen (NULL si boleta manual)")

    # ─── Periodo ──────────────────────────────────────────
    periodo = Column(String(7), nullable=False, comment="Formato YYYY-MM")

    # ─── Snapshot de Lecturas ─────────────────────────────
    lectura_anterior = Column(Integer, nullable=False, default=0, comment="Índice periodo anterior")
    lectura_actual = Column(Integer, nullable=False, default=0, comment="Índice periodo actual")
    consumo_m3 = Column(Integer, nullable=False, default=0, comment="Consumo real con multiplicador (m³)")

    # ─── Snapshot de Tarifa Aplicada (trazabilidad) ───────
    tarifa_cargo_fijo = Column(Float, nullable=False, default=0)
    tarifa_valor_m3 = Column(Float, nullable=False, default=0)
    tarifa_limite_sobreconsumo = Column(Integer, nullable=False, default=15)
    tarifa_valor_m3_sobreconsumo = Column(Float, nullable=False, default=0)
    tarifa_subsidio_pct = Column(Float, nullable=True, default=0)
    tarifa_tope_subsidio_m3 = Column(Integer, nullable=False, default=15)

    # ─── Montos Calculados (CLP) ──────────────────────────
    monto_fijo = Column(Float, nullable=False, default=0, comment="Cargo fijo")
    monto_consumo_basico = Column(Float, nullable=False, default=0, comment="Consumo dentro de tarifa base")
    monto_sobreconsumo = Column(Float, nullable=False, default=0, comment="Consumo excedente al límite")
    monto_subsidio = Column(Float, nullable=False, default=0, comment="Descuento por subsidio estatal")
    monto_mora = Column(Float, nullable=False, default=0, comment="Multa por mora")
    monto_total = Column(Float, nullable=False, default=0, comment="Total a pagar por el socio")

    # ─── Estado y Fechas ──────────────────────────────────
    status = Column(SQLEnum(BillStatus), default=BillStatus.EMITIDA, nullable=False, index=True)
    fecha_emision = Column(Date, nullable=False)
    fecha_vencimiento = Column(Date, nullable=False)
    fecha_pago = Column(Date, nullable=True)

    observaciones = Column(Text, nullable=True)

    # ─── RELACIONES ───────────────────────────────────────
    partner = relationship('Partner', lazy='joined')
    reading = relationship('Reading', lazy='joined')
    created_by = relationship('User', foreign_keys=[created_by_id], lazy='selectin')
    updated_by = relationship('User', foreign_keys=[updated_by_id], lazy='selectin')

    # ─── VALIDADORES ──────────────────────────────────────
    @validates('periodo')
    def _validate_periodo(self, key, value):
        if value and len(value) == 7 and value[4] == '-':
            return value
        raise ValueError("Periodo debe tener formato YYYY-MM")

    # ─── PROPIEDADES HÍBRIDAS ─────────────────────────────
    @hybrid_property
    def subtotal(self):
        """Total antes de aplicar subsidio."""
        return self.monto_fijo + self.monto_consumo_basico + self.monto_sobreconsumo

    @hybrid_property
    def esta_pagada(self):
        return self.status == BillStatus.PAGADA

    @hybrid_property
    def esta_vencida(self):
        if self.status in (BillStatus.PAGADA, BillStatus.ANULADA):
            return False
        if self.fecha_vencimiento:
            return date.today() > self.fecha_vencimiento
        return False

    @property
    def periodo_display(self):
        """Formato legible: '2025-01' → 'Ene 2025'."""
        if not self.periodo:
            return '-'
        year, month = self.periodo.split('-')
        months = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
                  'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
        try:
            return f"{months[int(month) - 1]} {year}"
        except (ValueError, IndexError):
            return self.periodo

    @property
    def badge_status(self):
        """Clase CSS para badge de estado en UI."""
        mapping = {
            BillStatus.EMITIDA: 'badge-pending',
            BillStatus.PAGADA: 'badge-success',
            BillStatus.VENCIDA: 'badge-danger',
            BillStatus.ANULADA: 'badge-muted',
        }
        return mapping.get(self.status, 'badge-pending')

    # ─── MÉTODOS DE CÁLCULO ───────────────────────────────

    def calcular_desde_tarifa(self, tarifa: TariffConfig, consumo_m3: int, incluir_mora: bool = False):
        """Calcula todos los montos aplicando tarifa y regla de subsidio.

        Regla Ley 20.998 / Dec. Sup. N° 171:
        - Subsidio aplica como porcentaje sobre consumo, con tope máximo de 15 m³.
        - El cargo fijo NO está afecto a subsidio.
        - El sobreconsumo (m³ sobre el límite) NO está afecto a subsidio.

        Args:
            tarifa: Configuración de tarifas vigente.
            consumo_m3: Consumo real del periodo en m³ (con multiplicador).
            incluir_mora: Si True, agrega multa por mora al total.
        """
        self.consumo_m3 = consumo_m3

        # Snapshot de tarifa (trazabilidad completa)
        self.tarifa_cargo_fijo = tarifa.cargo_fijo
        self.tarifa_valor_m3 = tarifa.valor_m3_base
        self.tarifa_limite_sobreconsumo = tarifa.limite_sobreconsumo
        self.tarifa_valor_m3_sobreconsumo = tarifa.valor_m3_sobreconsumo
        self.tarifa_subsidio_pct = tarifa.porcentaje_subsidio or 0
        self.tarifa_tope_subsidio_m3 = tarifa.tope_subsidio_m3

        # 1. Cargo fijo
        self.monto_fijo = tarifa.cargo_fijo

        # 2. Consumo básico (hasta el límite de sobreconsumo)
        consumo_basico_m3 = min(consumo_m3, tarifa.limite_sobreconsumo)
        self.monto_consumo_basico = round(consumo_basico_m3 * tarifa.valor_m3_base)

        # 3. Sobreconsumo (sobre el límite)
        consumo_excedente_m3 = max(0, consumo_m3 - tarifa.limite_sobreconsumo)
        self.monto_sobreconsumo = round(consumo_excedente_m3 * tarifa.valor_m3_sobreconsumo)

        # 4. Subsidio estatal (tope legal: 15 m³ por socio)
        subsidio_pct = tarifa.porcentaje_subsidio or 0
        if subsidio_pct > 0 and consumo_m3 > 0:
            m3_subsidiables = min(consumo_m3, tarifa.tope_subsidio_m3)
            self.monto_subsidio = round(m3_subsidiables * tarifa.valor_m3_base * subsidio_pct)
        else:
            self.monto_subsidio = 0

        # 5. Mora (opcional, aplicable si boleta anterior vencida)
        self.monto_mora = tarifa.multa_mora if incluir_mora else 0

        # 6. Total a pagar (nunca negativo)
        self.monto_total = max(0, round(
            self.monto_fijo
            + self.monto_consumo_basico
            + self.monto_sobreconsumo
            - self.monto_subsidio
            + self.monto_mora
        ))

    # ─── MÉTODOS DE INSTANCIA (Ciclo de Vida) ─────────────

    def marcar_pagada(self, user_id=None):
        """Registra pago de la boleta."""
        self.status = BillStatus.PAGADA
        self.fecha_pago = date.today()
        self.updated_by_id = user_id

    def marcar_vencida(self, user_id=None):
        """Marca boleta como vencida (ejecutado por job o manualmente)."""
        if self.status == BillStatus.EMITIDA:
            self.status = BillStatus.VENCIDA
            self.updated_by_id = user_id

    def anular(self, user_id=None, motivo=None):
        """Anula la boleta (error administrativo, duplicada, etc.)."""
        self.status = BillStatus.ANULADA
        if motivo:
            self.observaciones = motivo
        self.updated_by_id = user_id

    # ─── SERIALIZACIÓN ────────────────────────────────────

    def to_dict(self):
        """Serialización completa para API/JS/DataTables."""
        return {
            'id': self.id,
            'partner_id': self.partner_id,
            'partner_nombre': self.partner.nombre if self.partner else None,
            'partner_rut': self.partner.rut if self.partner else None,
            'reading_id': self.reading_id,
            'periodo': self.periodo,
            'periodo_display': self.periodo_display,
            'lectura_anterior': self.lectura_anterior,
            'lectura_actual': self.lectura_actual,
            'consumo_m3': self.consumo_m3,
            'monto_fijo': self.monto_fijo,
            'monto_consumo_basico': self.monto_consumo_basico,
            'monto_sobreconsumo': self.monto_sobreconsumo,
            'monto_subsidio': self.monto_subsidio,
            'monto_mora': self.monto_mora,
            'subtotal': self.subtotal,
            'monto_total': self.monto_total,
            'status': self.status.value,
            'status_label': self.status.name.capitalize(),
            'badge_status': self.badge_status,
            'fecha_emision': self.fecha_emision.isoformat() if self.fecha_emision else None,
            'fecha_vencimiento': self.fecha_vencimiento.isoformat() if self.fecha_vencimiento else None,
            'fecha_pago': self.fecha_pago.isoformat() if self.fecha_pago else None,
            'esta_pagada': self.esta_pagada,
            'esta_vencida': self.esta_vencida,
            'observaciones': self.observaciones,
            'created_by': self.created_by.nombre if self.created_by else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return (f"<Bill {self.periodo} - Partner:{self.partner_id} "
                f"${self.monto_total:,.0f} ({self.status.value})>")