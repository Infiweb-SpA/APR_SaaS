# APR_SaaS
Sistema de Trazabilidad, Gestión y Cumplimiento Normativo para APR / SSR (Agua Potable Rural)

## Especificaciones Técnicas y Desarrollo Modular por Fases
**Stack:** Python (Flask), SQLite (SQLAlchemy), JavaScript (ES6+), Tailwind CSS.

Para mantener una metodología de desarrollo limpia mediante **Vibecoding**, cada módulo está diseñado de forma atómica y acotada en pocos archivos dedicados por contexto.

---

## Matriz de Roles y Niveles de Permisos

El sistema implementa un modelo de **Control de Acceso Basado en Roles (RBAC)** con niveles de permisos numéricos aplicables por módulo:

*   **Nivel `0` (Sin acceso):** Sin lectura ni escritura. La ruta o recurso está bloqueado.
*   **Nivel `1` (Solo lectura):** Puede visualizar consultas, estados de cuenta o reportes, pero no editar ni crear registros.
*   **Nivel `2` (Lectura y Escritura):** Acceso total para crear, editar, procesar pagos, ejecutar cierres o modificar datos del módulo.

### Perfiles de Usuario Predefinidos:
1.  **Socio / Cliente:** 
    *   `auth`: Level 2 (Acceso a su sesión).
    *   `portal_socio`: Level 1 (Consulta estado de cuenta/boletas) / Level 2 (Realizar pagos online).
    *   Demás módulos: Level 0.
2.  **Operario de Terreno:**
    *   `readings` (Lecturas): Level 2.
    *   `partners` (Catastro): Level 1.
    *   Demás módulos: Level 0.
3.  **Secretaria / Caja:**
    *   `partners`: Level 2.
    *   `readings`: Level 1.
    *   `billing` (Facturación): Level 1 (Lectura) y Level 2 (Cierre de Mes/Configuración).
4.  **Dirigente / Administrador:**
    *   Acceso Nivel 2 en todos los módulos administrativos (auth, partners, readings, billing), configuración global de tarifas y gestión de usuarios/permisos.

---

### MÓDULO 1: Dashboard de Presentación (Landing Pública)
*Objetivo: Portal institucional público del comité APR para información a la comunidad.*

*   **Acceso:** Público (Sin autenticación requerida).
*   **Rutas / Vistas:**
    *   `/` (Inicio / Hero Section)
    *   `/servicios` (Información de empalmes, factibilidad y tarifas públicas)
    *   `/quienes-somos` (Historia, directiva y reglamento interno)
    *   `/obras` (Noticias de proyectos, cortes programados y mejoras de red)
    *   `/info-util` (Ahorro de agua, fechas de pago y protocolos)
    *   `/directivos` (Organigrama del comité)
    *   `/contacto` (Formulario de consultas y teléfonos de emergencia)
    *   *Redirección:* Botón "**MI APR**" apunta a `/auth/login`.
*   **Archivos de trabajo:**
    *   `app/blueprints/dashboard.py`
    *   `app/templates/layouts/base_public.html`
    *   `app/templates/components/public_navbar.html`
    *   `app/templates/dashboard/index.html` (y sub-vistas atómicas)

---

### MÓDULO 2: Autenticación, Usuarios y Permisos (`auth`)
*Objetivo: Gestión de acceso seguro, sesiones y control granular de permisos (0, 1, 2).*

*   **Funcionalidades:**
    *   Login con RUT (limpieza dinámica de puntos y guion en cliente/servidor) y clave hash (`Werkzeug`/`Bcrypt`).
    *   Manejo de sesiones mediante `Flask-Login`.
    *   Decorador personalizado `@permission_required(module, min_level)` que valida si el usuario tiene permiso `1` o `2` antes de responder una ruta.
    *   Administrador de Usuarios y Asignación de Roles/Permisos por Módulo.
    *   Recuperación de clave por correo o RUT registrado.
*   **Archivos de trabajo:**
    *   `app/models/user.py` (Incluye tabla `User` y matriz/JSON de permisos por módulo).
    *   `app/services/auth_service.py` (Decoradores `@permission_required` e inicio de sesión).
    *   `app/services/rut_validator.py`
    *   `app/blueprints/auth.py`
    *   `app/static/js/rut_val.js`
    *   `app/templates/auth/login.html`
    *   `app/templates/auth/recover_password.html`
    *   `app/templates/auth/users_admin.html` (Gestión de usuarios y niveles de permiso)

---

### MÓDULO 3: Panel Principal Interno / Portal Socio (`main`)
*Objetivo: Workspace administrativo post-login adaptado al nivel de acceso del usuario.*

*   **Funcionalidades:**
    *   Vista diferenciada según el rol:
        *   **Vista Staff:** Resumen ejecutivo (total recaudado, % lecturas, deudores en mora y alertas).
        *   **Vista Socio ("MI APR"):** Estado de cuenta personal, historial de consumo ($m^3$), boleta actual en PDF y botón de pago.
*   **Archivos de trabajo:**
    *   `app/blueprints/main.py`
    *   `app/templates/layouts/base_admin.html`
    *   `app/templates/components/admin_sidebar.html` (Opciones renderizadas dinámicamente según nivel de permiso > 0)
    *   `app/templates/main/admin_dashboard.html`
    *   `app/templates/main/socio_portal.html`

---

### MÓDULO 4: Gestión de Socios, Medidores y Conexiones (`partners`)
*Objetivo: Administrar el catastro maestro del comité.*

*   **Nivel de Permiso Requerido:** Lectura (`1`), Escritura/CRUD (`2`).
*   **Funcionalidades:**
    *   Ficha Única del Socio (RUT validado, dirección, sector, datos de contacto, estado).
    *   Catastro de Medidores (Nº Serie, Marca, Coordenadas GPS, Estado) en relación $1:N$ con socios.
    *   Gestión de cambio de medidor (registro de lectura final saliente e inicial entrante).
    *   Gestión de Sectores de Lectura/Facturación.
*   **Archivos de trabajo:**
    *   `app/models/partner.py` (Define `Partner`, `Meter`, `Sector`)
    *   `app/services/partner_service.py` (Lógica transaccional: cambio de medidor, instalación, CRUD)
    *   `app/blueprints/partners.py`
    *   `app/templates/partners/index.html`
    *   `app/templates/partners/detail.html`
    *   `app/templates/partners/form.html`
    *   `app/templates/partners/meters.html`
    *   `app/templates/partners/sectors.html`

---

### MÓDULO 5: Toma de Lecturas en Terreno (`readings`)
*Objetivo: Captura de consumos mensuales desde smartphone (Mobile-First & Offline-Ready).*

*   **Nivel de Permiso Requerido:** Lectura (`1`), Ingreso/Sincronización (`2`).
*   **Funcionalidades:**
    *   Interfaz con teclado numérico forzado y búsqueda por ruta/sector.
    *   Validación en tiempo real por JS: Alerta si el consumo excede en un 100% el promedio de los últimos 3 meses o si la lectura es menor a la anterior.
    *   Sincronización Offline (`LocalStorage`): En caso de perder señal, guarda las lecturas y habilita envío en lote (`POST`) al recuperar internet.
    *   Aprobación/Rechazo de lecturas por parte de administración.
*   **Archivos de trabajo:**
    *   `app/models/reading.py` (Define `Reading` y `ReadingStatus`)
    *   `app/services/reading_service.py` (Lógica de captura, validación, sincronización y estadísticas)
    *   `app/blueprints/readings.py`
    *   `app/static/js/offline_sync.js`
    *   `app/static/js/reading_val.js`
    *   `app/templates/readings/capture.html`
    *   `app/templates/readings/index.html`
    *   `app/templates/readings/detail.html`

---

### MÓDULO 6: Motor de Facturación, Tarifas y Subsidios (`billing`)
*Objetivo: Procesar consumos y calcular cobros respetando la Ley 20.998 y Dec. Sup. Nº 171.*

*   **Nivel de Permiso Requerido:** Lectura (`1`), Configurar/Cierre de Mes (`2`).
*   **Funcionalidades:**
    *   Configuración de Tarifas con Historial (Cargo Fijo, Valor $m^3$ Base, Límite Sobreconsumo, Valor $m^3$ Sobreconsumo, Multa por Mora).
    *   Cálculo de Subsidios Estatales: Aplica % de subsidio respetando estrictamente el **tope máximo legal de 15 $m^3$** por socio.
    *   Motor Cierre de Mes: Generación masiva de boletas y cálculo de saldos pendientes.
    *   Ciclo de vida de boletas (Emitida, Pagada, Vencida, Anulada).
*   **Archivos de trabajo:**
    *   `app/models/billing.py` (Define `Bill`, `TariffConfig` y `BillStatus`)
    *   `app/services/billing_service.py` (Motor de cálculo, cierre de mes, estadísticas)
    *   `app/blueprints/billing.py`
    *   `app/templates/billing/config.html`
    *   `app/templates/billing/index.html`
    *   `app/templates/billing/process.html`

---

## Estructura de Directorios del Proyecto (Actualizada)

```text
APR_SaaS/
|   .env.example
|   .gitignore
|   config.py
|   LICENSE
|   README.md
|   requirements.txt
|   run.py
|   wsgi.py
|   
+---app
|   |   __init__.py
|   |   
|   +---blueprints
|   |   |   auth.py
|   |   |   billing.py
|   |   |   dashboard.py
|   |   |   main.py
|   |   |   partners.py
|   |   |   readings.py
|   |   |   __init__.py
|   |   |   
|   |   \---__pycache__
|   |           
|   +---models
|   |   |   billing.py
|   |   |   partner.py
|   |   |   reading.py
|   |   |   user.py
|   |   |   __init__.py
|   |   |   
|   |   \---__pycache__
|   |           
|   +---services
|   |   |   auth_service.py
|   |   |   billing_service.py
|   |   |   partner_service.py
|   |   |   reading_service.py
|   |   |   rut_validator.py
|   |   |   __init__.py
|   |   |   
|   |   \---__pycache__
|   |           
|   +---static
|   |   +---css
|   |   |       input.css
|   |   |       
|   |   +---dist
|   |   \---js
|   |           offline_sync.js
|   |           reading_val.js
|   |           rut_val.js
|   |           
|   +---templates
|   |   +---auth
|   |   |       login.html
|   |   |       recover_password.html
|   |   |       users_admin.html
|   |   |       
|   |   +---billing
|   |   |       config.html
|   |   |       index.html
|   |   |       process.html
|   |   |       
|   |   +---components
|   |   |       admin_sidebar.html
|   |   |       public_navbar.html
|   |   |       
|   |   +---dashboard
|   |   |       contacto.html
|   |   |       directivos.html
|   |   |       index.html
|   |   |       info_util.html
|   |   |       obras.html
|   |   |       quienes_somos.html
|   |   |       servicios.html
|   |   |       
|   |   +---layouts
|   |   |       base_admin.html
|   |   |       base_public.html
|   |   |       
|   |   +---main
|   |   |       admin_dashboard.html
|   |   |       socio_portal.html
|   |   |       
|   |   +---partners
|   |   |       detail.html
|   |   |       form.html
|   |   |       index.html
|   |   |       meters.html
|   |   |       sectors.html
|   |   |       
|   |   +---readings
|   |   |       capture.html
|   |   |       detail.html
|   |   |       index.html
|   |   |       
|   |   \---__pycache__
|   |           
|   \---__pycache__
|           
+---contextos
|       modulo1.md
|       modulo2.md
|       modulo3.md
|       modulo4.md
|       modulo5.md
|       modulo6.md
|       
+---instance
|       apr_database.sqlite
|       
+---migrations
|   |   alembic.ini
|   |   env.py
|   |   README
|   |   script.py.mako
|   |   
|   +---versions
|   \---__pycache__
|           
+---tests
\---__pycache__