/**
 * Módulo 2 – Validador y formateador de RUT chileno (Cliente).
 * Aplicación: inputs con clase "rut-input".
 * Formato en tiempo real: XX.XXX.XXX-K
 */

(function () {
    'use strict';

    // ── Utilidades ────────────────────────────────────────

    /**
     * Limpia un RUT: elimina todo excepto dígitos y K/k.
     */
    function cleanRut(value) {
        return value.replace(/[^0-9kK]/g, '').toUpperCase();
    }

    /**
     * Calcula el dígito verificador para un cuerpo numérico.
     */
    function calculateDV(body) {
        var total = 0;
        var factor = 2;
        for (var i = body.length - 1; i >= 0; i--) {
            total += parseInt(body[i], 10) * factor;
            factor = factor < 7 ? factor + 1 : 2;
        }
        var remainder = total % 11;
        var result = 11 - remainder;
        if (result === 11) return '0';
        if (result === 10) return 'K';
        return String(result);
    }

    /**
     * Formatea un RUT limpio al formato XX.XXX.XXX-K.
     */
    function formatRut(cleaned) {
        if (cleaned.length < 2) return cleaned;

        var body = cleaned.slice(0, -1);
        var dv = cleaned.slice(-1);

        // Agregar puntos de miles
        var formatted = '';
        var count = 0;
        for (var i = body.length - 1; i >= 0; i--) {
            if (count > 0 && count % 3 === 0) {
                formatted = '.' + formatted;
            }
            formatted = body[i] + formatted;
            count++;
        }

        return formatted + '-' + dv;
    }

    /**
     * Valida el dígito verificador de un RUT limpio.
     */
    function validateRut(cleaned) {
        if (cleaned.length < 2) return false;

        var body = cleaned.slice(0, -1);
        var dv = cleaned.slice(-1);

        if (!/^\d+$/.test(body)) return false;
        if (body.length < 7 || body.length > 8) return false;

        return calculateDV(body) === dv;
    }

    // ── Formateo en tiempo real ───────────────────────────

    function onRutInput(e) {
        var input = e.target;
        var cursorPos = input.selectionStart;
        var oldLength = input.value.length;

        var cleaned = cleanRut(input.value);
        var formatted = formatRut(cleaned);

        input.value = formatted;

        // Ajustar posición del cursor
        var newLength = formatted.length;
        var diff = newLength - oldLength;
        var newPos = Math.max(0, cursorPos + diff);
        input.setSelectionRange(newPos, newPos);
    }

    // ── Validación al perder foco ─────────────────────────

    function onRutBlur(e) {
        var input = e.target;
        var cleaned = cleanRut(input.value);

        if (cleaned.length === 0) {
            clearValidation(input);
            return;
        }

        // Formatear definitivamente
        input.value = formatRut(cleaned);

        // Validar dígito verificador
        if (validateRut(cleaned)) {
            markValid(input);
        } else {
            markInvalid(input);
        }
    }

    // ── Feedback visual ───────────────────────────────────

    function markValid(input) {
        input.classList.remove('border-red-400', 'focus:ring-red-300');
        input.classList.add('border-teal', 'focus:ring-teal/40');

        // Remover mensaje de error previo
        var errorEl = input.parentNode.querySelector('.rut-error');
        if (errorEl) errorEl.remove();

        // Agregar checkmark
        var existingCheck = input.parentNode.querySelector('.rut-check');
        if (!existingCheck) {
            var check = document.createElement('span');
            check.className = 'rut-check absolute right-3 top-1/2 -translate-y-1/2 text-teal';
            check.innerHTML = '<svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/></svg>';
            // Asegurar posición relativa en el contenedor
            input.parentNode.style.position = 'relative';
            input.parentNode.appendChild(check);
        }
    }

    function markInvalid(input) {
        input.classList.remove('border-teal', 'focus:ring-teal/40');
        input.classList.add('border-red-400', 'focus:ring-red-300');

        // Remover checkmark previo
        var existingCheck = input.parentNode.querySelector('.rut-check');
        if (existingCheck) existingCheck.remove();

        // Agregar o actualizar mensaje de error
        var errorEl = input.parentNode.querySelector('.rut-error');
        if (!errorEl) {
            errorEl = document.createElement('p');
            errorEl.className = 'rut-error mt-1.5 text-xs text-red-500';
            input.parentNode.appendChild(errorEl);
        }
        errorEl.textContent = 'El RUT ingresado no es válido';
    }

    function clearValidation(input) {
        input.classList.remove(
            'border-red-400', 'focus:ring-red-300',
            'border-teal', 'focus:ring-teal/40'
        );
        var errorEl = input.parentNode.querySelector('.rut-error');
        if (errorEl) errorEl.remove();
        var checkEl = input.parentNode.querySelector('.rut-check');
        if (checkEl) checkEl.remove();
    }

    // ── Limpiar antes de enviar formulario ────────────────

    function onFormSubmit(e) {
        var inputs = e.target.querySelectorAll('.rut-input');
        inputs.forEach(function (input) {
            var cleaned = cleanRut(input.value);
            if (cleaned.length >= 2) {
                input.value = formatRut(cleaned);
            }
        });
    }

    // ── Inicialización ────────────────────────────────────

    function init() {
        // Adjuntar a todos los inputs con clase rut-input
        document.querySelectorAll('.rut-input').forEach(function (input) {
            input.addEventListener('input', onRutInput);
            input.addEventListener('blur', onRutBlur);
            input.setAttribute('maxlength', '12');
            input.setAttribute('placeholder', '12.345.678-9');
            input.setAttribute('autocomplete', 'off');
        });

        // Adjuntar limpieza a formularios que contengan rut-input
        document.querySelectorAll('form').forEach(function (form) {
            if (form.querySelector('.rut-input')) {
                form.addEventListener('submit', onFormSubmit);
            }
        });
    }

    // Ejecutar cuando el DOM esté listo
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Exportar funciones para uso externo (testing, etc.)
    window.RutValidator = {
        clean: cleanRut,
        format: formatRut,
        validate: validateRut,
        calculateDV: calculateDV,
    };
})();