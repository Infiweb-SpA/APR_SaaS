# Contexto Técnico – Módulo 3: Panel Principal Interno / Portal Socio (`main`)

> **Generado automáticamente** a partir del código real del proyecto.  
> Última actualización: 2025-01-15  

---

## 1. Resumen del Módulo

| Aspecto | Detalle |
|---------|---------|
| **Propósito** | Workspace administrativo post-login adaptado al nivel de acceso del usuario (Vista Staff vs Vista Socio). |
| **Blueprint** | `main_bp` – registrado **sin `url_prefix`** en `app/__init__.py`. |
| **Layout base** | `layouts/base_admin.html` (incluye `components/admin_sidebar.html`). |
| **Acceso** | **Privado** – requiere `@login_required` en todas las rutas. |
| **Control de acceso** | Decorador `@permission_required(module, level)` + condicionales `current_user.has_permission()` en templates. |
| **Vistas principales** | `/panel` (router inteligente), `/panel/admin` (Staff), `/panel/socio` (Portal Socio). |
| **Estado actual** | **Datos mockeados** (placeholders) – espera integración real con Módulos 4, 5, 6, 8, 9. |

---

## 2. Blueprint y Rutas (`app/blueprints/main.py`)

```python
main_bp = Blueprint('main', __name__, template_folder='../templates/main')
```

### 2.1 Tabla de Rutas

| Ruta | Método | Decoradores | Función | Descripción |
|------|--------|-------------|---------|-------------|
| `/panel` | GET | `@login_required` | `panel()` | **Router principal**: redirige a `admin_dashboard` si `auth` level 2, sino a `socio_portal`. |
| `/panel/admin` | GET | `@login_required`, `@permission_required('auth', 1)` | `admin_dashboard()` | Vista Staff (lectura mínima `auth:1`). Renderiza `_render_admin_dashboard()`. |
| `/panel/socio` | GET | `@login_required` | `socio_portal()` | Vista Socio ("MI APR"). Renderiza `_render_socio_portal()`. |

### 2.2 Helpers Privados (Lógica de Presentación)

#### `_render_admin_dashboard()`
```python
def _render_admin_dashboard():
    stats = {
        'total_socios': 0, 'socios_activos': 0,
        'total_recaudado': 0, 'meta_recaudacion': 0,
        'pct_lecturas': 0, 'lecturas_tomadas': 0, 'lecturas_total': 0,
        'deudores_mora': 0, 'monto_mora': 0,
        'consumo_promedio': 0,
    }
    alerts = []
    recent_activity = []
    return render_template('main/admin_dashboard.html', stats=stats, alerts=alerts, recent_activity=recent_activity)
```
> **Clave:** Estructura `stats` define el **contrato de datos** que deberán cumplir los servicios de Módulos 4, 5, 6, 8.

#### `_render_socio_portal()`
```python
def _render_socio_portal():
    socio_data = {
        'nombre': current_user.nombre, 'rut': current_user.rut,
        'direccion': 'Sin datos aún', 'sector': 'Sin datos aún',
        'medidor': 'Sin datos aún', 'estado': 'Al día',
        'saldo_pendiente': 0, 'ultima_boleta': None,
        'consumo_actual': 0, 'consumo_promedio': 0,
    }
    consumption_history = []  # Lista de dicts {month, consumption}
    recent_bills = []         # Lista de dicts {period, consumption, amount, due_date, status}
    return render_template('main/socio_portal.html', socio=socio_data, consumption_history=consumption_history, recent_bills=recent_bills)
```
> **Clave:** Estructura `socio_data`, `consumption_history`, `recent_bills` definen el **contrato de datos** para Módulos 4, 5, 6.

### 2.3 Patrones Críticos
1.  **Router Inteligente (`/panel`)**: Centraliza la decisión de UX post-login. Evita lógica dispersa en `auth.py`.
2.  **Permiso Mínimo Staff (`auth:1`)**: Permite a `secretaria` (auth:1) ver el dashboard admin, aunque no gestione usuarios (auth:2).
3.  **Separación de Datos**: Helpers devuelven diccionarios planos → fácil testeo y futura extracción a `main_service.py`.
4.  **Placeholders Explícitos**: Comentarios `# se reemplazarán con consultas reales...` documentan dependencias futuras.

---

## 3. Layout Base Administrativo (`app/templates/layouts/base_admin.html`)

### 3.1 Arquitectura de Página (SPA-like Server Rendered)
```text
<body class="flex min-h-screen">
  ├─ #sidebarOverlay (mobile backdrop, fixed, z-40)
  ├─ #sidebar (fixed, left-0, w-64, z-50, transform -translate-x-full lg:translate-x-0)
  │   └─ {% include 'components/admin_sidebar.html' %}
  └─ .flex-1.lg:ml-64 (Main Wrapper)
      ├─ <header> (sticky top-0, z-30, hamburger + user avatar + logout)
      ├─ <main> (flex-1, {% block content %})
      └─ <footer> (fixed bottom info)
```
*   **Desktop (`lg:`)**: Sidebar siempre visible (`ml-64` en main). Header sin hamburger.
*   **Mobile (`< lg`)**: Sidebar oculta (`-translate-x-full`). Header muestra hamburger. Click overlay/ESC cierra.

### 3.2 Bloques Jinja2 Disponibles
| Bloque | Uso | Requerido |
|--------|-----|-----------|
| `title` | `<title>...</title>` | Sí |
| `extra_head` | CSS/JS específicos de página (ej. Chart.js) | No |
| `content` | **Cuerpo principal** | **Sí** |
| `extra_scripts` | JS al final del body (ej. init Chart.js) | No |

### 3.3 Header (Top Bar) – Detalles
*   **Hamburger**: Solo mobile (`lg:hidden`). `onclick="openSidebar()"`.
*   **Título**: "Panel Administrativo" (hidden mobile).
*   **Usuario**: Avatar con iniciales (1ra letra nombre + 1ra apellido). Nombre completo + RUT (hidden mobile).
*   **Logout**: Link directo a `auth.logout` con icono SVG.

### 3.4 JavaScript Global (Inline)
```javascript
function openSidebar() { /* remove -translate-x-full, show overlay, lock body scroll */ }
function closeSidebar() { /* add -translate-x-full, hide overlay, unlock body scroll */ }
document.addEventListener('keydown', e => e.key === 'Escape' && closeSidebar());
```
> **Dependencia:** IDs fijos `#sidebar`, `#sidebarOverlay`. No usar clases para selectores JS globales.

### 3.5 Assets & Config Tailwind
*   **Fuentes**: DM Serif Display (heading), Lora (body), **DM Mono (mono)** – *nuevo vs Módulo 1*.
*   **Tailwind CDN**: Config idéntica a `base_public.html` (paleta `navy`, `teal`, `sand`).
*   **CSS Custom**: `app/static/css/input.css` (mismo archivo que público).

---

## 4. Sidebar Dinámico por Permisos (`app/templates/components/admin_sidebar.html`)

### 4.1 Estructura de Datos de Navegación (Hardcoded en Template)
```jinja
{% set nav_items = [
  { 'endpoint': 'main.admin_dashboard', 'label': 'Panel Principal', 'module': None, 'min_level': 0, 'icon': '...', 'available': true },
  { 'endpoint': 'auth.users_admin',     'label': 'Gestión Usuarios', 'module': 'auth',  'min_level': 2, 'icon': '...', 'available': true },
  { 'endpoint': None,                   'label': 'Socios / Medidores', 'module': 'partners', 'min_level': 1, 'icon': '...', 'available': false },
  { 'endpoint': None,                   'label': 'Lecturas',           'module': 'readings', 'min_level': 1, 'icon': '...', 'available': false },
  { 'endpoint': None,                   'label': 'Facturación',        'module': 'billing',  'min_level': 1, 'icon': '...', 'available': false },
  { 'endpoint': None,                   'label': 'Caja / Cobranza',    'module': 'pos',      'min_level': 1, 'icon': '...', 'available': false },
  { 'endpoint': None,                   'label': 'Reportes SISS',      'module': 'reports',  'min_level': 1, 'icon': '...', 'available': false },
] %}
```
*   **`module: None`** → Acceso libre (solo login).
*   **`available: false`** → Renderiza *disabled* con badge "Pronto".
*   **Iconos**: SVG `path` `d` attribute como string (inline, sin sprite).

### 4.2 Lógica de Renderizado (Motor RBAC en Template)
```jinja
{% for item in nav_items %}
  {% set has_perm = true %}
  {% if item.module is not none %}
    {% set has_perm = current_user.has_permission(item.module, item.min_level) %}
  {% endif %}

  {% if has_perm %}
    {% if item.available %}
      <a href="{{ url_for(item.endpoint) }}" class="... {% if request.endpoint == item.endpoint %}active{% endif %}">...</a>
    {% else %}
      <div class="... cursor-not-allowed">... <span class="badge">Pronto</span></div>
    {% endif %}
  {% endif %}
{% endfor %}
```
> **Patrón Clave:** **Filtro en plantilla** (`has_perm`) + **Estado visual** (`available`). El usuario *no ve* el ítem si no tiene permiso (seguridad por ofuscación UI, la real está en `@permission_required` en blueprint).

### 4.3 Footer de Sidebar
Avatar + Nombre + RUT del usuario logueado. Siempre visible.

---

## 5. Vista Staff: Dashboard Administrativo (`app/templates/main/admin_dashboard.html`)

### 5.1 Estructura de Secciones
1.  **Header**: Título + Bienvenida usuario.
2.  **Flash Messages**: Render global (ver 5.2).
3.  **KPI Cards (Grid 1/2/4 cols)**: Recaudación, Lecturas, Mora, Socios.
4.  **Accesos Rápidos (Grid 2/3 cols)**: Botones condicionales por permiso.
5.  **Alertas + Estado Sistema (Grid 2 cols)**: Lado a lado.

### 5.2 Flash Messages – Implementación Canónica
```jinja
{% with messages = get_flashed_messages(with_categories=true) %}
  {% if messages %}
    <div class="mb-6 space-y-3">
      {% for category, message in messages %}
        <div class="p-4 rounded-xl text-sm font-medium flex items-start gap-3
                    {% if category == 'success' %} bg-teal/10 text-teal-dark border border-teal/20
                    {% elif category == 'warning' %} bg-amber-50 text-amber-700 border border-amber-200
                    {% else %} bg-red-50 text-red-700 border border-red-200 {% endif %}">
          <svg>...icono según categoría...</svg>
          <span>{{ message }}</span>
        </div>
      {% endfor %}
    </div>
  {% endif %}
{% endwith %}
```
> **Estándar:** Usar este bloque exacto en **todas** las vistas privadas. Categorías: `success` (teal), `warning` (amber), `error`/`danger` (red), `info` (blue/navy).

### 5.3 Tarjetas KPI – Lógica de Renderizado Condicional
Patrón repetido 4 veces:
```jinja
{% if stats.valor_clave > 0 %}
  <!-- Mostrar datos reales + barra de progreso si aplica -->
  <p class="text-2xl font-heading text-navy-900">{{ stats.valor }}</p>
  <div class="h-1.5 bg-sand-200 rounded-full overflow-hidden">
    <div class="h-full bg-{color} rounded-full" style="width: {{ stats.pct }}%"></div>
  </div>
{% else %}
  <!-- Estado Vacío (Empty State) -->
  <p class="text-2xl font-heading text-stone-300">0</p>
  <p class="text-xs text-stone-400 mt-2">Mensaje descriptivo...</p>
{% endif %}
```
*   **Recaudación**: Barra % vs `meta_recaudacion`. Color `teal`.
*   **Lecturas**: Barra % `pct_lecturas`. Color `navy-600`.
*   **Mora**: Sin barra. Color `red-600` si > 0.
*   **Socios**: Sin barra. Texto secundario "X activos".

### 5.4 Accesos Rápidos – Matriz de Permisos en UI
```jinja
{% if current_user.has_permission('auth', 2) %}
  <a href="{{ url_for('auth.users_admin') }}" class="... hover:bg-teal/5 ...">Gestión Usuarios</a>
{% endif %}
{% if current_user.has_permission('partners', 1) %}
  <div class="... opacity-60 cursor-not-allowed">Socios / Medidores <span>Pronto · Módulo 4</span></div>
{% endif %}
{# ... readings, billing, pos, reports ... #}
```
*   **Permiso `2` (Escritura)** → Link activo (`<a>`) con hover `teal`.
*   **Permiso `1` (Lectura) / Módulo no construido** → `div` deshabilitado (`opacity-60`, `cursor-not-allowed`), badge "Pronto · Módulo N".
*   **Sin permiso** → No se renderiza (protección UI).

### 5.5 Panel Alertas
*   Itera `alerts` (lista de dicts `{type: 'danger'|'warning'|'info', message: '...'}`).
*   Estados vacíos con ilustración SVG centrada.
*   Colores: `danger`→red, `warning`→amber, `info`→teal.

### 5.6 Panel Estado Sistema
*   Hardcoded: DB Conectada (teal badge), Módulos activos "3 / 9", DTE/Reportes "Pendiente" (stone badge).
*   Version footer: "APR SaaS v1.0 · Módulos 1-3 implementados".

---

## 6. Vista Socio: Portal "MI APR" (`app/templates/main/socio_portal.html`)

### 6.1 Layout Específico
*   **Extiende `layouts/base_public.html`** (NO `base_admin.html`). **Sin sidebar, sin header admin.**
*   **Hero Gradient**: Navy 950→900→800 con ola SVG `sand-50` inferior (consistente con Módulo 1).
*   **Contenido**: `max-w-7xl mx-auto px-4...` centrado.

### 6.2 Secciones Principales

#### A. Header Socio (Hero)
*   Badge "Portal del Socio" (teal).
*   Saludo "Hola, {primer_nombre}".
*   RUT formateado (mono font).
*   **Badge Estado Cuenta**:
    *   `saldo_pendiente > 0`: Rojo, icono pulso, monto.
    *   `== 0`: Teal, "Al día".

#### B. Resumen de Cuenta (4 Cards Grid)
| Card | Dato | Formato | Empty State |
|------|------|---------|-------------|
| Consumo Actual | `socio.consumo_actual` | `X m³` | `-- m³` |
| Promedio 3M | `socio.consumo_promedio` | `X m³` | `-- m³` |
| Saldo Pendiente | `socio.saldo_pendiente` | `$X` (red/teal) | `$0` |
| Medidor | `socio.medidor` | Texto / `—` | Sector info |

#### C. Historial de Consumo (Gráfico)
*   **Contenedor**: Card blanca con header "Historial de Consumo · Últimos 12 meses".
*   **Canvas**: `<canvas id="consumptionChart" height="200"></canvas>`.
*   **Empty State**: SVG ilustrativo + copy explicativo.
*   **JS Requerido**: `Chart.js` + script en `{% block extra_scripts %}` para hidratar `consumption_history` (labels + data). *Pendiente implementar.*

#### D. Boletas Recientes (Lista)
*   **Estructura**: `divide-y` rows.
*   **Row**: Icono boleta | Periodo + Consumo + Vencimiento | Monto + Badge Estado.
*   **Estados Badge**: `paid` (teal), `pending` (amber), `overdue` (red).
*   **Empty State**: Ilustrativo + copy "aparecerán cuando se procese facturación".

#### E. Info Contacto Rápida (2 Cols)
*   **Izq**: Dirección + Sector.
*   **Der**: Teléfono emergencias 24h (link `tel:`), icono teal.

---

## 7. Contratos de Datos (Interfaces Implícitas para Futuros Servicios)

### 7.1 `AdminDashboardStats` (para `main_service.py` futuro)
```python
# app/services/main_service.py -> get_admin_stats()
class AdminDashboardStats(TypedDict):
    total_socios: int
    socios_activos: int
    total_recaudado: int          # CLP centavos o pesos enteros
    meta_recaudacion: int
    pct_lecturas: int             # 0-100
    lecturas_tomadas: int
    lecturas_total: int
    deudores_mora: int
    monto_mora: int
    consumo_promedio: float       # m3
    # Futuro: recent_activity: List[ActivityItem]
```

### 7.2 `SocioPortalData` (para `main_service.py` futuro)
```python
# app/services/main_service.py -> get_socio_portal_data(user_id)
class SocioInfo(TypedDict):
    nombre: str
    rut: str
    direccion: str
    sector: str
    medidor: str                  # Nº Serie o '—'
    estado: str                   # 'Al día' | 'En mora' | 'Cortado'
    saldo_pendiente: int          # CLP
    ultima_boleta: Optional[date]
    consumo_actual: float         # m3 mes en curso
    consumo_promedio: float       # m3 últimos 3 meses

class ConsumptionHistoryItem(TypedDict):
    month: str                    # 'YYYY-MM' o 'MMM YY'
    consumption: float            # m3

class BillSummaryItem(TypedDict):
    period: str                   # '2025-01'
    consumption: float
    amount: int                   # CLP
    due_date: date
    status: Literal['paid', 'pending', 'overdue']

# Return: (socio: SocioInfo, history: List[ConsumptionHistoryItem], bills: List[BillSummaryItem])
```

---

## 8. JavaScript Específico Requerido (Pendiente Creación)

| Archivo Futuro | Funcionalidad | Dependencia |
|----------------|---------------|-------------|
| `app/static/js/admin_dashboard.js` | Ninguna por ahora (todo server-rendered). Futuro: refresh KPIs vía HTMX/Alpine/Fetch. | - |
| `app/static/js/socio_portal.js` | **Chart.js** instanciación en `#consumptionChart` usando `consumption_history` (pasado vía `data-attrs` o `window.__CONSUMPTION_DATA__`). | Chart.js (CDN o bundle) |
| `app/static/js/sidebar.js` | Extraer lógica `openSidebar/closeSidebar` de `base_admin.html` para no duplicar si hay más layouts. | - |

> **Convención:** Cargar JS específico en `{% block extra_scripts %}` de cada vista.

---

## 9. Matriz de Permisos UI (Resumen Visual)

| Módulo / Acción | `dirigente` (2) | `secretaria` (1/2) | `operario` (1/2) | `socio` (0) |
|-----------------|-----------------|--------------------|------------------|-------------|
| **Ver Panel Admin** (`/panel/admin`) | ✅ (auth:2) | ✅ (auth:1) | ❌ (auth:0) | ❌ |
| **Gestión Usuarios** (Sidebar + Link) | ✅ (auth:2) | ❌ (auth:1) | ❌ | ❌ |
| **Socios/Medidores** (Sidebar) | ✅ (partners:2) | ✅ (partners:2) | 👁️ (partners:1) | ❌ |
| **Lecturas** (Sidebar) | ✅ (readings:2) | 👁️ (readings:1) | ✅ (readings:2) | ❌ |
| **Facturación** (Sidebar) | ✅ (billing:2) | 👁️ (billing:1) | ❌ | ❌ |
| **Caja/POS** (Sidebar) | ✅ (pos:2) | ✅ (pos:2) | ❌ | ❌ |
| **Reportes SISS** (Sidebar) | ✅ (reports:2) | ❌ | ✅ (reports:2) | ❌ |
| **Portal Socio** (`/panel/socio`) | ✅ (portal_socio:2) | ❌ | ❌ | ✅ (portal_socio:2) |

*Leyenda: ✅ Acceso completo (Link activo), 👁️ Solo lectura (Sidebar visible "Pronto"), ❌ Oculto.*

---

## 10. Archivos del Módulo 3 (Inventario Final)

```
app/
├── blueprints/
│   └── main.py                    # Router, vistas, helpers de datos mock
├── templates/
│   ├── layouts/
│   │   └── base_admin.html        # Layout privado: sidebar fija/overlay, header, main, footer, JS global
│   ├── components/
│   │   └── admin_sidebar.html     # Nav dinámico RBAC (nav_items hardcoded + has_permission + available flag)
│   └── main/
│       ├── admin_dashboard.html   # Staff: KPIs, Accesos Rápidos (permiso), Alertas, Estado Sistema
│       └── socio_portal.html      # Socio: Hero, Resumen Cuenta, Gráfico Consumo (Chart.js ready), Boletas, Contacto
├── static/
│   ├── css/
│   │   └── input.css              # (Compartido) Tailwind source + animaciones + utilidades
│   └── js/
│       └── (pendientes: admin_dashboard.js, socio_portal.js, sidebar.js)
```

---

## 11. Puntos de Extensión e Integración (Checklist Módulos 4-9)

| Módulo Futuro | Punto de Conexión en Módulo 3 | Acción Requerida |
|---------------|-------------------------------|------------------|
| **4. Partners** | `admin_dashboard.html`: Link "Socios / Medidores" (`available: true`, `endpoint: 'partners.list'`). `socio_portal.html`: Poblar `socio.direccion`, `sector`, `medidor`. | 1. Cambiar `available: true` + `endpoint` en `admin_sidebar.html:nav_items`. 2. Implementar `main_service.get_socio_portal_data()` uniendo `Partner` + `Meter`. |
| **5. Readings** | `admin_dashboard.html`: Link "Lecturas" (`available: true`). KPI "Lecturas del Mes" usa `stats.lecturas_*`. `socio_portal.html`: `consumption_history` para Chart.js. | 1. Habilitar link sidebar. 2. `main_service.get_admin_stats()` calcula lecturas mes actual. 3. `get_socio_portal_data()` serializa últimas 12 lecturas. |
| **6. Billing** | `admin_dashboard.html`: Link "Facturación". KPI "Total Recaudado" usa `stats.total_recaudado`, `meta_recaudacion`. `socio_portal.html`: `recent_bills`, `saldo_pendiente`, `consumo_actual`. | 1. Habilitar link. 2. `get_admin_stats()` agrega `Billing` del mes. 3. `get_socio_portal_data()` trae `Bill` no pagadas + última boleta. |
| **8. POS** | `admin_dashboard.html`: Link "Caja / Cobranza". KPI "Deudores en Mora" usa `stats.deudores_mora`, `monto_mora`. | 1. Habilitar link. 2. `get_admin_stats()` query `Payment`/`Bill` mora (>60 días o 2 boletas). |
| **9. Reports** | `admin_dashboard.html`: Link "Reportes SISS". Panel "Estado Sistema" badges DTE/Reportes. | 1. Habilitar link. 2. Actualizar badges estado real (conectado/pendiente). |

---

## 12. Convenciones y Deuda Técnica Identificada

1.  **Datos Hardcodeados en Sidebar**: `nav_items` en `admin_sidebar.html` → **Mover a `app/services/navigation.py`** o context processor para DRY y testeo.
2.  **SVG Icons Inline**: Paths `d="..."` repetidos en sidebar, dashboard, portal → **Crear `components/icons.html` con macros** o sprite SVG.
3.  **Flash Messages Duplicados**: Bloque copiado en `admin_dashboard.html` → **Crear `components/_flashes.html`** e `{% include %}`.
4.  **Chart.js No Integrado**: `socio_portal.html` tiene `<canvas id="consumptionChart">` pero **no carga Chart.js ni script de init**. Bloque `extra_scripts` vacío.
5.  **Empty States Consistentes**: Patrón "SVG + Texto + Copy" repetido → **Macro `empty_state(icon, title, description)`**.
6.  **Moneda Formateada**: Filtro `"{:,.0f}".format(valor)` repetido → **Registrar filtro Jinja `clp`** en `app/__init__.py`.
7.  **RUT Formateado**: `socio.rut` se muestra crudo → **Usar `format_rut`** (disponible via context processor o filtro).
8.  **Responsive Sidebar**: JS global en `base_admin.html` → **Mover a `static/js/sidebar.js`** y cargar en `extra_scripts` del layout.

---

## 13. Comandos de Verificación Rápida

```bash
# 1. Verificar rutas registradas
flask routes | grep main

# 2. Testear permisos (simular usuarios)
flask shell
# >>> from app.models.user import User, ROLE_DEFAULTS
# >>> u = User.query.filter_by(role='secretaria').first()
# >>> u.has_permission('partners', 2), u.has_permission('auth', 2)
# (True, False)

# 3. Lint templates (buscar TODOs/FIXMEs)
grep -r "Pronto" app/templates/main/ app/templates/components/admin_sidebar.html
```

---

> **Fin del contexto Módulo 3**