## Contexto del Módulo 3

Ahora te entrego el contexto actualizado del Módulo 3:

---

```markdown
# Contexto Técnico – Módulo 3: Panel Principal Interno / Portal Socio (`main`)

> **Generado automáticamente** a partir del código real del proyecto.  
> Última actualización: 2026-08-17

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
| **Módulos activos** | `auth`, `portal_socio`, `partners`, `readings`, `billing`. |

---

## 2. Blueprint y Rutas (`app/blueprints/main.py`)

```python
main_bp = Blueprint('main', __name__, template_folder='../templates/main')
```

### 2.1 Tabla de Rutas

| Ruta | Método | Decoradores | Función | Descripción |
|------|--------|-------------|---------|-------------|
| `/panel` | GET | `@login_required` | `panel()` | **Router principal**: redirige a `admin_dashboard` si tiene permisos en módulos activos (`auth` level 2, `partners` level 1, `readings` level 1, `billing` level 1), sino a `socio_portal`. |
| `/panel/admin` | GET | `@login_required`, `@permission_required('auth', 1)` | `admin_dashboard()` | Vista Staff (lectura mínima `auth:1`). |
| `/panel/socio` | GET | `@login_required` | `socio_portal()` | Vista Socio ("MI APR"). |

### 2.2 Helpers Privados

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

#### `_render_socio_portal()`
```python
def _render_socio_portal():
    socio_data = {
        'nombre': current_user.nombre,
        'rut': current_user.rut,
        'direccion': 'Sin datos aún',
        'sector': 'Sin datos aún',
        'medidor': 'Sin datos aún',
        'estado': 'Al día',
        'saldo_pendiente': 0,
        'ultima_boleta': None,
        'consumo_actual': 0,
        'consumo_promedio': 0,
    }
    consumption_history = []
    recent_bills = []
    return render_template('main/socio_portal.html', socio=socio_data, consumption_history=consumption_history, recent_bills=recent_bills)
```

---

## 3. Layout Base Administrativo (`app/templates/layouts/base_admin.html`)

### 3.1 Arquitectura de Página
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

### 3.2 Bloques Jinja2 Disponibles
| Bloque | Uso | Requerido |
|--------|-----|-----------|
| `title` | `<title>...</title>` | Sí |
| `extra_head` | CSS/JS específicos de página | No |
| `content` | **Cuerpo principal** | **Sí** |
| `extra_scripts` | JS al final del body | No |

### 3.3 JavaScript Global
```javascript
function openSidebar() { /* muestra sidebar y overlay, lock body */ }
function closeSidebar() { /* oculta sidebar y overlay, unlock body */ }
document.addEventListener('keydown', e => e.key === 'Escape' && closeSidebar());
```

---

## 4. Sidebar Dinámico por Permisos (`app/templates/components/admin_sidebar.html`)

### 4.1 Estructura de Datos de Navegación (Actualizada)
```jinja
{% set nav_items = [
    { 'endpoint': 'main.admin_dashboard', 'label': 'Panel Principal', 'module': None, 'min_level': 0, 'available': True },
    { 'endpoint': 'auth.users_admin',     'label': 'Gestión Usuarios', 'module': 'auth', 'min_level': 2, 'available': True },
    { 'endpoint': 'partners.index',       'label': 'Socios / Medidores', 'module': 'partners', 'min_level': 1, 'available': True },
    { 'endpoint': 'readings.index',       'label': 'Lecturas', 'module': 'readings', 'min_level': 1, 'available': True },
    { 'endpoint': 'billing.index',        'label': 'Facturación', 'module': 'billing', 'min_level': 1, 'available': True },
] %}
```

### 4.2 Lógica de Renderizado
```jinja
{% for item in nav_items %}
    {% set has_perm = true %}
    {% if item.module is not none %}
        {% set has_perm = current_user.has_permission(item.module, item.min_level) %}
    {% endif %}

    {% if has_perm and item.available %}
        <a href="{{ url_for(item.endpoint) }}" ...>
    {% endif %}
{% endfor %}
```

---

## 5. Vista Staff: Dashboard Administrativo (`app/templates/main/admin_dashboard.html`)

### 5.1 Estructura de Secciones
1. **Header**: Título + Bienvenida usuario.
2. **Flash Messages**.
3. **KPI Cards (Grid 1/2/4 cols)**: Recaudación, Lecturas, Mora, Socios.
4. **Accesos Rápidos (Grid 2/3 cols)**: Botones condicionales por permiso (módulos activos: `auth`, `partners`, `readings`, `billing`).
5. **Alertas + Estado Sistema**: Lado a lado.

### 5.2 Flash Messages
```jinja
{% with messages = get_flashed_messages(with_categories=true) %}
    {% if messages %}
        <div class="mb-6 space-y-3">
            {% for category, message in messages %}
                <div class="p-4 rounded-xl text-sm font-medium flex items-start gap-3
                            {% if category == 'success' %} bg-teal/10 text-teal-dark border border-teal/20
                            {% elif category == 'warning' %} bg-amber-50 text-amber-700 border border-amber-200
                            {% else %} bg-red-50 text-red-700 border border-red-200 {% endif %}">
                    ...
                </div>
            {% endfor %}
        </div>
    {% endif %}
{% endwith %}
```

### 5.3 Accesos Rápidos – Matriz de Permisos
| Módulo | Condición | Estado |
|--------|-----------|--------|
| Gestión Usuarios | `current_user.has_permission('auth', 2)` | ✅ Activo |
| Socios / Medidores | `current_user.has_permission('partners', 1)` | ✅ Activo |
| Lecturas | `current_user.has_permission('readings', 1)` | ✅ Activo |
| Facturación | `current_user.has_permission('billing', 1)` | ✅ Activo |

### 5.4 Estado del Sistema
- Base de datos: Conectada ✅
- Módulos activos: 4 / 6
- DTE / SII: Pendiente
- Reportes SISS: Pendiente
- Versión: APR SaaS v1.0 · Módulos 1-6 implementados

---

## 6. Vista Socio: Portal "MI APR" (`app/templates/main/socio_portal.html`)

### 6.1 Layout Específico
- **Extiende `layouts/base_public.html`** (NO `base_admin.html`). **Sin sidebar, sin header admin.**
- **Hero Gradient**: Navy 950→900→800 con ola SVG `sand-50` inferior.

### 6.2 Secciones Principales

#### A. Header Socio
- Badge "Portal del Socio".
- Saludo "Hola, {nombre}".
- RUT formateado.
- **Badge Estado Cuenta**: Teal "Al día" o Rojo con monto pendiente.

#### B. Resumen de Cuenta (4 Cards)
| Card | Dato | Formato | Empty State |
|------|------|---------|-------------|
| Consumo Actual | `socio.consumo_actual` | `X m³` | `-- m³` |
| Promedio 3M | `socio.consumo_promedio` | `X m³` | `-- m³` |
| Saldo Pendiente | `socio.saldo_pendiente` | `$X` (red/teal) | `$0` |
| Medidor | `socio.medidor` | Texto / `—` | Sector info |

#### C. Historial de Consumo (Gráfico)
- Contenedor con `<canvas id="consumptionChart">` preparado para Chart.js.
- Actualmente muestra Empty State.

#### D. Boletas Recientes
- Lista de boletas con periodo, consumo, vencimiento, monto y badge de estado.
- Actualmente muestra Empty State.

#### E. Info Contacto Rápida
- Dirección + Sector.
- Teléfono emergencias 24h (link `tel:`).

---

## 7. Contratos de Datos (Interfaces Implícitas para Futuros Servicios)

### 7.1 `AdminDashboardStats` (futuro en `partner_service.py`)
```python
class AdminDashboardStats(TypedDict):
    total_socios: int
    socios_activos: int
    total_recaudado: int
    meta_recaudacion: int
    pct_lecturas: int
    lecturas_tomadas: int
    lecturas_total: int
    deudores_mora: int
    monto_mora: int
    consumo_promedio: float
```

### 7.2 `SocioPortalData` (futuro en `partner_service.py`)
```python
class SocioInfo(TypedDict):
    nombre: str
    rut: str
    direccion: str
    sector: str
    medidor: str
    estado: str
    saldo_pendiente: int
    ultima_boleta: Optional[date]
    consumo_actual: float
    consumo_promedio: float

# Return: (socio: SocioInfo, history: List[ConsumptionHistoryItem], bills: List[BillSummaryItem])
```

---

## 8. Matriz de Permisos UI (Módulos Activos)

| Módulo / Acción | `dirigente` (2) | `secretaria` (1/2) | `operario` (1/2) | `socio` (0) |
|-----------------|-----------------|--------------------|------------------|-------------|
| **Ver Panel Admin** (`/panel/admin`) | ✅ (auth:2) | ✅ (auth:1) | ❌ (auth:0) | ❌ |
| **Gestión Usuarios** (Sidebar + Link) | ✅ (auth:2) | ❌ (auth:1) | ❌ | ❌ |
| **Socios/Medidores** (Sidebar) | ✅ (partners:2) | ✅ (partners:2) | 👁️ (partners:1) | ❌ |
| **Lecturas** (Sidebar) | ✅ (readings:2) | 👁️ (readings:1) | ✅ (readings:2) | ❌ |
| **Facturación** (Sidebar) | ✅ (billing:2) | 👁️ (billing:1) | ❌ | ❌ |
| **Portal Socio** (`/panel/socio`) | ✅ (portal_socio:2) | ❌ | ❌ | ✅ (portal_socio:2) |

*Leyenda: ✅ Acceso completo, 👁️ Solo lectura, ❌ Oculto.*

---

## 9. Archivos del Módulo 3 (Inventario Final)

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
│       ├── admin_dashboard.html   # Staff: KPIs, Accesos Rápidos, Alertas, Estado Sistema
│       └── socio_portal.html      # Socio: Hero, Resumen Cuenta, Gráfico Consumo, Boletas, Contacto
```

---
