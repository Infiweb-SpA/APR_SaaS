# APR_SaaS
sistema de trazabilidad y gestión de apr

# Especificaciones Técnicas y Funcionalidades por Módulo (Stack: Flask, Python, JS, Tailwind, SQLite)

Este documento define el alcance funcional detallado para el desarrollo modular de la plataforma de gestión de Agua Potable Rural (APR).

---

## MÓDULO 1: Gestión de Socios, Medidores y Conexiones (CRUD & Estado)
*Objetivo: Administrar el catastro completo del comité.*

*   **Ficha Única del Socio:**
    *   Formulario de registro con validación de RUT chileno (algoritmo de dígito verificador en JS y Python).
    *   Campos: ID correlativo, RUT, Nombre Completo, Dirección/Sector, Teléfono, Correo Electrónico, Fecha de Alta, Estado (Activo / Suspendido / En Corte).
    *   Historial vinculante que muestre todas las propiedades o medidores a su nombre.
*   **Catastro de Medidores:**
    *   Campos: Número de Serie (Único), Marca, Diámetro (mm), Coordenadas GPS (Lat/Lng), Fecha de Instalación, Estado (Operativo / Defectuoso).
    *   Relación de base de datos de 1 a muchos (Un socio puede tener más de un medidor, un medidor pertenece a un solo socio).
*   **Gestión de Cambios de Medidor:**
    *   Función interna para reemplazar un medidor dañado. Debe registrar la lectura final del medidor retirado y la lectura inicial (habitualmente 0) del nuevo medidor para evitar errores en el cálculo de consumo de ese mes.

---

## MÓDULO 2: Toma de Lecturas en Terreno (Mobile-First & Offline-Ready)
*Objetivo: Permitir al operario registrar los consumos mensuales en un smartphone de forma ágil.*

*   **Interfaz de Captura Optimizada:**
    *   Diseño responsivo estricto con Tailwind CSS, botones grandes y teclado numérico forzado (`type="number" inputmode="numeric"`).
    *   Buscador rápido por Nombre de Socio, Número de Medidor o Filtrado por Sector/Ruta de calle.
*   **Validación de Consumo en Tiempo Real (JavaScript):**
    *   Al ingresar la `Lectura Actual`, JS busca de forma asíncrona la `Lectura Anterior`.
    *   Calcula: $Consumo = Lectura\ Actual - Lectura\ Anterior$.
    *   **Regla de Alerta:** Si el consumo supera en un 100% el promedio de los últimos 3 meses del socio, o si la Lectura Actual es menor a la Anterior, el sistema bloquea el guardado y muestra un modal de advertencia: *"Consumo anómalo detectado. ¿Confirmar ingreso o verificar fuga?"*.
*   **Sincronización Inteligente Offline (LocalStorage):**
    *   Uso de JavaScript para detectar la pérdida de conexión (`navigator.onLine`).
    *   Si no hay señal, las lecturas se guardan localmente en formato JSON dentro del navegador. Al recuperar internet, un botón de "Sincronizar" envía en lote (`POST`) los datos retenidos al backend de Flask.

---

## MÓDULO 3: Motor de Facturación y Subsidios (Lógica Core en Python)
*Objetivo: Procesar mensualmente los consumos y aplicar la estructura tarifaria.*

*   **Configuración Global de Tarifas:**
    *   Panel de administración para definir parámetros del comité: Cargo Fijo ($), Valor por $m^3$ Base ($), Límite de Sobreconsumo ($m^3$), Valor por $m^3$ con Sobreconsumo ($), e Interés por Mora (%).
*   **Algoritmo de Cálculo Mensual:**
    *   Función en `billing.py` que recibe `Consumo_m3`.
    *   Si $Consumo \le LimiteSobreconsumo$: $Total = Cargo\ Fijo + (Consumo \times Valor\ Base)$.
    *   Si $Consumo > LimiteSobreconsumo$: $Total = Cargo\ Fijo + (Limite \times Valor\ Base) + ((Consumo - Limite) \times Valor\ Sobreconsumo)$.
*   **Módulo de Subsidios Estatales:**
    *   Campos en la ficha del socio: % de Subsidio (ej: 50% o 100%) y Tope de Subsidio en metros cúbicos (máximo legal de 15 $m^3$).
    *   La lógica calcula el descuento: aplica el porcentaje asignado únicamente a los metros cúbicos consumidos que estén por debajo o igual al tope configurado. El descuento se resta del total de la boleta.
*   **Motor de Cierre de Mes:**
    *   Script que procesa en lote a todos los medidores activos, calcula sus cobros, genera el registro en la tabla `Boletas` y cambia el estado de la lectura del mes a "Facturada".

---

## MÓDULO 4: Recaudación, Caja y Morosidad
*Objetivo: Procesar los ingresos monetarios del comité y controlar las deudas.*

*   **Punto de Venta / Caja Presencial:**
    *   Interfaz rápida para la secretaria del comité. Busca al socio, muestra las boletas pendientes y permite registrar el pago en efectivo o transferencia.
    *   Emisión de un comprobante de pago digital imprimible en formato ticket térmico (58mm/80mm).
*   **Control Automático de Morosidad:**
    *   Al ejecutar un nuevo cierre de mes, el sistema busca boletas anteriores que sigan con estado "Pendiente".
    *   Aplica la multa por mora configurada (monto fijo o porcentaje) y acumula el saldo anterior en la nueva boleta del socio.
*   **Listado de Corte Automático:**
    *   Vista que filtra y genera un reporte en PDF de todos los socios con 2 o más boletas consecutivas impagas, ordenados por sector para el equipo técnico.

---

## MÓDULO 5: Reportabilidad Técnica y Contable
*Objetivo: Proveer métricas críticas de operación y administración.*

*   **Balance de Agua (Cálculo de Pérdidas):**
    *   Registro mensual de la "Macro-medición" (el agua total extraída de la bomba/pozo).
    *   El sistema calcula: $Agua\ No\ Facturada = Macro-medición - \sum(Micro-mediciones\ de\ socios)$.
    *   Representación en un gráfico de torta/línea (usando Chart.js) para monitorear el porcentaje de pérdidas por fugas en las matrices de la red.
*   **Reportes de Caja Financieros:**
    *   Libro de Ingresos y Gastos mensual.
    *   Exportación directa a formato Excel (`.xlsx`) utilizando la librería `pandas` u `openpyxl` en Python.

# Requerimientos Legales y Cumplimiento Normativo para APR en Chile (Ley 20.998)

Para que este software pueda competir con 5SNAP y comercializarse legalmente a comités o cooperativas de Servicios Sanitarios Rurales (SSR) en Chile, el sistema debe cumplir obligatoriamente con las siguientes directrices fiscalizadas por la SISS y la DSSR.

---

## 1. Estructura Tarifaria Homologada (DSSR)
*   **Separación de Conceptos:** La base de datos y la visualización de la boleta deben separar estrictamente los ingresos por:
    1.  Cargo Fijo Sanitario.
    2.  Consumo de Agua Variable (Tramos normal y sobreconsumo).
    3.  Aportes de Capital o Cuotas de Incorporación (si aplica).
    4.  Intereses por mora de meses anteriores.
*   **Restricción:** El sistema no puede aplicar cobros arbitrarios o conceptos comerciales que no estén previamente aprobados por la asamblea del comité y ratificados por el organismo regulador competente.

---

## 2. Gestión de Subsidios Estatales (Decreto Supremo Nº 171)
*   **Cálculo e Informes de Cobro Municipal:** El estado subsidia el consumo de agua potable a familias vulnerables. El software debe generar de forma obligatoria un informe mensual consolidado en formato Excel estructurado por la municipalidad correspondiente.
*   **Campos Requeridos en el Informe:** RUT del Beneficiario, Número de Decreto del Subsidio, Porcentaje Subsidiado, Consumo en $m^3$, Monto Pesos ($) Subsidiado cobrado al Municipio, y Monto Neto cobrado al Socio.
*   **Validación de Tope:** El software debe bloquear estrictamente el cálculo de subsidio por sobre los 15 metros cúbicos mensuales por socio, según dicta la ley actual.

---

## 3. Integración con Facturación Electrónica (SII)
*   **Documento Tributario Electrónico (DTE):** Las APR están obligadas a emitir Boletas Electrónicas y/o Facturas por los servicios sanitarios entregados.
*   **Requerimiento Técnico backend:** El backend en Python debe estructurar los datos del cobro mensual en formato XML según el esquema del Servicio de Impuestos Internos (SII).
*   **Estrategia de Desarrollo:** Implementar una integración vía API REST utilizando un proveedor de facturación intermedio (ej: OpenFactura, Haulmer, Bsale, u otro similar) o conexión directa mediante firmas digitales, garantizando el envío del documento y el retorno del timbre electrónico (PDF con código de barras bidimensional PDF417).

---

## 4. Exportación de Datos para Fiscalización (SISS)
*   **Informes Técnicos del Servicio:** La Superintendencia de Servicios Sanitarios (SISS) requiere datos periódicos del comportamiento del APR. El sistema debe contar con consultas SQL listas para exportar los siguientes indicadores:
    *   **Índice de Continuidad del Servicio:** Registro de horas/días sin suministro o por cortes de emergencia programados.
    *   **Registro de Presiones y Cloro:** Formulario técnico donde el operario ingresa manualmente los niveles de cloro libre residual (PPM) medidos en las puntas de red, con alertas si bajan del límite legal (0.2 mg/L).
    *   **Catastro de Pérdidas:** El reporte de Balance de Agua (Módulo 5 de funcionalidades) debe ser exportable en un formato estándar compatible con las planillas de rendición de cuentas de la DSSR.

---

## 5. Normas de Suspensión de Servicio (Cortes por Deuda)
*   **Plazos Legales de Aviso:** El sistema no puede emitir órdenes de corte de manera aleatoria. La ley estipula que el corte procede tras acumular 2 boletas impagas consecutivas.
*   **Notificación Previa:** La boleta actual emitida debe indicar explícitamente en el cuerpo del documento si el socio se encuentra en "Aviso de Corte" indicando la fecha límite de pago antes de la suspensión física del servicio. El software debe validar que hayan transcurrido los días hábiles legales mínimos antes de incluir al socio en la ruta de corte.

# estructura de carpetas y archivos
```
APR_SaaS/
│
├── config.py                 # Configuración por entorno (Development, Production, SQLite DB URL)
├── app.py                    # Application Factory (Inicializa Flask, DB, Migraciones y Blueprints)
├── wsgi.py                   # Punto de entrada para el servidor de producción (Gunicorn/Waitress)
├── requirements.txt          # Dependencias de Python (Flask, SQLAlchemy, Pandas, openpyxl, etc.)
├── .env.example              # Ejemplo de variables de entorno (Secret Key, credenciales API SII/OpenFactura)
├── README.md                 # Documentación del proyecto
│
├── app/
│   ├── __init__.py           # Inicialización de la aplicación Flask y extensiones
│   │
│   ├── models/               # Modelos de base de datos (SQLAlchemy ORM)
│   │   ├── __init__.py
│   │   ├── partner.py        # Socios/Clientes (RUT con verificador, Datos personales, Subsidios)
│   │   ├── meter.py          # Medidores (Nº Serie, Marca, Coordenadas GPS, Estado) y Cambios de medidor
│   │   ├── reading.py        # Lecturas mensuales de consumos
│   │   ├── billing.py        # Boletas, Detalle de tarifas, Subsidios aplicados, Multas/Intereses
│   │   ├── payment.py        # Registros de Caja, Transacciones POS y Comprobantes
│   │   └── technical.py      # Macro-medidores, Registro de Cloro Residual/Presión, Eventos de Corte
│   │
│   ├── services/             # Lógica Core de Negocio y Dominio Legal
│   │   ├── __init__.py
│   │   ├── rut_validator.py  # Algoritmo de validación de RUT chileno (Módulo 1)
│   │   ├── billing_engine.py # Motor de cálculo tarifario, sobreconsumo y tope subsidio <=15m³ (Módulo 3 & Ley 20.998)
│   │   ├── sii_service.py    # Generación de XML y conexión API para Facturación Electrónica (DTE / SII)
│   │   ├── siss_reports.py   # Generador de reportes legales (Continuidad, Cloro residual, Balance de Agua)
│   │   └── export_service.py # Exportación de planillas Excel para la Municipalidad (Decreto Supremo Nº 171)
│   │
│   ├── blueprints/           # Controladores y Endpoints (Rutas HTTP y API)
│   │   ├── __init__.py
│   │   ├── main.py           # Dashboard principal e indicadores generales
│   │   ├── partners.py       # CRUD Ficha Única del Socio y Medidores asociados (Módulo 1)
│   │   ├── readings.py       # API y Vistas para la Toma de Lecturas en Terreno Mobile-First (Módulo 2)
│   │   ├── billing.py        # Configuración global de tarifas y ejecutor del Cierre de Mes (Módulo 3)
│   │   ├── pos.py            # Punto de Venta / Caja Presencial y Gestión de Morosidad (Módulo 4)
│   │   └── reports.py        # Reportabilidad técnica, Balance de Agua y Fiscalización (Módulo 5)
│   │
│   ├── static/               # Archivos estáticos
│   │   ├── css/
│   │   │   └── input.css     # Archivo fuente de Tailwind CSS
│   │   ├── js/
│   │   │   ├── rut_val.js    # Validación de RUT chileno en el cliente
│   │   │   ├── offline_sync.js # Manejo de LocalStorage, detección offline y envío batch
│   │   │   ├── reading_val.js # Alertas en tiempo real por anomalías de consumo (>100% o menor)
│   │   │   ├── pos_print.js  # Formateador de impresión para ticket térmico (58mm/80mm)
│   │   │   └── charts.js     # Gráficos del Balance de Pérdidas de Agua (Chart.js)
│   │   └── dist/             # Archivos CSS/JS compilados para producción
│   │       └── output.css
│   │
│   └── templates/            # Plantillas HTML (Jinja2)
│       ├── base.html         # Plantilla maestra (Layout general con Tailwind CSS)
│       ├── components/       # Modales, Alertas y Navbar
│       │   ├── navbar.html
│       │   └── anomaly_modal.html
│       ├── partners/         # Vistas Módulo 1
│       │   ├── list.html
│       │   ├── form.html
│       │   └── meter_change.html
│       ├── readings/         # Vistas Módulo 2 (Mobile-First)
│       │   └── capture.html  # Interfaz optimizada con teclado numérico e inputs adaptados
│       ├── billing/          # Vistas Módulo 3
│       │   ├── config.html
│       │   └── process.html
│       ├── pos/              # Vistas Módulo 4
│       │   ├── cashier.html  # Interfaz de cobranza presencial
│       │   └── ticket_template.html # Plantilla de ticket para la boleta/comprobante
│       └── reports/          # Vistas Módulo 5 y Cumplimiento Normativo
│           ├── water_balance.html
│           ├── municipal_subsidy.html
│           └── siss_cloro.html
│
├── instance/                 # Base de datos local SQLite y archivos persistentes
│   └── apr_database.sqlite
│
├── migrations/               # Control de versiones del esquema de base de datos (Flask-Migrate/Alembic)
└── tests/                    # Pruebas unitarias e integración
    ├── test_billing.py       # Tests del cálculo tarifario y tope de 15m³ de subsidio
    ├── test_rut.py           # Unit tests de algoritmos DV del RUT
    └── test_sii.py           # Tests del formateador DTE
 ```