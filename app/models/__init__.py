# app/models/__init__.py
"""
Paquete de Modelos SQLAlchemy.
Centraliza exports para evitar imports circulares y registrar tablas en db.create_all().
"""

from app.models.user import (
    User, 
    ROLE_DEFAULTS, 
    ROLE_LABELS, 
    ALL_MODULES, 
    MODULE_LABELS
)

from app.models.partner import (
    Partner,
    Meter,
    Sector,
    PartnerStatus,
    MeterStatus
)

# Importación perezosa de modelos futuros para no romper si no existen aún
try:
    from app.models.reading import Reading
except ImportError:
    Reading = None

try:
    from app.models.billing import Bill, Tariff
except ImportError:
    Bill = Tariff = None

__all__ = [
    # User / Auth
    'User', 'ROLE_DEFAULTS', 'ROLE_LABELS', 'ALL_MODULES', 'MODULE_LABELS',
    # Partner / Catastro
    'Partner', 'Meter', 'Sector', 'PartnerStatus', 'MeterStatus',
    # Futuro
    'Reading', 'Bill', 'Tariff',
]