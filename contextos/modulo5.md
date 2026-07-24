Aquí tienes el archivo `modulo5.md` completo. Créalo en la raíz del proyecto junto a los demás:

---

```markdown
# Contexto Técnico – Módulo 5: Toma de Lecturas en Terreno (`readings`)

> **Generado automáticamente** a partir del código real del proyecto.  
> Última actualización: 2026-07-24  

---

## 1. Resumen del Módulo

| Aspecto | Detalle |
|---------|---------|
| **Propósito** | Captura mensual de lecturas de medidores en terreno/officina, validación administrativa, sincronización offline, y provisión de datos de consumo para Dashboard (Módulo 3), Portal Socio (Módulo 3) y Facturación (futura Módulo 6). |
| **Blueprint** | `readings_bp` (variable `bp`) – registrado con `url_prefix='/readings'` en `app/__init__.py`. |
| **Layout base** | `layouts/base_admin.html` (incluye `components/admin_sidebar.html` con item "Lecturas" visible si `readings` ≥ 1). |
| **Acceso** | **Privado** – requiere `@login_required` + `@permission_required('readings', level)`. |
| **Permisos RBAC** | `readings`: Level 1 (Lectura/Listado/Detalle/APIs consulta), Level 2 (Captura, Aprobación, Rechazo, Batch). |
| **Modelos Core** | `Reading` (definido en `app/models/reading.py`). Consume `Partner`, `Meter`, `Sector` de `app/models/partner.py`. |
| **Servicio Central** | `app/services/reading_service.py` (Lógica transaccional: `capture_reading`, `validate_reading`, `reject_reading`, `validate_batch`, `sync_offline_readings`, `get_readings_for_capture`, `get_lecturas_stats`, `get_consumption_history`). |
| **JavaScript** | Vanilla ES6: `reading_val.js` (validación cliente), `offline_sync.js` (sincronización offline via LocalStorage). Lógica inline en templates (DataTables, Chart.js, modales). |
| **Estilo** | Tailwind CSS CDN + CSS custom inline para DataTables y captura mobile-first. Google Fonts `DM Serif Display` + `Lora`. |

---

## 2. Modelo de Datos (`app/models/reading.py`)

### 2.1 Enum de Estado de Lectura

```python
class ReadingStatus(str, enum.Enum):
    PENDIENTE = 'pendiente'         # Capturada en terreno, no revisada
    VALIDADA = 'validada'           # Revisada y aprobada por admin/secretaria
    RECHAZADA = 'rechazada'         # Rechazada por datos incoherentes
    ANULADA = 'anulada'             # Anulada por error humano o duplicada
```

### 2.2 Tabla `readings` (Lectura Mensual de Medidor)

| Campo | Tipo | Detalle |
|-------|------|---------|
| `id` | PK Integer | |
| `created_at` / `updated_at` | DateTime | Auditoría. |
| `created_by_id` / `updated_by_id` | FK Integer (users.id) | Nullable. Usuario que capturó/modificó. |
| `meter_id` | FK Integer (meters.id) | **NOT NULL, Index**. Medidor leído. |
| `partner_id` | FK Integer (partners.id) | **NOT NULL, Index**. Socio dueño del medidor. |
| `sector_id` | FK Integer (sectors.id) | Nullable, Index. Sector/ruta de captura. |
| `periodo` | String(7) | **NOT NULL**. Formato `YYYY-MM`. Index compuesto único con `meter_id` (excluye ANULADAS). |
| `fecha` | Date | **NOT NULL**. Fecha real de toma en terreno. |
| `lectura_actual` | Integer | **NOT NULL**. Valor del contador (índice). CheckConstraint ≥ 0. |
| `lectura_anterior` | Integer | **NOT NULL**. Valor cacheado del periodo anterior (de `Meter.ultima_lectura_valor`). |
| `consumo` | Integer | **NOT NULL**. Calculado: `lectura_actual - lectura_anterior` (m³). CheckConstraint ≥ 0. |
| `consumo_estimado` | Integer | Nullable. Para lecturas aproximadas. |
| `multiplicador` | Integer | Default 1. Copiado de `Meter.multiplicador` al crear. |
| `status` | Enum `ReadingStatus` | Default `PENDIENTE`. Index. |
| `origen` | String(20) | Default `terreno`. Valores: `terreno`, `oficina`, `estimada`, `ajuste`. |
| `latitud` / `longitud` | Float | Nullable. GPS WGS84 del punto de lectura. |
| `foto_url` | String(500) | Nullable. Placeholder para foto del medidor (futuro). |
| `observaciones` | Text | Nullable. Notas del capturador. |
| `motivo_rechazo` | Text | Nullable. Obligatorio si `status=RECHAZADA`. |
| `es_lectura_inicial` | Boolean | Default False. True si es la primera post-instalación. |
| `offline_id` | String(50) | Nullable. ID local para sincronización offline. |
| `sincronizado` | Boolean | Default True. False si capturado offline pendiente de sync. |

**Índices y Constraints:**
- `ix_reading_meter_periodo` → Índice compuesto único `(meter_id, periodo)` (evita duplicados).
- `ix_reading_periodo` → Index en `periodo`.
- `ix_reading_status` → Index en `status`.
- `ix_reading_ruta` → Index compuesto `(sector_id, fecha)` para captura por ruta.
- `ck_reading_lectura_no_negativa` → `lectura_actual >= 0`.
- `ck_reading_consumo_no_negativo` → `consumo >= 0`.

### 2.3 Relaciones

```python
meter = relationship('Meter', back_populates='readings', lazy='joined')
partner = relationship('Partner', lazy='joined')       # Sin back_populates explícito
sector = relationship('Sector', lazy='joined')          # Sin back_populates explícito
created_by = relationship('User', foreign_keys=[created_by_id], lazy='selectin')
updated_by = relationship('User', foreign_keys=[updated_by_id], lazy='selectin')
```

**Nota:** `Reading.partner` y `Reading.sector` son relaciones directas (no a través de `Meter`), ya que se almacenan como FK independientes para desnormalizar y simplificar queries.

### 2.4 Propiedades Híbridas / Helpers

| Propiedad | Descripción |
|-----------|-------------|
| `consumo_real` | `consumo * multiplicador`. Consumo neto aplicando factor del medidor. |
| `periodo_display` | Formato legible: `Ene 2025`, `Jul 2026`, etc. |
| `fecha_formateada` | `DD/MM/YYYY`. |
| `badge_status` | Clase CSS semántica para UI (`badge-pending`, `badge-success`, `badge-danger`, `badge-muted`). |

### 2.5 Métodos de Instancia (State Machine)

| Método | Efecto |
|--------|--------|
| `validar(user_id)` | `status → VALIDADA`. **Actualiza cache en Meter**: `ultima_lectura_valor = lectura_actual`, `fecha_ultima_lectura = fecha`. |
| `rechazar(motivo, user_id)` | `status → RECHAZADA`, `motivo_rechazo = motivo`. |
| `anular(user_id)` | `status → ANULADA`. No afecta cálculos. |
| `calcular_consumo()` | Recalcula `consumo = max(0, lectura_actual - lectura_anterior)`. |
| `to_dict()` | Serialización completa para API/JS (incluye `partner_nombre`, `meter_serie`, `consumo_real`, `created_by`, etc.). |

### 2.6 Validadores del Modelo

```python
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
```

---

## 3. Capa de Servicio (`app/services/reading_service.py`)

> **Patrón:** Funciones puras, transaccionales (`db.session.commit/rollback`), excepciones tipadas (`ValidationError`, `BusinessRuleError`, `NotFoundError`), helpers de tipado seguro (`_to_int`, `_to_float`, `_to_date`).

### 3.1 Excepciones Personalizadas
```python
class ReadingServiceError(Exception): ...
class ValidationError(ReadingServiceError): ...       # field específico
class BusinessRuleError(ReadingServiceError): ...    # regla de negocio
class NotFoundError(ReadingServiceError): ...        # entidad no existe
```

### 3.2 Helpers Privados

| Helper | Descripción |
|--------|-------------|
| `_to_int(val)` | Conversión segura a int (None si vacío/inválido). |
| `_to_float(val)` | Conversión segura a float. |
| `_to_date(val)` | Convierte ISO `YYYY-MM-DD` o `DD/MM/YYYY`. Default: hoy. |
| `_generate_periodo(fecha)` | Genera `YYYY-MM` de una fecha. |
| `_get_current_periodo()` | Periodo actual (mes en curso). |
| `_get_reading_query()` | Query base con eager loading: `meter`, `partner`, `sector`. |

### 3.3 Reglas de Negocio – Validación de Consumo

#### `validate_consumption_rules(meter_id, lectura_actual, lectura_anterior)`
Retorna `{consumo, warnings[], errors[], avg_consumption, is_valid}`.

**Reglas aplicadas:**
1. **Lectura retrocedida** → Error: `lectura_actual < lectura_anterior` (medidor cambiado/reiniciado).
2. **Consumo > 100% promedio** → Warning: consumo supera `2× promedio últimos 3 meses`.
3. **Consumo negativo** → Error defensivo (redundante si regla 1 pasa).

#### `_calc_avg_consumption(meter_id, months=3)`
Promedio de consumo de las últimas N lecturas (VALIDADAS/PENDIENTES).

### 3.4 Captura Individual

#### `capture_reading(data, user_id) → Reading`
**Flujo:**
1. Valida `meter_id` → existe, `es_actual=True`, `estado=INSTALADO`.
2. Valida socio asociado → `estado` en `[ACTIVO, CORTADO]`.
3. Parsea `lectura_actual` (int, ≥ 0), `fecha` (date).
4. Calcula `lectura_anterior` de `Meter.ultima_lectura_valor` (o `lectura_instalacion`).
5. Calcula `consumo = max(0, actual - anterior)`.
6. **Unicidad:** No puede haber dos lecturas del mismo medidor en el mismo periodo (excluye ANULADAS).
7. Ejecuta `validate_consumption_rules()` → bloquea si hay errors.
8. Crea `Reading` con todos los campos. Commit.

**Data esperada:**
```python
{
    'meter_id': int,
    'lectura_actual': int,
    'fecha': str,           # YYYY-MM-DD o DD/MM/YYYY
    'observaciones': str,   # opcional
    'origen': str,          # default 'terreno'
    'latitud': float,       # opcional
    'longitud': float,      # opcional
    'offline_id': str,      # opcional
    'periodo': str,         # opcional (se calcula de fecha)
}
```

### 3.5 Sincronización Offline (Batch)

#### `sync_offline_readings(readings_data, user_id) → Dict`
Procesa un lote de lecturas capturadas offline.

**Retorna:**
```python
{
    'synced': int,       # Cantidad OK
    'skipped': int,      # Duplicadas por offline_id o periodo
    'errors': list,      # Errores por lectura [{index, offline_id, error}]
    'readings': list,    # Objetos creados (to_dict())
}
```

**Flujo:** Itera cada item, verifica `offline_id` duplicado en BD, llama `capture_reading()`. Duplicados de periodo → skip silencioso.

### 3.6 Listado y Consultas (DataTables)

#### `search_readings(term, periodo, status, sector_id, page, per_page, order_by, order_dir)`
Búsqueda paginada con filtros combinados. `outerjoin(Meter)` + `outerjoin(Partner)` para búsqueda por RUT/nombre/serie. Retorna `(items, total)`.

#### `get_readings_for_capture(sector_id, periodo) → List[Dict]`
Genera la lista de medidores para captura en terreno.

**Flujo:**
1. Query `Meter` con `es_actual=True`, `estado=INSTALADO`, `partner_id IS NOT NULL`.
2. **JOIN único** a `Partner` y `Sector` (via `contains_eager` para evitar duplicados).
3. Filtro por `sector_id` si se proporciona.
4. Ordenamiento: `Sector.orden_lectura → Partner.nombre`.
5. Para cada medidor, verifica si ya tiene lectura en el periodo.
6. Retorna lista de dicts con `meter_id`, `partner_nombre`, `partner_rut`, `direccion`, `sector`, `lectura_anterior`, `lectura_actual`, `consumo`, `status`, `capturado`.

**Nota técnica (Fix):** Se usa `contains_eager()` en vez de `joinedload()` + `.join()` duplicados. Esto evita el error `ambiguous column name: partners.sector_id` que ocurría con SQLite cuando el mismo JOIN se generaba múltiples veces.

### 3.7 Validación / Aprobación / Rechazo (Admin)

| Función | Descripción |
|---------|-------------|
| `validate_reading(reading_id, user_id)` | Aprueba lectura pendiente. Llama `reading.validar()` que actualiza cache en `Meter`. |
| `reject_reading(reading_id, motivo, user_id)` | Rechaza lectura con motivo obligatorio. Solo PENDIENTE/VALIDADA. |
| `validate_batch(reading_ids, user_id)` | Aprueba lote de lecturas. Retorna `{validated, errors}`. |

### 3.8 Estadísticas para Dashboard

#### `get_lecturas_stats(periodo) → Dict`
**Retorna:**
```python
{
    'periodo': str,
    'total_medidores': int,
    'lecturas_tomadas': int,
    'lecturas_validadas': int,
    'lecturas_pendientes': int,
    'lecturas_rechazadas': int,
    'pct_lecturas': float,       # % avance
    'consumo_promedio': float,   # m³ promedio del periodo
}
```

### 3.9 Historial de Consumo

| Función | Descripción |
|---------|-------------|
| `get_consumption_history(meter_id, months=12)` | Historial para Chart.js. Lista de `{periodo, label, consumo, consumo_real, lectura, fecha}`. Orden cronológico. |
| `get_partner_readings_summary(partner_id)` | Resumen para ficha socio: `{lecturas_count, consumo_total, consumo_promedio, ultima_lectura, history}`. |
| `get_consumption_history_for_portal(meter_id, months=12)` | Versión simplificada para `partner_service.get_socio_portal_data()`. Formato `{month, consumption}`. |

### 3.10 Contratos de Datos para Módulos Externos

**Integración con `partner_service.py` (Módulo 4):**
- `get_admin_stats()` importa y llama `get_lecturas_stats()` para llenar `pct_lecturas`, `lecturas_tomadas`, `consumo_promedio`.
- `get_socio_portal_data()` importa y llama `get_consumption_history_for_portal()` para llenar `consumption_history`.

---

## 4. Blueprint y Rutas (`app/blueprints/readings.py`)

> **Estructura:** `bp = Blueprint('readings', __name__, url_prefix='/readings')`.  
> **Decoradores:** `@login_required` en **todas**. `@permission_required('readings', 1)` en GET (list, detail, api stats/history). `@permission_required('readings', 2)` en POST (capture, validate, reject, sync, batch).

### 4.1 Rutas Principales

| Ruta | Método | Permiso | Función | Descripción |
|------|--------|---------|---------|-------------|
| `/` | GET | `readings:1` | `index()` | Listado DataTables Server-Side (`index.html`). Pasa `sectores`, `estados`, `periodos`. |
| `/api/list` | GET | `readings:1` | `api_list()` | **JSON DataTables** Lecturas (filtros: search, periodo, status, sector_id). Serializa campos `periodo_display`, `partner_nombre`, `partner_rut`, `meter_serie`, `consumo`, `status`, `status_raw`, etc. |
| `/capture` | GET | `readings:2` | `capture()` | **Interfaz mobile-first** de captura por sector/ruta. Pasa `sectores`, `periodo`, `sector_id`, `items` (lista de medidores). |
| `/api/capture` | POST | `readings:2` | `api_capture()` | **AJAX JSON** Captura individual. Llama `capture_reading()`. Retorna `{success, message, reading}`. |
| `/api/validate-consumption` | POST | `readings:1` | `api_validate_consumption()` | **AJAX JSON** Validación en tiempo real del consumo (llamado desde JS). |
| `/api/sync` | POST | `readings:2` | `api_sync()` | **AJAX JSON** Sincronización batch offline. Acepta JSON array. Llama `sync_offline_readings()`. |
| `/api/sync/status` | GET | `readings:1` | `api_sync_status()` | **JSON** Estado de sincronización del periodo: `{offline_pending, readings_pending}`. |
| `/<int:reading_id>/validate` | POST | `readings:2` | `validate_route()` | Aprueba lectura individual. Soporta JSON (AJAX) y form POST. |
| `/<int:reading_id>/reject` | POST | `readings:2` | `reject_route()` | Rechaza lectura con `motivo_rechazo`. Soporta JSON y form. |
| `/api/validate-batch` | POST | `readings:2` | `api_validate_batch()` | **AJAX JSON** Aprobación masiva. Acepta `{reading_ids: [int]}`. |
| `/<int:reading_id>` | GET | `readings:1` | `detail()` | Detalle lectura individual. Pasa `reading` + `history` (consumo últimos 6 meses). |

### 4.2 APIs Auxiliares

| Ruta | Método | Permiso | Función | Descripción |
|------|--------|---------|---------|-------------|
| `/api/stats` | GET | `readings:1` | `api_stats()` | Estadísticas para dashboard. Opcional `?periodo=YYYY-MM`. |
| `/api/history/<int:meter_id>` | GET | `readings:1` | `api_consumption_history()` | Historial Chart.js. Opcional `?months=12`. Retorna `{labels, data, history}`. |
| `/api/partner/<int:partner_id>/summary` | GET | `readings:1` | `api_partner_summary()` | Resumen lecturas socio para ficha partners/detail. |

### 4.3 Helper Privado

#### `_get_available_periodos()`
Genera lista de periodos (últimos 12 meses + actual) para filtro dropdown. Retorna lista de `(periodo_str, label)` ej: `('2026-07', 'Jul 2026')`.

---

## 5. Templates (Vistas Jinja2)

### 5.1 Herencia y Estructura Común
- **Todos** extienden `layouts/base_admin.html`.
- **Bloques usados:** `title`, `extra_head`, `content`, `extra_scripts`.
- **Navbar/Sidebar:** `admin_sidebar.html` muestra "Lecturas" activo (`request.endpoint.startswith('readings.')`).

### 5.2 `readings/index.html` (Listado Principal)

**Componentes Clave:**
1. **Header:** Título + Botón "Capturar Lecturas" (permiso 2, link a `/readings/capture`).
2. **Filtros (Form `#filterForm`):** Input Search (debounce 350ms), Select Periodo (últimos 12 meses), Select Estado (`ReadingStatus`), Select Sector (activos), Botón "Limpiar".
3. **Tabla `#tablaLecturas` (DataTables Server-Side):**
   - **Columnas:** Checkbox (solo pendientes), Periodo, Socio (+ RUT), Medidor (mono), Sector (badge navy), Lect. Anterior, Lect. Actual, Consumo (mono + multiplicador), Estado (Badge Semántico), Fecha, Acciones (Ver Detalle).
   - **Ordenamiento por defecto:** `[1, 'desc']` (Periodo), `[9, 'desc']` (Fecha).
   - **Responsive:** `scrollX: true`, `autoWidth: false`.
4. **Footer:** Botón "Aprobar seleccionadas" (con badge contador + lógica batch) + Link "Ir a Captura" + Info registros.

**Badges Semánticos:**
```
pendiente → bg: amber-100, text: amber-800, dot: amber-500
validada  → bg: teal-100, text: teal-800, dot: teal-500
rechazada → bg: red-100, text: red-800, dot: red-500
anulada   → bg: stone-100, text: stone-600, dot: stone-400
```

**Funcionalidad Checkbox + Batch (JS inline):**
- Checkbox master `#selectAll` en thead.
- Checkboxes individuales `.row-checkbox` con `data-id` (solo si `status_raw === 'pendiente'`).
- `selectedIds` (Set) persiste entre páginas DataTables (restauración en `draw` event).
- Botón `#btnValidateSelected` → `fetch(POST /readings/api/validate-batch, {reading_ids: [...]})` → Toast → `table.ajax.reload()`.
- Badge `#selectionCount` muestra cantidad seleccionada.

### 5.3 `readings/capture.html` (Captura Mobile-First)

**Componentes Clave:**
1. **Header:** Título, Periodo, Indicador de conectividad (online/offline), Link "Ver listado".
2. **Filtros Sticky (`.capture-sticky`):** Select Sector (con orden de lectura), Input Month (periodo), Botón "Cargar". Sticky debajo del header admin.
3. **Barra de Progreso:** `X / Y lecturas` con progress bar teal.
4. **Cards de Lectura (`.reading-card`):** Grid responsive (1 col mobile, 2 col desktop).
   - **Cabecera:** Nombre socio, dirección, Nº serie medidor, sector, badge "Capturada".
   - **Grid 3 columnas:** Lectura anterior (solo lectura), Lectura actual (input editable o display si capturada), Consumo calculado.
   - **Botón individual** "Guardar" (si no capturada).
   - **Observaciones** expandible (toggle).
   - **Feedback messages** inyectados por JS.
5. **Botón flotante** "Siguiente pendiente" (scroll + focus).
6. **Empty State** si no hay medidores.

**Estilos CSS:**
- `.reading-card` (base, `.captured`, `.has-warning`, `.has-error`).
- `.reading-input` (font mono, center, sin spinners, focus teal ring).
- `.capture-sticky` (sticky top, backdrop blur).
- `.capture-grid` (CSS Grid responsive).
- `.btn-next-pending` (fixed bottom-right).

**JS Inline (capture.html):**
- `OfflineSync.init()` con CSRF token y sync URL.
- `_saveReading(meterId, btn)`: Valida con `ReadingValidator.validate()`, fetch POST a `/readings/api/capture`, fallback offline con `OfflineSync.enqueue()`.
- `_markAsCaptured()`: Reemplaza input con display estático, agrega badge, elimina botón guardar.
- Auto-focus primer input pendiente (solo desktop).
- Navegación Enter → Guardar, Tab → siguiente input vacío.
- Progreso dinámico (`_updateProgress()`).

### 5.4 `readings/detail.html` (Detalle de Lectura)

**Layout:** Grid `lg:col-span-2` (Izq: Lectura + Gráfico + Observaciones) + `lg:col-span-1` (Der: Acciones + Medidor + Auditoría).

**Secciones Izquierda:**
1. **Header:** Nombre socio, periodo, Botones Aprobar/Rechazar (solo si `pendiente`, permiso 2).
2. **Tarjeta principal:** Badge estado, fecha, KPIs (Anterior, Actual, Consumo con multiplicador), Info socio/medidor/sector/origen.
3. **Gráfico Chart.js:** Barras de historial consumo (6 meses). Periodo actual resaltado en teal, resto en navy-200.
4. **Observaciones + Motivo Rechazo** (si existen).

**Secciones Derecha:**
1. **Acciones:** Ver Socio (link), Captura del Sector (link con params), Generar Boleta (disabled "Pronto").
2. **Datos técnicos medidor:** Serie, Marca, Modelo, Multiplicador, Lect. Instalación, Consumo Acumulado.
3. **Auditoría:** Capturada por, fecha, modificada por, periodo, offline_id.

**Modal Rechazo (`#modal-reject`):**
- Overlay + form con textarea `motivo_rechazo` (obligatorio).
- Submit → `fetch(POST /readings/{id}/reject, {motivo_rechazo})` → Toast → `location.reload()`.
- Cierre: botón, overlay click, ESC.

**JS Inline:**
- `showToast()` local.
- Modal helpers (open/close, ESC, overlay click).
- Botón Aprobar → `fetch(POST /readings/{id}/validate)` → Toast → reload.
- Gráfico Chart.js con datos `{{ history | tojson }}`.

---

## 6. JavaScript del Módulo

### 6.1 `reading_val.js` (Validación Cliente – Captura)

> **API:** `window.ReadingValidator`  
> **Dependencias:** Ninguna (Vanilla ES6).  
> **Carga:** `capture.html` via `<script src="static/js/reading_val.js">`.

| Método | Descripción |
|--------|-------------|
| `validate(lecturaActual, lecturaAnterior, avgConsumption)` | Retorna `{isValid, consumo, warnings[], errors[], level}`. |
| `init()` | Inicializa validación en todos los `.reading-input`. Auto-init al DOMContentLoaded. |
| `validateAll()` | Valida todos los inputs (pre-submit batch). Retorna `{allValid, invalidCount, details[]}`. |
| `forceNumericKeyboard(input)` | Fuerza `inputmode="numeric"`, `pattern="[0-9]*"`, previene no-dígitos. |

**Reglas de Validación (idénticas al backend):**
1. `lectura_actual < lectura_anterior` → **Error**: "menor a la anterior, verificar medidor cambiado".
2. `consumo > 2× promedio 3 meses` → **Warning**: "consumo alto, supera 100% del promedio".
3. `consumo === 0` → **Warning informativo**: "sin consumo, verificar medidor".

**Feedback Visual:**
- Input borde: `border-teal` (válido), `border-amber-400` (warning), `border-red-400` (error).
- Icono inyectado (check/alerta/cruz) posicionado absolute right del input.
- Mensaje inyectado debajo del input wrapper.
- Consumo display actualizado en tiempo real (color navy-700/stone-400/red-600).

**Configuración:**
```javascript
CONFIG = {
    INPUT_SELECTOR: '.reading-input',
    ROW_SELECTOR: '.reading-row',
    ATTR_LECTURA_ANTERIOR: 'data-lectura-anterior',
    ATTR_AVG_CONSUMPTION: 'data-avg-consumption',
    CONSUMPTION_THRESHOLD: 1.0,
    DEBOUNCE_MS: 300,
}
```

### 6.2 `offline_sync.js` (Sincronización Offline)

> **API:** `window.OfflineSync`  
> **Dependencias:** Ninguna (Vanilla ES6).  
> **Carga:** `capture.html` via `<script src="static/js/offline_sync.js">`.

| Método | Descripción |
|--------|-------------|
| `init(options)` | Inicializa con `{syncUrl, csrfToken, maxRetries, autoSync}`. |
| `enqueue(readingData)` | Agrega a cola offline. Prevención duplicados por `offline_id` y `meter_id+periodo`. Retorna `{queued, offline_id, queue_length}`. |
| `syncNow()` | Fuerza sincronización batch. Promise con resultado. |
| `getQueue()` | Cola actual de LocalStorage. |
| `getPendingCount()` | Cantidad pendientes. |
| `clearQueue()` | Limpia toda la cola. |
| `removeById(offlineId)` | Elimina item específico. |
| `getStatus()` | Estado completo: `{isOnline, isSyncing, pendingCount, lastSyncAttempt, lastSyncResult}`. |

**Persistencia:** LocalStorage clave `apr_readings_offline_queue`.

**Sincronización:**
- Batch POST a `SYNC_URL` (`/readings/api/sync`) con toda la cola como JSON array.
- Procesamiento de resultado: remueve sincronizados (`offline_id` en `serverResult.readings`), mantiene errores con `sync_attempts++`.
- **Retry con backoff exponencial:** base 2000ms × 2^(retry-1), max 3 reintentos.

**Conectividad:**
- Listeners `window.online/offline`.
- Health check cada 30s contra `/readings/api/sync/status` (fetch HEAD con timeout 5s).
- Auto-sync al recuperar conexión (configurable).

**UI:**
- Badge fijo `#offline-badge` bottom-left: amber (offline), teal (pendientes), navy (syncing).
- Barra progreso `#sync-progress-bar` top durante sync.
- Indicadores `.connectivity-indicator` / `.connectivity-text` en header captura (toggle clases teal/amber).
- Toast notifications para eventos (sync, error, offline).

---

## 7. CSS Crítico y Patrones Visuales

### 7.1 DataTables + Tailwind CDN (Mismo patrón Módulo 4)
**CSS Puro** en `<style>` del template replicando paleta `navy/teal/sand/stone`. Selectores `.dataTables_wrapper`, `.paginate_button`, `table.dataTable thead th`, `tbody td`, etc.

### 7.2 Badges Semánticos
```css
.badge-reading-pendiente  { bg: #fef3c7; color: #92400e; dot: #f59e0b; }
.badge-reading-validada   { bg: #ccfbf1; color: #115e59; dot: #14b8a6; }
.badge-reading-rechazada  { bg: #fee2e2; color: #991b1b; dot: #ef4444; }
.badge-reading-anulada    { bg: #f5f5f4; color: #57534e; dot: #a8a29e; }
```

### 7.3 Captura Mobile-First (capture.html)
- `.reading-input`: font DM Mono, center, sin spinners, 2px border, focus teal ring.
- `.reading-card`: 1px sand-200 border, 0.75rem radius. Estados: `.captured` (teal-50 + teal-200), `.has-warning` (amber-300), `.has-error` (red-300).
- `.capture-sticky`: sticky top 4rem, backdrop blur, sand-50/95% opacity.
- `.capture-grid`: CSS Grid, 1 col mobile → 2 col tablet+.
- `.btn-next-pending`: fixed bottom-right, rounded-full, shadow-lg.

### 7.4 Animaciones
```css
@keyframes slide-in { from { translateX(100%) opacity:0 } to { translateX(0) opacity:1 } }
@keyframes fadeUp { from { opacity:0; translateY(24px) } to { opacity:1; translateY(0) } }
```

### 7.5 Selección de Checkbox (index.html)
```css
.reading-checkbox { accent-color: #0d9488; }
tr.selected-row { background: rgba(13,148,136,0.06) !important; }
.selection-badge { bg: #0d9488; color: white; min-w: 1.25rem; font-size: 0.6875rem; }
```

---

## 8. Integración con Otros Módulos

### 8.1 Módulo 1 (Dashboard Público)
- Sin integración directa. Lecturas son dato privado.

### 8.2 Módulo 2 (Auth/RBAC)
- `@permission_required('readings', 1/2)` en todas las rutas Blueprint.
- `current_user.has_permission('readings', 1)` en `admin_sidebar.html` → Visibilidad item "Lecturas".
- `current_user.has_permission('readings', 2)` en templates → Botones Capturar/Aprobar/Rechazar.
- `created_by_id`, `updated_by_id` en `Reading` → FK a `User`.

### 8.3 Módulo 3 (Main/Portal)
- **Admin Dashboard:** `get_lecturas_stats()` integrado en `partner_service.get_admin_stats()` → KPIs `pct_lecturas`, `lecturas_tomadas`, `consumo_promedio`.
- **Portal Socio:** `get_consumption_history_for_portal()` integrado en `partner_service.get_socio_portal_data()` → `consumption_history` array para Chart.js.

### 8.4 Módulo 4 (Partners/Catastro)
**Consumo de datos (Lecturas ← Catastro):**
- `Meter` → `meter_id`, `es_actual`, `estado`, `ultima_lectura_valor`, `lectura_instalacion`, `multiplicador`.
- `Partner` → `partner_id`, `nombre`, `rut`, `sector_id`, `estado` (filtrado ACTIVO/CORTADO para captura).
- `Sector` → `sector_id`, `nombre`, `orden_lectura` (para ordenamiento ruta).

**Actualización de cache (Lecturas → Catastro):**
- `Reading.validar()` → `meter.ultima_lectura_valor = lectura_actual`, `meter.fecha_ultima_lectura = fecha`.
- `capture_reading()` → `meter.ultima_lectura_valor` se lee como `lectura_anterior`.

**Relaciones en BD:**
- `Reading.meter` → `Meter` (back_populates `readings`).
- `Reading.partner` → `Partner` (sin back_populates explícito).
- `Reading.sector` → `Sector` (sin back_populates explícito).
- `Meter.readings` → `Reading` (1:N, `lazy='dynamic'`).

### 8.5 Módulo 6 (Facturación) – Puntos de Conexión Futuros
- `Reading` con `status=VALIDADA` → Base para cálculo de boleta.
- `Reading.consumo_real` (aplica `multiplicador`) → Consumo facturable.
- `Reading.partner_id` + `Reading.periodo` → Agrupación facturación.
- `Reading.sector_id` → Agrupación impresión por ruta.

### 8.6 Módulo 8 (POS/Caja) – Puntos de Conexión Futuros
- Consumo acumulado por socio → Información en caja.
- Alertas de consumo alto → Derivar a revisión.

### 8.7 Módulo 9 (Reportes SISS) – Puntos de Conexión Futuros
- Lecturas por periodo → Informes de producción/distribución.
- Consumo promedio por sector → Balance hídrico.
- % lecturas tomadas → Cumplimiento normativo.

---

## 9. Inventario de Archivos del Módulo 5

```
app/
├── models/
│   └── reading.py              # Reading, ReadingStatus, Validadores, Hybrid Props, Métodos State Machine
├── services/
│   └── reading_service.py      # Excepciones, Helpers Tipado, Captura, Sync Offline, Validación/Rechazo/Batch, Stats, Historial
├── blueprints/
│   └── readings.py             # Rutas: index, api_list, capture, api_capture, validate-consumption, sync, sync/status, validate, reject, validate-batch, detail, stats, history, partner/summary
├── templates/
│   └── readings/
│       ├── index.html          # Listado DataTables + Filtros + Checkbox Batch Aprobación
│       ├── capture.html        # Captura Mobile-First + Cards + Barra Progreso + Offline
│       └── detail.html         # Detalle Lectura + Chart.js + Modal Rechazo + Auditoría
├── static/
│   └── js/
│       ├── reading_val.js      # Validación cliente: reglas consumo, feedback visual, teclado numérico
│       └── offline_sync.js     # Sincronización offline: LocalStorage, batch, retry backoff, badge UI
│
├── models/
│   └── partner.py              # (Módulo 4) Meter.readings relationship
├── services/
│   └── partner_service.py      # (Módulo 4) get_admin_stats() y get_socio_portal_data() consumen reading_service
└── __init__.py                  # Registro readings_bp
```

---

## 10. Convenciones, Deuda Técnica y Checklist

| Tema | Estado / Regla | Acción Futura |
|------|----------------|---------------|
| **Unicidad Lectura** | `(meter_id, periodo)` único vía Index + check en `capture_reading()`. | OK. |
| **Cache en Meter** | `Reading.validar()` actualiza `Meter.ultima_lectura_valor` + `fecha_ultima_lectura`. | OK. |
| **Validación Consumo** | Reglas idénticas en backend (`validate_consumption_rules`) y frontend (`ReadingValidator.validate`). | OK. |
| **Captura Offline** | `OfflineSync` → LocalStorage → batch POST → retry backoff. | OK. |
| **DataTables Server-Side** | Implementado en `index.html` con AJAX + filtros externos. | OK. |
| **Aprobación Masiva** | Checkboxes + `api_validate_batch` endpoint + JS batch logic. | OK. |
| **Gráfico Consumo** | Chart.js CDN en `detail.html`. Barras con periodo actual resaltado. | **Futuro:** Agregar línea de promedio. Tooltip con lectura + fecha. |
| **Foto Medidor** | `foto_url` en modelo (String 500). | **Pendiente Módulo 5b:** Upload foto desde captura mobile. |
| **GPS en Captura** | `latitud/longitud` en modelo. | **Pendiente:** Capturar GPS automáticamente desde `navigator.geolocation` en `capture.html`. |
| **CSRF en API JSON** | `X-CSRFToken` header enviado desde JS (variable `CSRF_TOKEN` inyectada desde Jinja2 `{{ csrf_token() }}`). | OK. `CSRFProtect` habilitado globalmente en `__init__.py`. |
| **Flash Messages** | No se usan en `index.html` ni `capture.html` (todo es AJAX + Toasts). En `detail.html` redirect tras validate/reject usa flash. | OK. |
| **Export Excel/PDF** | No implementado. | **Pendiente:** Cargar jsPDF/SheetJS para export lecturas. |
| **Notificación Consumo Alto** | Warning visual en captura. | **Futuro:** Push notification / email al secretario. |
| **Tests** | No existen tests unitarios para `reading_service`. | **Crítico:** Testear `capture_reading` (duplicados, lectura negativa, socio inactivo), `validate_batch`, `sync_offline_readings` (duplicados, errores parciales). |

---

## 11. Comandos de Verificación Rápida

```bash
# 1. Rutas registradas
flask routes | grep readings

# 2. Shell: Probar Service Layer
flask shell
# >>> from app.services.reading_service import capture_reading, get_lecturas_stats, get_readings_for_capture
# >>> stats = get_lecturas_stats()
# >>> print(stats['total_medidores'], stats['lecturas_tomadas'], stats['pct_lecturas'])
# >>> items = get_readings_for_capture(sector_id=1, periodo='2026-07')
# >>> print(len(items), items[0] if items else 'Sin medidores')

# 3. Verificar Modelo
flask shell
# >>> from app.models.reading import Reading, ReadingStatus
# >>> r = Reading.query.first()
# >>> print(r.periodo_display, r.consumo_real, r.meter.numero_serie, r.partner.nombre)
# >>> print(r.status.value, r.badge_status)

# 4. Verificar Integración con Módulo 4
flask shell
# >>> from app.services.partner_service import get_admin_stats, get_socio_portal_data
# >>> stats = get_admin_stats()
# >>> print('pct_lecturas:', stats['pct_lecturas'], 'consumo_promedio:', stats['consumo_promedio'])

# 5. Lint Templates
grep -rn "FIX\|TODO\|FIXME" app/templates/readings/

# 6. Verificar Esquema BD
flask shell
# >>> from app import db
# >>> db.engine.execute("PRAGMA table_info(readings);").fetchall()

# 7. Verificar migración
flask db current
flask db history
```

---

## 12. Puntos de Extensión Inmediatos (Próximos Módulos)

| Módulo | Archivo a Modificar / Extender | Detalle |
|--------|-------------------------------|---------|
| **5b. Captura GPS + Foto** | `capture.html`, `reading_val.js` | Agregar `navigator.geolocation.getCurrentPosition()` + botón cámara/upload. Guardar en `Reading.latitud/longitud/foto_url`. |
| **6. Facturación** | `reading_service.py` | Crear `get_readings_for_billing(periodo)` → filtra `status=VALIDADA`, agrupa por socio. |
| **6. Facturación** | `models/reading.py` | Agregar relación `Reading.bills` (Módulo 6) para trazabilidad lectura→boleta. |
| **7. Notificaciones** | `reading_service.py` | En `capture_reading()`: si consumo > 200% promedio, crear notificación para admin. |
| **8. POS** | `reading_service.py` | Exponer `get_consumo_pendiente_facturacion(partner_id)` para módulo caja. |
| **9. Reportes** | `reading_service.py` | Crear `get_lecturas_report(periodo, sector_id)` → datos crudos para export SISS. Agregar `% avance por sector`, `ranking consumo`, `lecturas rechazadas`. |
| **10. Dashboard Avanzado** | `reading_service.py` | KPIs: tendencia consumo 6 meses, comparativa sectores, detección anomalías (consumo cero recurrente). |

---

> **Fin del contexto Módulo 5**