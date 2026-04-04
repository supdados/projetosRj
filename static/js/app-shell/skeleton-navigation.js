// === skeleton-navigation.js — Skeleton loading e navegação com transição ===
// Nota: innerHTML usado apenas com templates estáticos pré-renderizados no HTML
// (template store do skeleton), não com conteúdo de usuário.
(function (global) {
    var skeletonNav = global.AppShellSkeleton = {};

    document.addEventListener('DOMContentLoaded', function () {
        var baseAppConfig = global.__BASE_APP_CONFIG__ || {};
        var body = document.body;
        var loadingOverlay = document.querySelector('.loading-overlay');
        var skeletonContent = document.querySelector('.skeleton-content');
        var skeletonTemplateStore = document.getElementById('skeleton-template-store');
        var skeletonPreviewEnabled = Boolean(baseAppConfig.skeletonPreviewEnabled);
        var skeletonPreviewType = baseAppConfig.skeletonPreviewType || null;
        var skeletonTemplates = {};

        skeletonNav.isPreviewEnabled = function () { return skeletonPreviewEnabled; };

        function showLoadingOverlay() {
            if (loadingOverlay) {
                loadingOverlay.classList.remove('active');
            }
            body.classList.remove('page-ready');
            body.classList.add('loading-active');
        }

        function hideLoadingOverlay() {
            if (loadingOverlay) {
                loadingOverlay.classList.remove('active');
            }
            body.classList.add('page-ready');
            body.classList.remove('loading-active');
            var currentPage = document.querySelector('.main-content');
            if (currentPage) {
                currentPage.classList.remove('page-transition');
            }
        }

        function normalizePath(pathname) {
            if (!pathname) return '/';
            var normalized = pathname.replace(/\/+$/, '');
            return normalized || '/';
        }

        function resolveSkeletonTypeForUrl(targetUrl) {
            var pathname = '/';
            try {
                var parsedUrl = new URL(targetUrl, window.location.origin);
                pathname = normalizePath(parsedUrl.pathname);
            } catch (error) {
                return 'generic';
            }

            if (pathname === '/dashboard') return 'dashboard';
            if (
                pathname === '/' ||
                pathname === '/login' ||
                pathname === '/login/govbr' ||
                pathname === '/auth/govbr/callback'
            ) return 'login';
            if (pathname === '/projects') return 'projects';
            if (pathname === '/projetos_pendentes') return 'pending';
            if (pathname === '/tarefas') return 'tasks';
            if (pathname === '/tarefas/arquivadas') return 'tasks';
            if (pathname === '/tarefas/finalizadas') return 'tasks';
            if (/^\/projeto\/\d+\/tarefas$/.test(pathname)) return 'project_tasks';
            if (pathname === '/busca') return 'search';
            if (pathname === '/admin/templates') return 'templates_list';
            if (pathname === '/admin/templates/new' || /^\/admin\/templates\/\d+\/edit$/.test(pathname)) return 'templates_form';
            if (/^\/tarefas\/\d+$/.test(pathname)) return 'task_detail';
            if (/^\/project\/\d+$/.test(pathname)) return 'project_detail';
            return 'generic';
        }

        function setSkeletonType(type) {
            if (!skeletonContent) return;
            var targetType = skeletonTemplates[type] ? type : 'generic';
            if (skeletonContent.dataset.skeletonActive === targetType) return;
            var nextMarkup = skeletonTemplates[targetType];
            if (!nextMarkup) return;
            // Conteúdo vem de <template> estáticos do HTML, não de input de usuário
            skeletonContent.insertAdjacentHTML('afterbegin', '');
            skeletonContent.textContent = '';
            skeletonContent.insertAdjacentHTML('afterbegin', nextMarkup);
            skeletonContent.dataset.skeletonActive = targetType;
        }

        function navigateWithSkeleton(destinationUrl, skipTransition) {
            if (!destinationUrl) return;
            var currentPage = document.querySelector('.main-content');
            if (currentPage && !skipTransition) {
                currentPage.classList.add('page-transition');
            }
            setSkeletonType(resolveSkeletonTypeForUrl(destinationUrl));
            showLoadingOverlay();
            window.setTimeout(function () {
                window.location.href = destinationUrl;
            }, 100);
        }

        // Parsear template store
        if (skeletonTemplateStore) {
            skeletonTemplateStore.querySelectorAll('template[data-skeleton-template]').forEach(function (templateEl) {
                var templateType = templateEl.dataset.skeletonTemplate;
                if (templateType) {
                    skeletonTemplates[templateType] = templateEl.innerHTML.trim();
                }
            });
        }

        if (skeletonPreviewEnabled && skeletonPreviewType) {
            setSkeletonType(skeletonPreviewType);
        }

        // Expor funções para outros módulos
        skeletonNav.navigateWithSkeleton = navigateWithSkeleton;
        skeletonNav.showLoadingOverlay = showLoadingOverlay;
        skeletonNav.hideLoadingOverlay = hideLoadingOverlay;
    });
})(window);
