// === global-search.js — Widget de busca global com dropdown ===
// Nota: insertAdjacentHTML usado com conteúdo sanitizado via escapeHtml()
(function (global) {
    document.addEventListener('DOMContentLoaded', function () {
        var globalSearchWidget = document.querySelector('[data-global-search]');
        if (!globalSearchWidget) return;

        var navigateWithSkeleton = global.AppShellSkeleton && global.AppShellSkeleton.navigateWithSkeleton;
        var escapeHtml = global.escapeHtml;

        var searchForm = globalSearchWidget.querySelector('.app-global-search-form');
        var searchInput = globalSearchWidget.querySelector('.app-global-search-input');
        var searchDropdown = globalSearchWidget.querySelector('.app-global-search-dropdown');
        var searchState = globalSearchWidget.querySelector('[data-role="state"]');
        var searchResultsContainer = globalSearchWidget.querySelector('[data-role="results"]');
        var searchFooter = globalSearchWidget.querySelector('[data-role="footer"]');
        var searchApiUrl = globalSearchWidget.dataset.searchUrl;
        var groupConfig = [
            { key: 'projects', label: 'Projetos', icon: 'fa-folder-open', badgeClass: 'type-project' },
            { key: 'stages', label: 'Etapas', icon: 'fa-list-check', badgeClass: 'type-stage' },
            { key: 'tasks', label: 'Tarefas', icon: 'fa-clipboard-list', badgeClass: 'type-task' },
            { key: 'events', label: 'Eventos', icon: 'fa-calendar-alt', badgeClass: 'type-event' },
        ];

        var debounceTimer = null;
        var requestController = null;
        var currentResultLinks = [];
        var selectedIndex = -1;

        function openSearchDropdown() {
            if (!searchDropdown) return;
            searchDropdown.hidden = false;
            searchInput.setAttribute('aria-expanded', 'true');
        }

        function closeSearchDropdown() {
            if (!searchDropdown) return;
            searchDropdown.hidden = true;
            searchInput.setAttribute('aria-expanded', 'false');
            clearSearchFooter();
            selectedIndex = -1;
            currentResultLinks.forEach(function (link) {
                link.classList.remove('active');
            });
        }

        function getSearchPageDestination(query) {
            var searchPageUrl = searchForm.getAttribute('action') || window.location.pathname;
            var trimmed = (query || '').trim();
            if (!trimmed) return searchPageUrl;
            var area = (global.__APP_SELECTED_AREA__ || '').trim();
            var areaParam = area ? '&area=' + encodeURIComponent(area) : '';
            return searchPageUrl + '?q=' + encodeURIComponent(trimmed) + areaParam;
        }

        function clearSearchFooter() {
            if (!searchFooter) return;
            searchFooter.textContent = '';
            searchFooter.hidden = true;
        }

        function renderSearchFooter(query, hasMoreResults) {
            if (!searchFooter) return;
            var trimmedQuery = (query || '').trim();
            if (trimmedQuery.length < 2) {
                clearSearchFooter();
                return;
            }
            var destinationUrl = getSearchPageDestination(trimmedQuery);
            var footerLabel = hasMoreResults ? 'Ver tudo' : 'Ir para a página de busca';
            searchFooter.textContent = '';
            searchFooter.insertAdjacentHTML('afterbegin',
                '<a href="' + escapeHtml(destinationUrl) + '" class="app-global-search-footer-link" data-search-url="' + escapeHtml(destinationUrl) + '">' +
                    '<span>' + footerLabel + '</span>' +
                    '<i class="fas fa-arrow-right"></i>' +
                '</a>'
            );
            searchFooter.hidden = false;
        }

        function renderSearchState(message) {
            searchState.textContent = message;
            searchState.style.display = 'block';
            searchResultsContainer.textContent = '';
            clearSearchFooter();
            currentResultLinks = [];
            selectedIndex = -1;
        }

        function updateSelectedLink() {
            currentResultLinks.forEach(function (link, index) {
                var isActive = index === selectedIndex;
                link.classList.toggle('active', isActive);
                if (isActive) {
                    link.scrollIntoView({ block: 'nearest' });
                }
            });
        }

        function moveSelection(step) {
            if (!currentResultLinks.length) return;
            if (selectedIndex === -1) {
                selectedIndex = step > 0 ? 0 : currentResultLinks.length - 1;
            } else {
                selectedIndex = (selectedIndex + step + currentResultLinks.length) % currentResultLinks.length;
            }
            updateSelectedLink();
        }

        function renderSearchResults(payload) {
            var groupedResults = payload && payload.results ? payload.results : {};
            var hasMoreByType = payload && payload.meta && payload.meta.has_more ? payload.meta.has_more : {};
            var hasMoreResults = Boolean(hasMoreByType.any);
            var currentQuery = payload && payload.query ? payload.query : searchInput.value;
            var hasAnyResult = false;
            var html = '';

            groupConfig.forEach(function (group) {
                var items = Array.isArray(groupedResults[group.key]) ? groupedResults[group.key] : [];
                if (!items.length) return;
                hasAnyResult = true;
                html += '<div class="app-global-search-group">' +
                    '<div class="app-global-search-group-title">' +
                        '<i class="fas ' + group.icon + '"></i>' +
                        '<span>' + group.label + '</span>' +
                        '<span class="app-global-search-group-count">' + items.length + '</span>' +
                    '</div>';

                items.forEach(function (item) {
                    var itemUrl = item && item.url ? item.url : '#';
                    var title = item && item.title ? item.title : '';
                    var displayTitle = item && item.display_title ? item.display_title : title;
                    var subtitle = item && item.subtitle ? item.subtitle : '';
                    var meta = item && item.meta ? item.meta : '';
                    var typeLabel = item && item.type_label ? item.type_label : group.label;
                    var matchField = item && item.match_field ? item.match_field : '';
                    var matchLabel = item && item.match_label ? item.match_label : '';
                    var matchExcerpt = item && item.match_excerpt ? item.match_excerpt : '';
                    var shouldRenderCommentMatch = matchField === 'comentarios';
                    var matchBadge = shouldRenderCommentMatch && matchLabel
                        ? '<span class="app-global-search-match-badge">Encontrado em: ' + escapeHtml(matchLabel) + '</span>'
                        : '';
                    var matchText = shouldRenderCommentMatch && matchExcerpt
                        ? '<div class="app-global-search-match-text">' + escapeHtml(matchExcerpt) + '</div>'
                        : '';
                    var matchBlock = (matchBadge || matchText)
                        ? '<div class="app-global-search-item-match">' + matchBadge + matchText + '</div>'
                        : '';

                    html +=
                        '<a href="' + escapeHtml(itemUrl) + '" class="app-global-search-item" data-search-url="' + escapeHtml(itemUrl) + '">' +
                            '<div class="app-global-search-item-main">' +
                                '<div class="app-global-search-item-head">' +
                                    '<span class="app-global-search-item-type ' + group.badgeClass + '">' + escapeHtml(typeLabel) + '</span>' +
                                    '<span class="app-global-search-item-title">' + escapeHtml(displayTitle) + '</span>' +
                                '</div>' +
                                (subtitle ? '<div class="app-global-search-item-subtitle">' + escapeHtml(subtitle) + '</div>' : '') +
                                (meta ? '<div class="app-global-search-item-meta">' + escapeHtml(meta) + '</div>' : '') +
                                matchBlock +
                            '</div>' +
                            '<i class="fas fa-chevron-right app-global-search-item-arrow"></i>' +
                        '</a>';
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
            searchResultsContainer.textContent = '';
            searchResultsContainer.insertAdjacentHTML('afterbegin', html);
            renderSearchFooter(currentQuery, hasMoreResults);
            currentResultLinks = Array.from(searchResultsContainer.querySelectorAll('.app-global-search-item'));
            selectedIndex = -1;
            updateSelectedLink();
            openSearchDropdown();
        }

        function fetchSearchResults(query) {
            if (!searchApiUrl) return;
            if (requestController) {
                requestController.abort();
            }
            requestController = new AbortController();
            var localController = requestController;
            renderSearchState('Buscando...');
            openSearchDropdown();

            var _searchArea = (global.__APP_SELECTED_AREA__ || '').trim();
            var _areaParam = _searchArea ? '&area=' + encodeURIComponent(_searchArea) : '';
            fetch(searchApiUrl + '?q=' + encodeURIComponent(query) + '&limit=5' + _areaParam, {
                method: 'GET',
                headers: { 'Accept': 'application/json' },
                signal: requestController.signal,
            })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error('Erro HTTP ' + response.status);
                }
                return response.json();
            })
            .then(function (payload) {
                renderSearchResults(payload);
            })
            .catch(function (error) {
                if (error.name === 'AbortError') return;
                renderSearchState('Nao foi possivel carregar os resultados.');
                openSearchDropdown();
            })
            .finally(function () {
                if (requestController === localController) {
                    requestController = null;
                }
            });
        }

        searchInput.addEventListener('input', function () {
            var query = this.value.trim();
            clearTimeout(debounceTimer);
            selectedIndex = -1;

            if (query.length < 2) {
                if (requestController) {
                    requestController.abort();
                }
                closeSearchDropdown();
                return;
            }

            debounceTimer = setTimeout(function () {
                fetchSearchResults(query);
            }, 250);
        });

        searchInput.addEventListener('focus', function () {
            var query = this.value.trim();
            if (query.length < 2) return;
            if (currentResultLinks.length || searchState.style.display === 'block') {
                openSearchDropdown();
            } else {
                fetchSearchResults(query);
            }
        });

        searchInput.addEventListener('keydown', function (event) {
            if (event.key === 'ArrowDown') {
                event.preventDefault();
                if (!searchDropdown.hidden) moveSelection(1);
            } else if (event.key === 'ArrowUp') {
                event.preventDefault();
                if (!searchDropdown.hidden) moveSelection(-1);
            } else if (event.key === 'Escape') {
                if (!searchDropdown.hidden) {
                    event.preventDefault();
                    closeSearchDropdown();
                }
            } else if (event.key === 'Enter' && selectedIndex >= 0 && currentResultLinks[selectedIndex]) {
                event.preventDefault();
                var url = currentResultLinks[selectedIndex].getAttribute('href');
                if (url && navigateWithSkeleton) {
                    navigateWithSkeleton(url);
                }
            }
        });

        searchForm.addEventListener('submit', function (event) {
            var trimmed = searchInput.value.trim();
            searchInput.value = trimmed;
            if (selectedIndex >= 0 && currentResultLinks[selectedIndex]) {
                event.preventDefault();
                var selectedUrl = currentResultLinks[selectedIndex].getAttribute('href');
                if (selectedUrl && navigateWithSkeleton) {
                    navigateWithSkeleton(selectedUrl);
                }
                return;
            }

            event.preventDefault();
            var destinationUrl = getSearchPageDestination(trimmed);
            if (navigateWithSkeleton) {
                navigateWithSkeleton(destinationUrl);
            }
        });

        searchResultsContainer.addEventListener('mousemove', function (event) {
            var hoveredLink = event.target.closest('.app-global-search-item');
            if (!hoveredLink) return;
            var hoveredIndex = currentResultLinks.indexOf(hoveredLink);
            if (hoveredIndex === -1 || hoveredIndex === selectedIndex) return;
            selectedIndex = hoveredIndex;
            updateSelectedLink();
        });

        searchResultsContainer.addEventListener('mousedown', function (event) {
            var clickedLink = event.target.closest('.app-global-search-item');
            if (!clickedLink) return;
            event.preventDefault();
            var clickedUrl = clickedLink.getAttribute('href');
            if (clickedUrl && navigateWithSkeleton) {
                navigateWithSkeleton(clickedUrl);
            }
        });

        searchDropdown.addEventListener('click', function (event) {
            var footerLink = event.target.closest('.app-global-search-footer-link');
            if (!footerLink) return;
            event.preventDefault();
            var footerUrl = footerLink.getAttribute('href');
            if (footerUrl && navigateWithSkeleton) {
                navigateWithSkeleton(footerUrl);
            }
        });

        document.addEventListener('click', function (event) {
            if (!globalSearchWidget.contains(event.target)) {
                closeSearchDropdown();
            }
        });
    });
})(window);
