# Contexto Técnico – Módulo 2: Autenticación, Usuarios y Permisos (RBAC)

> **Generado automáticamente** a partir del código real del proyecto.  
> Última actualización: 2025-01-15  

---

## 1. Resumen del Módulo

| Aspecto | Detalle |
|---------|---------|
| **Propósito** | Gestión de acceso seguro, sesiones y control granular de permisos (niveles 0, 1, 2) por módulo. |
| **Blueprint** | `auth_bp` – registrado con `url_prefix='/auth'` en `app/__init__.py`. |
| **Layouts** | `login.html` y `recover_password.html` usan layout *standalone* (no extienden `base_public.html`); `users_admin.html` extiende `layouts/base_admin.html` (Módulo 3). |
| **Modelo central** | `app.models.user.User` + `ROLE_DEFAULTS`, `ROLE_LABELS`, `ALL_MODULES`, `MODULE_LABELS`. |
| **Seguridad** | Hash `werkzeug.security.generate_password_hash` (PBKDF2-SHA256 por defecto). RUT validado servidor/cliente (algoritmo módulo 11). |
| **Sesiones** | `Flask-Login` (`login_manager`) con `remember=True` y `user_loader` por `id`. |
| **Permisos** | Decorador `@permission_required(module, min_level)` en `auth_service.py`. |

---

## 2. Modelo de Usuario (`app/models/user.py`)

### 2.1 Tabla `users`
```python
class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id             = db.Column(db.Integer, primary_key=True)
    rut            = db.Column(db.String(12), unique=True, nullable=False, index=True)  # formato XX.XXX.XXX-K
    nombre         = db.Column(db.String(120), nullable=False)
    email          = db.Column(db.String(120), unique=True, nullable=False)
    password_hash  = db.Column(db.String(256), nullable=False)
    role           = db.Column(db.String(20), nullable=False, default='socio')
    permissions    = db.Column(db.JSON, nullable=False, default=lambda: ROLE_DEFAULTS['socio'].copy())
    _is_active     = db.Column('is_active', db.Boolean, default=True, nullable=False)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
```

### 2.2 Constantes de configuración RBAC
```python
ROLE_DEFAULTS = {
    'socio':       {'auth':2, 'portal_socio':2, 'partners':0, 'readings':0, 'billing':0, 'pos':0, 'reports':0},
    'operario':    {'auth':1, 'portal_socio':0, 'partners':1, 'readings':2, 'billing':0, 'pos':0, 'reports':2},
    'secretaria':  {'auth':1, 'portal_socio':0, 'partners':2, 'readings':1, 'billing':1, 'pos':2, 'reports':0},
    'dirigente':   {'auth':2, 'portal_socio':2, 'partners':2, 'readings':2, 'billing':2, 'pos':2, 'reports':2},
}

ROLE_LABELS = {
    'socio': 'Socio / Cliente',
    'operario': 'Operario de Terreno',
    'secretaria': 'Secretaria / Caja',
    'dirigente': 'Dirigente / Administrador',
}

ALL_MODULES = ['auth', 'portal_socio', 'partners', 'readings', 'billing', 'pos', 'reports']

MODULE_LABELS = {
    'auth': 'Autenticación / Usuarios',
    'portal_socio': 'Portal Socio',
    'partners': 'Socios / Medidores',
    'readings': 'Lecturas',
    'billing': 'Facturación',
    'pos': 'Caja / Cobranza',
    'reports': 'Reportes SISS',
}
```

### 2.3 Métodos clave del modelo
| Método | Descripción |
|--------|-------------|
| `set_password(pwd)` | `generate_password_hash(pwd)` → guarda en `password_hash`. |
| `check_password(pwd)` | `check_password_hash(self.password_hash, pwd)` → `bool`. |
| `has_permission(module, min_level=1)` | `self.permissions.get(module, 0) >= min_level`. |
| `get_permission_level(module)` | Nivel numérico (0/1/2) para un módulo. |
| `apply_role_defaults()` | Sobrescribe `permissions` con `ROLE_DEFAULTS[self.role]`. |
| `is_active` (property) | Getter/setter sobre columna `_is_active` (requerido por Flask-Login). |

---

## 3. Validador de RUT (`app/services/rut_validator.py`)

### 3.1 Funciones públicas
| Función | Entrada | Salida | Uso |
|---------|---------|--------|-----|
| `clean_rut(rut)` | `"12.345.678-9"` | `"123456789"` | Normalización antes de BD/búsqueda. |
| `format_rut(rut)` | `"123456789"` | `"12.345.678-9"` | Presentación / almacenamiento canónico. |
| `validate_rut(rut)` | `"12.345.678-9"` | `bool` | Verificación DV (módulo 11). |
| `calculate_dv(body)` | `"12345678"` | `"9" \| "K" \| "0"` | Cálculo puro del dígito verificador. |

### 3.2 Algoritmo DV (Módulo 11)
```python
factor = 2
for digit in reversed(body):
    total += int(digit) * factor
    factor = factor + 1 if factor < 7 else 2
remainder = total % 11
result = 11 - remainder
# 11 → '0', 10 → 'K', else str(result)
```

### 3.3 Búsqueda flexible en BD (`auth.py:login`)
```python
rut_formatted = format_rut(rut)      # 12.345.678-9
rut_dashed    = rut[:-1] + '-' + rut[-1]  # 12345678-9
rut_plain     = rut                   # 123456789
User.query.filter(
    (User.rut == rut_formatted) |
    (User.rut == rut_dashed) |
    (User.rut == rut_plain)
).first()
```
> **Nota:** tras login exitoso, si el RUT almacenado no está en formato canónico, se normaliza y commitea.

---

## 4. Decorador de Permisos (`app/services/auth_service.py`)

```python
def permission_required(module: str, min_level: int = 1):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Debe iniciar sesión para acceder.', 'warning')
                return redirect(url_for('auth.login', next=request.url))
            if not current_user.has_permission(module, min_level):
                flash('No tiene permisos suficientes para acceder a esta sección.', 'error')
                return redirect(url_for('dashboard.index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator
```

**Uso típico en otros blueprints:**
```python
from app.services.auth_service import permission_required

@bp.route('/lecturas')
@permission_required('readings', 2)  # requiere escritura
def capture(): ...
```

---

## 5. Blueprint de Autenticación (`app/blueprints/auth.py`)

### 5.1 Rutas públicas
| Ruta | Métodos | Función | Descripción |
|------|---------|---------|-------------|
| `/auth/login` | GET, POST | `login()` | Login + panel sesión activa. |
| `/auth/logout` | GET | `logout()` | Cierra sesión (requiere login). |
| `/auth/recover` | GET, POST | `recover_password()` | Genera clave temporal vía RUT/email. |

### 5.2 Rutas administrativas (protegidas `@permission_required('auth', 2)`)
| Ruta | Método | Función | Descripción |
|------|--------|---------|-------------|
| `/auth/users` | GET | `users_admin()` | Lista usuarios + tabla permisos expandible. |
| `/auth/users/new` | POST | `user_create()` | Crea usuario con rol + permisos default. |
| `/auth/users/<id>/permissions` | POST | `user_update_permissions()` | Actualiza matrix de permisos (0/1/2 por módulo). |
| `/auth/users/<id>/toggle` | POST | `user_toggle()` | Activa/desactiva usuario (no auto-desactivación). |
| `/auth/users/<id>/reset-password` | POST | `user_reset_password()` | Genera nueva clave temporal (secrets.token_urlsafe). |
| `/auth/users/<id>/role` | POST | `user_update_role()` | Cambia rol y **reaplica** `apply_role_defaults()`. |

### 5.3 Lógica de redirección post-login (`_redirect_by_role()`)
```python
if current_user.has_permission('auth', 2):           → main.admin_dashboard
elif any(has_permission(m, 1) for m in staff_modules): → main.admin_dashboard
else:                                                  → main.socio_portal
```

### 5.4 Helpers internos
- `_is_safe_url(target)` – valida redirección `next` (mismo host, http/https).
- Imports diferidos (`secrets`) dentro de funciones para evitar overhead.

---

## 6. JavaScript Cliente – RUT (`app/static/js/rut_val.js`)

### 6.1 API expuesta en `window.RutValidator`
```js
window.RutValidator = {
    clean(value),      // "12.345.678-9" → "123456789"
    format(cleaned),   // "123456789" → "12.345.678-9"
    validate(cleaned), // bool DV correcto
    calculateDV(body)  // "12345678" → "9"
}
```

### 6.2 Comportamiento automático (clase `.rut-input`)
| Evento | Acción |
|--------|--------|
| `input` | Formatea en tiempo real (añade puntos/guión), ajusta cursor. |
| `blur` | Valida DV → `<input>` gets `.border-teal` + ✓ checkmark **o** `.border-red-400` + mensaje error. |
| `submit` (form) | Normaliza valor a formato canónico antes de enviar. |

### 6.3 Feedback visual inyectado
```html
<span class="rut-check absolute right-3 top-1/2 -translate-y-1/2 text-teal"><svg>✓</svg></span>
<p class="rut-error mt-1.5 text-xs text-red-500">El RUT ingresado no es válido</p>
```
> Requiere que el `<input>` esté en contenedor `position: relative` (se setea en JS).

---

## 7. Templates de Autenticación

### 7.1 `auth/login.html` – Layout *standalone* (no extiende base)
**Estructura:** Split-screen (desktop) / stacked (mobile).
- **Izquierda** (`lg:w-5/12`): Branding, beneficios, gradiente navy + animaciones float.
- **Derecha** (`lg:w-7/12`): Formulario o panel sesión activa.

**Bloque condicional `{% if session_active %}`** (pasado desde `login()`):
- Muestra avatar con iniciales, nombre, RUT, rol.
- Botones: "Ir al Panel de Administración" (si `auth` level 2), "Ir al Sitio Público", "Cerrar Sesión e Iniciar con Otro Usuario".

**Formulario login** (`session_active=False`):
- Campo RUT: `.rut-input` + icono usuario + `autofocus`.
- Campo Password: icono candado + botón toggle ojo (JS inline).
- Enlace "¿Olvidó su contraseña?" → `/auth/recover`.
- Submit: botón full-width navy-900.

**Flash messages** renderizados inline con categorías `success`/`warning`/`error`.

### 7.2 `auth/recover_password.html` – Extiende `layouts/base_public.html`
- Hero con icono candado ámbar.
- Formulario único: `identifier` (RUT o email) con `.rut-input`.
- POST a `auth.recover_password` → genera `secrets.token_urlsafe(8)`, hashea, flashea clave temporal **en pantalla** (dev only), redirige a login.
- Carga `rut_val.js` vía `{% block extra_scripts %}`.

### 7.3 `auth/users_admin.html` – Extiende `layouts/base_admin.html` (Módulo 3)
**Secciones:**
1. **Header** + botón "Nuevo Usuario" (toggle `#createSection`).
2. **Flash messages** con iconos SVG inline.
3. **Formulario crear** (colapsable) – campos: RUT (`.rut-input`), Nombre, Email, Rol (select `ROLE_LABELS`), Password (minlength 6).
4. **Tabla usuarios** – columnas: RUT, Nombre, Email (hidden md), Rol (select inline `onchange=submit`), Estado (badge Activo/Inactivo), Acciones (iconos: permisos, toggle, reset pwd).
5. **Fila expandible permisos** (`id="perms-{{user.id}}"` hidden) – grid 3 cols con selects `perm_<module>` (0/1/2) pre-seleccionados según `user.get_permission_level(module)`. Botón "Guardar Permisos" → POST `user_update_permissions`.

**JS inline:** `togglePerms(userId)` alterna clase `.hidden` en fila de permisos.

---

## 8. Integración con `app/__init__.py` (ya visto en Módulo 1)

```python
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Debe iniciar sesión para acceder a esta página.'
login_manager.login_message_category = 'warning'

@login_manager.user_loader
def load_user(user_id):
    from app.models.user import User
    return User.query.get(int(user_id))

# Blueprints
from app.blueprints.auth import auth_bp
app.register_blueprint(auth_bp, url_prefix='/auth')

# CLI
@app.cli.command('seed-admin')
def seed_admin():
    from app.models.user import User, ROLE_DEFAULTS
    from app.services.rut_validator import format_rut
    rut_formatted = format_rut('111111111')
    admin = User(rut=rut_formatted, nombre='Administrador General', email='admin@apr.cl',
                 role='dirigente', permissions=ROLE_DEFAULTS['dirigente'])
    admin.set_password('admin123')
    db.session.add(admin); db.session.commit()
```

---

## 9. Convenciones y Patrones Críticos para Módulos Futuros

| Tema | Regla / Patrón |
|------|----------------|
| **Permisos en vistas** | Usar `@permission_required('module', level)` **antes** de la lógica. Niveles: 1=lectura, 2=escritura. |
| **Permisos en templates** | `current_user.has_permission('module', 1)` para mostrar/ocultar enlaces (sidebar Módulo 3). |
| **RUT en BD** | **Siempre** almacenar formato canónico `XX.XXX.XXX-K` (ver `format_rut`). |
| **Búsqueda de usuario** | Usar las 3 variantes (formateado, dashed, plain) para compatibilidad con datos legacy. |
| **Flash categories** | `success` (teal), `error` (red), `warning` (amber), `info` (blue). Render consistente en todos los templates. |
| **Roles** | Strings exactos: `'socio'`, `'operario'`, `'secretaria'`, `'dirigente'`. Cambio de rol → `apply_role_defaults()` sobrescribe permisos. |
| **Módulos RBAC** | Lista fija `ALL_MODULES` (7 items). Para añadir módulo: actualizar `ALL_MODULES`, `MODULE_LABELS`, `ROLE_DEFAULTS` y migración BD. |
| **JS RUT** | Cargar `rut_val.js` en cualquier template con inputs `.rut-input` (vía `extra_scripts` o layout). |
| **Protección CSRF** | **No implementado aún** (Flask-WTF ausente). Formularios POST confían en same-site + HTTPS. Pendiente para producción. |
| **Recuperación clave** | Genera clave temporal **visible en flash** (dev). En prod debería enviar email. |
| **CLI seed** | `flask seed-admin` crea dirigente con RUT `11.111.111-1` / pass `admin123`. |

---

## 10. Archivos del Módulo 2 (Inventario)

```
app/
├── models/
│   └── user.py                 # User, ROLE_DEFAULTS, ROLE_LABELS, ALL_MODULES, MODULE_LABELS
├── services/
│   ├── auth_service.py         # @permission_required
│   └── rut_validator.py        # clean/format/validate/calculate_dv
├── blueprints/
│   └── auth.py                 # login, logout, recover, users_admin, CRUD usuarios/permisos
├── static/
│   └── js/
│       └── rut_val.js          # Formateo/validación cliente + window.RutValidator
└── templates/
    ├── auth/
    │   ├── login.html          # Layout standalone split-screen
    │   ├── recover_password.html
    │   └── users_admin.html    # Extiende base_admin.html (Módulo 3)
    └── layouts/
        └── base_admin.html     # (Definido en Módulo 3, referenciado aquí)
```

---

## 11. Puntos de Conexión con Módulos 1, 3 y Futuros

1. **Módulo 1 (Dashboard)** – Navbar `public_navbar.html` usa `current_user.has_permission('auth', 2)` para mostrar botón "Panel" y avatar/logout.
2. **Módulo 3 (Main/Portal)** – `_redirect_by_role()` envía a `main.admin_dashboard` o `main.socio_portal` (blueprint `main_bp` registrado sin prefix).
3. **Módulo 4 (Partners)** – Requerirá `@permission_required('partners', 1/2)` en sus rutas.
4. **Módulo 5 (Readings)** – Requerirá `@permission_required('readings', 2)` para captura.
5. **Módulo 6 (Billing)** – Requerirá `@permission_required('billing', 2)` para cierre de mes.
6. **Módulo 8 (POS)** – Requerirá `@permission_required('pos', 2)` para caja.
7. **Módulo 9 (Reports)** – Requerirá `@permission_required('reports', 2)` para carga muestras.

---

> **Fin del contexto Módulo 2**.  
> Con este documento cualquier IA puede implementar control de acceso consistente, extender la matriz RBAC y mantener la UX de RUT/permison copias al resto del sistema.