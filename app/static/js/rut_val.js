/**
 * APR SaaS - Validador y Formateador RUT Chileno (Vanilla JS)
 * Uso: <input class="rut-input" ...>
 * Expone: window.RutValidator { clean, format, validate, calculateDV }
 */
(function () {
  'use strict';

  // ═══════════════════════════════════════════════════════════
  // CORE
  // ═══════════════════════════════════════════════════════════
  function cleanRut(value) {
    return (value || '').replace(/[^0-9kK]/g, '').toUpperCase();
  }

  function calculateDV(body) {
    let total = 0, factor = 2;
    for (let i = body.length - 1; i >= 0; i--) {
      total += parseInt(body[i], 10) * factor;
      factor = factor < 7 ? factor + 1 : 2;
    }
    const rem = total % 11;
    const res = 11 - rem;
    if (res === 11) return '0';
    if (res === 10) return 'K';
    return String(res);
  }

  function formatRut(cleaned) {
    if (!cleaned || cleaned.length < 2) return cleaned;
    const body = cleaned.slice(0, -1);
    const dv = cleaned.slice(-1);
    let formatted = '';
    for (let i = body.length - 1, c = 1; i >= 0; i--, c++) {
      formatted = body[i] + (c % 3 === 0 && i !== 0 ? '.' : '') + formatted;
    }
    return `${formatted}-${dv}`;
  }

  function validateRut(cleaned) {
    if (!cleaned || cleaned.length < 2) return false;
    const body = cleaned.slice(0, -1);
    const dv = cleaned.slice(-1);
    if (!/^\d+$/.test(body)) return false;
    if (body.length < 7 || body.length > 8) return false; // RUTs estándar
    return calculateDV(body) === dv;
  }

  // ═══════════════════════════════════════════════════════════
  // EVENTOS
  // ═══════════════════════════════════════════════════════════
  function onInput(e) {
    const el = e.target;
    const pos = el.selectionStart;
    const oldLen = el.value.length;
    const cleaned = cleanRut(el.value);
    const formatted = formatRut(cleaned);
    el.value = formatted;
    // Ajuste cursor simple
    const diff = formatted.length - oldLen;
    el.setSelectionRange(pos + diff, pos + diff);
  }

  function onBlur(e) {
    const el = e.target;
    const cleaned = cleanRut(el.value);
    if (!cleaned) { clearValidation(el); return; }
    el.value = formatRut(cleaned);
    validateRut(cleaned) ? markValid(el) : markInvalid(el);
  }

  // ═══════════════════════════════════════════════════════════
  // UI FEEDBACK (Tailwind v3 classes)
  // ═══════════════════════════════════════════════════════════
  function markValid(el) {
    el.classList.remove('border-red-400', 'focus:ring-red-300');
    el.classList.add('border-teal-500', 'focus:ring-teal-500/40');
    removeError(el);
    addCheck(el);
  }

  function markInvalid(el) {
    el.classList.remove('border-teal-500', 'focus:ring-teal-500/40');
    el.classList.add('border-red-400', 'focus:ring-red-300');
    removeCheck(el);
    addError(el, 'El RUT ingresado no es válido');
  }

  function clearValidation(el) {
    el.classList.remove('border-red-400', 'focus:ring-red-300', 'border-teal-500', 'focus:ring-teal-500/40');
    removeError(el);
    removeCheck(el);
  }

  function addCheck(el) {
    if (el.parentNode.querySelector('.rut-check')) return;
    const wrap = ensureRelative(el.parentNode);
    const span = document.createElement('span');
    span.className = 'rut-check absolute right-3 top-1/2 -translate-y-1/2 text-teal-500 pointer-events-none';
    span.innerHTML = '<svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/></svg>';
    wrap.appendChild(span);
  }

  function removeCheck(el) {
    const c = el.parentNode.querySelector('.rut-check');
    if (c) c.remove();
  }

  function addError(el, msg) {
    let p = el.parentNode.querySelector('.rut-error');
    if (!p) {
      p = document.createElement('p');
      p.className = 'rut-error mt-1.5 text-xs text-red-500';
      ensureRelative(el.parentNode).appendChild(p);
    }
    p.textContent = msg;
  }

  function removeError(el) {
    const p = el.parentNode.querySelector('.rut-error');
    if (p) p.remove();
  }

  function ensureRelative(node) {
    if (window.getComputedStyle(node).position === 'static') node.style.position = 'relative';
    return node;
  }

  // ═══════════════════════════════════════════════════════════
  // FORM SUBMIT: normalizar valor enviado
  // ═══════════════════════════════════════════════════════════
  function onSubmit(e) {
    e.target.querySelectorAll('.rut-input').forEach(el => {
      const cleaned = cleanRut(el.value);
      if (cleaned.length >= 2) el.value = formatRut(cleaned);
    });
  }

  // ═══════════════════════════════════════════════════════════
  // INIT
  // ═══════════════════════════════════════════════════════════
  function init() {
    document.querySelectorAll('.rut-input').forEach(el => {
      el.addEventListener('input', onInput);
      el.addEventListener('blur', onBlur);
      el.setAttribute('maxlength', '13'); // XX.XXX.XXX-X = 11, 8 dígitos = 12
      el.setAttribute('placeholder', '12.345.678-9');
      el.setAttribute('autocomplete', 'off');
      // Si ya tiene valor al cargar (edición), formatear y validar
      if (el.value) {
        const cleaned = cleanRut(el.value);
        el.value = formatRut(cleaned);
        if (cleaned.length >= 2) validateRut(cleaned) ? markValid(el) : markInvalid(el);
      }
    });
    document.querySelectorAll('form:has(.rut-input)').forEach(form => {
      form.addEventListener('submit', onSubmit);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // ═══════════════════════════════════════════════════════════
  // PUBLIC API
  // ═══════════════════════════════════════════════════════════
  window.RutValidator = {
    clean: cleanRut,
    format: formatRut,
    validate: validateRut,
    calculateDV: calculateDV
  };
})();