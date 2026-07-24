/**
 * reading_val.js – Validación cliente para captura de lecturas.
 *
 * Funcionalidades:
 * 1. Teclado numérico forzado en inputs de lectura (mobile-first).
 * 2. Validación en tiempo real: alerta si consumo > 100% promedio 3 meses.
 * 3. Validación en tiempo real: alerta si lectura < lectura anterior.
 * 4. Feedback visual inmediato (colores, iconos, mensajes).
 * 5. Pre-submit validation antes de enviar al backend.
 *
 * Dependencias: Ninguna (Vanilla ES6).
 * Uso: Cargar en capture.html vía <script> o {% block extra_scripts %}.
 *
 * Convención: Expone window.ReadingValidator como API pública.
 */

(function () {
    'use strict';

    // ══════════════════════════════════════════════════════════
    // CONFIGURACIÓN
    // ══════════════════════════════════════════════════════════

    var CONFIG = {
        // Selector del input de lectura actual
        INPUT_SELECTOR: '.reading-input',
        // Selector del contenedor con data attributes
        ROW_SELECTOR: '.reading-row',
        // Atributos data esperados en cada row
        ATTR_METER_ID: 'data-meter-id',
        ATTR_LECTURA_ANTERIOR: 'data-lectura-anterior',
        ATTR_AVG_CONSUMPTION: 'data-avg-consumption',
        // Clases CSS para feedback
        CLASS_VALID: 'border-teal',
        CLASS_WARNING: 'border-amber-400',
        CLASS_ERROR: 'border-red-400',
        CLASS_NEUTRAL: 'border-sand-300',
        // Umbral de advertencia (100% del promedio)
        CONSUMPTION_THRESHOLD: 1.0,
        // Debounce para validación en tiempo real
        DEBOUNCE_MS: 300,
    };

    // ══════════════════════════════════════════════════════════
    // API PÚBLICA
    // ══════════════════════════════════════════════════════════

    window.ReadingValidator = {
        /**
         * Valida una lectura individual contra sus reglas de negocio.
         * @param {number} lecturaActual - Valor capturado en terreno.
         * @param {number} lecturaAnterior - Última lectura registrada.
         * @param {number} avgConsumption - Promedio consumo últimos 3 meses.
         * @returns {Object} { isValid, consumo, warnings[], errors[] }
         */
        validate: function (lecturaActual, lecturaAnterior, avgConsumption) {
            return _validateReading(lecturaActual, lecturaAnterior, avgConsumption);
        },

        /**
         * Inicializa la validación en todos los inputs .reading-input.
         * Llamar una vez al cargar la página.
         */
        init: function () {
            _initAllInputs();
        },

        /**
         * Valida todos los inputs antes de submit batch.
         * @returns {Object} { allValid, invalidCount, details[] }
         */
        validateAll: function () {
            return _validateAllInputs();
        },

        /**
         * Fuerza teclado numérico en un input específico.
         * @param {HTMLElement} input
         */
        forceNumericKeyboard: function (input) {
            _applyNumericAttributes(input);
        },
    };

    // ══════════════════════════════════════════════════════════
    // VALIDACIÓN INDIVIDUAL (Core Logic)
    // ══════════════════════════════════════════════════════════

    function _validateReading(lecturaActual, lecturaAnterior, avgConsumption) {
        var result = {
            isValid: true,
            consumo: 0,
            warnings: [],
            errors: [],
            level: 'neutral', // 'neutral' | 'valid' | 'warning' | 'error'
        };

        // Parsear valores (defensivo)
        var actual = parseInt(lecturaActual, 10);
        var anterior = parseInt(lecturaAnterior, 10);
        var avg = parseFloat(avgConsumption) || 0;

        // Sin valor → neutral
        if (isNaN(actual) || lecturaActual === '' || lecturaActual === null) {
            result.level = 'neutral';
            return result;
        }

        // Valor negativo
        if (actual < 0) {
            result.isValid = false;
            result.errors.push('La lectura no puede ser negativa.');
            result.level = 'error';
            return result;
        }

        // Consumo calculado
        var consumo = actual - anterior;
        result.consumo = consumo;

        // ── Regla 1: Lectura menor a la anterior ──
        if (actual < anterior) {
            result.isValid = false;
            result.errors.push(
                'La lectura (' + actual + ') es menor a la anterior (' + anterior + '). ' +
                'Verifique si el medidor fue cambiado o reiniciado.'
            );
            result.level = 'error';
            return result;
        }

        // ── Regla 2: Consumo > 100% del promedio ──
        if (consumo > 0 && avg > 0) {
            var threshold = avg * (1 + CONFIG.CONSUMPTION_THRESHOLD);
            if (consumo > threshold) {
                result.warnings.push(
                    'Consumo alto: ' + consumo + ' m³ (promedio: ' + avg.toFixed(1) + ' m³). ' +
                    'Supera el ' + (CONFIG.CONSUMPTION_THRESHOLD * 100) + '% del promedio de los últimos 3 meses.'
                );
                result.level = 'warning';
            }
        }

        // ── Regla 3: Consumo = 0 (podría ser válido pero informativo) ──
        if (consumo === 0 && actual === anterior) {
            result.warnings.push('Sin consumo registrado. Verifique que el medidor esté funcionando.');
            if (result.level === 'neutral') {
                result.level = 'warning';
            }
        }

        // ── Sin warnings ni errors → válido ──
        if (result.errors.length === 0 && result.warnings.length === 0) {
            result.level = 'valid';
        }

        return result;
    }

    // ══════════════════════════════════════════════════════════
    // INICIALIZACIÓN DE INPUTS
    // ══════════════════════════════════════════════════════════

    function _initAllInputs() {
        var inputs = document.querySelectorAll(CONFIG.INPUT_SELECTOR);
        inputs.forEach(function (input) {
            _applyNumericAttributes(input);
            _attachValidationListeners(input);
        });
    }

    function _applyNumericAttributes(input) {
        // Forzar teclado numérico en mobile
        input.setAttribute('inputmode', 'numeric');
        input.setAttribute('pattern', '[0-9]*');
        input.setAttribute('autocomplete', 'off');

        // Si no tiene type number, forzarlo
        if (input.type !== 'number') {
            input.type = 'number';
        }
        input.setAttribute('min', '0');
        input.setAttribute('step', '1');
    }

    function _attachValidationListeners(input) {
        var timer = null;

        // Validación con debounce en cada input
        input.addEventListener('input', function () {
            clearTimeout(timer);
            var el = this;
            timer = setTimeout(function () {
                _validateAndRender(el);
            }, CONFIG.DEBOUNCE_MS);
        });

        // Validación inmediata en blur (pierde foco)
        input.addEventListener('blur', function () {
            clearTimeout(timer);
            _validateAndRender(this);
        });

        // Prevenir caracteres no numéricos
        input.addEventListener('keypress', function (e) {
            // Permitir: backspace, tab, enter, delete, arrows
            var allowed = [8, 9, 13, 46, 37, 38, 39, 40];
            if (allowed.indexOf(e.keyCode) !== -1) {
                return;
            }
            // Solo dígitos
            if (e.key && !/^[0-9]$/.test(e.key)) {
                e.preventDefault();
            }
        });

        // Limpiar ceros a la izquierda al perder foco
        input.addEventListener('blur', function () {
            if (this.value && this.value.length > 1 && this.value[0] === '0') {
                this.value = parseInt(this.value, 10).toString();
            }
        });
    }

    // ══════════════════════════════════════════════════════════
    // RENDERIZADO DE FEEDBACK VISUAL
    // ══════════════════════════════════════════════════════════

    function _validateAndRender(input) {
        var row = input.closest(CONFIG.ROW_SELECTOR);
        if (!row) return;

        var lecturaAnterior = parseInt(row.getAttribute(CONFIG.ATTR_LECTURA_ANTERIOR), 10) || 0;
        var avgConsumption = parseFloat(row.getAttribute(CONFIG.ATTR_AVG_CONSUMPTION)) || 0;

        var result = _validateReading(input.value, lecturaAnterior, avgConsumption);

        // Limpiar feedback previo
        _clearFeedback(input, row);

        // Aplicar nuevo feedback según nivel
        switch (result.level) {
            case 'valid':
                _renderValid(input, row, result);
                break;
            case 'warning':
                _renderWarning(input, row, result);
                break;
            case 'error':
                _renderError(input, row, result);
                break;
            default:
                // neutral: sin feedback
                break;
        }

        // Actualizar consumo display si existe el elemento
        _updateConsumoDisplay(row, result);
    }

    function _clearFeedback(input, row) {
        // Remover clases de estado del input
        input.classList.remove(
            CONFIG.CLASS_VALID,
            CONFIG.CLASS_WARNING,
            CONFIG.CLASS_ERROR
        );

        // Remover mensajes previos
        var prevMsg = row.querySelector('.reading-feedback');
        if (prevMsg) prevMsg.remove();

        // Remover iconos previos
        var prevIcon = row.querySelector('.reading-icon');
        if (prevIcon) prevIcon.remove();
    }

    function _renderValid(input, row, result) {
        input.classList.add(CONFIG.CLASS_VALID);
        _injectIcon(row, 'valid');
    }

    function _renderWarning(input, row, result) {
        input.classList.add(CONFIG.CLASS_WARNING);
        _injectIcon(row, 'warning');

        if (result.warnings.length > 0) {
            _injectMessage(row, result.warnings[0], 'warning');
        }
    }

    function _renderError(input, row, result) {
        input.classList.add(CONFIG.CLASS_ERROR);
        _injectIcon(row, 'error');

        if (result.errors.length > 0) {
            _injectMessage(row, result.errors[0], 'error');
        }
    }

    function _injectIcon(row, level) {
        var input = row.querySelector(CONFIG.INPUT_SELECTOR);
        if (!input) return;

        // Asegurar contenedor relativo
        var wrapper = input.parentElement;
        if (getComputedStyle(wrapper).position === 'static') {
            wrapper.style.position = 'relative';
        }

        var icon = document.createElement('span');
        icon.className = 'reading-icon absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none';

        var icons = {
            valid: '<svg class="w-5 h-5 text-teal" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>',
            warning: '<svg class="w-5 h-5 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.072 16.5c-.77.833.192 2.5 1.732 2.5z"/></svg>',
            error: '<svg class="w-5 h-5 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>',
        };

        icon.innerHTML = icons[level] || '';
        wrapper.appendChild(icon);

        // Ajustar padding-right del input para no solapar con el icono
        input.style.paddingRight = '2.5rem';
    }

    function _injectMessage(row, message, level) {
        var msg = document.createElement('p');
        msg.className = 'reading-feedback mt-1.5 text-xs flex items-start gap-1.5';

        var colorClass = level === 'error' ? 'text-red-500' : 'text-amber-600';
        msg.classList.add(colorClass);

        // Icono inline pequeño
        var miniIcon = level === 'error' ? '!' : '⚠';
        msg.innerHTML = '<span class="font-bold">' + miniIcon + '</span> ' + message;

        // Insertar después del input wrapper
        var input = row.querySelector(CONFIG.INPUT_SELECTOR);
        if (input) {
            var wrapper = input.parentElement;
            wrapper.parentElement.insertBefore(msg, wrapper.nextSibling);
        }
    }

    function _updateConsumoDisplay(row, result) {
        var consumoEl = row.querySelector('.consumo-display');
        if (!consumoEl) return;

        if (result.consumo > 0) {
            consumoEl.textContent = result.consumo + ' m³';
            consumoEl.classList.remove('text-stone-400');
            consumoEl.classList.add('text-navy-700', 'font-medium');
        } else if (result.consumo === 0) {
            consumoEl.textContent = '0 m³';
            consumoEl.classList.add('text-stone-400');
            consumoEl.classList.remove('text-navy-700', 'font-medium');
        } else {
            consumoEl.textContent = result.consumo + ' m³';
            consumoEl.classList.add('text-red-600', 'font-medium');
            consumoEl.classList.remove('text-stone-400', 'text-navy-700');
        }
    }

    // ══════════════════════════════════════════════════════════
    // VALIDACIÓN GLOBAL (PRE-SUBMIT BATCH)
    // ══════════════════════════════════════════════════════════

    function _validateAllInputs() {
        var inputs = document.querySelectorAll(CONFIG.INPUT_SELECTOR);
        var details = [];
        var invalidCount = 0;

        inputs.forEach(function (input) {
            var row = input.closest(CONFIG.ROW_SELECTOR);
            if (!row) return;

            var lecturaAnterior = parseInt(row.getAttribute(CONFIG.ATTR_LECTURA_ANTERIOR), 10) || 0;
            var avgConsumption = parseFloat(row.getAttribute(CONFIG.ATTR_AVG_CONSUMPTION)) || 0;
            var meterId = row.getAttribute(CONFIG.ATTR_METER_ID);

            var result = _validateReading(input.value, lecturaAnterior, avgConsumption);

            details.push({
                meterId: meterId,
                lecturaActual: input.value,
                lecturaAnterior: lecturaAnterior,
                result: result,
            });

            if (!result.isValid) {
                invalidCount++;
            }

            // Renderizar feedback visual
            _validateAndRender(input);
        });

        return {
            allValid: invalidCount === 0,
            invalidCount: invalidCount,
            totalInputs: inputs.length,
            details: details,
        };
    }

    // ══════════════════════════════════════════════════════════
    // AUTO-INIT (cuando el DOM está listo)
    // ══════════════════════════════════════════════════════════

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            window.ReadingValidator.init();
        });
    } else {
        // DOM ya cargado (script al final del body)
        window.ReadingValidator.init();
    }

})();