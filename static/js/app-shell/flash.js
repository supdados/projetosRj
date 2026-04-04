// === flash.js — Sistema de flash messages unificado ===
(function () {
    var FLASH_TIMEOUTS = { success: 2200, info: 2200, warning: 3200, danger: 4200, error: 4200 };
    var FLASH_ICONS = {
        success: 'fa-check-circle',
        danger: 'fa-exclamation-circle',
        error: 'fa-exclamation-circle',
        warning: 'fa-exclamation-triangle',
        info: 'fa-info-circle',
    };

    function dismissFlash(el) {
        if (el.classList.contains('flash-hiding')) return;
        el.classList.add('flash-hiding');
        window.setTimeout(function () { el.remove(); }, 300);
    }

    window.showFlash = function (message, type) {
        if (!message) return;
        var t = (type === 'error' ? 'danger' : type) || 'info';
        var stack = document.querySelector('.app-flash-stack');
        if (!stack) {
            stack = document.createElement('div');
            stack.className = 'app-flash-stack';
            stack.setAttribute('role', 'status');
            stack.setAttribute('aria-live', 'polite');
            stack.setAttribute('aria-atomic', 'true');
            document.body.appendChild(stack);
        }
        var activeFlashes = Array.from(stack.children).filter(function (c) {
            return !c.classList.contains('flash-hiding');
        });
        while (activeFlashes.length >= 3) {
            dismissFlash(activeFlashes.shift());
        }
        var el = document.createElement('div');
        el.className = 'app-flash-alert alert-' + t;
        el.setAttribute('role', 'alert');
        var icon = document.createElement('i');
        icon.className = 'fas ' + (FLASH_ICONS[t] || 'fa-info-circle') + ' app-flash-icon';
        var span = document.createElement('span');
        span.textContent = message;
        el.appendChild(icon);
        el.appendChild(span);
        stack.appendChild(el);
        window.setTimeout(function () { dismissFlash(el); }, FLASH_TIMEOUTS[t] || 2200);
    };

    // Auto-dismiss dos flashes renderizados pelo servidor
    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('.app-flash-stack .app-flash-alert').forEach(function (el) {
            var t = el.dataset.flashType || 'info';
            window.setTimeout(function () { dismissFlash(el); }, FLASH_TIMEOUTS[t] || 2200);
        });
    });
})();
