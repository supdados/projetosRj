// === app-shell.js — Orquestrador do shell da aplicação ===
// Sub-módulos carregados antes deste arquivo:
//   app-shell/theme.js, flash.js, skeleton-navigation.js, global-search.js, notifications.js

/* Shared HTML-escape utility — single source of truth for all modules */
window.escapeHtml = function escapeHtml(value) {
    var div = document.createElement('div');
    div.textContent = value == null ? '' : String(value);
    return div.innerHTML;
};

document.addEventListener('DOMContentLoaded', function () {
    var body = document.body;
    var skeletonNav = window.AppShellSkeleton || {};
    var hasBootstrap = typeof window.bootstrap !== 'undefined';
    var nonNavigationalToggles = ['dropdown', 'collapse', 'modal', 'offcanvas', 'tab', 'pill'];

    // ── Bootstrap tooltips ──────────────────────────────────────────────
    if (hasBootstrap && bootstrap.Tooltip) {
        document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(function (el) {
            new bootstrap.Tooltip(el);
        });
    }

    // ── Loading overlay inicial ─────────────────────────────────────────
    body.classList.add('loading-active');
    if (typeof skeletonNav.showLoadingOverlay === 'function') {
        skeletonNav.showLoadingOverlay();
    }

    var loadingOverlay = document.querySelector('.loading-overlay');
    if (loadingOverlay) {
        loadingOverlay.classList.remove('active');
    }

    if (typeof skeletonNav.isPreviewEnabled === 'function' && skeletonNav.isPreviewEnabled()) {
        body.classList.remove('page-ready');
        body.classList.add('loading-active');
    }

    // ── Interceptação de links para navegação com skeleton ──────────────
    function shouldInterceptLink(link) {
        var hrefAttr = link.getAttribute('href');
        if (!hrefAttr || hrefAttr === '#' || hrefAttr.startsWith('#')) return false;

        if (
            hrefAttr.startsWith('javascript:') ||
            hrefAttr.startsWith('mailto:') ||
            hrefAttr.startsWith('tel:')
        ) return false;

        if (link.getAttribute('target') === '_blank' || link.hasAttribute('download')) return false;

        var toggleType = (link.getAttribute('data-bs-toggle') || '').toLowerCase();
        if (nonNavigationalToggles.includes(toggleType)) return false;

        try {
            var parsedUrl = new URL(link.href, window.location.origin);
            return parsedUrl.origin === window.location.origin;
        } catch (error) {
            return false;
        }
    }

    var navigateWithSkeleton = typeof skeletonNav.navigateWithSkeleton === 'function'
        ? skeletonNav.navigateWithSkeleton
        : null;

    if (navigateWithSkeleton) {
        document.querySelectorAll('a[href]').forEach(function (link) {
            if (!shouldInterceptLink(link)) return;

            link.addEventListener('click', function (event) {
                if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
                event.preventDefault();
                navigateWithSkeleton(this.href);
            });
        });
    }

    // ── Window load / pageshow ──────────────────────────────────────────
    var isPreviewEnabled = typeof skeletonNav.isPreviewEnabled === 'function' && skeletonNav.isPreviewEnabled();
    var hideLoadingOverlay = typeof skeletonNav.hideLoadingOverlay === 'function'
        ? skeletonNav.hideLoadingOverlay
        : null;

    window.addEventListener('load', function () {
        if (isPreviewEnabled) return;
        if (hideLoadingOverlay) {
            setTimeout(function () { hideLoadingOverlay(); }, 800);
        }
    });

    window.addEventListener('pageshow', function (event) {
        if (isPreviewEnabled) return;
        if (event.persisted || body.classList.contains('loading-active')) {
            if (hideLoadingOverlay) hideLoadingOverlay();
        }
    });
});
