Aquí tienes el `modulo6.md` completo. Sigue la misma estructura y convenciones que `modulo4.md` y `modulo5.md`:

---

```markdown
# Contexto Técnico – Módulo 6: Facturación – Tarifas, Boletas y Subsidios (`billing`)

> **Generado automáticamente** a partir del código real del proyecto.  
> Última actualización: 2026-07-25  

---

## 1. Resumen del Módulo

| Aspecto | Detalle |
|---------|---------|
| **Propósito** | Motor de facturación mensual del APR: configuración de tarifas con historial, generación masiva de boletas (cierre de mes), ciclo de vida de boletas (emitir/pagar/vencer/anular), subsidios estatales (Ley 20.998 / Dec. Sup. N° 171), y provisión de datos de cobros para Dashboard (Módulo 3) y Portal Socio (Módulo 3). |
| **Blueprint** | `billing_bp` (variable `bp`) – registrado con `url_prefix='/billing'` en `app/__init__.py`. |
| **Layout base** | `layouts/base_admin.html` (incluye `components/admin_sidebar.html` con item "Facturación" visible si `billing` ≥ 1). |
| **Acceso** | **Privado** – requiere `@login_required` + `@permission_required('billing', level)`. |
| **Permisos RBAC** | `billing`: Level 1 (Listado/Detalle/APIs consulta), Level 2 (Cierre de mes, Pago, Anulación, Marcar vencidas, CRUD Tarifas). |
| **Modelos Core** | `Bill`, `TariffConfig`, `BillStatus` (definidos en `app/models/billing.py`). Consume `Partner`, `Meter`, `Sector` de `app/models/partner.py` y `Reading`, `ReadingStatus` de `app/models/reading.py`. |
| **Servicio Central** | `app/services/billing_service.py` (Lógica transaccional: `execute_monthly_billing`, `create_tariff`, `mark_bill_as_paid`, `mark_overdue_bills`, `anular_bill`, `get_billing_preview`, `get_billing_stats`). |
| **JavaScript** | jQuery + DataTables CDN (Server-Side) en `index.html`. Vanilla ES6 inline en `config.html` (simulación cobro, submit AJAX) y `process.html` (wizard 3 pasos, preview AJAX, confirm modal). |
| **Estilo** | Tailwind CSS CDN + CSS custom inline para DataTables (compatibilidad CDN). Google Fonts `DM Serif Display` + `Lora`. |

---

## 2. Modelos de Datos (`app/models/billing.py`)

### 2.1 Enum de Estado de Boleta

```python
class BillStatus(str, enum.Enum):
    EMITIDA = 'emitida'       # Generada, pendiente de pago
    PAGADA = 'pagada'         # Pagada por el socio
    VENCIDA = 'vencida'       # Vencida sin pago (candidata a corte)
    ANULADA = 'anulada'       # Anulada por error administrativo
```

### 2.2 Tabla `tariff_configs` (Configuración de Tarifas Vigentes)

| Campo | Tipo | Detalle |
|-------|------|---------|
| `id` | PK Integer | |
| `created_at` / `updated_at` | DateTime | Auditoría. |
| `created_by_id` / `updated_by_id` | FK Integer (users.id) | Nullable. Usuario que creó/modificó. |
| `cargo_fijo` | Float | **NOT NULL, Default 0**. Cargo fijo mensual por conexión (CLP). CheckConstraint ≥ 0. |
| `valor_m3_base` | Float | **NOT NULL, Default 0**. Precio por m³ consumo base (CLP). CheckConstraint ≥ 0. |
| `limite_sobreconsumo` | Integer | **NOT NULL, Default 15**. Umbral m³ para tarifa de sobreconsumo. CheckConstraint ≥ 0. |
| `valor_m3_sobreconsumo` | Float | **NOT NULL, Default 0**. Precio por m³ en sobreconsumo (CLP). CheckConstraint ≥ 0. |
| `multa_mora` | Float | **NOT NULL, Default 0**. Multa fija por pago fuera de plazo (CLP). CheckConstraint ≥ 0. |
| `porcentaje_subsidio` | Float | Nullable, Default 0. Fracción subsidio estatal (0.0 a 1.0, ej: 0.85 = 85%). CheckConstraint 0–1. |
| `tope_subsidio_m3` | Integer | **NOT NULL, Default 15**. Tope máximo legal de m³ subsidiados por socio. CheckConstraint ≥ 0. |
| `activo` | Boolean | **NOT NULL, Default True, Index**. Solo una config debe estar activa a la vez. |
| `vigente_desde` | Date | **NOT NULL**. Fecha inicio de vigencia. |
| `observaciones` | Text | Nullable. |

**CheckConstraints en tabla:**
- `ck_tariff_cargo_fijo_positivo`: `cargo_fijo >= 0`
- `ck_tariff_valor_m3_positivo`: `valor_m3_base >= 0`
- `ck_tariff_sobreconsumo_positivo`: `valor_m3_sobreconsumo >= 0`
- `ck_tariff_mora_positiva`: `multa_mora >= 0`
- `ck_tariff_subsidio_pct`: `porcentaje_subsidio IS NULL OR (porcentaje_subsidio >= 0 AND porcentaje_subsidio <= 1)`
- `ck_tariff_tope_subsidio_positivo`: `tope_subsidio_m3 >= 0`
- `ck_tariff_limite_positivo`: `limite_sobreconsumo >= 0`

**Propiedades:**
- `porcentaje_subsidio_display` → `0.85 → '85%'`.

**Serialización:** `to_dict()` → Todos los campos + `porcentaje_subsidio_display`.

**Patrón de Historial:** Cada cambio crea un nuevo registro. Solo uno tiene `activo=True`. El anterior se desactiva automáticamente.

### 2.3 Tabla `bills` (Boleta de Cobro Mensual)

| Campo | Tipo | Detalle |
|-------|------|---------|
| `id` | PK Integer | |
| `created_at` / `updated_at` | DateTime | Auditoría. |
| `created_by_id` / `updated_by_id` | FK Integer (users.id) | Nullable. Usuario que generó/modificó. |
| `partner_id` | FK Integer (partners.id) | **NOT NULL, Index**. Socio facturado. |
| `reading_id` | FK Integer (readings.id) | Nullable, Index. Lectura origen (NULL si boleta manual). |
| `periodo` | String(7) | **NOT NULL**. Formato `YYYY-MM`. |
| `lectura_anterior` | Integer | **NOT NULL, Default 0**. Índice periodo anterior. |
| `lectura_actual` | Integer | **NOT NULL, Default 0**. Índice periodo actual. |
| `consumo_m3` | Integer | **NOT NULL, Default 0**. Consumo real con multiplicador (m³). CheckConstraint ≥ 0. |
| `tarifa_cargo_fijo` | Float | **NOT NULL, Default 0**. Snapshot trazabilidad. |
| `tarifa_valor_m3` | Float | **NOT NULL, Default 0**. Snapshot trazabilidad. |
| `tarifa_limite_sobreconsumo` | Integer | **NOT NULL, Default 15**. Snapshot trazabilidad. |
| `tarifa_valor_m3_sobreconsumo` | Float | **NOT NULL, Default 0**. Snapshot trazabilidad. |
| `tarifa_subsidio_pct` | Float | Nullable, Default 0. Snapshot trazabilidad. |
| `tarifa_tope_subsidio_m3` | Integer | **NOT NULL, Default 15**. Snapshot trazabilidad. |
| `monto_fijo` | Float | **NOT NULL, Default 0**. Cargo fijo aplicado. |
| `monto_consumo_basico` | Float | **NOT NULL, Default 0**. Consumo dentro de tarifa base. |
| `monto_sobreconsumo` | Float | **NOT NULL, Default 0**. Consumo excedente al límite. |
| `monto_subsidio` | Float | **NOT NULL, Default 0**. Descuento por subsidio estatal. |
| `monto_mora` | Float | **NOT NULL, Default 0**. Multa por mora. |
| `monto_total` | Float | **NOT NULL, Default 0**. Total a pagar por el socio. CheckConstraint ≥ 0. |
| `status` | Enum `BillStatus` | **Default EMITIDA, Index**. |
| `fecha_emision` | Date | **NOT NULL**. |
| `fecha_vencimiento` | Date | **NOT NULL, Index**. |
| `fecha_pago` | Date | Nullable. Seteado en `marcar_pagada()`. |
| `observaciones` | Text | Nullable. Motivo si anulada. |

**Índices y Constraints:**
- `ix_bill_partner_periodo` → Índice compuesto único `(partner_id, periodo)`.
- `ix_bill_periodo` → Index en `periodo`.
- `ix_bill_status` → Index en `status`.
- `ix_bill_vencimiento` → Index en `fecha_vencimiento`.
- `ck_bill_consumo_no_negativo` → `consumo_m3 >= 0`.
- `ck_bill_total_no_negativo` → `monto_total >= 0`.

### 2.4 Relaciones de Bill

```python
partner = relationship('Partner', lazy='joined')
reading = relationship('Reading', lazy='joined')
created_by = relationship('User', foreign_keys=[created_by_id], lazy='selectin')
updated_by = relationship('User', foreign_keys=[updated_by_id], lazy='selectin')
```

**Nota:** `Bill` almacena un **snapshot completo** de la tarifa aplicada (`tarifa_*` columns) para garantizar trazabilidad total aunque las tarifas cambien en el futuro.

### 2.5 Propiedades Híbridas / Helpers de Bill

| Propiedad | Descripción |
|-----------|-------------|
| `subtotal` | `monto_fijo + monto_consumo_basico + monto_sobreconsumo`. Total antes de subsidio. |
| `esta_pagada` | `status == PAGADA`. |
| `esta_vencida` | `True` si no PAGADA/ANULADA y `fecha_vencimiento < today`. |
| `periodo_display` | Formato legible: `'2025-01' → 'Ene 2025'`. |
| `badge_status` | Clase CSS semántica (`badge-pending`, `badge-success`, `badge-danger`, `badge-muted`). |

### 2.6 Método de Cálculo Principal

#### `calcular_desde_tarifa(tarifa, consumo_m3, incluir_mora=False)`
Calcula todos los montos aplicando tarifa y regla de subsidio.

**Regla Ley 20.998 / Dec. Sup. N° 171:**
1. **Cargo fijo** → `monto_fijo = tarifa.cargo_fijo`.
2. **Consumo básico** → `min(consumo_m3, tarifa.limite_sobreconsumo) × tarifa.valor_m3_base`.
3. **Sobreconsumo** → `max(0, consumo_m3 - tarifa.limite_sobreconsumo) × tarifa.valor_m3_sobreconsumo`.
4. **Subsidio estatal** → `min(consumo_m3, tarifa.tope_subsidio_m3) × tarifa.valor_m3_base × tarifa.porcentaje_subsidio`. Tope legal: **15 m³ por socio**. El cargo fijo y el sobreconsumo **NO** están afectos a subsidio.
5. **Mora** → `tarifa.multa_mora` si `incluir_mora=True` (aplicable si boleta anterior vencida).
6. **Total** → `max(0, monto_fijo + monto_consumo_basico + monto_sobreconsumo - monto_subsidio + monto_mora)`.

**Snapshot:** Antes de calcular, copia todos los valores de `tarifa` a los campos `tarifa_*` del Bill para trazabilidad.

### 2.7 Métodos de Instancia (Ciclo de Vida de Bill)

| Método | Efecto |
|--------|--------|
| `marcar_pagada(user_id)` | `status → PAGADA`, `fecha_pago = today()`. |
| `marcar_vencida(user_id)` | Solo si `EMITIDA` → `status → VENCIDA`. |
| `anular(user_id, motivo)` | `status → ANULADA`, `observaciones = motivo`. |

### 2.8 Validadores del Modelo

```python
@validates('periodo')
def _validate_periodo(self, key, value):
    if value and len(value) == 7 and value[4] == '-':
        return value
    raise ValueError("Periodo debe tener formato YYYY-MM")
```

---

## 3. Capa de Servicio (`app/services/billing_service.py`)

> **Patrón:** Funciones puras, transaccionales (`db.session.commit/rollback`), excepciones tipadas (`ValidationError`, `BusinessRuleError`, `NotFoundError`), helpers de tipado seguro (`_to_float`, `_to_int`, `_to_date`).

### 3.1 Excepciones Personalizadas
```python
class BillingServiceError(Exception): ...    # Base, con code + field
class ValidationError(BillingServiceError): ...      # field específico
class BusinessRuleError(BillingServiceError): ...    # regla de negocio
class NotFoundError(BillingServiceError): ...        # entidad no existe
```

### 3.2 Helpers Privados

| Helper | Descripción |
|--------|-------------|
| `_to_int(val)` | Conversión segura a int (None si vacío/inválido). |
| `_to_float(val)` | Conversión segura a float. |
| `_to_date(val)` | Convierte ISO `YYYY-MM-DD` o `DD/MM/YYYY`. Default: hoy. |
| `_get_current_periodo()` | Periodo actual `YYYY-MM` (mes en curso). |
| `_get_bill_query()` | Query base con eager loading: `joinedload(Bill.partner)`, `joinedload(Bill.reading)`. |
| `_partner_tiene_mora(partner_id)` | Verifica si socio tiene boletas `VENCIDA` sin pagar. |

### 3.3 Configuración de Tarifas (ABM)

| Función | Descripción |
|---------|-------------|
| `get_active_tariff()` | Tarifa activa actual. `None` si no hay. |
| `get_tariff_history()` | Historial completo, más reciente primero. |
| `get_tariff_by_id(tariff_id)` | Lanza `NotFoundError` si no existe. |
| `create_tariff(data, user_id)` | **Desactiva** tarifa anterior (`activo=False`), crea nueva (`activo=True`). Valida montos ≥ 0, `porcentaje_subsidio` 0–1. Commit. |
| `update_tariff(tariff_id, data, user_id)` | Solo si es activa. Campos editables: `cargo_fijo`, `valor_m3_base`, `limite_sobreconsumo`, `valor_m3_sobreconsumo`, `multa_mora`, `tope_subsidio_m3`, `porcentaje_subsidio`, `vigente_desde`, `observaciones`. Si no es activa → `BusinessRuleError`. |

### 3.4 Consulta de Boletas (DataTables + Detalle)

| Función | Descripción |
|---------|-------------|
| `get_bill_by_id(bill_id)` | Con eager loading. Lanza `NotFoundError`. |
| `search_bills(term, periodo, status, partner_id, page, per_page, order_by, order_dir)` | Búsqueda paginada con filtros combinados. `outerjoin(Partner)` para buscar por RUT/nombre. `distinct()`. Retorna `(items, total)`. |
| `get_bills_for_partner(partner_id, limit=6)` | Últimas boletas no anuladas de un socio (para ficha y portal). |
| `get_partner_outstanding_balance(partner_id)` | Saldo pendiente total (CLP): suma `monto_total` de boletas `EMITIDA` + `VENCIDA`. |

### 3.5 Previsualización de Cierre de Mes

#### `get_billing_preview(periodo) → Dict`
Genera un preview de lo que produciría el cierre de mes.

**Retorna:**
```python
{
    'periodo': str,
    'tarifa': dict,                 # TariffConfig.to_dict()
    'total_partners': int,          # Socios facturables (ACTIVO/CORTADO)
    'partners_con_lectura': int,
    'partners_sin_lectura': int,
    'detalle_con_lectura': list,    # [{partner_id, nombre, rut, consumo_m3, monto_estimado, reading_status, tiene_mora}]
    'detalle_sin_lectura': list,    # [{partner_id, nombre, rut, estado}]
    'estimated_total': float,       # Monto total estimado
    'existing_bills': int,          # Boletas ya emitidas para el periodo
}
```

**Flujo:**
1. Obtiene tarifa activa (si no hay → `BusinessRuleError`).
2. Socios facturables: `estado` in `[ACTIVO, CORTADO]`.
3. Lecturas del periodo: `VALIDADA` o `PENDIENTE`, indexadas por `partner_id`.
4. Para cada socio con lectura: simula cálculo completo (fijo + básico + sobreconsumo - subsidio + mora).
5. Para cada socio sin lectura: agrega a omitidos.

### 3.6 Motor de Cierre de Mes (Operación Crítica)

#### `execute_monthly_billing(periodo, fecha_emision, fecha_vencimiento, user_id) → Dict`
Ejecuta el cierre de mes: genera boletas masivamente.

**Flujo Atómico (Try/Except + Rollback):**
1. **Verificar unicidad:** No pueden existir boletas no anuladas para el mismo periodo. Si existen → `BusinessRuleError`.
2. **Obtener tarifa activa.** Si no hay → `BusinessRuleError`.
3. **Socios facturables:** `estado` in `[ACTIVO, CORTADO]`.
4. **Lecturas del periodo:** `VALIDADA` o `PENDIENTE`, indexadas por `partner_id`.
5. **Para cada socio:**
   - Sin lectura → omitido.
   - Lectura `PENDIENTE` → **auto-valida** (`reading.validar(user_id)`), incrementa contador.
   - Calcula `consumo_m3 = reading.consumo_real` (aplica multiplicador).
   - Verifica mora (`_partner_tiene_mora`).
   - Crea `Bill` con snapshot completo de lectura + tarifa.
   - Llama `bill.calcular_desde_tarifa(tariff, consumo_m3, incluir_mora)`.
6. **Commit atómico.**
7. **Retorna resumen:** `{periodo, boletas_creadas, omitidos, omitidos_count, lecturas_auto_validadas, warnings, tarifa_aplicada}`.

### 3.7 Ciclo de Vida de Boletas

| Función | Descripción |
|---------|-------------|
| `mark_bill_as_paid(bill_id, user_id)` | Marca como pagada. Valida que no esté ya pagada ni anulada. |
| `mark_overdue_bills(user_id)` | Marca como `VENCIDA` todas las `EMITIDA` con `fecha_vencimiento < today`. Retorna cantidad. |
| `anular_bill(bill_id, motivo, user_id)` | Anula con motivo obligatorio. Valida que no esté ya anulada ni pagada (pagada → `BusinessRuleError`: "Registre nota de crédito"). |

### 3.8 Estadísticas para Dashboard

#### `get_billing_stats(periodo=None) → Dict`
**Retorna:**
```python
{
    'total_recaudado': int,     # Suma monto_total de PAGADAS del periodo
    'meta_recaudacion': int,    # Suma monto_total no ANULADAS del periodo
    'deudores_mora': int,       # Socios distintos con al menos 1 VENCIDA
    'monto_mora': int,          # Suma monto_total de VENCIDAS
}
```

### 3.9 Contratos de Datos para Portal Socio (Módulo 3)

| Función | Descripción |
|---------|-------------|
| `get_bills_for_socio_portal(partner_id, limit=6)` | Últimas boletas para `recent_bills` en Portal. Formato: `{periodo, consumption, amount, due_date, status}`. |
| `get_socio_saldo_pendiente(partner_id)` | Saldo pendiente CLP. |
| `get_socio_ultima_boleta(partner_id)` | Fecha de última boleta emitida. |

---

## 4. Blueprint y Rutas (`app/blueprints/billing.py`)

> **Estructura:** `bp = Blueprint('billing', __name__, url_prefix='/billing')`.  
> **Decoradores:** `@login_required` en **todas**. `@permission_required('billing', 1)` en GET (list, detail, api stats, api tariff). `@permission_required('billing', 2)` en POST (cierre, pago, anulación, vencimiento, tarifas).

### 4.1 Rutas Principales

| Ruta | Método | Permiso | Función | Descripción |
|------|--------|---------|---------|-------------|
| `/` | GET | `billing:1` | `index()` | Listado DataTables Server-Side (`index.html`). Pasa `periodos` (últimos 12), `estados` (BillStatus). |
| `/api/list` | GET | `billing:1` | `api_list()` | **JSON DataTables** Boletas (filtros: search, periodo, status). Serializa `bill.to_dict()`. |
| `/config` | GET | `billing:2` | `config()` | Vista de tarifa activa + historial (`config.html`). |
| `/config/save` | POST | `billing:2` | `config_save()` | Crea o actualiza tarifa. Soporta AJAX (`X-Requested-With`) y form POST. Si `tariff_id` → update, sino → create. |
| `/api/tariff` | GET | `billing:1` | `api_tariff()` | **JSON** Tarifa activa (para preview en process). |

### 4.2 Motor de Cierre de Mes

| Ruta | Método | Permiso | Función | Descripción |
|------|--------|---------|---------|-------------|
| `/process` | GET | `billing:2` | `process()` | Vista wizard 3 pasos (`process.html`). Pasa `preview` (del periodo actual), `periodo_default`, `periodos_cerrados`. |
| `/process/preview` | POST | `billing:2` | `process_preview()` | **AJAX JSON** Previsualiza cierre para periodo específico. Llama `get_billing_preview()`. |
| `/process/execute` | POST | `billing:2` | `process_execute()` | **AJAX JSON** Ejecuta cierre definitivo. Params: `periodo`, `fecha_emision`, `fecha_vencimiento`. Llama `execute_monthly_billing()`. Default vencimiento: día 28. |

### 4.3 Acciones sobre Boletas

| Ruta | Método | Permiso | Función | Descripción |
|------|--------|---------|---------|-------------|
| `/<int:bill_id>/pay` | POST | `billing:2` | `mark_paid()` | **AJAX JSON** Marca boleta como pagada. |
| `/<int:bill_id>/anular` | POST | `billing:2` | `anular()` | **AJAX JSON** Anula boleta con `motivo` (obligatorio). |
| `/overdue/mark` | POST | `billing:2` | `mark_overdue()` | **AJAX JSON** Marca como vencidas todas las boletas fuera de plazo. |
| `/api/stats` | GET | `billing:1` | `api_stats()` | **JSON** Estadísticas para dashboard. Opcional `?periodo=YYYY-MM`. |

---

## 5. Templates (Vistas Jinja2)

### 5.1 Herencia y Estructura Común
- **Todos** extienden `layouts/base_admin.html`.
- **Bloques usados:** `title`, `extra_head` (DataTables CSS, CSS custom), `content`, `extra_scripts` (jQuery + DataTables JS, lógica modales/Fetch).
- **Navbar/Sidebar:** `admin_sidebar.html` muestra "Facturación" activo (`request.endpoint.startswith('billing.')`).

### 5.2 `billing/index.html` (Listado Principal de Boletas)

**Componentes Clave:**
1. **Header:** Título "Facturación" + Botón "Marcar vencidas" (permiso 2) + Botón "Cierre de Mes" (link a `/billing/process`, permiso 2).
2. **Filtros (Form `#filterForm`):** Input Search (debounce 350ms, RUT o nombre), Select Periodo (últimos 12 meses), Select Estado (`BillStatus`). Botón "Limpiar filtros".
3. **Tabla `#tablaBoletas` (DataTables Server-Side):**
   - **Columnas:** Periodo (mono), Socio (+ RUT), Consumo (m³), Fijo, Consumo $ (básico + sobreconsumo con detalle), Subsidio (teal, negativo), Mora (red), Total (mono, bold, rojo si mora), Estado (Badge Semántico), Vencimiento (DD/MM/YYYY + "VENCIDA" si aplica), Acciones.
   - **Acciones (Render JS `accionesHtml`):** Pagar (check icon, solo si no pagada/anulada), Anular (trash icon, solo si no anulada/pagada). **Permiso 2 requerido.**
   - **Responsive:** `scrollX: true`, `autoWidth: false`.
4. **Footer:** Link "Configurar Tarifas" + Info registros (`#tableInfo`).
5. **Modal Anular (`#modal-anular`):** Overlay + form con textarea `motivo_rechazo` (obligatorio). Submit → `fetch(POST /billing/{id}/anular)` → Toast + `location.reload()`.

**Badges Semánticos:**
```
emitida  → bg: amber-100 (#fef3c7), text: amber-800 (#92400e), dot: amber-500 (#f59e0b)
pagada   → bg: teal-100 (#ccfbf1), text: teal-800 (#115e59), dot: teal-500 (#14b8a6)
vencida  → bg: red-100 (#fee2e2), text: red-800 (#991b1b), dot: red-500 (#ef4444)
anulada  → bg: stone-100 (#f5f5f4), text: stone-600 (#57534e), dot: stone-400 (#a8a29e)
```

### 5.3 `billing/config.html` (Configuración de Tarifas)

**Componentes Clave:**
1. **Header:** Título + Botón "Volver a Boletas".
2. **Tarjeta Tarifa Activa:**
   - Cabecera: icono + "Tarifa Vigente" o "Crear Primera Configuración". Info: vigente desde + ID.
   - Formulario (`#tariffForm`) con 3 fieldsets:
     - **Cargos por Consumo:** Cargo fijo ($), Valor m³ base ($), Límite sobreconsumo (m³), Valor m³ sobreconsumo ($), Multa mora ($).
     - **Subsidios Estatales:** Porcentaje subsidio (0.0–1.0, con preview en tiempo real), Tope máximo subsidio (m³, default 15). Info box legal (Ley 20.998 / Dec. Sup. N° 171).
     - **Vigencia:** Fecha vigente desde, Observaciones.
   - Hidden `tariff_id` para update (vacío para create).
   - Botones: "Vista Previa" (simulación) + "Crear y Activar" / "Actualizar Tarifa".
3. **Sección Vista Previa (`#previewSection`):** Simulación de cobro con 2 ejemplos: "Consumo Bajo" (12 m³) y "Consumo Alto" (25 m³). Desglose: cargo fijo, consumo básico, sobreconsumo, subsidio, total. Renderizada via JS.
4. **Historial de Configuraciones:** Tabla simple (solo si `historial|length > 1`): ID, Cargo Fijo, Valor m³, Subsidio, Vigente Desde, Estado (badge activa/inactiva), Creada.

**JS Inline:**
- Preview de subsidio en tiempo real (`inputSubsidio` → `updateSubsidioPreview()`).
- `calcularEjemplo(consumo, tarifa)` → Simula cálculo idéntico al backend.
- `renderPreviewCard(ex, label)` → Genera card HTML con desglose.
- Submit AJAX (`fetch` a `/billing/config/save`, `X-Requested-With: XMLHttpRequest`). CSRF via `FormData`. Error/Success con div y Toast.
- Doble submit prevention (`submitting` flag + `btn.disabled`).

### 5.4 `billing/process.html` (Motor de Cierre de Mes)

**Componentes Clave:**
1. **Header:** Título "Motor de Cierre de Mes" + Botón "Volver a Boletas".
2. **Steps Indicator:** 3 pasos con dots (inactive/active/done) y líneas conectoras: 1. Configurar → 2. Revisar → 3. Ejecutar.
3. **Alerta si no hay tarifa:** Warning amber con link a "Configurar tarifas".
4. **Step 1 – Configurar (`#configSection`):**
   - Form: Periodo (`type="month"`, default mes actual), Fecha Emisión (`type="date"`, default hoy), Fecha Vencimiento (`type="date"`, default día 28).
   - Botón "Generar Vista Previa" (deshabilitado si no hay tarifa).
5. **Step 2 – Revisar (`#previewSection`, hidden):**
   - Tarifa aplicada (grid 6 KPIs: cargo fijo, valor m³, límite, sobreconsumo, mora, subsidio %).
   - Barra de avance lecturas (progress bar teal + texto X/Y).
   - Monto estimado total (KPI grande) + Boletas existentes.
   - Tabla "Socios con Lectura" (Socio, RUT, Consumo, Lectura, Mora, Monto Est.).
   - Tabla "Socios sin Lectura (Omitidos)" (Socio, RUT, Estado, Razón) – solo si hay.
   - Warning boletas existentes (red, con link a boletas).
   - Botones: "Modificar parámetros" + "Ejecutar Cierre de Mes".
6. **Confirm Modal (`#confirmModal`):** Cantidad boletas + periodo + advertencia "no se puede deshacer". Botones Cancelar + "Sí, Ejecutar Cierre".
7. **Step 3 – Resultado (`#resultSection`, hidden):**
   - KPIs: boletas creadas, omitidos, lecturas auto-validadas, warnings.
   - Warnings (amber) y Omitidos (lista).
   - Acciones post-cierre: "Ver Boletas Generadas" (link index) + "Nuevo Cierre" (reset).
8. **Historial de Cierres:** Tags clickeables con periodo + cantidad de boletas. Link a `index?periodo=YYYY-MM`.

**JS Inline:**
- Estado local: `currentPreview`, `currentPeriodo`, `currentFechaEmision`, `currentFechaVencimiento`.
- `setStep(step)` → Actualiza dots, líneas, labels.
- Submit Preview → `fetch(POST /billing/process/preview)` → Renderiza tarifa, avance, tablas, warnings.
- "Modificar parámetros" → `volverAConfig()` → Oculta preview, vuelve a step 1.
- Execute → Abre confirm modal → `fetch(POST /billing/process/execute)` → Muestra resultado step 3.
- `resetProcess()` → Vuelve a step 1 limpia.

**CSS Custom (en `extra_head`):**
- `.badge-sm` variants (teal, amber, red, stone).
- `.progress-track` / `.progress-fill` (barra de avance).
- `.step-dot` / `.step-dot-inactive` / `.step-dot-active` / `.step-dot-done`.
- `.preview-table` (tabla compacta).
- `@keyframes resultFadeUp` → `.result-animate`.

---

## 6. JavaScript del Módulo (Patrones)

### 6.1 DataTables Server-Side (`index.html`)
```javascript
var table = $('#tablaBoletas').DataTable({
  processing: true, serverSide: true,
  ajax: { url: '/billing/api/list', data: function(d){ d.periodo = ...; d.status = ...; } },
  columns: [...],
  order: [[0, 'desc']], pageLength: 25,
  language: { url: '//cdn.datatables.net/plug-ins/.../es-ES.json' },
  scrollX: true, autoWidth: false,
});
```

### 6.2 Fetch API Pattern (Config + Process + Acciones)
Mismo patrón que Módulos 4 y 5:
```javascript
fetch(url, {
  method: 'POST',
  headers: {'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': CSRF_TOKEN},
  body: new FormData(form) /* o JSON */
})
.then(res => res.json())
.then(data => { if(data.success) { showToast(); reload(); } else { showError(); } })
.catch(() => showError('Error de conexión.'))
.finally(() => { submitting = false; btn.disabled = false; });
```

### 6.3 Utilidades Comunes (Duplicadas en templates)
```javascript
function formatCLP(val) { return '$' + Number(val||0).toLocaleString('es-CL', {maximumFractionDigits:0}); }
function showToast(msg, type) { ... } // Slide-in, auto-dismiss 4s
function badgeStatus(status) { ... } // Genera HTML badge
```

### 6.4 Simulación de Cobro (`config.html`)
```javascript
function calcularEjemplo(consumo, tarifa) { ... } // Replica exacta de calcular_desde_tarifa
function renderPreviewCard(ex, label) { ... }      // Card HTML con desglose
document.getElementById('btnPreview').addEventListener('click', ...); // Genera 2 ejemplos
```

---

## 7. CSS Crítico y Patrones Visuales

### 7.1 DataTables + Tailwind CDN (Mismo patrón Módulos 4 y 5)
**CSS Puro** en `<style>` del template replicando paleta `navy/teal/sand/stone`. Selectores `.dataTables_wrapper`, `.paginate_button`, `table.dataTable thead th`, `tbody td`, etc.

### 7.2 Badges Semánticos de Boletas
```css
.badge-bill-emitida  { bg: #fef3c7; color: #92400e; dot: #f59e0b; }
.badge-bill-pagada   { bg: #ccfbf1; color: #115e59; dot: #14b8a6; }
.badge-bill-vencida  { bg: #fee2e2; color: #991b1b; dot: #ef4444; }
.badge-bill-anulada  { bg: #f5f5f4; color: #57534e; dot: #a8a29e; }
```
- Estructura: `<span class="badge-bill badge-bill-{status}"><span class="dot"></span>Label</span>`.

### 7.3 Montos en Tabla
```css
.monto-total { font-weight: 600; font-family: 'DM Mono', monospace; }
.monto-total-con-mora { color: #991b1b; }
.monto-subsidio { color: #0d9488; font-size: 0.75rem; }
```

### 7.4 Acciones en Tabla
```css
.actions-group { display: inline-flex; gap: 0.375rem; }
.action-btn { width: 2rem; height: 2rem; border-radius: 0.5rem; border: 1px solid #e8e4de; }
.action-btn--pay { border-color: #0d9488; color: #0d9488; }
.action-btn--anular:hover { border-color: #ef4444; color: #ef4444; }
```

### 7.5 Wizard Steps (`process.html`)
```css
.step-dot-inactive { bg: #f5f3f0; color: #a8a29e; border: 2px solid #e8e4de; }
.step-dot-active   { bg: #0d9488; color: white; box-shadow: 0 0 0 4px rgba(13,148,136,0.15); }
.step-dot-done     { bg: #14b8a6; color: white; }
```

### 7.6 Animaciones
```css
@keyframes resultFadeUp { from { opacity:0; translateY(16px) } to { opacity:1; translateY(0) } }
.result-animate { animation: resultFadeUp 0.5s ease-out forwards; }
```

---

## 8. Integración con Otros Módulos

### 8.1 Módulo 1 (Dashboard Público)
- Sin integración directa. Facturación es dato privado.

### 8.2 Módulo 2 (Auth/RBAC)
- `@permission_required('billing', 1/2)` en todas las rutas Blueprint.
- `current_user.has_permission('billing', 1)` en `admin_sidebar.html` → Visibilidad item "Facturación".
- `current_user.has_permission('billing', 2)` en templates → Botones Cierre de Mes, Pagar, Anular, Marcar vencidas, Configurar Tarifas.
- `created_by_id`, `updated_by_id` en `Bill`, `TariffConfig` → FK a `User`.

### 8.3 Módulo 3 (Main/Portal)
- **Admin Dashboard:** `get_billing_stats()` integrado en `partner_service.get_admin_stats()` → KPIs `total_recaudado`, `meta_recaudacion`, `deudores_mora`, `monto_mora`.
- **Portal Socio:** `get_bills_for_socio_portal()` + `get_socio_saldo_pendiente()` integrados en `partner_service.get_socio_portal_data()` → `recent_bills` array + `saldo_pendiente`.

### 8.4 Módulo 4 (Partners/Catastro)
**Consumo de datos (Facturación ← Catastro):**
- `Partner` → `partner_id`, `nombre`, `rut`, `estado` (filtrado ACTIVO/CORTADO para facturación).
- `Meter` → `multiplicador` (vía `Reading.consumo_real`).
- `Sector` → Agrupación facturación/impresión por ruta (futuro).

**Actualización de estado (Facturación → Catastro):**
- `mark_overdue_bills()` → Marca boletas VENCIDAS. El POS/Caja (Módulo 8) usará esto para lista de corte (`Partner.estado == CORTADO`).
- **Nota:** El cambio de `Partner.estado` a CORTADO por mora se maneja en POS (Módulo 8), no en billing directamente.

**En `partners/detail.html`:**
- Botón "Generar Boleta" visible como **deshabilitado/"Pronto"** en acciones rápidas. Conecta con `partner_service` para facturación individual (futuro).
- Botón "Historial Consumos" visible como **deshabilitado/"Pronto"**. Conecta con `reading_service.get_consumption_history()` (Módulo 5).

### 8.5 Módulo 5 (Lecturas)
**Consumo de datos (Facturación ← Lecturas):**
- `Reading` → `reading_id`, `partner_id`, `periodo`, `lectura_actual`, `lectura_anterior`, `consumo_real`, `consumo`, `multiplicador`, `status`.
- Solo lecturas con `status` in `[VALIDADA, PENDIENTE` se consideran para facturación.
- Lecturas `PENDIENTE` son **auto-validadas** durante el cierre de mes (`reading.validar(user_id)`).

**Flujo completo:**
1. Módulo 5: Operario captura lectura → `status = PENDIENTE`.
2. Módulo 5: Admin valida → `status = VALIDADA` → actualiza `Meter.ultima_lectura_valor`.
3. Módulo 6: Cierre de mes → consume `Reading.consumo_real` → genera `Bill`.
4. Si lectura sigue `PENDIENTE` al momento del cierre → auto-valida.

### 8.6 Módulo 8 (POS/Caja) – Puntos de Conexión Futuros
- `Bill.status == VENCIDA` → Lista de candidatos a corte.
- `Partner` con 2+ boletas vencidas → `partner.cortar_suministro()`.
- `get_partner_outstanding_balance()` → Saldo en caja.
- `Bill.marcar_pagada()` → Registrada desde POS.

### 8.7 Módulo 9 (Reportes SISS) – Puntos de Conexión Futuros
- Boletas por periodo → Informe de recaudación.
- Consumo facturado por sector → Producción/distribución.
- Subsidios aplicados → Informe de subsidios estatales.

---

## 9. Inventario de Archivos del Módulo 6

```
app/
├── models/
│   └── billing.py              # Bill, TariffConfig, BillStatus, Validadores, Hybrid Props, calcular_desde_tarifa, Ciclo de Vida
├── services/
│   └── billing_service.py      # Excepciones, Helpers Tipado, CRUD Tarifas, Preview Cierre, execute_monthly_billing, Ciclo Vida Boletas, Stats, Portal Data
├── blueprints/
│   └── billing.py              # Rutas: index, api_list, config, config_save, api_tariff, process, process_preview, process_execute, mark_paid, anular, mark_overdue, api_stats
├── templates/
│   └── billing/
│       ├── index.html          # Listado DataTables + Filtros + Acciones Pagar/Anular + Modal Anulación
│       ├── config.html         # Configuración Tarifas + Historial + Simulación Cobro JS + Submit AJAX
│       └── process.html        # Wizard 3 Pasos (Configurar→Revisar→Ejecutar) + Preview AJAX + Confirm Modal + Resultado + Historial Cierres
├── static/
│   └── (sin archivos JS dedicados – toda la lógica es inline en templates)
│
├── models/
│   └── partner.py              # (Módulo 4) Partner, Meter, Sector – consumidos por billing
│   └── reading.py              # (Módulo 5) Reading, ReadingStatus – consumidos por billing
├── services/
│   └── partner_service.py      # (Módulo 4) get_admin_stats() y get_socio_portal_data() consumen billing_service
└── __init__.py                  # Registro billing_bp
```

---

## 10. Convenciones, Deuda Técnica y Checklist Extensión

| Tema | Estado / Regla | Acción Futura |
|------|----------------|---------------|
| **Snapshot de Tarifa** | `Bill` almacena `tarifa_*` columns completas. Trazabilidad garantizada aunque tarifas cambien. | OK. |
| **Unicidad Boleta** | `(partner_id, periodo)` único vía Index. Verificado en `execute_monthly_billing()`. | OK. |
| **Subsidio Ley 20.998** | Implementado en `calcular_desde_tarifa()`: % sobre consumo, tope 15 m³, fijo/sobreconsumo no afectos. | OK. |
| **Historial Tarifas** | Patrón: cada cambio crea nuevo registro, desactiva anterior. Solo se edita la activa. | OK. |
| **Auto-validación Lecturas** | `execute_monthly_billing()` auto-valida lecturas `PENDIENTE` durante cierre. | OK. |
| **Mora Automática** | `_partner_tiene_mora()` verifica boletas `VENCIDA` antes de generar nueva boleta. | OK. |
| **DataTables Server-Side** | Implementado en `index.html`. jQuery + DataTables Core + Responsive. | **Pendiente:** Exportar Excel/PDF (cargar jsPDF/SheetJS). |
| **Detalle Boleta** | No existe template `bill/detail.html`. | **Pendiente:** Crear vista detalle de boleta individual con desglose completo + botón imprimir/PDF. |
| **Facturación Individual** | Solo existe cierre masivo. | **Futuro:** Botón "Generar Boleta" en `partners/detail.html` (actualmente "Pronto"). Requiere ruta `POST /billing/generate/<partner_id>`. |
| **Impresión/PDF** | No implementado. | **Futuro:** Generar PDF de boleta para impresión/distribución. Librería: WeasyPrint o ReportLab. |
| **Notificación Vencimiento** | `mark_overdue_bills()` solo actualiza BD. | **Futuro:** Push notification / email al secretario y/o socio al marcar vencida. |
| **CSRF en API JSON** | `X-CSRFToken` header o `csrf_token` en FormData. `CSRFProtect` habilitado globalmente. | OK. |
| **Flash Messages** | Render en `index.html`, `config.html`, `process.html` (inline). | **Crear** `components/_flashes.html` macro para DRY. |
| **JS Duplicado** | `showToast()`, `formatCLP()` duplicados en `index.html`, `config.html`, `process.html`. | **Extraer** `static/js/billing_utils.js` para DRY. |
| **Tests** | No existen tests unitarios para `billing_service`. | **Crítico:** Testear `execute_monthly_billing` (duplicados, sin lectura, auto-validación, mora), `create_tariff` (desactiva anterior), `calcular_desde_tarifa` (subsidio, sobreconsumo, mora). |

---

## 11. Comandos de Verificación Rápida

```bash
# 1. Rutas registradas
flask routes | grep billing

# 2. Shell: Probar Service Layer
flask shell
# >>> from app.services.billing_service import get_active_tariff, get_billing_stats, get_billing_preview
# >>> tarifa = get_active_tariff()
# >>> print(tarifa.cargo_fijo, tarifa.valor_m3_base, tarifa.porcentaje_subsidio_display)
# >>> stats = get_billing_stats()
# >>> print(stats['total_recaudado'], stats['meta_recaudacion'], stats['deudores_mora'])

# 3. Verificar Modelos
flask shell
# >>> from app.models.billing import Bill, TariffConfig, BillStatus
# >>> b = Bill.query.first()
# >>> print(b.periodo_display, b.monto_total, b.status.value, b.badge_status)
# >>> print(b.partner.nombre, b.tarifa_cargo_fijo, b.tarifa_subsidio_pct)
# >>> t = TariffConfig.query.filter_by(activo=True).first()
# >>> print(t.cargo_fijo, t.valor_m3_base, t.limite_sobreconsumo)

# 4. Verificar Integración con Módulo 4 y 5
flask shell
# >>> from app.services.partner_service import get_admin_stats, get_socio_portal_data
# >>> stats = get_admin_stats()
# >>> print('total_recaudado:', stats['total_recaudado'], 'deudores_mora:', stats['deudores_mora'])

# 5. Verificar Preview
flask shell
# >>> from app.services.billing_service import get_billing_preview
# >>> preview = get_billing_preview('2026-07')
# >>> print(preview['total_partners'], preview['partners_con_lectura'], preview['estimated_total'])

# 6. Lint Templates
grep -rn "FIX\|TODO\|FIXME" app/templates/billing/

# 7. Verificar Esquema BD
flask shell
# >>> from app import db
# >>> db.engine.execute("PRAGMA table_info(bills);").fetchall()
# >>> db.engine.execute("PRAGMA table_info(tariff_configs);").fetchall()
```

---

## 12. Puntos de Extensión Inmediatos (Próximos Módulos)

| Módulo | Archivo a Modificar / Extender | Detalle |
|--------|-------------------------------|---------|
| **6b. Detalle Boleta** | `billing.py` (blueprint), `templates/billing/detail.html` | Crear vista detalle individual con desglose completo (fijo + consumo + sobreconsumo - subsidio + mora = total), snapshot de tarifa, datos socio/lectura, botón imprimir/PDF. |
| **6c. Facturación Individual** | `billing_service.py`, `billing.py` (blueprint), `partners/detail.html` | Habilitar botón "Generar Boleta" en ficha socio. Ruta `POST /billing/generate/<partner_id>` que crea boleta individual (no masiva). |
| **6d. PDF/Impresión** | `billing_service.py`, `billing.py` (blueprint) | Generar PDF de boleta. WeasyPrint o ReportLab. Ruta `GET /billing/<id>/pdf`. |
| **7. Notificaciones** | `billing_service.py` | En `mark_overdue_bills()`: crear notificación para admin cuando se marcan vencidas. En `execute_monthly_billing()`: notificar socios con boleta nueva. |
| **8. POS/Caja** | `billing_service.py` | Exponer `get_corte_candidates()` → socios con 2+ boletas VENCIDAS. Exponer `get_partner_outstanding_balance()` (ya existe). `mark_bill_as_paid()` llamado desde POS. |
| **9. Reportes SISS** | `billing_service.py` | Crear `get_billing_report(periodo)` → recaudación, subsidios aplicados, mora, consumo facturado por sector. |

---

> **Fin del contexto Módulo 6**.  
> Este documento permite a cualquier IA continuar el desarrollo del **Módulo 6b (Detalle/Impresión Boleta)**, **Módulo 7 (Notificaciones)**, o **Módulo 8 (POS/Caja)** entendiendo exactamente cómo el motor de facturación genera boletas masivamente, cómo calcula montos aplicando la Ley 20.998 con subsidios y sobreconsumo, cómo funciona el ciclo de vida completo de una boleta (emitida → pagada/vencida → anulada), y qué APIs y contratos de datos están disponibles para integración con los módulos siguientes.
```