# Contexto Técnico – Módulo 1: Dashboard de Presentación (Landing Pública)

> **Generado automáticamente** a partir del código real del proyecto.  
> Última actualización: 2025-01-15  

---

## 1. Resumen del Módulo

| Aspecto | Detalle |
|---------|---------|
| **Propósito** | Portal institucional público del comité APR (información, servicios, contacto). |
| **Acceso** | Público – **sin autenticación requerida**. |
| **Blueprint** | `dashboard_bp` (registrado sin `url_prefix` en `app/__init__.py`). |
| **Layout base** | `layouts/base_public.html` (incluye `components/public_navbar.html`). |
| **Estilo** | Tailwind CSS vía CDN (desarrollo) + `app/static/css/input.css` (custom). |
| **JS** | Vanilla ES6 en `<script>` inline en `base_public.html` (menú mobile, scroll navbar, IntersectionObserver). |

---

## 2. Rutas y Vistas (`app/blueprints/dashboard.py`)

```python
dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/')                 -> index()              # Hero + cards + noticias + CTA
@dashboard_bp.route('/servicios')        -> servicios()          # Tipos empalme + tabla tarifas + pasos
@dashboard_bp.route('/quienes-somos')    -> quienes_somos()      # Historia + Misión/Visión + Marco legal
@dashboard_bp.route('/obras')            -> obras()              # (Plantilla existe, lógica vacía)
@dashboard_bp.route('/info-util')        -> info_util()          # Consejos ahorro + fechas pago + protocolos + FAQ
@dashboard_bp.route('/directivos')       -> directivos()         # Organigrama visual (cards + líneas SVG)
@dashboard_bp.route('/contacto', POST)   -> contacto()           # Formulario + flash + redirect PRG
```

**Patrón común:** todas las vistas devuelven `render_template('dashboard/<vista>.html')` sin pasar contexto extra (datos *hard-coded* en templates).

---

## 3. Layout Base Público (`app/templates/layouts/base_public.html`)

### 3.1 Estructura HTML
```html
<!DOCTYPE html>
<html lang="es" class="scroll-smooth">
<head>
  <!-- meta, title, description (bloqueables) -->
  <!-- Google Fonts: DM Serif Display (headings) + Lora (body) -->
  <!-- Tailwind CDN + tailwind.config inline (colores navy/teal/sand, fontFamily) -->
  <link rel="stylesheet" href="{{ url_for('static', filename='css/input.css') }}">
  {% block extra_head %}{% endblock %}
</head>
<body class="bg-sand-50 text-stone-900 font-body antialiased">
  {% include 'components/public_navbar.html' %}
  <main>{% block content %}{% endblock %}</main>
  <footer>…footer fijo con 4 columnas + barra inferior…</footer>
  <script>…JS global (mobile menu, nav scroll, IntersectionObserver)…</script>
  {% block extra_scripts %}{% endblock %}
</body>
</html>
```

### 3.2 Bloques Jinja2 disponibles
| Bloque | Uso típico |
|--------|------------|
| `title` | `<title>{% block title %}APR – Agua Potable Rural{% endblock %}</title>` |
| `meta_description` | SEO por página |
| `extra_head` | CSS/JS específicos de página |
| `content` | **Obligatorio** – cuerpo principal |
| `extra_scripts` | JS al final del body |

### 3.3 Configuración Tailwind inline (claves)
```js
tailwind.config = {
  theme: {
    extend: {
      colors: {
        navy: { 50:'#eef5fb', ..., 950:'#071e30' },
        teal: { DEFAULT:'#0d9488', light:'#2dd4bf', dark:'#0f766e', 50:'#f0fdfa', 100:'#ccfbf1' },
        sand: { 50:'#faf9f7', 100:'#f5f3f0', 200:'#e8e4de' }
      },
      fontFamily: { heading:['"DM Serif Display"'], body:['"Lora"'] }
    }
  }
}
```

### 3.4 JavaScript global (inline)
1. **Menú mobile** – toggle `#mobileMenu` / `#mobileMenuBtn` + aria-expanded.
2. **Navbar scroll** – clase `.nav-scrolled` (bg navy-950/97 + blur) cuando `scrollY > 40`.
3. **IntersectionObserver** – detecta `.will-animate` y quita la clase para disparar animaciones CSS.

---

## 4. Navbar Pública (`app/templates/components/public_navbar.html`)

### 4.1 Estructura responsiva
- **Desktop (`lg:flex`)** – logo + 7 enlaces + zona derecha dinámica.
- **Mobile** – botón hamburguesa (`#mobileMenuBtn`) + panel `#mobileMenu` (replica enlaces + zona usuario).

### 4.2 Zona derecha – lógica de sesión (`current_user`)
```jinja
{% if current_user.is_authenticated %}
  {% if current_user.has_permission('auth', 2) %}  <!-- Botón "Panel" → /auth/users -->
  <div class="avatar + nombre">
  <a href="/auth/logout">Salir</a>
{% else %}
  <a href="/auth/login" class="btn-teal">MI APR →</a>
{% endif %}
```
> **Dependencia:** requiere `Flask-Login` + modelo `User` con método `has_permission(module, level)`.

### 4.3 Clases CSS clave
| Elemento | Clases |
|----------|--------|
| Nav contenedor | `fixed top-0 z-50 transition-all duration-300 bg-transparent` |
| Nav scrolled | `.nav-scrolled` (aplicada por JS) |
| Enlaces activos | `{% if request.endpoint == endpoint %}text-white bg-white/10{% endif %}` |

---

## 5. Vistas (Templates) – Patrones Comunes

### 5.1 Hero interno (todas menos `index.html`)
```html
<section class="relative pt-20 overflow-hidden">
  <div class="absolute inset-0 bg-gradient-to-br from-navy-950 via-navy-900 to-navy-800"></div>
  <div class="relative max-w-7xl mx-auto px-4 py-16 md:py-24">
    <h1 class="text-4xl md:text-5xl font-heading text-white will-animate anim-fade-up">Título</h1>
    <p class="mt-4 text-lg text-navy-200 max-w-2xl will-animate anim-fade-up stagger-1">Descripción</p>
    <nav class="mt-6 ..."><!-- breadcrumb --></nav>
  </div>
  <svg class="absolute bottom-0 left-0 w-full" viewBox="0 0 1440 60" ...><!-- ola sand --></svg>
</section>
```

### 5.2 Tarjetas de servicio / grid
```html
<div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
  <a href="{{ url_for('dashboard.servicios') }}" class="group block bg-white rounded-2xl p-6 border border-sand-200 hover:border-teal/30 hover:shadow-xl transition-all will-animate anim-fade-up">
    <div class="w-12 h-12 rounded-xl bg-teal/10 flex items-center justify-center mb-4 group-hover:bg-teal/20">…SVG…</div>
    <h3 class="font-heading text-xl text-navy-900 group-hover:text-teal">Título</h3>
    <p class="mt-2 text-sm text-stone-500">Descripción</p>
    <span class="inline-flex items-center gap-1 mt-4 text-sm font-semibold text-teal opacity-0 group-hover:opacity-100">Ver más →</span>
  </a>
</div>
```

### 5.3 Animaciones de entrada
- Clase base: `.will-animate { opacity: 0; }`
- Trigger: `.anim-fade-up { animation: fadeUp 0.7s ease-out forwards; }`
- Delays: `.stagger-1` (100ms) … `.stagger-5` (500ms).
- **Importante:** el `IntersectionObserver` en `base_public.html` quita `.will-animate` al hacer scroll → dispara la animación **una sola vez**.

### 5.4 Formulario contacto (`contacto.html`)
- Método `POST` a `url_for('dashboard.contacto')`.
- Campos: `nombre`, `email`, `asunto` (select), `mensaje` (textarea).
- Validación server-side simple (`if not all([...])`).
- Flash messages: `success` / `error` renderizados en el template con `get_flashed_messages(with_categories=true)`.
- Patrón **PRG** (Post-Redirect-Get) tras éxito.

---

## 6. Estilos Custom (`app/static/css/input.css`)

```css
@tailwind base; @tailwind components; @tailwind utilities;

@layer base {
  html { scroll-behavior: smooth; }
  body { font-family: 'Lora', serif; }
  h1,h2,h3,h4,h5,h6 { font-family: 'DM Serif Display', serif; }
}

@keyframes fadeUp   { from{opacity:0;transform:translateY(28px)} to{opacity:1;transform:translateY(0)} }
@keyframes fadeIn   { from{opacity:0} to{opacity:1} }
@keyframes slideDown{ from{opacity:0;transform:translateY(-12px)} to{opacity:1;transform:translateY(0)} }
@keyframes floatSlow{ 0%,100%{transform:translateY(0) rotate(0deg)} 50%{transform:translateY(-12px) rotate(2deg)} }

@layer utilities {
  .anim-fade-up  { animation: fadeUp 0.7s ease-out forwards; }
  .anim-fade-in  { animation: fadeIn 0.6s ease-out forwards; }
  .anim-slide-dn { animation: slideDown 0.35s ease-out forwards; }
  .anim-float    { animation: floatSlow 6s ease-in-out infinite; }
  .will-animate  { opacity: 0; }
  .stagger-1 { animation-delay: 100ms; } ... .stagger-5 { animation-delay: 500ms; }
}

.nav-scrolled { background: rgba(7,30,48,0.97) !important; backdrop-filter: blur(12px); box-shadow: 0 1px 24px rgba(0,0,0,0.18); }

.grain::after { /* textura SVG noise */ opacity: 0.035; pointer-events: none; }

/* scrollbar personalizada */
```

> **Build producción:** `npx tailwindcss -i ./app/static/css/input.css -o ./app/static/dist/output.css --minify`

---

## 7. Application Factory & Config (`app/__init__.py`, `config.py`, `run.py`)

### 7.1 `config.py`
```python
class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'apr-dev-secret-key')
    SQLALCHEMY_DATABASE_URI = 'sqlite:///<basedir>/instance/apr_database.sqlite'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

class DevelopmentConfig(Config): DEBUG = True
class ProductionConfig(Config):  DEBUG = False
config_map = {'development': DevelopmentConfig, 'production': ProductionConfig, 'default': DevelopmentConfig}
```

### 7.2 `app/__init__.py` – `create_app()`
```python
def create_app(config_name='default'):
    app = Flask(__name__, template_folder='templates', static_folder='static', static_url_path='/static')
    app.config.from_object(config_map[config_name])

    db.init_app(app)
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        from app.models.user import User
        return User.query.get(int(user_id))

    # Blueprints
    from app.blueprints.dashboard import dashboard_bp; app.register_blueprint(dashboard_bp)
    from app.blueprints.auth import auth_bp;           app.register_blueprint(auth_bp, url_prefix='/auth')
    from app.blueprints.main import main_bp;           app.register_blueprint(main_bp)

    with app.app_context():
        from app.models import user  # noqa
        db.create_all()

    _register_commands(app)  # cli seed-admin
    return app
```

### 7.3 `run.py` (desarrollo)
```python
from app import create_app
app = create_app('development')
if __name__ == '__main__': app.run(host='0.0.0.0', port=5000, debug=True)
```

### 7.4 `wsgi.py` (producción)
```python
from app import create_app
app = create_app('production')
```

---

## 8. Dependencias y Convenciones Críticas para Módulos Futuros

| Tema | Detalle |
|------|---------|
| **Usuario actual** | `current_user` (Flask-Login) disponible en **todos los templates**. |
| **Permisos** | `current_user.has_permission(module, level)` → level 0/1/2. |
| **RUT** | Formato normalizado `XX.XXX.XXX-K` (ver `rut_validator.py` – aún no visto, pero usado en `seed-admin`). |
| **Flash messages** | Categorías: `'success'`, `'error'`, `'warning'`, `'info'`. Render genérico en `base_public.html` **no existe** – cada template lo hace (ver `contacto.html`). |
| **Colores Tailwind** | Usar paleta `navy-*`, `teal`, `sand-*`, `stone-*`, `amber-*`, `red-*`. |
| **Fuentes** | Headings: `font-heading` (DM Serif Display). Body: `font-body` (Lora). |
| **Iconos** | SVG inline (Heroicons style) – **no hay librería externa**. |
| **Responsive** | Mobile-first: `sm:` ≥640px, `md:` ≥768px, `lg:` ≥1024px, `xl:` ≥1280px. |
| **Animaciones** | Añadir `.will-animate` + `.anim-fade-up` + `.stagger-*` para entrada escalonada. |
| **Ola decorativa** | SVG `viewBox="0 0 1440 60/100"` con path Bezier y fill `sand-50` para separar secciones. |
| **CLI** | `flask seed-admin` crea usuario `role='dirigente'` con permisos `ROLE_DEFAULTS['dirigente']`. |

---

## 9. Archivos del Módulo 1 (Inventario)

```
app/
├── blueprints/
│   └── dashboard.py
├── templates/
│   ├── layouts/
│   │   └── base_public.html
│   ├── components/
│   │   └── public_navbar.html
│   └── dashboard/
│       ├── index.html
│       ├── servicios.html
│       ├── quienes_somos.html
│       ├── obras.html
│       ├── info_util.html
│       ├── directivos.html
│       └── contacto.html
├── static/
│   └── css/
│       └── input.css
├── __init__.py
config.py
run.py
wsgi.py
```

---

## 10. Puntos de Extensión para Módulos 2 y 3

1. **`base_public.html`** ya incluye `current_user` en navbar → **Módulo 2 (auth)** proveerá `User` model + `has_permission`.
2. **`dashboard_bp`** registrado sin prefijo → **Módulo 3 (main/portal socio)** usará `main_bp` (ya registrado en `__init__.py`).
3. **`login_manager.login_view = 'auth.login'`** → ruta de login será `auth.login` (blueprint `auth` con prefix `/auth`).
4. **CLI `seed-admin`** usa `ROLE_DEFAULTS['dirigente']` → **Módulo 2** debe definir ese dict en `models/user.py`.
5. **Flash messages** – considerar crear macro `_flashes.html` para no repetir código.

---

> **Fin del contexto Módulo 1**.  
> Con este documento cualquier IA puede continuar el desarrollo manteniendo coherencia visual, arquitectura y convenciones.