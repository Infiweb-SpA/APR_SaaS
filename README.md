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