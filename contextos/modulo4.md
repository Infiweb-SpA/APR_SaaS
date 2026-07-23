# Contexto Técnico – Módulo 4: Gestión de Socios, Medidores y Conexiones (`partners`)

> **Generado automáticamente** a partir del código real del proyecto.  
> Última actualización: 2026-07-23  

---

## 1. Resumen del Módulo

| Aspecto | Detalle |
|---------|---------|
| **Propósito** | Catastro maestro del comité APR: Ficha única de Socio (`Partner`), Historial de Medidores (`Meter`), Sectores de lectura/facturación (`Sector`). Base de datos para facturación, lecturas y portal socio. |
| **Blueprint** | `partners_bp` – registrado con `url_prefix='/partners'` en `app/__init__.py`. |
| **Layout base** | `layouts/base_admin.html` (incluye `components/admin_sidebar.html` con item "Socios / Medidores" visible si `partners` ≥ 1). |
| **Acceso** | **Privado** – requiere `@login_required` + `@permission_required('partners', level)`. |
| **Permisos RBAC** | `partners`: Level 1 (Lectura/Listado/Detalle), Level 2 (CRUD Socios, CRUD Medidores, Cambio/Instalación Medidor, CRUD Sectores). |
| **Modelos Core** | `Partner`, `Meter`, `Sector` (definidos en `app/models/partner.py`). |
| **Servicio Central** | `app/services/partner_service.py` (Lógica transaccional: `change_meter`, `install_first_meter`, validaciones RUT/Serie). |
| **JavaScript** | Vanilla ES6 inline en templates (Modales, DataTables, Fetch API). `rut_val.js` (Módulo 2) para inputs `.rut-input`. |
| **Estilo** | Tailwind CSS CDN + `app/static/css/input.css` + CSS custom inline para DataTables (compatibilidad CDN). |

---

## 2. Modelos de Datos (`app/models/partner.py`)

### 2.1 Enums de Estado (Tipados Python + DB)

```python
class PartnerStatus(str, enum.Enum):
    ACTIVO = 'activo'             # Servicio normal, facturable
    CORTADO = 'cortado'           # Corte por mora (gestión POS)
    BAJA = 'baja'                 # Desconexión definitiva / Renuncia
    SIN_CONEXION = 'sin_conexion' # Empalme pagado, pendiente instalación

class MeterStatus(str, enum.Enum):
    BODEGA = 'bodega'             # Stock, sin instalar
    INSTALADO = 'instalado'       # Funcionando en terreno (es_actual=True)
    RETIRADO = 'retirado'         # Sacado de terreno, pendiente revisión
    REPARACION = 'reparacion'     # En taller proveedor
    BAJA = 'baja'                 # Dado de baja definitiva
```

### 2.2 Tabla `sectors` (Catastro Geográfico)

| Campo | Tipo | Detalle |
|-------|------|---------|
| `id` | PK Integer | |
| `codigo` | String(10) | Unique, ej: `SEC-01`, `URB-05`. Índice único. |
| `nombre` | String(100) | Legible, ej: `Sector Centro`. |
| `descripcion` | Text | Nullable. |
| `orden_lectura` | Integer | Default 0. Orden en ruta operario. |
| `activo` | Boolean | Default True. Filtro en selects. |
| `created_at` / `updated_at` | DateTime | Auditoría. |

**Relación:** `Sector.partners` → `Partner.sector_rel` (1:N, `lazy='dynamic'`).

### 2.3 Tabla `partners` (Ficha Única del Socio)

| Campo | Tipo | Detalle |
|-------|------|---------|
| `id` | PK Integer | |
| `rut` | String(12) | **Unique, Index, Canónico `XX.XXX.XXX-K`**. Validado `@validates` con `rut_validator`. |
| `nombre` | String(150) | Index. Razón social. |
| `nombre_fantasia` | String(150) | Nullable. |
| `direccion`, `numero`, `complemento` | String | Composición `direccion_completa` property. |
| `sector_id` | FK Integer | Nullable, Index. `Sector` relationship `joined`. |
| `latitud`, `longitud` | Float | Nullable. WGS84. Mapa en Detail. |
| `telefono`, `celular`, `email` | String | Contacto. Email lowercased + `@` validation. |
| `estado` | Enum `PartnerStatus` | Default `ACTIVO`, Index. |
| `fecha_ingreso` | Date | Default `utcnow`. |
| `fecha_baja`, `motivo_baja` | Date, Text | Seteados en `dar_baja()`. |
| `tipo_conexion` | String(30) | Default `domiciliaria`. |
| `diametro_empalme` | String(10) | Nullable. ej: `1/2"`. |
| `user_id` | FK Integer | **Unique, Nullable, Index**. Vinculación 1:1 `User` (Portal Socio). |
| `observaciones` | Text | Libre. |
| `created_by_id`, `updated_by_id` | FK Integer | Auditoría usuario. |

**Relaciones Clave:**
- `meters` → `Meter` (1:N, `lazy='dynamic'`, `order_by='desc(Meter.fecha_instalacion)'`).
- `medidor_activo` (Hybrid Property) → `meters.filter_by(es_actual=True).first()`.
- `lectura_actual` (Hybrid Property) → `medidor_activo.lectura_instalacion` o 0.
- `user` → `User` (1:1 opcional, `lazy='joined'`).

**Métodos de Instancia (State Machine):**
- `activar(user_id)`, `dar_baja(motivo, user_id)`, `cortar_suministro(user_id)`, `reconectar(user_id)`.
- `to_dict(include_meters=False)` → Serialización API/JS.

### 2.4 Tabla `meters` (Historial de Medidores 1:N Socio)

| Campo | Tipo | Detalle |
|-------|------|---------|
| `id` | PK Integer | |
| `numero_serie` | String(30) | **Unique, Index, Uppercase**. Nº Serie físico. |
| `marca`, `modelo`, `diametro` | String | Nullable. |
| `multiplicador` | Integer | Default 1. Factor lectura. |
| `estado` | Enum `MeterStatus` | Default `BODEGA`, Index. |
| `es_actual` | Boolean | **Index, Default False**. Solo uno por socio (`partner_id`). |
| `partner_id` | FK Integer | Nullable, Index. NULL = Bodega. |
| `fecha_instalacion`, `lectura_instalacion` | Date, Integer | Default 0. Base consumo. |
| `fecha_retiro`, `lectura_retiro` | Date, Integer | Nullable. CheckConstraint `retiro >= instalacion`. |
| `fecha_ultima_lectura`, `ultima_lectura_valor` | Date, Integer | **Cache Módulo 5** (Lecturas). |
| `observaciones`, `observaciones_instalacion`, `observaciones_retiro` | Text | Trazabilidad. |

**Relaciones:**
- `partner` → `Partner` (`lazy='joined'`).
- `readings` → `Reading` (Módulo 5, comentado).

**Métodos de Ciclo de Vida (Llamados desde Service):**
- `instalar(partner, lectura_inicial, fecha, user_id, obs)`: Setea `partner_id`, `es_actual=True`, `estado=INSTALADO`, lecturas.
- `retirar(lectura_retiro, fecha, user_id, obs)`: Valida `es_actual=True`, setea `es_actual=False`, `estado=RETIRADO`, lecturas.
- `enviar_reparacion()`, `dar_baja_definitiva()`, `recibir_de_reparacion()`.
- `consumo_acumulado_actual` (Hybrid Property) → `ultima_lectura_valor - lectura_instalacion` o `lectura_retiro - lectura_instalacion`.

---

## 3. Capa de Servicio (`app/services/partner_service.py`)

> **Patrón:** Funciones puras, transaccionales (`db.session.commit/rollback`), excepciones tipadas (`ValidationError`, `BusinessRuleError`, `NotFoundError`), helpers de tipado seguro (`_to_float`, `_to_int`, `_to_date`, `_validate_unique_rut`, `_validate_unique_meter_serie`).

### 3.1 Excepciones Personalizadas
```python
class PartnerServiceError(Exception): ...
class ValidationError(PartnerServiceError): ...      # field específico
class BusinessRuleError(PartnerServiceError): ...   # regla de negocio
class NotFoundError(PartnerServiceError): ...       # entidad no existe
```

### 3.2 Sectores (ABM Simple)
| Función | Descripción |
|---------|-------------|
| `get_sectores_activos()` | Lista para selects (orden `orden_lectura`, `nombre`). |
| `get_sector_by_id(id)` | Lanza `NotFoundError` si no existe. |
| `create_sector(data, user_id)` | Inserta, commit, retorna `Sector`. |

### 3.3 Socios (CRUD + Reglas)

| Función | Parámetros Clave | Reglas / Validaciones |
|---------|------------------|------------------------|
| `search_partners(term, estado, sector_id, page, per_page, order_by, order_dir)` | Filtros combinados + paginación. `outerjoin(Meter)` para buscar por Nº Serie. `distinct()`. | Retorna `(items, total)` para DataTables. |
| `create_partner(data, user_id)` | `data` dict plano. | 1. `_validate_unique_rut`. 2. Valida `sector_id` existe. 3. Vincula `user_id` si proveído (check `user.partner_profile` vacío + `is_active`). 4. `IntegrityError` catch → `ValidationError`. |
| `update_partner(partner_id, data, user_id)` | Partial update. | 1. Cambio RUT → `_validate_unique_rut(exclude_id)`. 2. Cambio Estado → `_apply_status_change()` (ver abajo). 3. Coordenadas via `_to_float`. |
| `_apply_status_change(partner, new_status, user_id, data)` | **State Machine Server-Side**. | `BAJA`: `partner.dar_baja()`. `CORTADO`: `partner.cortar_suministro()`. `ACTIVO`: `partner.activar()`. `SIN_CONEXION`: set directo. |

### 3.4 Medidores (Stock + Ciclo de Vida)

| Función | Descripción |
|---------|-------------|
| `get_meters_available_for_install()` | `estado=BODEGA` + `partner_id IS NULL`. Para selects "Instalar/Cambiar". |
| `create_meter(data, user_id)` | Ingreso a bodega. Valida serie única. `estado=BODEGA`, `es_actual=False`. |
| `update_meter(meter_id, data, user_id)` | Bloquea si `es_actual=True` ("Retírelo primero"). |
| `list_all_meters(estado, partner_id, term, page, per_page)` | DataTables Inventario (`meters.html`). Filtros estado, socio, búsqueda serie/marca. |

### 3.5 Operaciones Críticas (Transaccionales)

#### `change_meter(partner_id, new_meter_serie, lectura_salida, lectura_entrada, fecha, user_id, obs)`
**Flujo Atómico (Try/Except + Rollback):**
1. Carga `partner` + `old_meter = partner.medidor_activo`. Valida existencia.
2. Busca `new_meter` por serie. Valida `estado=BODEGA` y `partner_id IS NULL`.
3. **Validación Lecturas:** `lectura_salida >= old_meter.lectura_instalacion`.
4. `old_meter.retirar(lectura_salida, ...)` → `es_actual=False`, `estado=RETIRADO`.
5. `new_meter.instalar(partner, lectura_entrada, ...)` → `es_actual=True`, `estado=INSTALADO`, `partner_id=partner.id`.
6. Commit. Retorna `(old_meter, new_meter)`.

#### `install_first_meter(partner_id, meter_id, lectura_inicial, fecha, user_id, obs)`
**Regla:** Socio **SIN** medidor actual (`partner.medidor_activo is None`).
1. Valida `partner.medidor_activo` es None (sino → `BusinessRuleError`: "Use Cambio de Medidor").
2. Valida `meter.estado == BODEGA` y `partner_id IS NULL`.
3. `meter.instalar(partner, ...)`.
4. Si `partner.estado == SIN_CONEXION` → `partner.estado = ACTIVO`.
5. Commit.

#### `remove_meter(partner_id, lectura_retiro, fecha, user_id, motivo)`
Retira medidor actual **SIN** instalar nuevo + `partner.dar_baja(motivo)`.

### 3.6 Contratos de Datos para Módulos Externos (Módulo 3)

```python
def get_admin_stats() -> Dict:
    # Llena stats del Admin Dashboard (Módulo 3)
    return {
        'total_socios', 'socios_activos', 'socios_cortados', 'socios_sin_conexion',
        'medidores_instalados', 'medidores_bodega',
        # Placeholders Módulos 5,6,8:
        'total_recaudado': 0, 'meta_recaudacion': 0, 'pct_lecturas': 0, ...
    }

def get_socio_portal_data(user: User) -> Dict:
    # Llena Portal Socio (Módulo 3)
    if not user.partner_profile.first(): return _empty_socio_data(user)
    partner = user.partner_profile.first()
    meter = partner.medidor_activo
    return {
        'socio': { 'nombre', 'rut', 'direccion_completa', 'sector', 'medidor', 'estado', 'saldo_pendiente': 0, 'consumo_actual': meter.ultima_lectura_valor - meter.lectura_instalacion if meter else 0, ... },
        'consumption_history': [], # Módulo 5
        'recent_bills': [],        # Módulo 6
    }
```

---

## 4. Blueprint y Rutas (`app/blueprints/partners.py`)

> **Estructura:** `partners_bp = Blueprint('partners', __name__, url_prefix='/partners')`.  
> **Decoradores:** `@login_required` en **todas**. `@permission_required('partners', 1)` en GET (list, detail, api). `@permission_required('partners', 2)` en POST (create, edit, change, install, sectors CRUD).

### 4.1 Rutas Principales

| Ruta | Método | Permiso | Función | Descripción |
|------|--------|---------|---------|-------------|
| `/` | GET | `partners:1` | `index()` | Listado DataTables Server-Side (`index.html`). |
| `/api/list` | GET | `partners:1` | `api_list()` | **JSON DataTables** Socios (filtros: search, estado, sector_id). |
| `/nuevo` | GET/POST | `partners:2` | `create()` | Formulario `PartnerForm` → `create_partner()`. Flash + Redirect PRG. |
| `/<int:partner_id>` | GET | `partners:1` | `detail()` | Ficha completa + Historial Medidores + Modales Cambio/Instalar (`detail.html`). |
| `/<int:partner_id>/editar` | GET/POST | `partners:2` | `edit()` | Formulario `PartnerForm` (prellenado) → `update_partner()`. |
| `/cambio-medidor` | POST | `partners:2` | `change_meter_route()` | **AJAX JSON** ← Modal Detail. Llama `change_meter()`. Retorna `{success, message}`. |
| `/instalar-medidor/<int:partner_id>` | POST | `partners:2` | `install_meter()` | **AJAX JSON** ← Modal Detail. Llama `install_first_meter()`. |
| `/api/meters/available` | GET | `partners:1` | `api_meters_available()` | **JSON** Medidores en bodega para Select Modal Cambio. `{results: [{serie, text}]}`. |

### 4.2 Inventario Medidores (`/medidores`)

| Ruta | Método | Permiso | Función |
|------|--------|---------|---------|
| `/medidores` | GET | `partners:1` | `meters_index()` → `meters.html` (DataTables). |
| `/medidores/api` | GET | `partners:1` | `api_meters()` → JSON DataTables Medidores (filtros: search, estado). |
| `/medidores/crear` | POST | `partners:2` | `meters_create()` → AJAX FormData → `create_meter()`. Retorna JSON. |

### 4.3 Sectores (`/sectores`)

| Ruta | Método | Permiso | Función |
|------|--------|---------|---------|
| `/sectores` | GET | `partners:1` | `sectors_index()` → `sectors.html` (Tabla simple + Modales Vanilla JS). |
| `/sectores/crear` | POST | `partners:2` | `sectors_create()` → AJAX FormData → `create_sector()`. Retorna JSON. |
| `/sectores/<int:sector_id>/editar` | POST | `partners:2` | `sectors_edit()` → AJAX FormData → `update_sector()` (service). Retorna JSON. |
| `/sectores/<int:sector_id>/toggle` | POST | `partners:2` | `sectors_toggle()` → AJAX → `toggle_sector_activo()` (service). Retorna JSON. |

---

## 5. Templates (Vistas Jinja2)

### 5.1 Herencia y Estructura Común
- **Todos** extienden `layouts/base_admin.html`.
- **Bloques usados:** `title`, `extra_head` (DataTables CSS / `rut_val.js`), `content`, `extra_scripts` (DataTables JS + Lógica Modales/Fetch).
- **Navbar/Sidebar:** `admin_sidebar.html` muestra "Socios / Medidores" activo (`request.endpoint.startswith('partners.')`).

### 5.2 `partners/index.html` (Listado Principal)

**Componentes Clave:**
1. **Header:** Título + Botón "Nuevo Socio" (permiso 2).
2. **Filtros (Form `#filterForm`):** Input Search (debounce 350ms), Select Estado (enum `PartnerStatus`), Select Sector (activos). Botón "Limpiar".
3. **Tabla `#tablaSocios` (DataTables Server-Side):**
   - **Columnas:** RUT (mono), Nombre, Dirección, Sector (badge navy), Medidor (mono / `—`), Estado (Badge Semántico: Activo=Teal, Cortado=Amber, Baja=Red, Sin Conexión=Stone), Ingreso, Acciones.
   - **Acciones (Render JS `accionesHtml`):** Ver Detalle (siempre), Editar (permiso 2). **NO se genera HTML en backend** (Fix 33), se renderiza en frontend con SVG inline Tailwind.
   - **Responsive:** `scrollX: true`, `autoWidth: false`.
4. **Footer:** Link "Gestionar Sectores" + Info registros (`#tableInfo` actualizado en `drawCallback`).

**Fixes Críticos Documentados en Código:**
- **Fix 31:** CSS DataTables puro (sin `@apply`) para modo CDN.
- **Fix 32:** Solo jQuery + DataTables Core + Responsive (sin plugins Buttons/Export por dependencias faltantes jsPDF/SheetJS).
- **Fix 33:** Acciones renderizadas en **Frontend (JS)**, no Backend. Separación responsabilidades.
- **Fix 34:** Responsive nativo DataTables (child rows) vs Tailwind `hidden md:table-cell` → Colisión eliminada.

### 5.3 `partners/detail.html` (Ficha Socio + Operaciones)

**Layout:** Grid `lg:col-span-2` (Izq: Info + Historial) + `lg:col-span-1` (Der: Acciones + Mapa + Auditoría).

**Secciones Izquierda:**
1. **Header:** Nombre, RUT, Botones Editar / Cambio Medidor / Instalar Medidor (condicional `medidor_activo` + permiso 2).
2. **Tarjeta Estado:** Badge Estado Socio + Badge Medidor Actual (`meter-badge`) + Lectura Actual (cálculo `ultima_lectura_valor || lectura_instalacion`).
3. **Grid Datos:** Dirección completa, Sector, Tel/Email, Tipo Conexión, Diámetro, Usuario Portal (link si existe).
4. **Historial Medidores (Tabla):** Serie, Marca/Modelo, Fechas Inst/Retiro, Lecturas Inicial/Final, Consumo (diff), Badge Estado Medidor.
5. **Observaciones:** `whitespace-pre-wrap`.

**Secciones Derecha:**
1. **Acciones Rápidas (Cards):** Editar, Cambio/Instalar Medidor (botones duplicados para UX mobile), Generar Boleta (disabled "Pronto Módulo 6"), Historial Consumos (disabled "Pronto Módulo 5").
2. **Mapa GPS:** `iframe` Google Maps Embed si `latitud/longitud`.
3. **Auditoría:** Creado/Modificado por + Fechas.

**Modales Inline (Vanilla JS + Fetch):**
- **Modal Cambio Medidor (`#modal-change`):**
  - Carga medidores disponibles via `fetch(API_METERS_URL)` al abrir.
  - Campos: Select Nuevo Medidor (Serie), Lectura Salida (prefill `lectura_actual`), Lectura Entrada (default 0), Fecha (hoy), Obs.
  - Submit → `fetch(CHANGE_METER_URL, POST JSON)` → `partner_service.change_meter()` → Toast + `location.reload()`.
- **Modal Instalar Medidor (`#modal-install`):**
  - Select Medidor (opciones renderizadas server-side `available_meters`).
  - Campos: Lectura Inicial, Fecha, Obs.
  - Submit → `fetch(INSTALL_METER_URL, POST JSON)` → `partner_service.install_first_meter()`.

**JS Compartido (`extra_scripts`):**
- `showToast()` (contenedor dinámico `#toast-container`, animación `slide-in`).
- Helpers `openModal/closeModal` (overlay click, ESC key).
- `todayISO()` para defaults `type="date"`.

### 5.4 `partners/form.html` (Crear/Editar Socio)

**Estructura:** Fieldsets colapsados (Datos Principales, Ubicación, Contacto, Estado/Fechas, Técnico, Observaciones).

**Fixes Críticos (Comentados en Template):**
- **Fix 16:** **Eliminado Alpine.js**. Solo `rut_val.js` (clase `.rut-input`). `x-mask` + `@input` conflictuaban con `rut_val.js` listeners.
- **Fix 17:** Input RUT usa **solo** `.rut-input`. `rut_val.js` maneja formateo tiempo real, validación DV en `blur`, feedback visual (check/error), normalización en `submit`.
- **Fix 18:** Select Estado `#estadoSelect` + **Vanilla JS** `change` listener → `toggleMotivoBaja()`. **Antes:** `x-show="['cortado','baja'].includes($watch('form.estado'))"` → `$watch` es registrador, no evaluador → NUNCA funcionaba.
- **Fix 19:** Flash dismiss **Vanilla JS** (`.flash-dismiss`). Antes Alpine `x-data` sin cargar Alpine → botón muerto.
- **Fix 20:** Prevención **Doble Submit** (`btnSubmit.disabled = true` + spinner SVG en `submit` event).
- **Fix 21:** Confirmación nativa `confirm()` antes de submit si `estado == 'baja'`.

**Campos Especiales:**
- `sector_id`: Select poblado con `sectores` (activos).
- `user_id`: Select usuarios sin socio (`User.query.filter(~User.id.in_(...))` en backend).
- `tipo_conexion`: Select fijo (domiciliaria, industrial, publica, agricola).
- `estado`: Select Enum `PartnerStatus`.

### 5.5 `partners/meters.html` (Inventario Medidores)

**Estructura:** Header (Nuevo Medidor + Volver), Filtros (Search, Estado), Tabla DataTables Server-Side (`#tablaMeters`), Modal "Registrar Medidor" (`#meterModal`).

**Tabla Columnas:** Nº Serie (mono), Marca, Modelo, Estado (Badge + Dot + Label "Actual" si `es_actual`), Asignado a (Link a Socio / "Bodega"), Instalado, Lect. Inicial, Consumo Acum.

**Modal Registrar (`#meterModal`):**
- FormData POST a `meters_create`.
- Validación HTML5 nativa (`checkValidity`).
- `fetch` + `FormData` → JSON Response → Toast + `table.ajax.reload()`.

**Estilos:** Reutiliza CSS DataTables de `index.html` (Fix 31). Badges `badge-meter` semánticos por `MeterStatus`.

### 5.6 `partners/sectors.html` (ABM Sectores)

**Estructura:** Tabla HTML Simple (NO DataTables, dataset pequeño) + Modales Vanilla JS (`#sectorModal`).

**Tabla:** Código (mono), Nombre, Orden (hidden sm), Estado (Botón Toggle `btn-toggle-status` con estilo badge dinámico), Acciones (Botón Editar `btn-edit-sector` con `data-*` attributes).

**Modal Crear/Editar (`#sectorModal`):**
- **Fix 23:** **Eliminado Alpine.js**. `SectorManager` → Vanilla JS autocontenido.
- **Fix 24:** `{{ form.csrf_token }}` **incluido en form modal**. Antes faltaba → 403 CSRF en `sectors_create/edit` (FlaskForm valida CSRF).
- **Fix 25:** Submit `fetch` con `new URLSearchParams(formData)` (form-encoded) + `X-Requested-With: XMLHttpRequest`. Backend detecta AJAX → retorna JSON.
- **Fix 26:** Toggle Estado → `fetch` POST vacío + `X-CSRFToken` header. Ruta `sectors_toggle` no usa Form, solo invierte booleano.
- **Fix 27:** `showToast()` **definido localmente** (antes `ReferenceError` al no existir en este template).

**Campos Modal:** Código (uppercase), Nombre, Descripción, Orden Lectura (number).

---

## 6. JavaScript del Módulo (Patrones Vanilla ES6)

> **Filosofía:** **Zero Dependencies** (salvo jQuery/DataTables CDN). Sin Alpine, sin Bootstrap JS. Lógica inline en `{% block extra_scripts %}` por template.

### 6.1 Utilidades Comunes (Duplicadas en `detail.html`, `meters.html`, `sectors.html`)
```javascript
// Toast System
function showToast(msg, type) { ... } // Crea #toast-container dinámico, anima slide-in, auto-dismiss 4-5s.

// Modal Helpers
function openModal(id) { el.classList.add('active'); body.overflow='hidden'; }
function closeModal(id) { el.classList.remove('active'); body.overflow=''; }
document.addEventListener('keydown', e => e.key==='Escape' && closeModals());
```

### 6.2 DataTables Server-Side (Patrón Unificado)
```javascript
var table = $('#tablaX').DataTable({
  processing: true, serverSide: true,
  ajax: { url: '{{ url_for("partners.api_x") }}', data: function(d){ d.filtro = $('#filtro').val(); } },
  columns: [ {data: 'campo', render: ...}, ... ],
  order: [[1, 'asc']], pageLength: 25,
  language: { url: '//cdn.datatables.net/plug-ins/.../es-ES.json' },
  scrollX: true, autoWidth: false,
  drawCallback: function() { updateInfo(); }
});

// Filtros externos
$('#search').on('keyup', debounce(() => table.search(val).draw(), 350));
$('#filtroSelect').on('change', () => table.ajax.reload());
```

### 6.3 Fetch API Pattern (CRUD Modales)
```javascript
form.addEventListener('submit', async (e) => {
  e.preventDefault(); if(submitting) return;
  if(!form.checkValidity()) return form.reportValidity();
  submitting = true; btn.disabled = true; btn.textContent = 'Guardando...'; hideError();
  
  try {
    const res = await fetch(url, { method: 'POST', headers: {'X-Requested-With':'XMLHttpRequest', 'X-CSRFToken': csrf}, body: new FormData(form) /* o JSON */ });
    const data = await res.json();
    if(data.success) { closeModal(); showToast(data.message, 'success'); setTimeout(() => location.reload(), 800); }
    else { showError(data.error + (data.errors ? ' — ' + Object.entries(data.errors).map(([k,v])=>k+': '+v).join(', ') : '')); }
  } catch { showError('Error de conexión.'); }
  finally { submitting = false; btn.disabled = false; btn.textContent = 'Guardar'; }
});
```

### 6.4 `rut_val.js` (Módulo 2) - Integración
- Cargado en `form.html` (`extra_head`), `detail.html` (no necesario pero disponible), `index.html` (no inputs RUT).
- Clase `.rut-input` → Auto-formateo, Validación DV `blur`, Feedback visual (✓/Error), Normalización `submit`.

---

## 7. CSS Crítico y Fixes Visuales

### 7.1 DataTables + Tailwind CDN (Fix 31)
**Problema:** `@apply` no funciona en CDN. Clases `.dt-container` etc. sin estilos.
**Solución:** CSS Puro en `extra_head` replicando paleta `navy/teal/sand/stone`:
- `.dataTables_wrapper .dataTables_length select`, `.dataTables_filter input`: bordes `sand-200`, focus `teal` ring.
- `table.dataTable thead th`: bg `navy-50`, text `navy-950`, border `stone-300`.
- `tbody td`: border `sand-100`, hover `navy-950/3`.
- Paginación: botones `white`/`sand-200`, hover `teal-50`/`teal`, current `teal-800`/`white`.

### 7.2 Badges Semánticos (Consistentes Módulo 3)
```css
.badge-estado-activo / .badge-bodega / .badge-instalado { bg: teal-100/blue-100/teal-100; text: teal-800/blue-800/teal-800; }
.badge-estado-cortado / .badge-reparacion { bg: amber-100; text: amber-800; }
.badge-estado-baja / .badge-baja-meter { bg: red-100; text: red-800; }
.badge-estado-sin_conexion / .badge-retirado { bg: stone-100; text: stone-600; }
```
- Estructura: `<span class="badge..."><span class="dot"></span>Label</span>`.

### 7.3 Animaciones
- `@keyframes slide-in` (modales, toasts): `translateX(100%)` → `0`.
- `.will-animate` + `.anim-fade-up` (heredado `base_admin.html` via `input.css`).

---

## 8. Integración con Módulos 1, 2, 3 y Futuros

### 8.1 Módulo 1 (Dashboard Público)
- `public_navbar.html` → Botón "MI APR" → `/auth/login` → Post-login `_redirect_by_role()` (Módulo 2) → `main.socio_portal` (Módulo 3) → Consume `partner_service.get_socio_portal_data()`.

### 8.2 Módulo 2 (Auth/RBAC)
- `@permission_required('partners', 1/2)` en todas las rutas Blueprint.
- `current_user.has_permission('partners', 1)` en `admin_sidebar.html` → Visibilidad item "Socios / Medidores".
- `current_user.has_permission('partners', 2)` en templates → Botones Crear/Editar/Cambio/Instalar.
- `rut_validator` (Service) usado en `Partner._validate_rut` + `partner_service._validate_unique_rut` + `rut_val.js` (Frontend).

### 8.3 Módulo 3 (Main/Portal)
- **Admin Dashboard:** `get_admin_stats()` → KPIs "Total Socios", "Activos", "Cortados", "Medidores Instalados/Bodega".
- **Portal Socio:** `get_socio_portal_data(user)` → `socio.direccion_completa`, `sector`, `medidor_activo.numero_serie`, `consumo_actual` (cache `meter.ultima_lectura_valor`).
- **Contrato Futuro Módulo 5 (Lecturas):** `meter.fecha_ultima_lectura`, `meter.ultima_lectura_valor` actualizados por captura lecturas.
- **Contrato Futuro Módulo 6 (Facturación):** `partner.esta_activo_para_facturar` (ACTIVO/CORTADO), `partner.medidor_activo.lectura_instalacion` (base), `partner.sector_rel.orden_lectura` (ruta).

### 8.4 Módulo 5 (Lecturas) - Puntos de Conexión
- `Meter.ultima_lectura_valor` / `fecha_ultima_lectura` → Cache para `consumo_actual` en Portal y Detail.
- `Meter.consumo_acumulado_actual` → Base para validación "Consumo > 100% promedio" (JS Módulo 5).
- `Sector.orden_lectura` → Ordenamiento ruta operario en captura móvil.

### 8.5 Módulo 6 (Facturación) - Puntos de Conexión
- `Partner.estado` en `[ACTIVO, CORTADO]` → Genera boleta.
- `Partner.tipo_conexion`, `diametro_empalme` → Tarifas diferenciadas.
- `Meter.multiplicador` → Cálculo consumo real (lectura * mult).
- `Sector` → Agrupación facturación/impresión por ruta.

### 8.6 Módulo 8 (POS/Caja) - Puntos de Conexión
- `Partner.estado == CORTADO` → Lista orden de corte (2+ boletas impagas).
- `Partner.direccion_completa`, `celular` → Datos ticket/notificación.

### 8.7 Módulo 9 (Reportes SISS) - Puntos de Conexión
- `Partner.tipo_conexion`, `diametro_empalme` → Catastro técnico.
- `Meter.marca`, `modelo`, `fecha_instalacion` → Vida útil, renovación.
- `Sector` → Balance hídrico por zona (Macro vs Micro medición).

---

## 9. Inventario de Archivos del Módulo 4

```
app/
├── models/
│   └── partner.py              # Partner, Meter, Sector, Enums, Validadores, Hybrid Props, Métodos Ciclo Vida
├── services/
│   └── partner_service.py      # Excepciones, Helpers Tipado, CRUD Sectores/Partners/Meters, change_meter, install_first_meter, Stats/Portal Data
├── blueprints/
│   └── partners.py             # Rutas: index, api_list, create, detail, edit, change_meter, install_meter, meters (index, api, create), sectors (index, create, edit, toggle)
├── templates/
│   └── partners/
│       ├── index.html          # Listado DataTables + Filtros + Fixes 31-34
│       ├── detail.html         # Ficha + Historial + Modales Cambio/Instalar (Vanilla JS Fetch)
│       ├── form.html           # Crear/Editar Socio + Fixes 16-21 (RUT, Estado, Submit, Confirm)
│       ├── meters.html         # Inventario Medidores DataTables + Modal Registro
│       └── sectors.html        # ABM Sectores Tabla Simple + Modal Vanilla JS + Fixes 23-27
├── static/
│   └── js/
│       └── rut_val.js          # (Módulo 2) Formateo/Validación RUT Cliente
```

---

## 10. Convenciones, Deuda Técnica y Checklist Extensión

| Tema | Estado / Regla | Acción Futura |
|------|----------------|---------------|
| **Validación RUT** | Centralizada: `rut_validator` (Server) + `rut_val.js` (Client) + `Partner._validate_rut` (Modelo). | OK. |
| **Unicidad Medidor** | `Meter.numero_serie` Unique + `_validate_unique_meter_serie` (Service). | OK. |
| **Cambio Medidor Atómico** | `change_meter()` Service: Try/Except + Rollback + Validación lecturas. | OK. |
| **Primera Instalación** | `install_first_meter()` valida `partner.medidor_activo is None`. | OK. |
| **DataTables Server-Side** | Implementado en `index`, `meters`, `api_list`, `api_meters`. | **Pendiente:** Exportar Excel/PDF (cargar jsPDF/SheetJS). |
| **Modales Vanilla JS** | `detail` (2 modales), `meters` (1), `sectors` (1), `form` (ninguno). | **Extraer** `static/js/modal.js`, `toast.js`, `datatable.js` para DRY. |
| **Flash Messages** | Render en `form.html`, `sectors.html`, `detail.html` (inline). | **Crear** `components/_flashes.html` macro. |
| **Iconos SVG** | Inline en templates (Heroicons style). | **Crear** `components/icons.html` macros. |
| **CSRF en Modales** | `sectors.html` Fix 24: `{{ form.csrf_token }}` en modal. `detail.html`/`meters.html`: `X-CSRFToken` header (leído de `meter_form.csrf_token` o `form.csrf_token`). | **Estandarizar:** Siempre pasar `csrf_token` en `extra_scripts` como `window.CSRF_TOKEN`. |
| **Fechas** | Helper `_to_date` soporta `YYYY-MM-DD` y `DD/MM/YYYY`. Inputs `type="date"` → ISO. | OK. |
| **Coordenadas** | `_to_float` helper. Mapas Google Embed estático. | **Futuro:** Leaflet/MapLibre interactivo para edición GPS. |
| **Auditoría** | `created_by_id`, `updated_by_id` en Partner, Meter, Sector. `joinedload` en queries. | **Futuro:** Tabla `AuditLog` centralizada (Módulo 10?). |
| **Permisos UI** | `current_user.has_permission('partners', 2)` en botones/modales. Backend `@permission_required`. | OK. |
| **Tests** | No existen tests unitarios para `partner_service`. | **Crítico:** Testear `change_meter` (lecturas inválidas, medidor no disponible, socio sin medidor), `create_partner` (RUT duplicado, user vinculado). |

---

## 11. Comandos de Verificación Rápida

```bash
# 1. Rutas registradas
flask routes | grep partners

# 2. Shell: Probar Service Layer
flask shell
# >>> from app.services.partner_service import create_partner, change_meter, get_admin_stats
# >>> from app.models.user import User
# >>> u = User.query.filter_by(role='dirigente').first()
# >>> stats = get_admin_stats()
# >>> print(stats['total_socios'], stats['medidores_instalados'])

# 3. Verificar Modelos
flask shell
# >>> from app.models.partner import Partner, Meter, Sector, PartnerStatus, MeterStatus
# >>> p = Partner.query.first()
# >>> print(p.medidor_activo, p.lectura_actual, p.direccion_completa)
# >>> m = Meter.query.filter_by(es_actual=True).first()
# >>> print(m.consumo_acumulado_actual, m.partner.nombre)

# 4. Lint Templates (Buscar TODOs/FIXMEs)
grep -rn "FIX\|TODO\|FIXME" app/templates/partners/

# 5. Validar Esquema BD
flask shell
# >>> from app import db
# >>> db.engine.execute("PRAGMA table_info(partners);").fetchall()
# >>> db.engine.execute("PRAGMA table_info(meters);").fetchall()
# >>> db.engine.execute("PRAGMA table_info(sectors);").fetchall()
```

---

## 12. Puntos de Extensión Inmediatos (Próximos Módulos)

| Módulo | Archivo a Modificar / Extender | Detalle |
|--------|-------------------------------|---------|
| **5. Lecturas** | `partner_service.py` | Añadir `update_meter_reading(meter_id, valor, fecha, user_id)` → actualiza `ultima_lectura_valor`, `fecha_ultima_lectura`, valida `valor >= lectura_instalacion` y `< 2 * promedio_3m` (regla 100%). |
| **5. Lecturas** | `models/partner.py` | Añadir relación `readings = relationship('Reading', back_populates='meter')` en `Meter`. |
| **6. Facturación** | `partner_service.py` | Añadir `get_partners_for_billing(period)` → filtra `esta_activo_para_facturar`, join `medidor_activo`, `sector`. |
| **6. Facturación** | `models/partner.py` | Añadir `Partner.consumo_periodo(period_start, period_end)` → query `Reading` (Módulo 5). |
| **8. POS** | `partner_service.py` | Añadir `get_corte_candidates()` → `Partner` con `estado=ACTIVO` y 2+ `Bill` (Módulo 6) `status=overdue`. |
| **9. Reportes** | `partner_service.py` | Añadir `get_water_balance_data()` → `Sector` agg: `SUM(Meter.consumo_acumulado)` vs Macro-medición (input manual). |

---

> **Fin del contexto Módulo 4**.  
> Este documento permite a cualquier IA continuar el desarrollo del **Módulo 5 (Lecturas)** entendiendo exactamente cómo el Catastro (`Partner`, `Meter`, `Sector`) provee la base de datos maestros, cómo funcionan las transacciones críticas (`change_meter`, `install_first_meter`), y qué contratos de datos (`get_admin_stats`, `get_socio_portal_data`, caches `ultima_lectura_valor`) deben consumir o actualizar los módulos siguientes.