    // --- Responsável (picker multi-seleção) ---
    var responsavelAssignableUsersCache = {};

    function escapeResponsavelHtml(text) {
        var div = document.createElement('div');
        div.textContent = text == null ? '' : String(text);
        return div.innerHTML;
    }

    function normalizeResponsavelName(name) {
        return (name || '').trim().replace(/\s+/g, ' ');
    }

    function splitResponsavelNames(rawValue) {
        var raw = (rawValue || '').replace(/\r/g, '\n');
        var seen = {};
        var names = [];
        raw.split(/[,\n;]+/).forEach(function (part) {
            var normalized = normalizeResponsavelName((part || '').replace(/^@+/, ''));
            if (!normalized) return;
            var key = normalized.toLowerCase();
            if (seen[key]) return;
            seen[key] = true;
            names.push(normalized);
        });
        return names;
    }

    function formatResponsavelLabel(selectedNames, placeholderText) {
        var names = Array.isArray(selectedNames) ? selectedNames : [];
        if (!names.length) {
            return '<em class="responsavel-placeholder">' + escapeResponsavelHtml(placeholderText || 'Responsável') + '</em>';
        }

        var visibleCount = 2;
        var parts = [];
        for (var i = 0; i < names.length && i < visibleCount; i++) {
            parts.push(
                '<span class="responsavel-picker-chip responsavel-picker-chip-' + (i % 5) + '">' +
                escapeResponsavelHtml(names[i]) +
                '</span>'
            );
        }
        if (names.length > visibleCount) {
            parts.push('<span class="responsavel-picker-more">+' + (names.length - visibleCount) + '</span>');
        }
        return parts.join('');
    }

    function renderResponsavelPickerTrigger(triggerEl, selectedNames, placeholderText) {
        if (!triggerEl) return;
        var contentEl = triggerEl.querySelector('.responsavel-picker-trigger-content');
        if (!contentEl) return;
        contentEl.innerHTML = formatResponsavelLabel(selectedNames, placeholderText || 'Responsável');
        triggerEl.setAttribute('data-selected-count', String((selectedNames || []).length || 0));
    }

    function fetchAssignableUsers(taskId, sugestoesUrl) {
        if (!taskId || !sugestoesUrl) return Promise.resolve([]);
        var cacheKey = String(taskId) + '::' + String(sugestoesUrl);
        if (responsavelAssignableUsersCache[cacheKey]) {
            return responsavelAssignableUsersCache[cacheKey];
        }
        responsavelAssignableUsersCache[cacheKey] = fetch(sugestoesUrl, { headers: { 'Accept': 'application/json' } })
            .then(function (response) {
                return response.json().catch(function () { return {}; }).then(function (data) {
                    if (!response.ok) {
                        throw new Error((data && data.message) || 'Erro ao carregar responsáveis.');
                    }
                    var users = Array.isArray(data.users) ? data.users : [];
                    return users
                        .map(function (u) {
                            return {
                                id: u.id,
                                name: normalizeResponsavelName(u.name || ''),
                            };
                        })
                        .filter(function (u) { return !!u.name; })
                        .sort(function (a, b) {
                            return a.name.localeCompare(b.name, 'pt-BR', { sensitivity: 'base' });
                        });
                });
            })
            .catch(function (error) {
                delete responsavelAssignableUsersCache[cacheKey];
                throw error;
            });
        return responsavelAssignableUsersCache[cacheKey];
    }

    var responsavelPickerManager = (function () {
        var root = document.createElement('div');
        root.className = 'responsavel-picker-popover';
        root.setAttribute('hidden', '');
        root.innerHTML =
            '<div class="responsavel-picker-head">' +
            '<input type="text" class="responsavel-picker-search" placeholder="Buscar usuário..." autocomplete="off">' +
            '</div>' +
            '<div class="responsavel-picker-list" role="listbox" aria-multiselectable="true"></div>' +
            '<div class="responsavel-picker-status" hidden></div>' +
            '<div class="responsavel-picker-footer">' +
            '<button type="button" class="responsavel-picker-btn" data-action="cancel">Cancelar</button>' +
            '<button type="button" class="responsavel-picker-btn" data-action="clear">Limpar</button>' +
            '<button type="button" class="responsavel-picker-btn responsavel-picker-btn-primary" data-action="apply">Aplicar</button>' +
            '</div>';
        document.body.appendChild(root);

        var searchInput = root.querySelector('.responsavel-picker-search');
        var listEl = root.querySelector('.responsavel-picker-list');
        var statusEl = root.querySelector('.responsavel-picker-status');
        var btnCancel = root.querySelector('[data-action="cancel"]');
        var btnClear = root.querySelector('[data-action="clear"]');
        var btnApply = root.querySelector('[data-action="apply"]');

        var state = null;
        var openToken = 0;

        function cloneKeySet(keySet) {
            var clone = {};
            Object.keys(keySet || {}).forEach(function (key) {
                clone[key] = true;
            });
            return clone;
        }

        function keySetsEqual(a, b) {
            var keysA = Object.keys(a || {});
            var keysB = Object.keys(b || {});
            if (keysA.length !== keysB.length) return false;
            for (var i = 0; i < keysA.length; i++) {
                if (!b[keysA[i]]) return false;
            }
            return true;
        }

        function currentSelectedNames() {
            if (!state) return [];
            var names = [];
            state.users.forEach(function (u) {
                if (state.draftKeys[u.key]) names.push(u.name);
            });
            return names;
        }

        function setLoading(isLoading, message, isError) {
            root.classList.toggle('is-loading', !!isLoading);
            if (message) {
                statusEl.textContent = message;
                statusEl.removeAttribute('hidden');
                statusEl.classList.toggle('is-error', !!isError);
            } else {
                statusEl.textContent = '';
                statusEl.setAttribute('hidden', '');
                statusEl.classList.remove('is-error');
            }
            if (isLoading) {
                listEl.innerHTML = '';
            }
        }

        function setApplying(isApplying) {
            root.classList.toggle('is-applying', !!isApplying);
            [searchInput, btnCancel, btnClear, btnApply].forEach(function (el) {
                if (!el) return;
                el.disabled = !!isApplying;
            });
            listEl.querySelectorAll('input[type="checkbox"]').forEach(function (chk) {
                chk.disabled = !!isApplying;
            });
        }

        function positionPopover() {
            if (!state || !state.anchorEl || !document.body.contains(state.anchorEl)) return;
            var rect = state.anchorEl.getBoundingClientRect();
            var viewportWidth = window.innerWidth || document.documentElement.clientWidth || 1200;
            var viewportHeight = window.innerHeight || document.documentElement.clientHeight || 900;
            var width = Math.min(Math.max(rect.width, 280), Math.max(280, viewportWidth - 24));
            root.style.width = width + 'px';
            root.style.minWidth = '280px';
            root.style.maxWidth = '460px';
            var left = Math.max(12, Math.min(rect.left, viewportWidth - width - 12));
            root.style.left = left + 'px';

            var defaultTop = rect.bottom + 8;
            var popoverHeight = root.offsetHeight || 320;
            var top = defaultTop;
            if (defaultTop + popoverHeight > viewportHeight - 12 && rect.top - popoverHeight - 8 >= 12) {
                top = rect.top - popoverHeight - 8;
            }
            root.style.top = Math.max(12, top) + 'px';
        }

        function close(committed) {
            if (!state) return;
            var previous = state;
            state = null;
            root.setAttribute('hidden', '');
            root.classList.remove('is-loading', 'is-applying');
            searchInput.value = '';
            listEl.innerHTML = '';
            statusEl.textContent = '';
            statusEl.setAttribute('hidden', '');
            statusEl.classList.remove('is-error');
            if (previous.anchorEl) {
                previous.anchorEl.classList.remove('is-open');
                previous.anchorEl.setAttribute('aria-expanded', 'false');
            }
            if (!committed && typeof previous.onCancel === 'function') {
                previous.onCancel();
            }
        }

        function renderList() {
            if (!state) return;
            var query = (searchInput.value || '').trim().toLowerCase();
            var filteredUsers = state.users.filter(function (u) {
                return !query || u.name.toLowerCase().indexOf(query) !== -1;
            });

            listEl.innerHTML = '';
            if (!filteredUsers.length) {
                setLoading(false, 'Nenhum usuário encontrado.', false);
                return;
            }

            setLoading(false, '', false);
            filteredUsers.forEach(function (user) {
                var option = document.createElement('label');
                option.className = 'responsavel-picker-option';
                var checkbox = document.createElement('input');
                checkbox.type = 'checkbox';
                checkbox.className = 'responsavel-picker-option-checkbox';
                checkbox.checked = !!state.draftKeys[user.key];
                checkbox.dataset.userKey = user.key;
                var nameEl = document.createElement('span');
                nameEl.className = 'responsavel-picker-option-name';
                nameEl.textContent = user.name;
                option.appendChild(checkbox);
                option.appendChild(nameEl);
                if (checkbox.checked) option.classList.add('selected');
                checkbox.addEventListener('change', function () {
                    if (!state) return;
                    if (checkbox.checked) state.draftKeys[user.key] = true;
                    else delete state.draftKeys[user.key];
                    state.dirty = !keySetsEqual(state.initialKeys, state.draftKeys);
                    renderList();
                });
                listEl.appendChild(option);
            });
        }

        function open(options) {
            if (!options || !options.anchorEl) return;
            close(false);
            openToken += 1;
            var token = openToken;

            state = {
                anchorEl: options.anchorEl,
                onApply: options.onApply,
                onCancel: options.onCancel,
                users: [],
                userByKey: {},
                initialKeys: {},
                draftKeys: {},
                dirty: false,
            };

            root.removeAttribute('hidden');
            state.anchorEl.classList.add('is-open');
            state.anchorEl.setAttribute('aria-expanded', 'true');
            setLoading(true, 'Carregando usuários...', false);
            positionPopover();

            fetchAssignableUsers(options.taskId, options.sugestoesUrl)
                .then(function (users) {
                    if (!state || token !== openToken) return;

                    state.users = users.map(function (u) {
                        return {
                            id: u.id,
                            name: u.name,
                            key: u.name.toLowerCase(),
                        };
                    });
                    state.userByKey = {};
                    state.users.forEach(function (u) {
                        state.userByKey[u.key] = u.name;
                    });

                    var initialNames = splitResponsavelNames(options.initialRawValue || '');
                    initialNames.forEach(function (name) {
                        var key = name.toLowerCase();
                        if (state.userByKey[key]) state.initialKeys[key] = true;
                    });
                    state.draftKeys = cloneKeySet(state.initialKeys);
                    state.dirty = false;

                    searchInput.value = '';
                    renderList();
                    setApplying(false);
                    positionPopover();
                    searchInput.focus();
                })
                .catch(function (error) {
                    if (!state || token !== openToken) return;
                    setLoading(false, (error && error.message) || 'Erro ao carregar usuários.', true);
                    setApplying(false);
                });
        }

        function apply() {
            if (!state || root.classList.contains('is-loading') || root.classList.contains('is-applying')) return;
            var payload = {
                names: currentSelectedNames(),
                value: currentSelectedNames().join(', '),
                dirty: !keySetsEqual(state.initialKeys, state.draftKeys),
            };
            var result = true;
            if (typeof state.onApply === 'function') {
                try {
                    result = state.onApply(payload);
                } catch (error) {
                    alert((error && error.message) || 'Erro ao salvar.');
                    close(false);
                    return;
                }
            }

            if (result && typeof result.then === 'function') {
                setApplying(true);
                result.then(function (accepted) {
                    setApplying(false);
                    if (accepted === false) return;
                    close(true);
                }).catch(function (error) {
                    setApplying(false);
                    alert((error && error.message) || 'Erro ao salvar.');
                    close(false);
                });
                return;
            }
            if (result === false) return;
            close(true);
        }

        btnCancel.addEventListener('click', function () {
            close(false);
        });
        btnClear.addEventListener('click', function () {
            if (!state || root.classList.contains('is-loading') || root.classList.contains('is-applying')) return;
            state.draftKeys = {};
            state.dirty = !keySetsEqual(state.initialKeys, state.draftKeys);
            renderList();
        });
        btnApply.addEventListener('click', apply);

        searchInput.addEventListener('input', function () {
            if (!state || root.classList.contains('is-loading')) return;
            renderList();
            positionPopover();
        });
        searchInput.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') {
                e.preventDefault();
                close(false);
            }
            if (e.key === 'Enter') {
                e.preventDefault();
                apply();
            }
        });

        document.addEventListener('mousedown', function (e) {
            if (!state) return;
            if (root.classList.contains('is-applying')) return;
            if (root.contains(e.target)) return;
            if (state.anchorEl && state.anchorEl.contains(e.target)) return;
            close(false);
        });
        document.addEventListener('keydown', function (e) {
            if (!state) return;
            if (root.classList.contains('is-applying')) return;
            if (e.key === 'Escape') {
                e.preventDefault();
                close(false);
            }
        });
        window.addEventListener('resize', function () {
            if (!state) return;
            positionPopover();
        });
        window.addEventListener('scroll', function () {
            if (!state) return;
            positionPopover();
        }, true);

        return {
            open: open,
            close: close,
            closeIfAnchor: function (anchorEl) {
                if (!state || !anchorEl) return;
                if (state.anchorEl === anchorEl) close(false);
            },
            isEventInsidePopover: function (targetEl) {
                return !!(targetEl && root.contains(targetEl));
            },
        };
    })();

