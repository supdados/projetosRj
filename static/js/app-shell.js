        document.addEventListener('DOMContentLoaded', function() {
            const baseAppConfig = window.__BASE_APP_CONFIG__ || {};
            const body = document.body;
            const root = document.documentElement;
            const isAuthenticatedPage = body.classList.contains('is-authenticated');
            const loadingOverlay = document.querySelector('.loading-overlay');
            const skeletonContent = document.querySelector('.skeleton-content');
            const skeletonTemplateStore = document.getElementById('skeleton-template-store');
            const hasBootstrap = typeof window.bootstrap !== 'undefined';
            const nonNavigationalToggles = ['dropdown', 'collapse', 'modal', 'offcanvas', 'tab', 'pill'];
            const skeletonTemplates = {};
            const themeToggleButton = document.getElementById('appThemeToggle');
            const themeToggleIcon = document.getElementById('appThemeToggleIcon');
            const themeColorMeta = document.querySelector('meta[name="theme-color"]');
            const themeStorageKey = 'projetosrj.theme';
            const themeColorByMode = {
                light: '#005A92',
                dark: '#273447',
            };
            const darkMediaQuery = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;

            function normalizeTheme(themeName) {
                return themeName === 'dark' ? 'dark' : 'light';
            }

            function readStoredTheme() {
                try {
                    const storedTheme = window.localStorage.getItem(themeStorageKey);
                    return storedTheme === 'light' || storedTheme === 'dark' ? storedTheme : null;
                } catch (error) {
                    return null;
                }
            }

            let storedThemeOverride = readStoredTheme();

            function updateThemeColor(themeName) {
                if (!themeColorMeta) {
                    return;
                }
                themeColorMeta.setAttribute('content', themeColorByMode[themeName] || themeColorByMode.light);
            }

            function updateThemeToggle(themeName) {
                if (!themeToggleButton || !themeToggleIcon) {
                    return;
                }
                const isDarkTheme = themeName === 'dark';
                themeToggleButton.classList.toggle('is-dark', isDarkTheme);
                themeToggleButton.setAttribute('aria-pressed', isDarkTheme ? 'true' : 'false');
                themeToggleButton.setAttribute('title', isDarkTheme ? 'Ativar modo claro' : 'Ativar modo escuro');
                themeToggleButton.setAttribute('aria-label', isDarkTheme ? 'Ativar modo claro' : 'Ativar modo escuro');
                themeToggleIcon.classList.remove('fa-moon', 'fa-sun');
                themeToggleIcon.classList.add(isDarkTheme ? 'fa-moon' : 'fa-sun');
            }

            function applyTheme(themeName, persistChoice) {
                if (!isAuthenticatedPage) {
                    return;
                }
                const normalizedTheme = normalizeTheme(themeName);
                root.setAttribute('data-theme', normalizedTheme);
                updateThemeColor(normalizedTheme);
                updateThemeToggle(normalizedTheme);

                if (!persistChoice) {
                    return;
                }

                try {
                    window.localStorage.setItem(themeStorageKey, normalizedTheme);
                    storedThemeOverride = normalizedTheme;
                } catch (error) {
                    /* noop */
                }
            }

            function resolveInitialTheme() {
                const attrTheme = root.getAttribute('data-theme');
                if (attrTheme === 'light' || attrTheme === 'dark') {
                    return attrTheme;
                }
                if (storedThemeOverride) {
                    return storedThemeOverride;
                }
                return darkMediaQuery && darkMediaQuery.matches ? 'dark' : 'light';
            }

            if (isAuthenticatedPage) {
                applyTheme(resolveInitialTheme(), false);

                if (themeToggleButton) {
                    themeToggleButton.addEventListener('click', function() {
                        const currentTheme = normalizeTheme(root.getAttribute('data-theme'));
                        const nextTheme = currentTheme === 'dark' ? 'light' : 'dark';
                        applyTheme(nextTheme, true);
                    });
                }

                if (darkMediaQuery) {
                    const onSystemThemeChange = function(event) {
                        if (storedThemeOverride) {
                            return;
                        }
                        applyTheme(event.matches ? 'dark' : 'light', false);
                    };

                    if (typeof darkMediaQuery.addEventListener === 'function') {
                        darkMediaQuery.addEventListener('change', onSystemThemeChange);
                    } else if (typeof darkMediaQuery.addListener === 'function') {
                        darkMediaQuery.addListener(onSystemThemeChange);
                    }
                }
            } else {
                updateThemeColor('light');
            }

            body.classList.add('loading-active');

            if (skeletonTemplateStore) {
                skeletonTemplateStore.querySelectorAll('template[data-skeleton-template]').forEach(function(templateEl) {
                    const templateType = templateEl.dataset.skeletonTemplate;
                    if (templateType) {
                        skeletonTemplates[templateType] = templateEl.innerHTML.trim();
                    }
                });
            }

            if (hasBootstrap && bootstrap.Tooltip) {
                document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(function(el) {
                    new bootstrap.Tooltip(el);
                });
            }

            document.querySelectorAll('.app-flash-stack .app-flash-alert').forEach(function(alertEl) {
                const dismissDelay = parseInt(alertEl.dataset.autoDismiss || '2800', 10);
                window.setTimeout(function() {
                    if (!document.body.contains(alertEl)) {
                        return;
                    }
                    if (hasBootstrap && bootstrap.Alert) {
                        bootstrap.Alert.getOrCreateInstance(alertEl).close();
                    } else {
                        alertEl.remove();
                    }
                }, dismissDelay);
            });

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
                const currentPage = document.querySelector('.main-content');
                if (currentPage) {
                    currentPage.classList.remove('page-transition');
                }
            }

            function normalizePath(pathname) {
                if (!pathname) {
                    return '/';
                }
                const normalized = pathname.replace(/\/+$/, '');
                return normalized || '/';
            }

            function resolveSkeletonTypeForUrl(targetUrl) {
                let pathname = '/';
                try {
                    const parsedUrl = new URL(targetUrl, window.location.origin);
                    pathname = normalizePath(parsedUrl.pathname);
                } catch (error) {
                    return 'generic';
                }

                if (pathname === '/dashboard') {
                    return 'dashboard';
                }
                if (pathname === '/projects') {
                    return 'projects';
                }
                if (pathname === '/projetos_pendentes') {
                    return 'pending';
                }
                if (pathname === '/tarefas') {
                    return 'tasks';
                }
                if (pathname === '/tarefas/arquivadas') {
                    return 'tasks';
                }
                if (pathname === '/tarefas/finalizadas') {
                    return 'tasks';
                }
                if (/^\/projeto\/\d+\/tarefas$/.test(pathname)) {
                    return 'project_tasks';
                }
                if (pathname === '/busca') {
                    return 'search';
                }
                if (pathname === '/admin/templates') {
                    return 'templates_list';
                }
                if (pathname === '/admin/templates/new' || /^\/admin\/templates\/\d+\/edit$/.test(pathname)) {
                    return 'templates_form';
                }
                if (/^\/tarefas\/\d+$/.test(pathname)) {
                    return 'task_detail';
                }
                if (/^\/project\/\d+$/.test(pathname)) {
                    return 'project_detail';
                }
                return 'generic';
            }

            function setSkeletonType(type) {
                if (!skeletonContent) {
                    return;
                }
                const targetType = skeletonTemplates[type] ? type : 'generic';
                if (skeletonContent.dataset.skeletonActive === targetType) {
                    return;
                }
                const nextMarkup = skeletonTemplates[targetType];
                if (!nextMarkup) {
                    return;
                }
                skeletonContent.innerHTML = nextMarkup;
                skeletonContent.dataset.skeletonActive = targetType;
            }

            function navigateWithSkeleton(destinationUrl, skipTransition) {
                if (!destinationUrl) {
                    return;
                }
                const currentPage = document.querySelector('.main-content');
                if (currentPage && !skipTransition) {
                    currentPage.classList.add('page-transition');
                }
                setSkeletonType(resolveSkeletonTypeForUrl(destinationUrl));
                showLoadingOverlay();
                window.setTimeout(function() {
                    window.location.href = destinationUrl;
                }, 100);
            }

            const globalSearchWidget = document.querySelector('[data-global-search]');
            if (globalSearchWidget) {
                const searchForm = globalSearchWidget.querySelector('.app-global-search-form');
                const searchInput = globalSearchWidget.querySelector('.app-global-search-input');
                const searchDropdown = globalSearchWidget.querySelector('.app-global-search-dropdown');
                const searchState = globalSearchWidget.querySelector('[data-role="state"]');
                const searchResultsContainer = globalSearchWidget.querySelector('[data-role="results"]');
                const searchFooter = globalSearchWidget.querySelector('[data-role="footer"]');
                const searchApiUrl = globalSearchWidget.dataset.searchUrl;
                const groupConfig = [
                    { key: 'projects', label: 'Projetos', icon: 'fa-folder-open', badgeClass: 'type-project' },
                    { key: 'stages', label: 'Etapas', icon: 'fa-list-check', badgeClass: 'type-stage' },
                    { key: 'tasks', label: 'Tarefas', icon: 'fa-clipboard-list', badgeClass: 'type-task' }
                ];

                let debounceTimer = null;
                let requestController = null;
                let currentResultLinks = [];
                let selectedIndex = -1;

                function escapeHtml(value) {
                    const helper = document.createElement('div');
                    helper.textContent = value == null ? '' : String(value);
                    return helper.innerHTML;
                }

                function openSearchDropdown() {
                    if (!searchDropdown) {
                        return;
                    }
                    searchDropdown.hidden = false;
                    searchInput.setAttribute('aria-expanded', 'true');
                }

                function closeSearchDropdown() {
                    if (!searchDropdown) {
                        return;
                    }
                    searchDropdown.hidden = true;
                    searchInput.setAttribute('aria-expanded', 'false');
                    clearSearchFooter();
                    selectedIndex = -1;
                    currentResultLinks.forEach(function(link) {
                        link.classList.remove('active');
                    });
                }

                function getSearchPageDestination(query) {
                    const searchPageUrl = searchForm.getAttribute('action') || window.location.pathname;
                    const trimmed = (query || '').trim();
                    return trimmed
                        ? `${searchPageUrl}?q=${encodeURIComponent(trimmed)}`
                        : searchPageUrl;
                }

                function clearSearchFooter() {
                    if (!searchFooter) {
                        return;
                    }
                    searchFooter.innerHTML = '';
                    searchFooter.hidden = true;
                }

                function renderSearchFooter(query, hasMoreResults) {
                    if (!searchFooter) {
                        return;
                    }
                    const trimmedQuery = (query || '').trim();
                    if (trimmedQuery.length < 2) {
                        clearSearchFooter();
                        return;
                    }
                    const destinationUrl = getSearchPageDestination(trimmedQuery);
                    const footerLabel = hasMoreResults ? 'Ver tudo' : 'Ir para a página de busca';
                    searchFooter.innerHTML = `
                        <a href="${escapeHtml(destinationUrl)}" class="app-global-search-footer-link" data-search-url="${escapeHtml(destinationUrl)}">
                            <span>${footerLabel}</span>
                            <i class="fas fa-arrow-right"></i>
                        </a>
                    `;
                    searchFooter.hidden = false;
                }

                function renderSearchState(message) {
                    searchState.textContent = message;
                    searchState.style.display = 'block';
                    searchResultsContainer.innerHTML = '';
                    clearSearchFooter();
                    currentResultLinks = [];
                    selectedIndex = -1;
                }

                function updateSelectedLink() {
                    currentResultLinks.forEach(function(link, index) {
                        const isActive = index === selectedIndex;
                        link.classList.toggle('active', isActive);
                        if (isActive) {
                            link.scrollIntoView({ block: 'nearest' });
                        }
                    });
                }

                function moveSelection(step) {
                    if (!currentResultLinks.length) {
                        return;
                    }
                    if (selectedIndex === -1) {
                        selectedIndex = step > 0 ? 0 : currentResultLinks.length - 1;
                    } else {
                        selectedIndex = (selectedIndex + step + currentResultLinks.length) % currentResultLinks.length;
                    }
                    updateSelectedLink();
                }

                function renderSearchResults(payload) {
                    const groupedResults = payload && payload.results ? payload.results : {};
                    const hasMoreByType = payload && payload.meta && payload.meta.has_more ? payload.meta.has_more : {};
                    const hasMoreResults = Boolean(hasMoreByType.any);
                    const currentQuery = payload && payload.query ? payload.query : searchInput.value;
                    let hasAnyResult = false;
                    let html = '';

                    groupConfig.forEach(function(group) {
                        const items = Array.isArray(groupedResults[group.key]) ? groupedResults[group.key] : [];
                        if (!items.length) {
                            return;
                        }
                        hasAnyResult = true;
                        html += `
                            <div class="app-global-search-group">
                                <div class="app-global-search-group-title">
                                    <i class="fas ${group.icon}"></i>
                                    <span>${group.label}</span>
                                    <span class="app-global-search-group-count">${items.length}</span>
                                </div>
                        `;

                        items.forEach(function(item) {
                            const itemUrl = item && item.url ? item.url : '#';
                            const title = item && item.title ? item.title : '';
                            const subtitle = item && item.subtitle ? item.subtitle : '';
                            const meta = item && item.meta ? item.meta : '';
                            const typeLabel = item && item.type_label ? item.type_label : group.label;
                            const matchField = item && item.match_field ? item.match_field : '';
                            const matchLabel = item && item.match_label ? item.match_label : '';
                            const matchExcerpt = item && item.match_excerpt ? item.match_excerpt : '';
                            const shouldRenderCommentMatch = matchField === 'comentarios';
                            const matchBadge = shouldRenderCommentMatch && matchLabel
                                ? `<span class="app-global-search-match-badge">Encontrado em: ${escapeHtml(matchLabel)}</span>`
                                : '';
                            const matchText = shouldRenderCommentMatch && matchExcerpt
                                ? `<div class="app-global-search-match-text">${escapeHtml(matchExcerpt)}</div>`
                                : '';
                            const matchBlock = (matchBadge || matchText)
                                ? `<div class="app-global-search-item-match">${matchBadge}${matchText}</div>`
                                : '';

                            html += `
                                <a href="${escapeHtml(itemUrl)}" class="app-global-search-item" data-search-url="${escapeHtml(itemUrl)}">
                                    <div class="app-global-search-item-main">
                                        <div class="app-global-search-item-head">
                                            <span class="app-global-search-item-type ${group.badgeClass}">${escapeHtml(typeLabel)}</span>
                                            <span class="app-global-search-item-title">${escapeHtml(title)}</span>
                                        </div>
                                        ${subtitle ? `<div class="app-global-search-item-subtitle">${escapeHtml(subtitle)}</div>` : ''}
                                        ${meta ? `<div class="app-global-search-item-meta">${escapeHtml(meta)}</div>` : ''}
                                        ${matchBlock}
                                    </div>
                                    <i class="fas fa-chevron-right app-global-search-item-arrow"></i>
                                </a>
                            `;
                        });

                        html += '</div>';
                    });

                    if (!hasAnyResult) {
                        renderSearchState('Nenhuma referencia encontrada.');
                        renderSearchFooter(currentQuery, false);
                        openSearchDropdown();
                        return;
                    }

                    searchState.style.display = 'none';
                    searchResultsContainer.innerHTML = html;
                    renderSearchFooter(currentQuery, hasMoreResults);
                    currentResultLinks = Array.from(searchResultsContainer.querySelectorAll('.app-global-search-item'));
                    selectedIndex = -1;
                    updateSelectedLink();
                    openSearchDropdown();
                }

                function fetchSearchResults(query) {
                    if (!searchApiUrl) {
                        return;
                    }
                    if (requestController) {
                        requestController.abort();
                    }
                    requestController = new AbortController();
                    const localController = requestController;
                    renderSearchState('Buscando...');
                    openSearchDropdown();

                    fetch(`${searchApiUrl}?q=${encodeURIComponent(query)}&limit=5`, {
                        method: 'GET',
                        headers: { 'Accept': 'application/json' },
                        signal: requestController.signal
                    })
                    .then(function(response) {
                        if (!response.ok) {
                            throw new Error(`Erro HTTP ${response.status}`);
                        }
                        return response.json();
                    })
                    .then(function(payload) {
                        renderSearchResults(payload);
                    })
                    .catch(function(error) {
                        if (error.name === 'AbortError') {
                            return;
                        }
                        renderSearchState('Nao foi possivel carregar os resultados.');
                        openSearchDropdown();
                    })
                    .finally(function() {
                        if (requestController === localController) {
                            requestController = null;
                        }
                    });
                }

                searchInput.addEventListener('input', function() {
                    const query = this.value.trim();
                    clearTimeout(debounceTimer);
                    selectedIndex = -1;

                    if (query.length < 2) {
                        if (requestController) {
                            requestController.abort();
                        }
                        closeSearchDropdown();
                        return;
                    }

                    debounceTimer = setTimeout(function() {
                        fetchSearchResults(query);
                    }, 250);
                });

                searchInput.addEventListener('focus', function() {
                    const query = this.value.trim();
                    if (query.length < 2) {
                        return;
                    }
                    if (currentResultLinks.length || searchState.style.display === 'block') {
                        openSearchDropdown();
                    } else {
                        fetchSearchResults(query);
                    }
                });

                searchInput.addEventListener('keydown', function(event) {
                    if (event.key === 'ArrowDown') {
                        event.preventDefault();
                        if (!searchDropdown.hidden) {
                            moveSelection(1);
                        }
                    } else if (event.key === 'ArrowUp') {
                        event.preventDefault();
                        if (!searchDropdown.hidden) {
                            moveSelection(-1);
                        }
                    } else if (event.key === 'Escape') {
                        if (!searchDropdown.hidden) {
                            event.preventDefault();
                            closeSearchDropdown();
                        }
                    } else if (event.key === 'Enter' && selectedIndex >= 0 && currentResultLinks[selectedIndex]) {
                        event.preventDefault();
                        const url = currentResultLinks[selectedIndex].getAttribute('href');
                        if (url) {
                            navigateWithSkeleton(url);
                        }
                    }
                });

                searchForm.addEventListener('submit', function(event) {
                    const trimmed = searchInput.value.trim();
                    searchInput.value = trimmed;
                    if (selectedIndex >= 0 && currentResultLinks[selectedIndex]) {
                        event.preventDefault();
                        const selectedUrl = currentResultLinks[selectedIndex].getAttribute('href');
                        if (selectedUrl) {
                            navigateWithSkeleton(selectedUrl);
                        }
                        return;
                    }

                    event.preventDefault();
                    const destinationUrl = getSearchPageDestination(trimmed);
                    navigateWithSkeleton(destinationUrl);
                });

                searchResultsContainer.addEventListener('mousemove', function(event) {
                    const hoveredLink = event.target.closest('.app-global-search-item');
                    if (!hoveredLink) {
                        return;
                    }
                    const hoveredIndex = currentResultLinks.indexOf(hoveredLink);
                    if (hoveredIndex === -1 || hoveredIndex === selectedIndex) {
                        return;
                    }
                    selectedIndex = hoveredIndex;
                    updateSelectedLink();
                });

                searchResultsContainer.addEventListener('mousedown', function(event) {
                    const clickedLink = event.target.closest('.app-global-search-item');
                    if (!clickedLink) {
                        return;
                    }
                    event.preventDefault();
                    const clickedUrl = clickedLink.getAttribute('href');
                    if (clickedUrl) {
                        navigateWithSkeleton(clickedUrl);
                    }
                });

                searchDropdown.addEventListener('click', function(event) {
                    const footerLink = event.target.closest('.app-global-search-footer-link');
                    if (!footerLink) {
                        return;
                    }
                    event.preventDefault();
                    const footerUrl = footerLink.getAttribute('href');
                    if (footerUrl) {
                        navigateWithSkeleton(footerUrl);
                    }
                });

                document.addEventListener('click', function(event) {
                    if (!globalSearchWidget.contains(event.target)) {
                        closeSearchDropdown();
                    }
                });
            }

            const notificationsMenu = document.querySelector('.app-notifications-menu');
            if (notificationsMenu) {
                const notificationsTrigger = document.getElementById('appNotificationsDesktop');
                const notificationsBadge = document.getElementById('appNotificationsBadge');
                const notificationsUnreadCounter = document.getElementById('appNotificationsUnreadCount');
                const notificationsList = document.getElementById('appNotificationsList');
                const notificationsState = document.getElementById('appNotificationsState');
                const notificationsApiUrl = baseAppConfig.notificationsApiUrl || '';
                let isLoadingNotifications = false;

                function escapeNotificationHtml(value) {
                    const helper = document.createElement('div');
                    helper.textContent = value == null ? '' : String(value);
                    return helper.innerHTML;
                }

                var notifStatusEntries = [
                    { label: 'Em andamento', css: 'app-notif-status app-notif-status-em-andamento' },
                    { label: 'Programado', css: 'app-notif-status app-notif-status-programado' },
                    { label: 'Validacao', css: 'app-notif-status app-notif-status-validacao' },
                    { label: 'Finalizado', css: 'app-notif-status app-notif-status-finalizado' },
                ];

                function colorizeNotificationSubline(escapedSubline, escapedActorName) {
                    var result = escapedSubline;
                    if (escapedActorName) {
                        var actorIdx = result.indexOf(escapedActorName);
                        if (actorIdx !== -1) {
                            result = result.substring(0, actorIdx)
                                + '<span class="app-notif-actor">' + escapedActorName + '</span>'
                                + result.substring(actorIdx + escapedActorName.length);
                        }
                    }
                    notifStatusEntries.forEach(function(entry) {
                        var escapedLabel = escapeNotificationHtml(entry.label);
                        result = result.split(escapedLabel).join(
                            '<span class="' + entry.css + '">' + escapedLabel + '</span>'
                        );
                    });
                    return result;
                }

                function updateNotificationsBadge(count) {
                    if (!notificationsBadge) {
                        return;
                    }
                    const safeCount = Number.isFinite(count) ? Math.max(0, count) : 0;
                    notificationsBadge.textContent = safeCount > 99 ? '99+' : String(safeCount);
                    notificationsBadge.classList.toggle('is-hidden', safeCount === 0);
                }

                function updateNotificationsCounter(count) {
                    if (!notificationsUnreadCounter) {
                        return;
                    }
                    const safeCount = Number.isFinite(count) ? Math.max(0, count) : 0;
                    notificationsUnreadCounter.textContent = `${safeCount} não lida(s)`;
                }

                function renderNotificationsState(message) {
                    notificationsList.innerHTML = `<div class="app-notifications-state">${escapeNotificationHtml(message)}</div>`;
                }

                function resolveNotificationVisual(eventType) {
                    const safeEventType = (eventType || '').toString().trim().toLowerCase();

                    if (
                        safeEventType.endsWith('_deleted') ||
                        safeEventType === 'task_deleted' ||
                        safeEventType === 'project_delete'
                    ) {
                        return { kind: 'deleted', icon: 'fa-trash-can' };
                    }

                    if (
                        safeEventType === 'task_finalized' ||
                        safeEventType === 'project_finalize' ||
                        safeEventType === 'project_toggle_done'
                    ) {
                        return { kind: 'finalized', icon: 'fa-check-circle' };
                    }

                    if (
                        safeEventType === 'task_assignment' ||
                        safeEventType === 'task_item_assignment'
                    ) {
                        return { kind: 'assignment', icon: 'fa-user-check' };
                    }

                    if (
                        safeEventType.startsWith('task_comment_') ||
                        safeEventType.startsWith('task_item_comment_')
                    ) {
                        return { kind: 'comment', icon: 'fa-comments' };
                    }

                    if (safeEventType.startsWith('project_')) {
                        return { kind: 'project', icon: 'fa-folder-tree' };
                    }

                    if (safeEventType.startsWith('task_')) {
                        return { kind: 'task', icon: 'fa-list-check' };
                    }

                    return { kind: 'update', icon: 'fa-bell' };
                }

                function renderNotificationsItems(items) {
                    if (!Array.isArray(items) || !items.length) {
                        renderNotificationsState('Sem notificações no momento.');
                        return;
                    }

                    const html = items.map(function(item) {
                        const notificationVisual = resolveNotificationVisual(item && item.event_type ? item.event_type : '');
                        const targetUrl = escapeNotificationHtml(item && item.target_url ? item.target_url : '#');
                        const titleRaw = item && item.title ? item.title : 'Atualização';
                        const title = escapeNotificationHtml(titleRaw);
                        const messageRaw = item && item.message ? item.message : '';
                        const createdAt = item && item.created_at ? escapeNotificationHtml(item.created_at) : '';
                        const actorNameRaw = item && item.actor_name ? item.actor_name : '';
                        const sublineRaw = messageRaw || actorNameRaw || '';
                        const subline = colorizeNotificationSubline(
                            escapeNotificationHtml(sublineRaw),
                            actorNameRaw ? escapeNotificationHtml(actorNameRaw) : ''
                        );
                        const isUnread = Boolean(item && item.is_unread);
                        const unreadClass = isUnread ? ' is-unread' : '';
                        const unreadDotClass = isUnread ? '' : ' is-hidden';
                        return `
                            <a
                                href="${targetUrl}"
                                class="app-notification-item${unreadClass}"
                                data-notification-kind="${escapeNotificationHtml(notificationVisual.kind)}"
                                data-notification-url="${targetUrl}"
                            >
                                <span class="app-notification-leading" aria-hidden="true">
                                    <span class="app-notification-unread-dot${unreadDotClass}"></span>
                                    <span class="app-notification-icon-wrap">
                                        <i class="fas ${notificationVisual.icon} app-notification-icon"></i>
                                    </span>
                                </span>
                                <span class="app-notification-main">
                                    <span class="app-notification-row">
                                        <span class="app-notification-title">${title}</span>
                                        <span class="app-notification-time">${createdAt}</span>
                                    </span>
                                    <span class="app-notification-subline">${subline}</span>
                                </span>
                            </a>
                        `;
                    }).join('');
                    notificationsList.innerHTML = html;
                }

                function loadNotifications() {
                    if (isLoadingNotifications) {
                        return;
                    }
                    isLoadingNotifications = true;
                    renderNotificationsState('Carregando notificações...');

                    fetch(notificationsApiUrl, {
                        method: 'POST',
                        headers: {
                            'Accept': 'application/json',
                            'X-Requested-With': 'XMLHttpRequest',
                        },
                    })
                    .then(function(response) {
                        if (!response.ok) {
                            throw new Error(`Erro HTTP ${response.status}`);
                        }
                        return response.json();
                    })
                    .then(function(payload) {
                        const unreadAfter = Number(payload && payload.unread_after);
                        // Mantém o texto "X não lida(s)" estável até recarregar a página.
                        // Apenas o badge do sino zera imediatamente ao abrir o dropdown.
                        updateNotificationsBadge(Number.isFinite(unreadAfter) ? unreadAfter : 0);
                        renderNotificationsItems(payload && payload.items ? payload.items : []);
                    })
                    .catch(function() {
                        renderNotificationsState('Não foi possível carregar as notificações.');
                    })
                    .finally(function() {
                        isLoadingNotifications = false;
                    });
                }

                if (notificationsTrigger) {
                    notificationsTrigger.addEventListener('show.bs.dropdown', loadNotifications);
                }

                notificationsList.addEventListener('mousedown', function(event) {
                    const itemLink = event.target.closest('.app-notification-item[data-notification-url]');
                    if (!itemLink) {
                        return;
                    }
                    event.preventDefault();
                    const targetUrl = itemLink.getAttribute('data-notification-url');
                    if (targetUrl) {
                        navigateWithSkeleton(targetUrl);
                    }
                });
            }

            function shouldInterceptLink(link) {
                const hrefAttr = link.getAttribute('href');
                if (!hrefAttr || hrefAttr === '#' || hrefAttr.startsWith('#')) {
                    return false;
                }

                if (
                    hrefAttr.startsWith('javascript:') ||
                    hrefAttr.startsWith('mailto:') ||
                    hrefAttr.startsWith('tel:')
                ) {
                    return false;
                }

                if (link.getAttribute('target') === '_blank' || link.hasAttribute('download')) {
                    return false;
                }

                const toggleType = (link.getAttribute('data-bs-toggle') || '').toLowerCase();
                if (nonNavigationalToggles.includes(toggleType)) {
                    return false;
                }

                try {
                    const parsedUrl = new URL(link.href, window.location.origin);
                    return parsedUrl.origin === window.location.origin;
                } catch (error) {
                    return false;
                }
            }

            document.querySelectorAll('a[href]').forEach(function(link) {
                if (!shouldInterceptLink(link)) {
                    return;
                }

                link.addEventListener('click', function(event) {
                    if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
                        return;
                    }

                    event.preventDefault();
                    const destinationUrl = this.href;
                    navigateWithSkeleton(destinationUrl);
                });
            });

            window.addEventListener('load', function() {
                setTimeout(() => {
                    hideLoadingOverlay();
                }, 800);
            });

            // Corrige retorno via histórico do navegador (BFCache):
            // garante que a página não fique presa em estado "loading-active".
            window.addEventListener('pageshow', function(event) {
                if (event.persisted || body.classList.contains('loading-active')) {
                    hideLoadingOverlay();
                }
            });

            showLoadingOverlay();
            if (loadingOverlay) {
                loadingOverlay.classList.remove('active');
            }
        });
