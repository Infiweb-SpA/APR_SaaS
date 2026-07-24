/**
 * offline_sync.js – Sistema de sincronización offline para lecturas.
 *
 * Funcionalidades:
 * 1. Detección automática de estado online/offline.
 * 2. Guardado local de lecturas en LocalStorage cuando no hay conexión.
 * 3. Indicador visual de estado de conexión y cola pendiente.
 * 4. Sincronización automática batch al recuperar internet.
 * 5. Sincronización manual forzada.
 * 6. Prevención de duplicados por offline_id.
 * 7. Retry con backoff exponencial ante fallos.
 *
 * Dependencias: Ninguna (Vanilla ES6).
 * API: window.OfflineSync
 */

(function () {
    'use strict';

    // ══════════════════════════════════════════════════════════
    // CONFIGURACIÓN
    // ══════════════════════════════════════════════════════════

    var CONFIG = {
        // Clave LocalStorage
        STORAGE_KEY: 'apr_readings_offline_queue',
        // Endpoint de sincronización
        SYNC_URL: '/readings/api/sync',
        // CSRF token (se inyecta desde template)
        CSRF_TOKEN: '',
        // Retry config
        MAX_RETRIES: 3,
        RETRY_BASE_DELAY: 2000, // ms, backoff exponencial
        // Intervalo de chequeo periódico (ms)
        HEALTH_CHECK_INTERVAL: 30000, // 30 segundos
        // Auto-sync al recuperar conexión
        AUTO_SYNC_ON_RECONNECT: true,
    };

    // ══════════════════════════════════════════════════════════
    // ESTADO INTERNO
    // ══════════════════════════════════════════════════════════

    var _state = {
        isOnline: navigator.onLine,
        isSyncing: false,
        retryCount: 0,
        lastSyncAttempt: null,
        lastSyncResult: null,
        queue: [], // Cola en memoria (espejo de LocalStorage)
    };

    // ══════════════════════════════════════════════════════════
    // API PÚBLICA
    // ══════════════════════════════════════════════════════════

    window.OfflineSync = {
        /**
         * Inicializa el sistema de sincronización offline.
         * Llamar una vez al cargar la página de captura.
         * @param {Object} options - Configuración opcional.
         */
        init: function (options) {
            _init(options);
        },

        /**
         * Agrega una lectura a la cola offline.
         * @param {Object} readingData - Datos de la lectura (mismos campos que capture API).
         * @returns {Object} { queued: true, offline_id, queue_length }
         */
        enqueue: function (readingData) {
            return _enqueueReading(readingData);
        },

        /**
         * Fuerza sincronización manual de toda la cola.
         * @returns {Promise} Resuelve con el resultado de la sincronización.
         */
        syncNow: function () {
            return _syncQueue();
        },

        /**
         * Retorna la cola actual de lecturas pendientes.
         * @returns {Array} Lista de lecturas pendientes.
         */
        getQueue: function () {
            return _loadQueue();
        },

        /**
         * Cantidad de lecturas pendientes en cola.
         * @returns {number}
         */
        getPendingCount: function () {
            return _loadQueue().length;
        },

        /**
         * Limpia toda la cola offline (usar con precaución).
         */
        clearQueue: function () {
            _saveQueue([]);
            _updateBadge();
        },

        /**
         * Elimina una lectura específica de la cola por offline_id.
         * @param {string} offlineId
         */
        removeById: function (offlineId) {
            var queue = _loadQueue();
            queue = queue.filter(function (item) {
                return item.offline_id !== offlineId;
            });
            _saveQueue(queue);
            _updateBadge();
        },

        /**
         * Estado actual del sistema.
         * @returns {Object}
         */
        getStatus: function () {
            return {
                isOnline: _state.isOnline,
                isSyncing: _state.isSyncing,
                pendingCount: _loadQueue().length,
                lastSyncAttempt: _state.lastSyncAttempt,
                lastSyncResult: _state.lastSyncResult,
                retryCount: _state.retryCount,
            };
        },

        /**
         * Configura el CSRF token necesario para las peticiones.
         * @param {string} token
         */
        setCsrfToken: function (token) {
            CONFIG.CSRF_TOKEN = token;
        },
    };

    // ══════════════════════════════════════════════════════════
    // INICIALIZACIÓN
    // ══════════════════════════════════════════════════════════

    function _init(options) {
        // Merge opciones
        if (options) {
            if (options.syncUrl) CONFIG.SYNC_URL = options.syncUrl;
            if (options.csrfToken) CONFIG.CSRF_TOKEN = options.csrfToken;
            if (options.maxRetries) CONFIG.MAX_RETRIES = options.maxRetries;
            if (options.autoSync !== undefined) CONFIG.AUTO_SYNC_ON_RECONNECT = options.autoSync;
        }

        // Cargar cola existente
        _state.queue = _loadQueue();

        // Detectar estado de conexión
        _setupConnectivityListeners();

        // Renderizar badge inicial
        _renderBadge();
        _updateBadge();

        // Verificar conexión periódicamente
        setInterval(_healthCheck, CONFIG.HEALTH_CHECK_INTERVAL);

        // Si hay cola pendiente y estamos online, intentar sync
        if (_state.isOnline && _state.queue.length > 0) {
            setTimeout(function () {
                _syncQueue();
            }, 2000); // Delay para no interferir con la carga de la página
        }
    }

    // ══════════════════════════════════════════════════════════
    // DETECCIÓN DE CONECTIVIDAD
    // ══════════════════════════════════════════════════════════

    function _setupConnectivityListeners() {
        window.addEventListener('online', function () {
            _state.isOnline = true;
            _updateConnectivityUI(true);

            if (CONFIG.AUTO_SYNC_ON_RECONNECT && _state.queue.length > 0) {
                _showToast('Conexión restaurada. Sincronizando ' + _state.queue.length + ' lecturas...', 'info');
                setTimeout(function () {
                    _syncQueue();
                }, 1000);
            }
        });

        window.addEventListener('offline', function () {
            _state.isOnline = false;
            _updateConnectivityUI(false);
            _showToast('Sin conexión. Las lecturas se guardarán localmente.', 'warning');
        });

        // Estado inicial
        _updateConnectivityUI(_state.isOnline);
    }

    function _healthCheck() {
        // Ping ligero al servidor para verificar conexión real
        if (!navigator.onLine) {
            if (_state.isOnline) {
                _state.isOnline = false;
                _updateConnectivityUI(false);
            }
            return;
        }

        // Fetch HEAD ligero con timeout corto
        var controller = new AbortController();
        var timeoutId = setTimeout(function () { controller.abort(); }, 5000);

        fetch('/readings/api/sync/status', {
            method: 'GET',
            signal: controller.signal,
            headers: { 'Accept': 'application/json' },
        })
        .then(function (res) {
            clearTimeout(timeoutId);
            if (!_state.isOnline) {
                _state.isOnline = true;
                _updateConnectivityUI(true);
                if (CONFIG.AUTO_SYNC_ON_RECONNECT && _state.queue.length > 0) {
                    _syncQueue();
                }
            }
        })
        .catch(function () {
            clearTimeout(timeoutId);
            // No cambiar estado: puede ser timeout puntual
        });
    }

    // ══════════════════════════════════════════════════════════
    // COLA: PERSISTENCIA (LocalStorage)
    // ══════════════════════════════════════════════════════════

    function _loadQueue() {
        try {
            var raw = localStorage.getItem(CONFIG.STORAGE_KEY);
            if (!raw) return [];
            var parsed = JSON.parse(raw);
            return Array.isArray(parsed) ? parsed : [];
        } catch (e) {
            console.error('[OfflineSync] Error leyendo cola:', e);
            return [];
        }
    }

    function _saveQueue(queue) {
        try {
            _state.queue = queue;
            localStorage.setItem(CONFIG.STORAGE_KEY, JSON.stringify(queue));
        } catch (e) {
            console.error('[OfflineSync] Error guardando cola:', e);
            // Si LocalStorage está lleno, intentar limpiar datos viejos
            if (e.name === 'QuotaExceededError') {
                _showToast('Almacenamiento local lleno. Sincronice pendientes.', 'error');
            }
        }
    }

    function _generateOfflineId() {
        return 'off_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6);
    }

    // ══════════════════════════════════════════════════════════
    // COLA: ENQUEUE (Agregar lectura)
    // ══════════════════════════════════════════════════════════

    function _enqueueReading(readingData) {
        var queue = _loadQueue();

        // Generar ID único para evitar duplicados
        var offlineId = readingData.offline_id || _generateOfflineId();

        // Verificar duplicado
        var exists = queue.some(function (item) {
            return item.offline_id === offlineId;
        });
        if (exists) {
            return { queued: false, offline_id: offlineId, reason: 'duplicate' };
        }

        // Verificar duplicado por meter_id + periodo
        var duplicateByPeriod = queue.some(function (item) {
            return item.meter_id === readingData.meter_id &&
                   item.periodo === readingData.periodo;
        });
        if (duplicateByPeriod) {
            return { queued: false, offline_id: offlineId, reason: 'duplicate_period' };
        }

        // Agregar metadatos
        var entry = Object.assign({}, readingData, {
            offline_id: offlineId,
            queued_at: new Date().toISOString(),
            sync_attempts: 0,
        });

        queue.push(entry);
        _saveQueue(queue);
        _updateBadge();

        return {
            queued: true,
            offline_id: offlineId,
            queue_length: queue.length,
        };
    }

    // ══════════════════════════════════════════════════════════
    // SINCRONIZACIÓN
    // ══════════════════════════════════════════════════════════

    function _syncQueue() {
        return new Promise(function (resolve, reject) {
            var queue = _loadQueue();

            if (queue.length === 0) {
                resolve({ synced: 0, skipped: 0, errors: [] });
                return;
            }

            if (_state.isSyncing) {
                resolve({ synced: 0, skipped: 0, errors: [], message: 'Sync ya en progreso' });
                return;
            }

            if (!_state.isOnline) {
                _showToast('Sin conexión. No se puede sincronizar.', 'warning');
                resolve({ synced: 0, skipped: 0, errors: [], message: 'Offline' });
                return;
            }

            _state.isSyncing = true;
            _state.lastSyncAttempt = new Date().toISOString();
            _updateBadge();

            _showSyncProgress(true);

            // Enviar toda la cola como batch
            fetch(CONFIG.SYNC_URL, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': CONFIG.CSRF_TOKEN,
                    'X-Requested-With': 'XMLHttpRequest',
                },
                body: JSON.stringify(queue),
            })
            .then(function (res) {
                return res.json();
            })
            .then(function (data) {
                _state.isSyncing = false;
                _state.retryCount = 0;

                if (data.success) {
                    // Remover de la cola los sincronizados exitosamente
                    _processSyncResult(data, queue);

                    _state.lastSyncResult = {
                        success: true,
                        synced: data.synced,
                        skipped: data.skipped,
                        errors: data.errors ? data.errors.length : 0,
                        timestamp: new Date().toISOString(),
                    };

                    var msg = 'Sincronizadas: ' + data.synced;
                    if (data.skipped > 0) msg += ', Omitidas: ' + data.skipped;
                    if (data.errors && data.errors.length > 0) msg += ', Errores: ' + data.errors.length;

                    _showToast(msg, data.errors && data.errors.length > 0 ? 'warning' : 'success');
                    _showSyncProgress(false);
                    _updateBadge();

                    resolve(data);
                } else {
                    throw new Error(data.error || 'Error desconocido del servidor');
                }
            })
            .catch(function (err) {
                _state.isSyncing = false;
                console.error('[OfflineSync] Error en sync:', err);

                _state.lastSyncResult = {
                    success: false,
                    error: err.message,
                    timestamp: new Date().toISOString(),
                };

                // Retry con backoff exponencial
                if (_state.retryCount < CONFIG.MAX_RETRIES) {
                    _state.retryCount++;
                    var delay = CONFIG.RETRY_BASE_DELAY * Math.pow(2, _state.retryCount - 1);

                    _showToast(
                        'Error sincronizando. Reintento ' + _state.retryCount +
                        '/' + CONFIG.MAX_RETRIES + ' en ' + (delay / 1000) + 's...',
                        'warning'
                    );

                    setTimeout(function () {
                        _syncQueue().then(resolve).catch(reject);
                    }, delay);
                } else {
                    _showToast(
                        'No se pudo sincronizar después de ' + CONFIG.MAX_RETRIES +
                        ' intentos. Las lecturas siguen guardadas localmente.',
                        'error'
                    );
                    _showSyncProgress(false);
                    _updateBadge();
                    reject(err);
                }
            });
        });
    }

    function _processSyncResult(serverResult, localQueue) {
        // IDs sincronizados exitosamente del servidor
        var syncedIds = new Set();
        if (serverResult.readings) {
            serverResult.readings.forEach(function (r) {
                if (r.offline_id) syncedIds.add(r.offline_id);
            });
        }

        // IDs con errores (no remover de la cola)
        var errorIds = new Set();
        if (serverResult.errors) {
            serverResult.errors.forEach(function (e) {
                if (e.offline_id) errorIds.add(e.offline_id);
            });
        }

        // Filtrar cola: remover sincronizados, mantener errores
        var remaining = localQueue.filter(function (item) {
            // Si fue sincronizado, remover
            if (syncedIds.has(item.offline_id)) return false;
            // Si tiene error, incrementar intentos y mantener
            if (errorIds.has(item.offline_id)) {
                item.sync_attempts = (item.sync_attempts || 0) + 1;
                return true;
            }
            // Si fue skipped (duplicado en servidor), remover
            return false;
        });

        _saveQueue(remaining);
    }

    // ══════════════════════════════════════════════════════════
    // UI: BADGE DE CONECTIVIDAD Y COLA
    // ══════════════════════════════════════════════════════════

    function _renderBadge() {
        // No crear si ya existe
        if (document.getElementById('offline-badge')) return;

        var badge = document.createElement('div');
        badge.id = 'offline-badge';
        badge.className = 'fixed bottom-4 left-4 z-[55] flex items-center gap-2 px-3 py-2 rounded-lg shadow-lg text-xs font-medium transition-all duration-300';
        badge.style.display = 'none';
        document.body.appendChild(badge);
    }

    function _updateBadge() {
        var badge = document.getElementById('offline-badge');
        if (!badge) return;

        var queue = _state.queue || _loadQueue();
        var count = queue.length;
        var isOnline = _state.isOnline;
        var isSyncing = _state.isSyncing;

        // Mostrar badge si: offline O hay cola pendiente
        if (!isOnline || count > 0 || isSyncing) {
            badge.style.display = 'flex';
        } else {
            badge.style.display = 'none';
            return;
        }

        // Contenido según estado
        var html = '';
        var bgClass = '';

        if (isSyncing) {
            bgClass = 'bg-navy-600 text-white';
            html = '<svg class="w-4 h-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">' +
                   '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>' +
                   '</svg>' +
                   '<span>Sincronizando...</span>';
        } else if (!isOnline) {
            bgClass = 'bg-amber-500 text-white';
            html = '<span class="w-2 h-2 rounded-full bg-white animate-pulse"></span>' +
                   '<span>Sin conexión</span>';
            if (count > 0) {
                html += '<span class="ml-1 bg-white/20 px-1.5 py-0.5 rounded">' + count + ' pendiente' + (count > 1 ? 's' : '') + '</span>';
            }
        } else if (count > 0) {
            bgClass = 'bg-teal-600 text-white';
            html = '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">' +
                   '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>' +
                   '</svg>' +
                   '<span>' + count + ' lectura' + (count > 1 ? 's' : '') + ' pendiente' + (count > 1 ? 's' : '') + '</span>' +
                   '<button id="btn-sync-now" class="ml-2 bg-white/20 hover:bg-white/30 px-2 py-0.5 rounded transition-colors">' +
                   'Sincronizar</button>';
        }

        badge.className = 'fixed bottom-4 left-4 z-[55] flex items-center gap-2 px-3 py-2 rounded-lg shadow-lg text-xs font-medium transition-all duration-300 ' + bgClass;
        badge.innerHTML = html;

        // Bind sync button
        var syncBtn = document.getElementById('btn-sync-now');
        if (syncBtn) {
            syncBtn.addEventListener('click', function () {
                _syncQueue();
            });
        }
    }

    function _updateConnectivityUI(isOnline) {
        _updateBadge();

        // Cambiar indicadores en la UI de captura si existen
        var indicators = document.querySelectorAll('.connectivity-indicator');
        indicators.forEach(function (el) {
            el.classList.toggle('text-teal', isOnline);
            el.classList.toggle('text-amber-500', !isOnline);
        });

        // Texto de estado
        var statusTexts = document.querySelectorAll('.connectivity-text');
        statusTexts.forEach(function (el) {
            el.textContent = isOnline ? 'En línea' : 'Sin conexión';
        });
    }

    // ══════════════════════════════════════════════════════════
    // UI: PROGRESO DE SINCRONIZACIÓN
    // ══════════════════════════════════════════════════════════

    function _showSyncProgress(show) {
        var bar = document.getElementById('sync-progress-bar');
        if (!bar && show) {
            bar = document.createElement('div');
            bar.id = 'sync-progress-bar';
            bar.className = 'fixed top-0 left-0 right-0 z-[70] h-1 bg-navy-600';
            bar.innerHTML = '<div class="h-full bg-teal animate-pulse" style="width:100%"></div>';
            document.body.appendChild(bar);
        }

        if (bar) {
            bar.style.display = show ? 'block' : 'none';
            if (!show) {
                setTimeout(function () {
                    if (bar.parentElement) bar.remove();
                }, 500);
            }
        }
    }

    // ══════════════════════════════════════════════════════════
    // UI: TOAST NOTIFICATIONS
    // ══════════════════════════════════════════════════════════

    function _showToast(msg, type) {
        type = type || 'info';
        var container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            container.className = 'fixed bottom-4 right-4 z-[60] flex flex-col gap-2';
            document.body.appendChild(container);
        }

        var el = document.createElement('div');
        var colors = {
            success: 'bg-teal-600 text-white',
            error: 'bg-red-600 text-white',
            warning: 'bg-amber-500 text-white',
            info: 'bg-navy-600 text-white',
        };

        el.className = 'flex items-start gap-3 px-4 py-3 rounded-lg shadow-lg text-sm max-w-sm ' + (colors[type] || colors.info);
        el.style.animation = 'slide-in 0.3s ease-out';
        el.textContent = msg;
        container.appendChild(el);

        setTimeout(function () {
            el.style.transition = 'opacity 0.3s ease';
            el.style.opacity = '0';
            setTimeout(function () { el.remove(); }, 300);
        }, 5000);
    }

    // ══════════════════════════════════════════════════════════
    // AUTO-INIT
    // ══════════════════════════════════════════════════════════

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            if (typeof window.OfflineSyncAutoInit !== 'undefined' && !window.OfflineSyncAutoInit) return;
            window.OfflineSync.init();
        });
    } else {
        if (typeof window.OfflineSyncAutoInit === 'undefined' || window.OfflineSyncAutoInit) {
            window.OfflineSync.init();
        }
    }

})();