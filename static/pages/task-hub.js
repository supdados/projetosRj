    // --- Editar tarefa (título e projeto) no header ---
    (function () {
        var header = document.getElementById('taskHeaderRefined');
        var viewBlock = document.getElementById('taskHeaderView');
        var editBlock = document.getElementById('taskHeaderEdit');
        var btnEdit = document.getElementById('btnEditTaskHeader');
        var inputTitulo = document.getElementById('taskEditTitulo');
        var inputProject = document.getElementById('taskEditProjectInput');
        var hiddenProjectId = document.getElementById('taskEditProjectId');
        var dropdown = document.getElementById('taskEditProjectDropdown');

        if (!header || !viewBlock || !editBlock || !btnEdit || !inputTitulo || !inputProject || !hiddenProjectId || !dropdown) return;

        var editUrl = header.getAttribute('data-edit-url');
        if (!editUrl) return;

        var options = dropdown.querySelectorAll('.project-search-option');
        var chipWrap = document.getElementById('taskEditProjectChipWrap');
        var projectWrap = chipWrap && chipWrap.closest('.task-edit-project-wrap');
        var editInited = false;
        var isEditing = false;
        var isSaving = false;
        var currentSavePromise = null;
        var lastSnapshot = null;
        var hideProjectDropdown = function () {};

        function escapeHtml(s) {
            var div = document.createElement('div');
            div.textContent = s;
            return div.innerHTML;
        }

        function normalizeProjectId(value) {
            return String(value || '').trim();
        }

        function getViewSnapshot() {
            var titleEl = viewBlock.querySelector('.task-title-refined');
            return {
                titulo: ((titleEl && titleEl.textContent) || '').trim(),
                projectId: normalizeProjectId(header.getAttribute('data-project-id')),
            };
        }

        function getEditSnapshot() {
            return {
                titulo: (inputTitulo.value || '').trim(),
                projectId: normalizeProjectId(hiddenProjectId.value),
            };
        }

        function snapshotsEqual(a, b) {
            if (!a || !b) return false;
            return a.titulo === b.titulo && normalizeProjectId(a.projectId) === normalizeProjectId(b.projectId);
        }

        function setSavingState(active) {
            isSaving = !!active;
            btnEdit.disabled = isSaving;
            inputTitulo.disabled = isSaving;
            inputProject.disabled = isSaving;
            hiddenProjectId.disabled = isSaving;
            editBlock.classList.toggle('is-saving', isSaving);
        }

        function renderProjectChip(label) {
            if (!chipWrap || !projectWrap) return;
            chipWrap.innerHTML = '';
            if (!label || label === 'Sem projeto') {
                projectWrap.classList.remove('has-chip');
                inputProject.style.display = '';
                inputProject.value = '';
                hiddenProjectId.value = '';
                return;
            }
            var chip = document.createElement('span');
            chip.className = 'task-edit-project-chip';
            chip.innerHTML = '<span>' + escapeHtml(label || '') + '</span>';
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'task-edit-project-chip-remove';
            btn.setAttribute('aria-label', 'Remover projeto');
            btn.innerHTML = '&times;';
            btn.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopPropagation();
                renderProjectChip(null);
                inputProject.focus();
            });
            chip.appendChild(btn);
            chipWrap.appendChild(chip);
            projectWrap.classList.add('has-chip');
            inputProject.style.display = 'none';
            inputProject.value = '';
        }

        function initProjectSearchEdit() {
            if (editInited) return;
            editInited = true;

            function filterOptions() {
                var q = (inputProject.value || '').trim().toLowerCase();
                options.forEach(function (opt) {
                    var label = (opt.getAttribute('data-label') || opt.textContent || '').toLowerCase();
                    opt.classList.toggle('hidden-by-filter', q && label.indexOf(q) === -1);
                });
            }

            function showDrop() {
                filterOptions();
                dropdown.removeAttribute('hidden');
                inputProject.setAttribute('aria-expanded', 'true');
            }

            function hideDrop() {
                dropdown.setAttribute('hidden', '');
                inputProject.setAttribute('aria-expanded', 'false');
            }

            function selectOpt(opt) {
                var val = opt.getAttribute('data-value') || '';
                var label = opt.getAttribute('data-label') || opt.textContent || '';
                hiddenProjectId.value = val;
                hideDrop();
                if (val === '') {
                    renderProjectChip(null);
                } else {
                    renderProjectChip(label);
                }
            }

            inputProject.addEventListener('focus', showDrop);
            inputProject.addEventListener('input', filterOptions);
            options.forEach(function (opt) {
                opt.addEventListener('click', function () { selectOpt(opt); });
            });
            document.addEventListener('click', function (e) {
                if (!header.contains(e.target)) hideDrop();
            });
            inputProject.addEventListener('blur', function () {
                setTimeout(function () {
                    if (!dropdown.contains(document.activeElement) && document.activeElement !== inputProject) hideDrop();
                }, 150);
            });

            hideProjectDropdown = hideDrop;
        }

        function showEdit() {
            if (isSaving) return;
            viewBlock.style.display = 'none';
            editBlock.removeAttribute('hidden');
            isEditing = true;
            lastSnapshot = getViewSnapshot();
            inputTitulo.value = lastSnapshot.titulo;
            hiddenProjectId.value = lastSnapshot.projectId;
            var projectLabel = header.getAttribute('data-project-label') || '';
            if (projectLabel && projectLabel !== 'Sem projeto' && hiddenProjectId.value) {
                renderProjectChip(projectLabel);
            } else {
                renderProjectChip(null);
            }
            initProjectSearchEdit();
            setTimeout(function () { inputTitulo.focus(); }, 50);
        }

        function showView() {
            editBlock.setAttribute('hidden', '');
            viewBlock.style.display = '';
            isEditing = false;
            if (typeof hideProjectDropdown === 'function') hideProjectDropdown();
        }

        function updateView(titulo, projectId, projectTitulo) {
            var h1 = viewBlock.querySelector('.task-title-refined');
            if (h1) h1.textContent = titulo;
            var breadcrumbCurrent = document.querySelector('.task-breadcrumb-current');
            if (breadcrumbCurrent) breadcrumbCurrent.textContent = titulo;
            header.setAttribute('data-project-label', projectTitulo || 'Sem projeto');
            header.setAttribute('data-project-id', projectId || '');
            var badgeContainer = viewBlock.querySelector('.task-project-badge-refined');
            if (!badgeContainer) return;
            var isLink = projectId && projectTitulo;
            var projectDetailUrl = '{{ url_for("main.project_detail", project_id=0) }}'.replace('/0', '/' + (projectId || ''));
            if (isLink) {
                var link = document.createElement('a');
                link.href = projectDetailUrl;
                link.className = 'task-project-badge-refined';
                link.innerHTML = '<span>' + escapeHtml(projectTitulo || '') + '</span>';
                badgeContainer.parentNode.replaceChild(link, badgeContainer);
            } else {
                var span = document.createElement('span');
                span.className = 'task-project-badge-refined task-project-badge-neutral task-project-empty';
                span.innerHTML = '<span class="no-project-label">Sem projeto</span><span class="no-project-label-hover">+ adicionar projeto referente</span>';
                badgeContainer.parentNode.replaceChild(span, badgeContainer);
            }
        }

        function saveHeaderEdit(options) {
            var opts = options || {};
            if (!isEditing) return Promise.resolve(false);
            if (isSaving && currentSavePromise) return currentSavePromise;

            var snapshot = getEditSnapshot();
            if (!snapshot.titulo) {
                if (!opts.silentInvalid) {
                    alert('Título é obrigatório.');
                }
                inputTitulo.focus();
                return Promise.resolve(false);
            }

            if (lastSnapshot && snapshotsEqual(snapshot, lastSnapshot)) {
                showView();
                return Promise.resolve(true);
            }

            var formData = new FormData();
            formData.append('titulo', snapshot.titulo);
            formData.append('project_id', snapshot.projectId || '');

            setSavingState(true);
            currentSavePromise = fetch(editUrl, {
                method: 'POST',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json',
                },
                body: formData,
            })
                .then(function (response) {
                    return response.json().catch(function () { return {}; }).then(function (data) {
                        if (!response.ok || !data.success || !data.task) {
                            throw new Error((data && data.message) || 'Erro ao salvar.');
                        }
                        return data.task;
                    });
                })
                .then(function (taskData) {
                    var nextProjectId = taskData.project_id ? String(taskData.project_id) : '';
                    updateView(taskData.titulo, nextProjectId, taskData.project_titulo || null);
                    lastSnapshot = {
                        titulo: (taskData.titulo || '').trim(),
                        projectId: nextProjectId,
                    };
                    showView();
                    if (document.title && document.title.indexOf(' - ') !== -1) {
                        document.title = taskData.titulo + document.title.substring(document.title.indexOf(' - '));
                    }
                    return true;
                })
                .catch(function (error) {
                    alert((error && error.message) || 'Erro ao salvar. Tente novamente.');
                    inputTitulo.focus();
                    return false;
                })
                .finally(function () {
                    setSavingState(false);
                    currentSavePromise = null;
                });

            return currentSavePromise;
        }

        var popover = document.getElementById('taskAddProjectPopover');
        var popoverInput = document.getElementById('taskAddProjectPopoverInput');
        var popoverId = document.getElementById('taskAddProjectPopoverId');
        var popoverDropdown = document.getElementById('taskAddProjectPopoverDropdown');

        function openAddProjectPopover() {
            if (!popover || !popoverDropdown || !dropdown) return;
            var badge = header.querySelector('.task-project-empty');
            if (badge) badge.classList.add('popover-open');
            popoverDropdown.innerHTML = '';
            var opts = dropdown.querySelectorAll('.project-search-option');
            for (var i = 0; i < opts.length; i++) {
                var clone = opts[i].cloneNode(true);
                popoverDropdown.appendChild(clone);
            }
            popoverInput.value = '';
            popoverId.value = '';
            popover.removeAttribute('hidden');
            setTimeout(function () { if (popoverInput) popoverInput.focus(); }, 50);
            var popOpts = popoverDropdown.querySelectorAll('.project-search-option');
            popOpts.forEach(function (opt) {
                opt.addEventListener('click', function () {
                    var val = opt.getAttribute('data-value') || '';
                    var titulo = (document.querySelector('.task-title-refined') && document.querySelector('.task-title-refined').textContent) || '';
                    var formData = new FormData();
                    formData.append('titulo', titulo);
                    formData.append('project_id', val);
                    var xhr = new XMLHttpRequest();
                    xhr.open('POST', editUrl);
                    xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
                    xhr.setRequestHeader('Accept', 'application/json');
                    xhr.onload = function () {
                        try {
                            var data = JSON.parse(xhr.responseText);
                            if (data.success && data.task) {
                                var t = data.task;
                                updateView(t.titulo, t.project_id ? String(t.project_id) : '', t.project_titulo || null);
                                closeAddProjectPopover();
                            } else {
                                alert(data.message || 'Erro ao salvar.');
                            }
                        } catch (err) {
                            if (xhr.status === 200) return;
                            alert('Erro ao salvar.');
                        }
                    };
                    xhr.onerror = function () { alert('Erro de conexão.'); };
                    xhr.send(formData);
                });
            });
        }

        function closeAddProjectPopover() {
            var badge = header.querySelector('.task-project-empty');
            if (badge) badge.classList.remove('popover-open');
            if (popover) popover.setAttribute('hidden', '');
        }

        function filterPopoverOptions() {
            if (!popoverDropdown) return;
            var q = (popoverInput && popoverInput.value || '').trim().toLowerCase();
            var popOpts = popoverDropdown.querySelectorAll('.project-search-option');
            popOpts.forEach(function (opt) {
                var label = (opt.getAttribute('data-label') || opt.textContent || '').toLowerCase();
                opt.classList.toggle('hidden-by-filter', q && label.indexOf(q) === -1);
            });
        }

        if (popoverInput) {
            popoverInput.addEventListener('input', filterPopoverOptions);
        }
        document.addEventListener('click', function (e) {
            if (popover && !popover.contains(e.target) && !e.target.closest('.task-project-empty')) {
                closeAddProjectPopover();
            }
        });

        btnEdit.addEventListener('click', function () {
            if (!isEditing) {
                showEdit();
                return;
            }
            saveHeaderEdit();
        });

        header.addEventListener('click', function (e) {
            if (e.target.closest('.task-project-empty')) {
                e.preventDefault();
                openAddProjectPopover();
            }
        });

        editBlock.addEventListener('keydown', function (event) {
            if (!isEditing) return;
            if (event.key === 'Escape') {
                event.preventDefault();
                showView();
                return;
            }
            if (event.key === 'Enter' && !event.shiftKey) {
                if (event.target && event.target.closest('.project-search-dropdown')) return;
                event.preventDefault();
                saveHeaderEdit();
            }
        });

        document.addEventListener('mousedown', function (event) {
            if (!isEditing || isSaving) return;
            if (header.contains(event.target)) return;
            if (popover && popover.contains(event.target)) return;
            saveHeaderEdit({ silentInvalid: true });
        });
    })();

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

    function fetchAssignableUsers(taskId, sugestoesUrl, projectValue) {
        if (!sugestoesUrl) return Promise.resolve([]);
        var normalizedProject = String(projectValue == null ? '' : projectValue).trim();
        if (!normalizedProject) return Promise.resolve([]);
        var requestUrl = sugestoesUrl + (sugestoesUrl.indexOf('?') >= 0 ? '&' : '?') + 'project=' + encodeURIComponent(normalizedProject);
        var cacheKey = requestUrl;
        if (responsavelAssignableUsersCache[cacheKey]) {
            return responsavelAssignableUsersCache[cacheKey];
        }
        responsavelAssignableUsersCache[cacheKey] = fetch(requestUrl, { headers: { 'Accept': 'application/json' } })
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

            fetchAssignableUsers(options.taskId, options.sugestoesUrl, options.projectValue)
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

    // --- Adicionar tarefa inline (hub com múltiplos projetos) ---
    (function () {
        var listEl = document.querySelector('.task-items-list');
        if (!listEl) return;

        var addRows = Array.prototype.slice.call(
            listEl.querySelectorAll('.task-hub-add-row[data-project-value]')
        );
        if (!addRows.length) return;

        var addUrl = listEl.getAttribute('data-add-item-url');
        var sugestoesUrl = listEl.getAttribute('data-sugestoes-url');
        if (!addUrl) return;

        function escapeHtml(text) {
            var div = document.createElement('div');
            div.textContent = text == null ? '' : String(text);
            return div.innerHTML;
        }

        function normalizeProjectValue(value) {
            var normalized = String(value == null ? '' : value).trim();
            return normalized || '';
        }

        function buildProjectDetailUrl(projectValue) {
            var normalized = normalizeProjectValue(projectValue);
            if (!normalized || normalized === 'sem_projeto') return '';
            return '/project/' + encodeURIComponent(normalized);
        }

        function buildProjectContextMarkup(projectValue, projectTitulo) {
            var projectLabel = projectTitulo || 'Sem projeto';
            var projectUrl = buildProjectDetailUrl(projectValue);
            if (!projectUrl) {
                return '<span>' + escapeHtml(projectLabel) + '</span>';
            }
            return '<a href="' + projectUrl + '">' + escapeHtml(projectLabel) + '</a>';
        }

        function getAddRowByProject(projectValue) {
            var value = normalizeProjectValue(projectValue);
            if (!value) return null;
            return listEl.querySelector('.task-hub-add-row[data-project-value="' + value + '"]');
        }

        function updateGroupCount(groupEl) {
            if (!groupEl) return;
            var countEl = groupEl.querySelector('.task-hub-group-count');
            if (!countEl) return;
            var count = groupEl.querySelectorAll('.task-item-row[data-item-id]').length;
            countEl.textContent = count + (count === 1 ? ' tarefa' : ' tarefas');
        }

        function buildItemRowMarkup(item) {
            var prioridade = item.prioridade || '';
            var tipoPedido = item.tipo_pedido || '';
            var taskId = item.task_id || item.id || '';
            var taskTitulo = item.task_titulo || item.descricao || '';
            var projectTitulo = item.project_titulo || 'Sem projeto';
            var projectValue = item.project_value || (item.project_id ? String(item.project_id) : 'sem_projeto');
            var commentsCount = Number(item.comments_count || 0);
            var anexosCount = Number(item.anexos_count || 0);
            var legacyTipoOption = tipoPedido === 'implementacao'
                ? '<option value="implementacao" selected hidden>Implementação (legado)</option>'
                : '';

            var prioridadeOptions = '<option value="">—</option>' +
                '<option value="baixa"' + (prioridade === 'baixa' ? ' selected' : '') + '>Baixa</option>' +
                '<option value="media"' + (prioridade === 'media' ? ' selected' : '') + '>Média</option>' +
                '<option value="alta"' + (prioridade === 'alta' ? ' selected' : '') + '>Alta</option>' +
                '<option value="urgente"' + (prioridade === 'urgente' ? ' selected' : '') + '>Urgente</option>';
            var tipoOptions = '<option value="">—</option>' +
                legacyTipoOption +
                '<option value="bug"' + (tipoPedido === 'bug' ? ' selected' : '') + '>Bug</option>' +
                '<option value="melhoria"' + (tipoPedido === 'melhoria' ? ' selected' : '') + '>Melhoria</option>' +
                '<option value="duvida"' + (tipoPedido === 'duvida' ? ' selected' : '') + '>Dúvida</option>' +
                '<option value="outros"' + (tipoPedido === 'outros' ? ' selected' : '') + '>Outros</option>';

            var rowHtml =
                '<div class="task-item-row" ' +
                'data-item-id="' + item.id + '" ' +
                'data-item-status="' + item.status + '" ' +
                'data-comments-count="' + commentsCount + '" ' +
                'data-item-prioridade="' + escapeHtml(prioridade) + '" ' +
                'data-item-tipo="' + escapeHtml(tipoPedido) + '" ' +
                'data-anexos-count="' + anexosCount + '" ' +
                'data-task-id="' + escapeHtml(taskId) + '" ' +
                'data-task-titulo="' + escapeHtml(taskTitulo) + '" ' +
                'data-project-value="' + escapeHtml(projectValue) + '" ' +
                'data-project-titulo="' + escapeHtml(projectTitulo) + '">' +
                '<div class="task-item-bar status-' + item.status + '"></div>' +
                '<div class="task-item-main">' +
                '<div class="task-item-line">' +
                '<div class="task-item-desc-wrap">' +
                '<div class="task-item-desc-row">' +
                '<p class="task-item-desc" data-item-id="' + item.id + '">' + htmlEncode(item.descricao) + '</p>' +
                '<button type="button" class="task-item-desc-edit-btn" data-item-id="' + item.id + '" title="Editar descrição">' +
                '<i class="fas fa-pen" aria-hidden="true"></i><span class="visually-hidden">Editar</span></button>' +
                '</div>' +
                '<p class="task-hub-item-context">' + buildProjectContextMarkup(projectValue, projectTitulo) + '</p>' +
                '</div>' +
                '<div class="task-item-meta">' +
                '<select class="task-item-prioridade-select prioridade-' + (prioridade || 'none') + '" data-item-id="' + item.id + '" title="Prioridade" onchange="updateItemPrioridade(' + item.id + ', this.value, this)">' + prioridadeOptions + '</select>' +
                '<select class="task-item-tipo-select" data-item-id="' + item.id + '" title="Tipo" onchange="updateItemTipo(' + item.id + ', this.value)">' + tipoOptions + '</select>' +
                '<select class="task-item-status status-' + item.status + '" onchange="updateItemStatus(' + item.id + ', this.value)" title="Status">' +
                '<option value="programado"' + (item.status === 'programado' ? ' selected' : '') + '>Programado</option>' +
                '<option value="em_andamento"' + (item.status === 'em_andamento' ? ' selected' : '') + '>Em andamento</option>' +
                '<option value="validacao"' + (item.status === 'validacao' ? ' selected' : '') + '>Validação</option>' +
                '<option value="finalizado"' + (item.status === 'finalizado' ? ' selected' : '') + '>Finalizado</option>' +
                '</select>' +
                '<span class="task-item-responsavel" data-item-id="' + item.id + '">' +
                (item.responsavel ? htmlEncode(item.responsavel) : '<em class="responsavel-placeholder">Responsável não informado</em>') +
                '</span>' +
                '<div class="task-item-actions">' +
                '<button type="button" class="task-item-comments-btn" aria-expanded="false" data-target="comments-body-' + item.id + '" onclick="toggleComments(this)" title="Comentários">' +
                '<i class="far fa-comment-alt" aria-hidden="true"></i><span class="task-item-comments-num">' + commentsCount + '</span></button>' +
                '<button type="button" class="task-item-anexos-btn" title="Anexos" data-item-id="' + item.id + '">' +
                '<i class="fas fa-paperclip" aria-hidden="true"></i><span class="task-item-anexos-num">' + anexosCount + '</span></button>' +
                '<button type="button" class="task-item-btn task-item-del" data-bs-toggle="modal" data-bs-target="#deleteItemModal-' + item.id + '" title="Excluir"><i class="fas fa-trash-alt" aria-hidden="true"></i></button>' +
                '</div></div></div>' +
                '<div id="comments-body-' + item.id + '" class="task-item-comments" hidden>' +
                '<div class="task-item-comments-inner">' +
                '<form class="task-comment-form" action="/tarefas/' + item.id + '/comentarios/add" method="POST" data-item-id="' + item.id + '">' +
                '<textarea name="content" rows="1" placeholder="Comentar... (Enter para enviar)" required></textarea>' +
                '<button type="submit" title="Enviar comentário"><i class="fas fa-paper-plane" aria-hidden="true"></i><span class="visually-hidden">Enviar</span></button>' +
                '</form></div></div></div></div>';

            var modalHtml =
                '<div class="modal fade task-detail-v2-modal" id="deleteItemModal-' + item.id + '" tabindex="-1" aria-hidden="true">' +
                '<div class="modal-dialog modal-dialog-centered"><div class="modal-content modal-clean">' +
                '<div class="modal-header-clean"><div><h5 class="modal-title-clean ds-type-section-title">Excluir Tarefa</h5><p class="modal-subtitle-clean ds-type-body-sm">Esta ação não pode ser desfeita</p></div>' +
                '<button type="button" class="btn-close-clean" data-bs-dismiss="modal">&times;</button></div>' +
                '<div class="modal-body-clean"><p>Confirma a exclusão desta tarefa?</p><p class="text-muted small">' + escapeHtml((item.descricao || '').substring(0, 100)) + ((item.descricao || '').length > 100 ? '...' : '') + '</p></div>' +
                '<div class="modal-footer-clean"><button type="button" class="btn-modal-clean btn-cancel-clean" data-bs-dismiss="modal">Cancelar</button>' +
                '<form action="/tarefas/' + item.id + '/delete" method="POST" class="inline-form">' +
                '<button type="submit" class="btn-modal-clean btn-confirm-delete">Excluir</button></form></div></div></div></div>';

            return { rowHtml: rowHtml, modalHtml: modalHtml };
        }

        function requestAddItem(payload) {
            return new Promise(function (resolve, reject) {
                var dataPayload = payload || {};
                var descricao = (dataPayload.descricao || '').trim();
                var projectValue = normalizeProjectValue(dataPayload.project);

                if (!projectValue) {
                    reject(new Error('Projeto é obrigatório.'));
                    return;
                }
                if (!descricao) {
                    reject(new Error('Descrição é obrigatória.'));
                    return;
                }

                var formData = new FormData();
                formData.append('project', projectValue);
                formData.append('descricao', descricao);
                formData.append('status', dataPayload.status || 'programado');
                formData.append('responsavel', (dataPayload.responsavel || '').trim());
                formData.append('prioridade', (dataPayload.prioridade || '').trim());
                formData.append('tipo_pedido', (dataPayload.tipo_pedido || '').trim());

                var xhr = new XMLHttpRequest();
                xhr.open('POST', addUrl);
                xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
                xhr.setRequestHeader('Accept', 'application/json');
                xhr.onload = function () {
                    try {
                        var data = JSON.parse(xhr.responseText);
                        if (data.success && data.item) {
                            resolve(data);
                        } else {
                            reject(new Error((data && data.message) || 'Erro ao adicionar tarefa.'));
                        }
                    } catch (err) {
                        reject(new Error('Erro ao adicionar tarefa. Tente novamente.'));
                    }
                };
                xhr.onerror = function () {
                    reject(new Error('Erro de conexão. Tente novamente.'));
                };
                xhr.send(formData);
            });
        }

        function insertNewItem(data, options) {
            var payload = data || {};
            var item = payload.item || {};
            var opts = options || {};
            var projectValue = normalizeProjectValue(item.project_value || item.project_id || opts.projectValue || '');
            var targetAddRow = opts.addRow || getAddRowByProject(projectValue);
            if (!targetAddRow || !targetAddRow.parentNode) return;

            var markup = buildItemRowMarkup(item);
            var wrap = document.createElement('div');
            wrap.innerHTML = markup.rowHtml + markup.modalHtml;
            targetAddRow.parentNode.insertBefore(wrap.firstChild, targetAddRow);
            targetAddRow.parentNode.insertBefore(wrap.firstChild, targetAddRow);

            updateGroupCount(targetAddRow.closest('.task-hub-group'));
            updateTaskItemsHeaderCount();
            updateTaskItemsTotalPill();
            if (window.taskItemsKanban && typeof window.taskItemsKanban.rebuildFromList === 'function') {
                window.taskItemsKanban.rebuildFromList();
            }
        }

        function focusInlineAdd(projectValue) {
            var addRow = getAddRowByProject(projectValue) || addRows[0];
            if (!addRow) return false;
            var placeholder = addRow.querySelector('[data-role="open-add-form"]');
            var formWrap = addRow.querySelector('[data-role="add-form"]');
            var desc = addRow.querySelector('[data-role="descricao"]');
            addRow.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            if (formWrap && formWrap.hasAttribute('hidden') && placeholder) {
                placeholder.click();
            }
            if (desc) desc.focus();
            return true;
        }

        addRows.forEach(function (addRow) {
            var projectValue = normalizeProjectValue(addRow.getAttribute('data-project-value'));
            var placeholder = addRow.querySelector('[data-role="open-add-form"]');
            var formWrap = addRow.querySelector('[data-role="add-form"]');
            var addDesc = addRow.querySelector('[data-role="descricao"]');
            var addPrioridade = addRow.querySelector('[data-role="prioridade"]');
            var addTipo = addRow.querySelector('[data-role="tipo_pedido"]');
            var addStatus = addRow.querySelector('[data-role="status"]');
            var addResponsavelTrigger = addRow.querySelector('[data-role="responsavel-trigger"]');
            var cancelBtn = addRow.querySelector('[data-role="cancel-add"]');
            var submitBtn = addRow.querySelector('[data-role="submit-add"]');
            if (!placeholder || !formWrap || !addDesc || !addStatus || !addResponsavelTrigger || !cancelBtn || !submitBtn) return;

            var responsavelNames = [];
            var isSubmitting = false;
            renderResponsavelPickerTrigger(addResponsavelTrigger, responsavelNames, 'Responsável');

            function resizeTextarea() {
                addDesc.style.height = 'auto';
                addDesc.style.height = Math.max(32, addDesc.scrollHeight) + 'px';
            }

            function resetForm() {
                addDesc.value = '';
                addStatus.value = 'programado';
                if (addPrioridade) addPrioridade.value = '';
                if (addTipo) addTipo.value = '';
                responsavelNames = [];
                renderResponsavelPickerTrigger(addResponsavelTrigger, responsavelNames, 'Responsável');
                resizeTextarea();
            }

            function showForm() {
                placeholder.style.display = 'none';
                formWrap.removeAttribute('hidden');
                resetForm();
                setTimeout(function () { addDesc.focus(); }, 30);
            }

            function hideForm() {
                formWrap.setAttribute('hidden', '');
                placeholder.style.display = 'flex';
                responsavelPickerManager.closeIfAnchor(addResponsavelTrigger);
            }

            function submitForm(keepOpen) {
                if (isSubmitting) return;
                var descricao = (addDesc.value || '').trim();
                if (!descricao) {
                    addDesc.focus();
                    return;
                }
                isSubmitting = true;
                requestAddItem({
                    project: projectValue,
                    descricao: descricao,
                    status: addStatus.value || 'programado',
                    responsavel: responsavelNames.join(', '),
                    prioridade: addPrioridade ? addPrioridade.value : '',
                    tipo_pedido: addTipo ? addTipo.value : '',
                })
                    .then(function (data) {
                        insertNewItem(data, { addRow: addRow, projectValue: projectValue });
                        if (keepOpen) resetForm();
                        else hideForm();
                    })
                    .catch(function (error) {
                        alert((error && error.message) || 'Erro ao adicionar tarefa.');
                    })
                    .finally(function () {
                        isSubmitting = false;
                    });
            }

            placeholder.addEventListener('click', showForm);
            cancelBtn.addEventListener('click', hideForm);
            submitBtn.addEventListener('click', function () {
                submitForm(false);
            });
            addDesc.addEventListener('input', resizeTextarea);
            addDesc.addEventListener('keydown', function (e) {
                if (e.key === 'Escape') {
                    e.preventDefault();
                    hideForm();
                    return;
                }
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    submitForm(true);
                }
            });

            addResponsavelTrigger.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopPropagation();
                responsavelPickerManager.open({
                    anchorEl: addResponsavelTrigger,
                    sugestoesUrl: sugestoesUrl,
                    projectValue: projectValue,
                    initialRawValue: responsavelNames.join(', '),
                    onApply: function (payload) {
                        responsavelNames = payload.names.slice();
                        renderResponsavelPickerTrigger(addResponsavelTrigger, responsavelNames, 'Responsável');
                        return true;
                    },
                });
            });

            document.addEventListener('mousedown', function (event) {
                if (formWrap.hasAttribute('hidden')) return;
                if (isSubmitting) return;
                if (addRow.contains(event.target)) return;
                if (responsavelPickerManager.isEventInsidePopover(event.target)) return;
                if ((addDesc.value || '').trim()) {
                    submitForm(false);
                    return;
                }
                hideForm();
            });
        });

        window.taskItemsListBridge = {
            listEl: listEl,
            taskId: '',
            sugestoesUrl: sugestoesUrl,
            addItemUrl: addUrl,
            insertItemFromPayload: insertNewItem,
            requestAddItem: requestAddItem,
            focusInlineAdd: focusInlineAdd,
        };
    })();

    // Utilidade global de escape HTML (usada fora de IIFEs)
    function htmlEncode(s) {
        var d = document.createElement('div');
        d.textContent = String(s == null ? '' : s);
        return d.innerHTML;
    }

    function getTaskItemRowById(itemId) {
        return document.querySelector('.task-item-row[data-item-id="' + itemId + '"]');
    }

    function getTaskItemProjectValue(itemId) {
        var row = getTaskItemRowById(itemId);
        if (!row) return '';
        return String(row.getAttribute('data-project-value') || '').trim();
    }

    function setTaskItemRowStatus(row, status) {
        if (!row) return;
        row.setAttribute('data-item-status', status);

        var bar = row.querySelector('.task-item-bar');
        if (bar) {
            bar.classList.remove('status-programado', 'status-em_andamento', 'status-validacao', 'status-finalizado');
            bar.classList.add('status-' + status);
        }

        var statusSelect = row.querySelector('.task-item-status');
        if (statusSelect) {
            statusSelect.value = status;
            statusSelect.classList.remove('status-programado', 'status-em_andamento', 'status-validacao', 'status-finalizado');
            statusSelect.classList.add('status-' + status);
        }
    }

    function syncTaskItemRowMetadata(row) {
        if (!row) return;
        var statusSelect = row.querySelector('.task-item-status');
        if (statusSelect && statusSelect.value) {
            row.setAttribute('data-item-status', statusSelect.value);
        }
        var commentsNum = row.querySelector('.task-item-comments-num');
        if (commentsNum) {
            row.setAttribute('data-comments-count', String(parseInt(commentsNum.textContent || '0', 10) || 0));
        }
        var anexosNum = row.querySelector('.task-item-anexos-num');
        if (anexosNum) {
            row.setAttribute('data-anexos-count', String(parseInt(anexosNum.textContent || '0', 10) || 0));
        }
    }

    function updateTaskItemsHeaderCount() {
        var countEl = document.querySelector('.items-header-clean .header-count');
        if (!countEl) return;
        var itemCount = document.querySelectorAll('.task-item-row[data-item-id]').length;
        countEl.textContent = itemCount + (itemCount === 1 ? ' tarefa' : ' tarefas');
    }

    function updateTaskItemsTotalPill() {
        var totalPill = document.querySelector('.tasks-header .tasks-total-pill');
        if (!totalPill) return;
        var itemCount = document.querySelectorAll('.task-item-row[data-item-id]').length;
        totalPill.textContent = itemCount + ' tarefa' + (itemCount === 1 ? '' : 's');
    }

    function updateTaskHubArchiveCounter(delta) {
        if (!delta) return;
        var countEl = document.querySelector('.tasks-header .tasks-archive-count');
        if (!countEl) return;
        var current = parseInt(countEl.textContent || '0', 10);
        if (!Number.isFinite(current)) current = 0;
        var next = current + delta;
        countEl.textContent = String(next < 0 ? 0 : next);
    }

    function ensureTaskHubEmptyState(root) {
        var pageRoot = root || document.getElementById('taskHubPage');
        if (!pageRoot) return;
        var listItems = document.querySelectorAll('.task-item-row[data-item-id]');
        if (listItems.length) return;
        if (pageRoot.querySelector('.tasks-empty-state')) return;

        var itemsSection = pageRoot.querySelector('.task-detail-v2-items.task-hub-items');
        if (itemsSection && itemsSection.parentNode) {
            itemsSection.parentNode.removeChild(itemsSection);
        }

        var emptyState = document.createElement('section');
        emptyState.className = 'tasks-empty-state';
        emptyState.innerHTML =
            '<h2 class="tasks-empty-title">' + escapeTaskItemHtml(pageRoot.getAttribute('data-empty-title') || 'Nenhuma tarefa encontrada') + '</h2>' +
            '<p class="tasks-empty-text">' + escapeTaskItemHtml(pageRoot.getAttribute('data-empty-text') || 'Ajuste os filtros para visualizar tarefas ativas.') + '</p>';
        pageRoot.appendChild(emptyState);
    }

    function removeTaskItemFromDom(itemId) {
        if (!itemId) return false;
        var removed = false;
        var row = getTaskItemRowById(itemId);
        var groupEl = row ? row.closest('.task-hub-group') : null;
        if (row && row.parentNode) {
            row.parentNode.removeChild(row);
            removed = true;
        }

        var modal = document.getElementById('deleteItemModal-' + itemId);
        if (modal && modal.parentNode) {
            modal.parentNode.removeChild(modal);
        }

        if (groupEl) {
            var remaining = groupEl.querySelectorAll('.task-item-row[data-item-id]').length;
            var groupCountEl = groupEl.querySelector('.task-hub-group-count');
            if (groupCountEl) {
                groupCountEl.textContent = remaining + (remaining === 1 ? ' tarefa' : ' tarefas');
            }
            if (remaining === 0 && groupEl.parentNode) {
                groupEl.parentNode.removeChild(groupEl);
            }
        }

        updateTaskItemsHeaderCount();
        updateTaskItemsTotalPill();
        return removed;
    }

    function escapeTaskItemHtml(text) {
        var div = document.createElement('div');
        div.textContent = text == null ? '' : String(text);
        return div.innerHTML;
    }

    function getTaskItemStatus(row) {
        if (!row) return 'programado';
        var status = row.getAttribute('data-item-status') || '';
        if (status) return status;
        var statusSelect = row.querySelector('.task-item-status');
        return statusSelect && statusSelect.value ? statusSelect.value : 'programado';
    }

    function getTaskItemDescricao(row) {
        if (!row) return '';
        var descEl = row.querySelector('.task-item-desc');
        return descEl ? (descEl.textContent || '').trim() : '';
    }

    function getTaskItemResponsavel(row) {
        if (!row) return '';
        var responsavelEl = row.querySelector('.task-item-responsavel');
        if (!responsavelEl) return '';
        if (responsavelEl.querySelector('.responsavel-placeholder')) return '';
        var value = (responsavelEl.textContent || '').trim();
        return value === '\u00a0' ? '' : value;
    }

    function getTaskItemCommentsCount(row) {
        if (!row) return 0;
        var count = parseInt(row.getAttribute('data-comments-count') || '0', 10);
        if (!Number.isFinite(count) || count < 0) count = 0;
        return count;
    }

    function setTaskItemCommentsCount(row, count) {
        if (!row) return;
        var safeCount = parseInt(count, 10);
        if (!Number.isFinite(safeCount) || safeCount < 0) safeCount = 0;
        var numEl = row.querySelector('.task-item-comments-num');
        if (numEl) numEl.textContent = String(safeCount);
        row.setAttribute('data-comments-count', String(safeCount));
    }

    function getTaskItemPrioridade(row) {
        if (!row) return '';
        return row.getAttribute('data-item-prioridade') || '';
    }

    function getTaskItemTipoPedido(row) {
        if (!row) return '';
        return row.getAttribute('data-item-tipo') || '';
    }

    function getTaskItemAnexosCount(row) {
        if (!row) return 0;
        var count = parseInt(row.getAttribute('data-anexos-count') || '0', 10);
        if (!Number.isFinite(count) || count < 0) count = 0;
        return count;
    }

    function setTaskItemAnexosCount(row, count) {
        if (!row) return;
        var safeCount = parseInt(count, 10);
        if (!Number.isFinite(safeCount) || safeCount < 0) safeCount = 0;
        var numEl = row.querySelector('.task-item-anexos-num');
        if (numEl) numEl.textContent = String(safeCount);
        row.setAttribute('data-anexos-count', String(safeCount));
    }

    var PRIORIDADE_LABELS = { baixa: 'Baixa', media: 'Média', alta: 'Alta', urgente: 'Urgente' };
    var TIPO_LABELS = { implementacao: 'Implementação', bug: 'Bug', melhoria: 'Melhoria', duvida: 'Dúvida', outros: 'Outros' };

    function setTaskItemChips(row, prioridade, tipo) {
        if (!row) return;
        row.setAttribute('data-item-prioridade', prioridade || '');
        row.setAttribute('data-item-tipo', tipo || '');

        var prioSel = row.querySelector('.task-item-prioridade-select');
        if (prioSel) {
            prioSel.value = prioridade || '';
            _applyPrioridadeClass(prioSel, prioridade || '');
        }

        var tipoSel = row.querySelector('.task-item-tipo-select');
        if (tipoSel) {
            tipoSel.value = tipo || '';
        }
    }

    function _applyPrioridadeClass(sel, prioridade) {
        sel.classList.remove('prioridade-baixa', 'prioridade-media', 'prioridade-alta', 'prioridade-urgente', 'prioridade-none');
        sel.classList.add(prioridade ? 'prioridade-' + prioridade : 'prioridade-none');
    }

    function getTaskItemCommentsInner(row) {
        if (!row) return null;
        return row.querySelector('.task-item-comments-inner');
    }

    function findTaskCommentElementById(commentId) {
        if (!commentId) return null;
        return document.getElementById('comment-' + commentId);
    }

    function extractTaskCommentData(commentEl) {
        if (!commentEl) return null;
        var idAttr = commentEl.id || '';
        var id = parseInt(idAttr.replace('comment-', ''), 10);
        if (!Number.isFinite(id)) return null;
        var toneIndex = null;
        if (commentEl.classList) {
            for (var i = 0; i < commentEl.classList.length; i++) {
                var cls = commentEl.classList[i];
                if (cls.indexOf('task-comment-author-') === 0) {
                    var parsedTone = parseInt(cls.replace('task-comment-author-', ''), 10);
                    if (Number.isFinite(parsedTone)) {
                        toneIndex = Math.abs(parsedTone) % 5;
                    }
                    break;
                }
            }
        }

        var authorEl = commentEl.querySelector('.task-comment-user');
        var timeEl = commentEl.querySelector('.task-comment-time');
        var textEl = commentEl.querySelector('.task-comment-text');
        var editBtn = commentEl.querySelector('.btn-edit-comment[data-comment-id]');
        var hasDelete = !!commentEl.querySelector('form[action*="/tarefas/comentarios/"][action$="/delete"]');

        return {
            id: id,
            author_name: authorEl ? (authorEl.textContent || '').trim() : '',
            created_at: timeEl ? (timeEl.textContent || '').trim() : '',
            content: textEl ? (textEl.textContent || '').trim() : '',
            is_own: !!editBtn && hasDelete,
            user_id: null,
            tone_index: toneIndex,
            updated_at: null,
        };
    }

    function buildTaskCommentMarkup(comment) {
        var item = comment || {};
        var commentId = item.id;
        var authorClass = 'task-comment-author-' + ((item.user_id != null ? item.user_id : commentId || 0) % 5);
        var createdAt = item.updated_at
            ? (item.updated_at + ' (edit.)')
            : (item.created_at || '');

        var html = '<div class="task-comment ' + authorClass + '" id="comment-' + commentId + '">' +
            '<div class="task-comment-head">' +
            '<span class="task-comment-user">' + escapeTaskItemHtml(item.author_name || '') + '</span>' +
            '<span class="task-comment-time">' + escapeTaskItemHtml(createdAt) + '</span>';

        if (item.is_own) {
            html += '<span class="task-comment-acts">' +
                '<button type="button" class="task-comment-btn btn-edit-comment" data-comment-id="' + commentId +
                '" data-comment-content="' + escapeTaskItemHtml(item.content || '') + '" title="Editar">Editar</button>' +
                '<form action="/tarefas/comentarios/' + commentId + '/delete" method="POST" class="d-inline" onsubmit="return confirm(\'Excluir comentário?\');">' +
                '<button type="submit" class="task-comment-btn task-comment-btn-del" title="Excluir">Excluir</button>' +
                '</form></span>';
        }

        html += '</div><p class="task-comment-text">' + escapeTaskItemHtml(item.content || '') + '</p></div>';
        return html;
    }

    function appendCommentToTaskItemRow(row, comment) {
        if (!row || !comment || !comment.id) return null;
        var wrap = getTaskItemCommentsInner(row);
        if (!wrap) return null;
        var form = wrap.querySelector('.task-comment-form');
        if (!form) return null;

        var temp = document.createElement('div');
        temp.innerHTML = buildTaskCommentMarkup(comment);
        var commentEl = temp.firstChild;
        if (!commentEl) return null;
        wrap.insertBefore(commentEl, form);
        setTaskItemCommentsCount(row, getTaskItemCommentsCount(row) + 1);
        syncTaskItemRowMetadata(row);
        return commentEl;
    }

    function updateTaskCommentInRow(commentId, content, updatedAt) {
        var commentEl = findTaskCommentElementById(commentId);
        if (!commentEl) return;
        var textEl = commentEl.querySelector('.task-comment-text');
        if (textEl) textEl.textContent = content;
        var timeEl = commentEl.querySelector('.task-comment-time');
        if (timeEl && updatedAt) {
            timeEl.textContent = updatedAt + ' (edit.)';
        }
        var editBtn = commentEl.querySelector('.btn-edit-comment[data-comment-id]');
        if (editBtn) editBtn.setAttribute('data-comment-content', content);
    }

    function deleteTaskCommentFromRow(commentId) {
        var commentEl = findTaskCommentElementById(commentId);
        if (!commentEl) return null;
        var row = commentEl.closest('.task-item-row');
        if (commentEl.parentNode) commentEl.parentNode.removeChild(commentEl);
        if (row) {
            setTaskItemCommentsCount(row, Math.max(0, getTaskItemCommentsCount(row) - 1));
            syncTaskItemRowMetadata(row);
        }
        return row;
    }

    function collectTaskItemCommentsFromRow(row) {
        var wrap = getTaskItemCommentsInner(row);
        if (!wrap) return [];
        return Array.prototype.map.call(
            wrap.querySelectorAll('.task-comment[id^="comment-"]'),
            function (commentEl) { return extractTaskCommentData(commentEl); }
        ).filter(function (item) { return !!item; });
    }

    function updateTaskItemRowFromPayload(item) {
        if (!item || !item.id) return null;
        var row = getTaskItemRowById(item.id);
        if (!row) return null;

        if (typeof item.descricao === 'string') {
            var descEl = row.querySelector('.task-item-desc');
            if (descEl) descEl.textContent = item.descricao;
        }

        if (typeof item.status === 'string') {
            setTaskItemRowStatus(row, item.status);
        }

        if (typeof item.responsavel === 'string') {
            var respEl = row.querySelector('.task-item-responsavel');
            if (respEl) {
                setResponsavelCellText(respEl, item.responsavel);
            }
        }

        if (typeof item.comments_count === 'number') {
            setTaskItemCommentsCount(row, item.comments_count);
        }

        if (typeof item.anexos_count === 'number') {
            setTaskItemAnexosCount(row, item.anexos_count);
        }

        if (typeof item.prioridade === 'string' || typeof item.tipo_pedido === 'string') {
            var newPrioridade = typeof item.prioridade === 'string' ? item.prioridade : getTaskItemPrioridade(row);
            var newTipo = typeof item.tipo_pedido === 'string' ? item.tipo_pedido : getTaskItemTipoPedido(row);
            setTaskItemChips(row, newPrioridade, newTipo);
        }

        syncTaskItemRowMetadata(row);
        return row;
    }

    function persistTaskItemDetails(itemId, payload) {
        var row = getTaskItemRowById(itemId);
        var safePayload = payload || {};
        var hasOwn = Object.prototype.hasOwnProperty;

        var descricaoValue = hasOwn.call(safePayload, 'descricao')
            ? (safePayload.descricao || '')
            : (row ? getTaskItemDescricao(row) : '');
        var statusValue = hasOwn.call(safePayload, 'status')
            ? (safePayload.status || 'programado')
            : (row ? getTaskItemStatus(row) : 'programado');
        var responsavelValue = hasOwn.call(safePayload, 'responsavel')
            ? (safePayload.responsavel || '')
            : (row ? getTaskItemResponsavel(row) : '');
        var prioridadeValue = hasOwn.call(safePayload, 'prioridade')
            ? (safePayload.prioridade || '')
            : (row ? getTaskItemPrioridade(row) : '');
        var tipoPedidoValue = hasOwn.call(safePayload, 'tipo_pedido')
            ? (safePayload.tipo_pedido || '')
            : (row ? getTaskItemTipoPedido(row) : '');

        var formData = new FormData();
        formData.append('descricao', descricaoValue);
        formData.append('status', statusValue);
        formData.append('responsavel', responsavelValue);
        formData.append('prioridade', prioridadeValue);
        formData.append('tipo_pedido', tipoPedidoValue);

        return fetch('/tarefas/' + itemId + '/edit', {
            method: 'POST',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'Accept': 'application/json',
            },
            body: formData,
        })
            .then(function (response) {
                return response.json().catch(function () { return {}; }).then(function (data) {
                    if (!response.ok || !data.success) {
                        throw new Error((data && data.message) || 'Erro ao salvar tarefa.');
                    }
                    return data;
                });
            });
    }

    function focusTaskItemRow(itemId, options) {
        var opts = options || {};
        var targetRow = getTaskItemRowById(itemId);
        if (!targetRow) return false;

        var scrollDelay = typeof opts.scrollDelay === 'number' ? opts.scrollDelay : 180;
        var shouldHighlight = opts.highlight !== false;

        setTimeout(function () {
            targetRow.scrollIntoView({ behavior: 'smooth', block: 'center' });
            if (!shouldHighlight) return;
            targetRow.classList.add('search-focus-highlight');
            setTimeout(function () {
                targetRow.classList.remove('search-focus-highlight');
            }, 2300);
        }, scrollDelay);
        return true;
    }

    // Atualizar status da tarefa via AJAX (sem recarregar a página)
    function updateItemStatus(itemId, status, options) {
        var opts = options || {};
        var showAlert = opts.showAlert !== false;

        return fetch('/tarefas/' + itemId + '/update_status', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ status: status })
        })
            .then(function (response) { return response.json(); })
            .then(function (data) {
                if (!data.success) {
                    throw new Error(data.message || 'Erro ao atualizar status.');
                }

                var row = getTaskItemRowById(itemId);
                if (row) {
                    setTaskItemRowStatus(row, status);
                    syncTaskItemRowMetadata(row);
                }

                if (!opts.skipKanbanSync && window.taskItemsKanban && typeof window.taskItemsKanban.syncItemFromRow === 'function') {
                    window.taskItemsKanban.syncItemFromRow(String(itemId));
                }

                return data;
            })
            .catch(function (error) {
                console.error('Erro:', error);
                if (showAlert) {
                    alert(error && error.message ? error.message : 'Erro ao atualizar status');
                }
                throw error;
            });
    }

    function updateItemPrioridade(itemId, prioridade, selectEl) {
        var prev = selectEl ? selectEl.getAttribute('data-prev-value') || '' : '';
        if (selectEl) selectEl.setAttribute('data-prev-value', prioridade);

        return fetch('/tarefas/' + itemId + '/update_prioridade', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prioridade: prioridade || null })
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.success) throw new Error(data.message || 'Erro ao atualizar prioridade.');
                var row = getTaskItemRowById(itemId);
                if (row) {
                    row.setAttribute('data-item-prioridade', prioridade || '');
                    if (selectEl) _applyPrioridadeClass(selectEl, prioridade);
                    syncTaskItemRowMetadata(row);
                }
                if (window.taskItemsKanban && typeof window.taskItemsKanban.syncItemFromRow === 'function') {
                    window.taskItemsKanban.syncItemFromRow(String(itemId));
                }
                return data;
            })
            .catch(function (error) {
                console.error('Erro:', error);
                if (selectEl) {
                    selectEl.value = prev;
                    _applyPrioridadeClass(selectEl, prev);
                }
                alert(error && error.message ? error.message : 'Erro ao atualizar prioridade');
            });
    }

    function updateItemTipo(itemId, tipo) {
        return fetch('/tarefas/' + itemId + '/update_tipo', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tipo_pedido: tipo || null })
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.success) throw new Error(data.message || 'Erro ao atualizar tipo.');
                var row = getTaskItemRowById(itemId);
                if (row) {
                    row.setAttribute('data-item-tipo', tipo || '');
                    syncTaskItemRowMetadata(row);
                }
                if (window.taskItemsKanban && typeof window.taskItemsKanban.syncItemFromRow === 'function') {
                    window.taskItemsKanban.syncItemFromRow(String(itemId));
                }
                return data;
            })
            .catch(function (error) {
                console.error('Erro:', error);
                alert(error && error.message ? error.message : 'Erro ao atualizar tipo');
            });
    }

    var taskItemsKanbanManager = (function () {
        var statusOrder = ['programado', 'em_andamento', 'validacao', 'finalizado'];
        var statusLabels = {
            programado: 'Programado',
            em_andamento: 'Em andamento',
            validacao: 'Validação',
            finalizado: 'Finalizado',
        };
        var pageRoot = document.querySelector('.task-detail-v2');
        var toggleRoot = document.getElementById('taskItemsViewToggle');
        var listView = document.getElementById('taskItemsListView');
        var kanbanView = document.getElementById('taskItemsKanbanView');
        var board = document.getElementById('taskItemsKanbanBoard');
        var listEl = document.querySelector('.task-items-list');
        var toggleButtons = toggleRoot ? toggleRoot.querySelectorAll('.task-items-view-btn[data-view]') : [];
        var toggleVisual = toggleRoot ? {
            pathLeft: toggleRoot.querySelector('[data-role="path-left"]'),
            pathRight: toggleRoot.querySelector('[data-role="path-right"]'),
            divider: toggleRoot.querySelector('[data-role="divider"]'),
            fillLeft: toggleRoot.querySelector('[data-role="fill-left"]'),
            fillRight: toggleRoot.querySelector('[data-role="fill-right"]'),
            highlightLeft: toggleRoot.querySelector('[data-role="highlight-left"]'),
            highlightRight: toggleRoot.querySelector('[data-role="highlight-right"]'),
            borderLeft: toggleRoot.querySelector('[data-role="border-left"]'),
            labelList: toggleRoot.querySelector('[data-view-label="list"]'),
            labelKanban: toggleRoot.querySelector('[data-view-label="kanban"]'),
        } : null;
        var reorderUrl = listEl ? (listEl.getAttribute('data-reorder-url') || '') : '';
        var taskId = listEl ? (listEl.getAttribute('data-task-id') || '') : '';
        var storageKey = taskId ? ('task-items-view:' + taskId) : 'task-hub-items-view';
        var currentUserIdRaw = pageRoot ? (pageRoot.getAttribute('data-current-user-id') || '') : '';
        var currentUserId = parseInt(currentUserIdRaw, 10);
        if (!Number.isFinite(currentUserId)) currentUserId = null;

        var drawer = document.getElementById('taskItemDrawer');
        var drawerBackdrop = document.getElementById('taskItemDrawerBackdrop');
        var drawerClose = document.getElementById('taskItemDrawerClose');
        var drawerTitle = document.getElementById('taskItemDrawerTitle');
        var drawerStatusBadge = document.getElementById('taskItemDrawerStatusBadge');
        var drawerDesc = document.getElementById('taskItemDrawerDesc');
        var drawerResponsavelTrigger = document.getElementById('taskItemDrawerResponsavelTrigger');
        var drawerAutosaveStatus = document.getElementById('taskItemDrawerAutosaveStatus');
        var drawerDeleteIcon = document.getElementById('taskItemDrawerDeleteIcon');
        var drawerDeleteConfirm = document.getElementById('taskItemDrawerDeleteConfirm');
        var drawerDeleteCancel = document.getElementById('taskItemDrawerDeleteCancel');
        var drawerDeleteConfirmBtn = document.getElementById('taskItemDrawerDeleteConfirmBtn');
        var drawerCommentsSection = drawer ? drawer.querySelector('.task-item-drawer-comments') : null;
        var drawerCommentsStatus = document.getElementById('taskItemDrawerCommentsStatus');
        var drawerCommentsList = document.getElementById('taskItemDrawerCommentsList');
        var drawerCommentsCount = document.getElementById('taskItemDrawerCommentsCount');
        var drawerCommentForm = document.getElementById('taskItemDrawerCommentForm');
        var drawerCommentsToggle = document.getElementById('taskItemDrawerCommentsToggle');
        var drawerCommentsBody = document.getElementById('taskItemDrawerCommentsBody');
        var drawerPrioridade = document.getElementById('taskItemDrawerPrioridade');
        var drawerTipoPedido = document.getElementById('taskItemDrawerTipoPedido');
        var drawerAnexosToggle = document.getElementById('taskItemDrawerAnexosToggle');
        var drawerAnexosBody = document.getElementById('taskItemDrawerAnexosBody');
        var drawerAnexosList = document.getElementById('taskItemDrawerAnexosList');
        var drawerAnexosCount = document.getElementById('taskItemDrawerAnexosCount');
        var drawerAnexoInput = document.getElementById('taskItemDrawerAnexoInput');
        var quickAnexoInput = document.getElementById('taskQuickAnexoInput');
        var anexoPreviewModal = document.getElementById('taskAnexoPreviewModal');
        var anexoPreviewBackdrop = document.getElementById('taskAnexoPreviewBackdrop');
        var anexoPreviewClose = document.getElementById('taskAnexoPreviewClose');
        var anexoPreviewTitle = document.getElementById('taskAnexoPreviewTitle');
        var anexoPreviewBody = document.getElementById('taskAnexoPreviewBody');
        var anexoPreviewOpen = document.getElementById('taskAnexoPreviewOpen');
        var anexoPreviewDownload = document.getElementById('taskAnexoPreviewDownload');

        var currentView = 'list';
        var dragContext = null;
        var isPersisting = false;
        var isDeleting = false;
        var suppressCardClickUntil = 0;
        var toggleVisualDir = 1;
        var toggleVisualFrame = null;
        var composerControllers = {};
        var drawerState = {
            itemId: null,
            responsavelNames: [],
            isSaving: false,
            isClosing: false,
            isCommentBusy: false,
            autosaveTimer: null,
            autosaveDebounceMs: 520,
            saveToken: 0,
            hasPendingSave: false,
            hasUnsavedChanges: false,
            lastSavedSnapshot: '',
            commentsStatusTimer: null,
            forceCommentsBottom: false,
            isCommentsExpanded: false,
            commentsTransitionTimer: null,
            commentsTransitionMs: 250,
        };
        var quickUploadState = { itemId: null };
        var previewState = {
            isOpen: false,
            hideTimer: null,
        };

        function noop() {}
        var fallbackApi = {
            applyView: noop,
            getCurrentView: function () { return 'list'; },
            rebuildFromList: noop,
            syncItemFromRow: noop,
            focusComposerForStatus: function () { return false; },
            openDrawerAnexos: noop,
            openDrawerComments: noop,
            openItemAnexoAction: noop,
        };

        if (!toggleRoot || !listView || !kanbanView || !board || !listEl) {
            return fallbackApi;
        }

        function hasDrawer() {
            return !!(
                drawer &&
                drawerBackdrop &&
                drawerDesc &&
                drawerResponsavelTrigger &&
                drawerCommentsList &&
                drawerCommentForm &&
                drawerCommentsToggle &&
                drawerCommentsBody &&
                drawerAutosaveStatus &&
                drawerStatusBadge &&
                drawerDeleteIcon &&
                drawerDeleteConfirm &&
                drawerDeleteCancel &&
                drawerDeleteConfirmBtn &&
                drawerCommentsStatus
            );
        }

        function clearDrawerAutosaveTimer() {
            if (!drawerState.autosaveTimer) return;
            clearTimeout(drawerState.autosaveTimer);
            drawerState.autosaveTimer = null;
        }

        function prefersReducedMotion() {
            return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
        }

        function payloadSnapshot(payload) {
            var data = payload || {};
            var descricao = (data.descricao || '').trim();
            var status = normalizeStatus(data.status || 'programado');
            var responsavel = (data.responsavel || '').trim();
            var prioridade = (data.prioridade || '').trim();
            var tipoPedido = (data.tipo_pedido || '').trim();
            return [descricao, status, responsavel, prioridade, tipoPedido].join('\u001f');
        }

        function buildToggleCurvePath(direction) {
            var d = direction;
            var x = 136;
            return [
                'M ' + x + ' 0',
                'C ' + (x + (7 * 0.3 * d)) + ' ' + (50 * 0.15) + ',',
                '  ' + (x + (7 * d)) + ' ' + (50 * 0.28) + ',',
                '  ' + (x + (7 * 0.5 * d)) + ' ' + (50 * 0.5),
                'C ' + x + ' ' + (50 * 0.72) + ',',
                '  ' + (x - (7 * 0.7 * d)) + ' ' + (50 * 0.85) + ',',
                '  ' + x + ' 50'
            ].join(' ');
        }

        function buildToggleLeftPath(direction) {
            return buildToggleCurvePath(direction) + ' L 0 50 L 0 0 Z';
        }

        function buildToggleRightPath(direction) {
            return buildToggleCurvePath(direction) + ' L 272 50 L 272 0 Z';
        }

        function syncTogglePaths(direction) {
            if (!toggleVisual || !toggleVisual.pathLeft || !toggleVisual.pathRight || !toggleVisual.divider) return;
            toggleVisual.pathLeft.setAttribute('d', buildToggleLeftPath(direction));
            toggleVisual.pathRight.setAttribute('d', buildToggleRightPath(direction));
            toggleVisual.divider.setAttribute('d', buildToggleCurvePath(direction));
        }

        function syncToggleColors(mode) {
            if (!toggleVisual) return;
            var isList = mode !== 'kanban';

            if (toggleVisual.fillLeft) {
                toggleVisual.fillLeft.setAttribute(
                    'fill',
                    isList ? 'url(#taskHubViewToggleActive)' : 'url(#taskHubViewToggleInactive)'
                );
            }
            if (toggleVisual.fillRight) {
                toggleVisual.fillRight.setAttribute(
                    'fill',
                    isList ? 'url(#taskHubViewToggleInactive)' : 'url(#taskHubViewToggleActive)'
                );
            }
            if (toggleVisual.highlightLeft) {
                toggleVisual.highlightLeft.setAttribute('opacity', isList ? '1' : '0');
            }
            if (toggleVisual.highlightRight) {
                toggleVisual.highlightRight.setAttribute('opacity', isList ? '0' : '1');
            }
            if (toggleVisual.borderLeft) {
                toggleVisual.borderLeft.setAttribute('opacity', isList ? '1' : '0');
            }
            if (toggleVisual.labelList) {
                toggleVisual.labelList.classList.toggle('is-active', isList);
            }
            if (toggleVisual.labelKanban) {
                toggleVisual.labelKanban.classList.toggle('is-active', !isList);
            }
        }

        function animateToggleVisual(targetDir) {
            var fromDir = toggleVisualDir;
            var start = performance.now();
            var duration = 500;

            if (toggleVisualFrame) {
                cancelAnimationFrame(toggleVisualFrame);
                toggleVisualFrame = null;
            }

            function ease(t) {
                return t < 0.5
                    ? 4 * t * t * t
                    : 1 - Math.pow(-2 * t + 2, 3) / 2;
            }

            function frame(now) {
                var elapsed = now - start;
                var progress = Math.min(elapsed / duration, 1);
                var dir = fromDir + ((targetDir - fromDir) * ease(progress));
                toggleVisualDir = dir;
                syncTogglePaths(dir);

                if (progress < 1) {
                    toggleVisualFrame = requestAnimationFrame(frame);
                    return;
                }

                toggleVisualDir = targetDir;
                toggleVisualFrame = null;
            }

            toggleVisualFrame = requestAnimationFrame(frame);
        }

        function setToggleActiveState(mode, opts) {
            var targetMode = mode === 'kanban' ? 'kanban' : 'list';
            var options = opts || {};
            var targetDir = targetMode === 'kanban' ? -1 : 1;
            toggleRoot.setAttribute('data-active-view', targetMode);
            toggleButtons.forEach(function (button) {
                var isActive = button.getAttribute('data-view') === targetMode;
                button.classList.toggle('is-active', isActive);
                button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
            });
            syncToggleColors(targetMode);

            if (!toggleVisual || !toggleVisual.pathLeft || !toggleVisual.pathRight || !toggleVisual.divider) {
                toggleVisualDir = targetDir;
                return;
            }

            if (options.animate === false || prefersReducedMotion() || toggleVisualDir === targetDir) {
                if (toggleVisualFrame) {
                    cancelAnimationFrame(toggleVisualFrame);
                    toggleVisualFrame = null;
                }
                syncTogglePaths(targetDir);
                toggleVisualDir = targetDir;
                return;
            }

            animateToggleVisual(targetDir);
        }

        function normalizeStatus(status) {
            return statusOrder.indexOf(status) !== -1 ? status : 'programado';
        }

        function getStatusLabel(status) {
            return statusLabels[normalizeStatus(status)] || 'Programado';
        }

        function getDropzone(status) {
            return board.querySelector('.task-items-kanban-dropzone[data-status="' + normalizeStatus(status) + '"]');
        }

        function buildKanbanProjectUrl(projectValue) {
            var normalized = String(projectValue == null ? '' : projectValue).trim();
            if (!normalized || normalized === 'sem_projeto') return '';
            return '/project/' + encodeURIComponent(normalized);
        }

        function renderKanbanContext(contextEl, item) {
            if (!contextEl) return;
            contextEl.innerHTML = '';

            var projectLabel = item.projectTitulo || 'Sem projeto';
            var projectUrl = buildKanbanProjectUrl(item.projectValue);
            if (!projectUrl) {
                contextEl.textContent = projectLabel;
                return;
            }

            var link = document.createElement('a');
            link.href = projectUrl;
            link.textContent = projectLabel;
            contextEl.appendChild(link);
        }

        function readStoredView() {
            if (!storageKey) return 'list';
            try {
                var raw = localStorage.getItem(storageKey);
                return raw === 'kanban' ? 'kanban' : 'list';
            } catch (error) {
                return 'list';
            }
        }

        function saveStoredView(mode) {
            if (!storageKey) return;
            try {
                localStorage.setItem(storageKey, mode);
            } catch (error) {}
        }

        function readRowItem(row) {
            if (!row) return null;
            syncTaskItemRowMetadata(row);

            var itemId = row.getAttribute('data-item-id');
            if (!itemId) return null;

            return {
                id: String(itemId),
                status: normalizeStatus(getTaskItemStatus(row)),
                descricao: getTaskItemDescricao(row),
                responsavel: getTaskItemResponsavel(row),
                commentsCount: getTaskItemCommentsCount(row),
                prioridade: getTaskItemPrioridade(row),
                tipoPedido: getTaskItemTipoPedido(row),
                anexosCount: getTaskItemAnexosCount(row),
                projectValue: String(row.getAttribute('data-project-value') || '').trim(),
                projectTitulo: String(row.getAttribute('data-project-titulo') || '').trim(),
                taskTitulo: String(row.getAttribute('data-task-titulo') || '').trim(),
            };
        }

        function collectListItems() {
            return Array.prototype.map.call(
                listEl.querySelectorAll('.task-item-row[data-item-id]'),
                function (row) { return readRowItem(row); }
            ).filter(function (item) { return !!item; });
        }

        function setCardStatus(card, status) {
            if (!card) return;
            var normalized = normalizeStatus(status);
            card.setAttribute('data-status', normalized);
            var badge = card.querySelector('.task-items-kanban-badge');
            if (badge) {
                badge.classList.remove('status-programado', 'status-em_andamento', 'status-validacao', 'status-finalizado');
                badge.classList.add('status-' + normalized);
                badge.textContent = getStatusLabel(normalized);
            }
        }

        function fillKanbanCardContent(card, item) {
            if (!card || !item) return;
            card.setAttribute('data-item-id', item.id);
            setCardStatus(card, item.status);

            var desc = card.querySelector('.task-items-kanban-desc');
            if (desc) desc.textContent = item.descricao || 'Sem descrição';

            var contextEl = card.querySelector('.task-hub-kanban-context');
            renderKanbanContext(contextEl, item);

            var owner = card.querySelector('.task-items-kanban-owner');
            if (owner) {
                owner.textContent = item.responsavel || 'Responsável não informado';
                owner.classList.toggle('is-empty', !item.responsavel);
            }

            var commentsValue = card.querySelector('.task-items-kanban-comments-count');
            if (commentsValue) commentsValue.textContent = String(item.commentsCount || 0);
            var commentsBtn = card.querySelector('.task-items-kanban-comments[data-action="kanban-open-comments"]');
            if (commentsBtn) commentsBtn.setAttribute('data-item-id', item.id);

            var anexosValue = card.querySelector('.task-items-kanban-anexos-count');
            if (anexosValue) {
                var anexosCount = item.anexosCount || 0;
                anexosValue.textContent = anexosCount > 0 ? String(anexosCount) : '';
                anexosValue.classList.toggle('is-hidden', anexosCount === 0);
            }
            var anexosBtn = card.querySelector('.task-items-kanban-anexos[data-action="kanban-open-anexos"]');
            if (anexosBtn) anexosBtn.setAttribute('data-item-id', item.id);

            var pChip = card.querySelector('.task-items-kanban-priority');
            if (pChip) {
                pChip.textContent = (item.prioridade && PRIORIDADE_LABELS[item.prioridade]) ? PRIORIDADE_LABELS[item.prioridade] : '';
                pChip.className = 'task-items-kanban-priority' + (item.prioridade ? ' priority-' + item.prioridade : ' is-empty');
            }

            var tChip = card.querySelector('.task-items-kanban-tipo');
            if (tChip) {
                tChip.textContent = (item.tipoPedido && TIPO_LABELS[item.tipoPedido]) ? TIPO_LABELS[item.tipoPedido] : '';
                tChip.className = 'task-items-kanban-tipo' + (item.tipoPedido ? '' : ' is-empty');
            }

            var deleteBtn = card.querySelector('.task-items-kanban-delete-btn[data-action="kanban-delete"]');
            if (deleteBtn) deleteBtn.setAttribute('data-item-id', item.id);
            var confirmBox = card.querySelector('.task-items-kanban-delete-confirm[data-role="delete-confirm"]');
            if (confirmBox) confirmBox.setAttribute('data-item-id', item.id);
        }

        function buildKanbanCard(item) {
            var card = document.createElement('article');
            card.className = 'task-items-kanban-card';
            card.setAttribute('draggable', 'true');
            card.setAttribute('data-item-id', item.id);
            card.setAttribute('data-status', item.status);
            card.tabIndex = 0;

            var top = document.createElement('div');
            top.className = 'task-items-kanban-card-top';

            var badge = document.createElement('span');
            badge.className = 'task-items-kanban-badge';
            top.appendChild(badge);

            var deleteBtn = document.createElement('button');
            deleteBtn.type = 'button';
            deleteBtn.className = 'task-items-kanban-delete-btn';
            deleteBtn.setAttribute('data-action', 'kanban-delete');
            deleteBtn.setAttribute('data-item-id', item.id);
            deleteBtn.setAttribute('aria-label', 'Excluir tarefa');
            deleteBtn.innerHTML = '<i class="fas fa-trash-alt" aria-hidden="true"></i>';
            top.appendChild(deleteBtn);

            var desc = document.createElement('p');
            desc.className = 'task-items-kanban-desc';

            var contextEl = document.createElement('p');
            contextEl.className = 'task-hub-kanban-context';

            var meta = document.createElement('div');
            meta.className = 'task-items-kanban-meta';

            var owner = document.createElement('span');
            owner.className = 'task-items-kanban-owner';
            meta.appendChild(owner);

            var metaIcons = document.createElement('div');
            metaIcons.className = 'task-items-kanban-meta-icons';

            var comments = document.createElement('button');
            comments.type = 'button';
            comments.className = 'task-items-kanban-comments';
            comments.setAttribute('data-action', 'kanban-open-comments');
            comments.setAttribute('data-item-id', item.id);
            comments.setAttribute('title', 'Abrir comentários');
            comments.setAttribute('aria-label', 'Abrir comentários da tarefa');
            comments.innerHTML = '<i class="far fa-comment-alt" aria-hidden="true"></i><span class="task-items-kanban-comments-count">0</span>';
            metaIcons.appendChild(comments);

            var anexos = document.createElement('button');
            anexos.type = 'button';
            anexos.className = 'task-items-kanban-anexos';
            anexos.setAttribute('data-action', 'kanban-open-anexos');
            anexos.setAttribute('data-item-id', item.id);
            anexos.setAttribute('title', 'Abrir anexos');
            anexos.setAttribute('aria-label', 'Abrir anexos da tarefa');
            anexos.innerHTML = '<i class="fas fa-paperclip" aria-hidden="true"></i><span class="task-items-kanban-anexos-count is-hidden"></span>';
            metaIcons.appendChild(anexos);

            meta.appendChild(metaIcons);

            var chipsGroup = document.createElement('div');
            chipsGroup.className = 'task-items-kanban-chips';

            var priority = document.createElement('span');
            priority.className = 'task-items-kanban-priority is-empty';
            chipsGroup.appendChild(priority);

            var tipo = document.createElement('span');
            tipo.className = 'task-items-kanban-tipo is-empty';
            chipsGroup.appendChild(tipo);

            top.insertBefore(chipsGroup, deleteBtn);

            card.appendChild(top);
            card.appendChild(desc);
            card.appendChild(contextEl);
            card.appendChild(meta);

            var deleteConfirm = document.createElement('div');
            deleteConfirm.className = 'task-items-kanban-delete-confirm';
            deleteConfirm.setAttribute('data-role', 'delete-confirm');
            deleteConfirm.setAttribute('data-item-id', item.id);
            deleteConfirm.setAttribute('hidden', '');
            deleteConfirm.innerHTML =
                '<p>Excluir esta tarefa?</p>' +
                '<div class="task-items-kanban-delete-confirm-actions">' +
                '<button type="button" class="task-items-kanban-delete-cancel" data-action="kanban-delete-cancel">Cancelar</button>' +
                '<button type="button" class="task-items-kanban-delete-confirm-btn" data-action="kanban-delete-confirm">Excluir</button>' +
                '</div>';
            card.appendChild(deleteConfirm);

            fillKanbanCardContent(card, item);
            return card;
        }

        function updateColumnMeta() {
            var columns = board.querySelectorAll('.task-items-kanban-column[data-status]');
            columns.forEach(function (column) {
                var status = normalizeStatus(column.getAttribute('data-status'));
                var dropzone = column.querySelector('.task-items-kanban-dropzone[data-status]');
                var count = dropzone ? dropzone.querySelectorAll('.task-items-kanban-card[data-item-id]').length : 0;
                var countEl = column.querySelector('.task-items-kanban-count[data-role="count"]');
                if (countEl) countEl.textContent = String(count);
                column.classList.toggle('is-empty', count === 0);
                column.classList.remove('status-programado', 'status-em_andamento', 'status-validacao', 'status-finalizado');
                column.classList.add('status-' + status);
            });
        }

        function renderKanbanFromList() {
            var items = collectListItems();
            statusOrder.forEach(function (status) {
                var dropzone = getDropzone(status);
                if (dropzone) dropzone.innerHTML = '';
            });

            items.forEach(function (item) {
                var dropzone = getDropzone(item.status);
                if (!dropzone) return;
                dropzone.appendChild(buildKanbanCard(item));
            });

            updateColumnMeta();

            if (drawerState.itemId && !getTaskItemRowById(drawerState.itemId)) {
                closeDrawer();
            } else if (drawerState.itemId) {
                syncDrawerFromCurrentRow();
            }
        }

        function syncCardFromRow(itemId) {
            if (!itemId) return;
            var row = getTaskItemRowById(itemId);
            if (!row) {
                renderKanbanFromList();
                return;
            }

            var item = readRowItem(row);
            if (!item) return;

            var card = board.querySelector('.task-items-kanban-card[data-item-id="' + item.id + '"]');
            if (!card) {
                if (currentView === 'kanban') renderKanbanFromList();
                return;
            }

            fillKanbanCardContent(card, item);
            var dropzone = getDropzone(item.status);
            if (dropzone && card.parentNode !== dropzone) {
                dropzone.appendChild(card);
            }
            updateColumnMeta();
        }

        function serializeKanbanOrder() {
            var order = [];
            statusOrder.forEach(function (status) {
                var dropzone = getDropzone(status);
                if (!dropzone) return;
                dropzone.querySelectorAll('.task-items-kanban-card[data-item-id]').forEach(function (card) {
                    var id = parseInt(card.getAttribute('data-item-id'), 10);
                    if (Number.isFinite(id)) order.push(id);
                });
            });
            return order;
        }

        function syncListOrderFromKanban() {
            if (!reorderUrl) return;
            var orderIds = serializeKanbanOrder();
            if (!orderIds.length) return;

            var addRow = listEl.querySelector('.task-hub-add-row') || listEl.querySelector('#addItemRow');
            var fragment = document.createDocumentFragment();

            orderIds.forEach(function (id) {
                var row = listEl.querySelector('.task-item-row[data-item-id="' + id + '"]');
                if (row) fragment.appendChild(row);

                var modal = listEl.querySelector('#deleteItemModal-' + id);
                if (modal) fragment.appendChild(modal);
            });

            if (addRow && addRow.parentNode === listEl) {
                listEl.insertBefore(fragment, addRow);
            } else {
                listEl.appendChild(fragment);
            }
        }

        function persistKanbanOrder() {
            if (!reorderUrl) return Promise.resolve();
            return fetch(reorderUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ ordem: serializeKanbanOrder() }),
            }).then(function (response) {
                return response.json().catch(function () { return {}; }).then(function (data) {
                    if (!response.ok || !data.success) {
                        throw new Error((data && data.message) || 'Erro ao reordenar tarefas.');
                    }
                    return data;
                });
            });
        }

        function closeCardDeleteConfirm(card) {
            if (!card) return;
            card.classList.remove('is-delete-confirming');
            var confirmBox = card.querySelector('.task-items-kanban-delete-confirm[data-role="delete-confirm"]');
            if (confirmBox) confirmBox.setAttribute('hidden', '');
        }

        function closeAllCardDeleteConfirms(exceptCard) {
            board.querySelectorAll('.task-items-kanban-card.is-delete-confirming').forEach(function (card) {
                if (exceptCard && card === exceptCard) return;
                closeCardDeleteConfirm(card);
            });
        }

        function setDrawerDeleteConfirmVisible(visible) {
            if (!hasDrawer() || !drawerDeleteConfirm) return;
            if (visible) {
                drawerDeleteConfirm.removeAttribute('hidden');
            } else {
                drawerDeleteConfirm.setAttribute('hidden', '');
            }
            drawer.classList.toggle('is-delete-confirming', !!visible);
            drawerDeleteIcon.classList.toggle('is-active', !!visible);
        }

        function deleteTaskItemAjax(itemId) {
            return fetch('/tarefas/' + itemId + '/delete', {
                method: 'POST',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json',
                },
            }).then(function (response) {
                return response.json().catch(function () { return {}; }).then(function (data) {
                    if (!response.ok || !data.success) {
                        throw new Error((data && data.message) || 'Erro ao excluir tarefa.');
                    }
                    return data;
                });
            });
        }

        function setDeletingState(active) {
            isDeleting = !!active;
            board.classList.toggle('is-deleting', isDeleting);
            if (hasDrawer()) {
                drawer.classList.toggle('is-deleting', isDeleting);
                refreshDrawerActionControls();
            }
        }

        function deleteKanbanItem(itemId) {
            if (!itemId || isDeleting || isPersisting) return;
            setDeletingState(true);

            deleteTaskItemAjax(itemId)
                .then(function () {
                    removeTaskItemFromDom(itemId);
                    closeAllCardDeleteConfirms();
                    if (drawerState.itemId && drawerState.itemId === String(itemId)) {
                        closeDrawer();
                    }
                    renderKanbanFromList();
                })
                .catch(function (error) {
                    alert((error && error.message) || 'Não foi possível excluir a tarefa.');
                    renderKanbanFromList();
                })
                .finally(function () {
                    setDeletingState(false);
                });
        }

        function refreshDrawerActionControls() {
            if (!hasDrawer()) return;
            var disableDelete = isDeleting || drawerState.isSaving || drawerState.isCommentBusy;
            drawerDeleteIcon.disabled = disableDelete;
            drawerDeleteCancel.disabled = disableDelete;
            drawerDeleteConfirmBtn.disabled = disableDelete;
        }

        function setDrawerAutosaveStatus(state, message) {
            if (!hasDrawer() || !drawerAutosaveStatus) return;
            var normalizedState = state || 'saved';
            drawerAutosaveStatus.classList.remove('is-saving', 'is-saved', 'is-error', 'is-invalid');
            drawerAutosaveStatus.classList.add('is-' + normalizedState);

            if (message) {
                drawerAutosaveStatus.textContent = message;
                return;
            }

            if (normalizedState === 'saving') {
                drawerAutosaveStatus.textContent = 'Salvando...';
            } else if (normalizedState === 'error') {
                drawerAutosaveStatus.textContent = 'Não foi possível salvar.';
            } else if (normalizedState === 'invalid') {
                drawerAutosaveStatus.textContent = 'Descrição é obrigatória.';
            } else {
                drawerAutosaveStatus.textContent = 'Salvo';
            }
        }

        function clearDrawerCommentsStatusTimer() {
            if (!drawerState.commentsStatusTimer) return;
            clearTimeout(drawerState.commentsStatusTimer);
            drawerState.commentsStatusTimer = null;
        }

        function clearDrawerCommentsTransitionTimer() {
            if (!drawerState.commentsTransitionTimer) return;
            clearTimeout(drawerState.commentsTransitionTimer);
            drawerState.commentsTransitionTimer = null;
        }

        function setDrawerCommentsExpanded(expanded, options) {
            if (!hasDrawer() || !drawerCommentsSection || !drawerCommentsBody || !drawerCommentsToggle) return;
            var opts = options || {};
            var shouldExpand = !!expanded;
            var instant = !!opts.instant || prefersReducedMotion();

            clearDrawerCommentsTransitionTimer();
            drawerState.isCommentsExpanded = shouldExpand;
            drawerCommentsSection.classList.toggle('is-expanded', shouldExpand);
            drawerCommentsToggle.setAttribute('aria-expanded', shouldExpand ? 'true' : 'false');
            drawerCommentsBody.setAttribute('aria-hidden', shouldExpand ? 'false' : 'true');

            if (shouldExpand) {
                if (drawerCommentsBody.hasAttribute('hidden')) {
                    drawerCommentsBody.removeAttribute('hidden');
                }

                if (instant) {
                    drawerCommentsBody.classList.add('is-expanded');
                    scrollDrawerCommentsToBottom(true);
                    return;
                }

                requestAnimationFrame(function () {
                    if (!drawerState.isCommentsExpanded) return;
                    drawerCommentsBody.classList.add('is-expanded');
                    scrollDrawerCommentsToBottom(true);
                });
                return;
            }

            drawerCommentsBody.classList.remove('is-expanded');
            if (instant) {
                drawerCommentsBody.setAttribute('hidden', '');
                return;
            }

            drawerState.commentsTransitionTimer = setTimeout(function () {
                if (drawerState.isCommentsExpanded || !drawerCommentsBody) return;
                drawerCommentsBody.setAttribute('hidden', '');
                drawerState.commentsTransitionTimer = null;
            }, drawerState.commentsTransitionMs);
        }

        function setDrawerCommentsStatus(type, message, options) {
            if (!hasDrawer() || !drawerCommentsStatus) return;
            clearDrawerCommentsStatusTimer();
            var opts = options || {};

            drawerCommentsStatus.classList.remove('is-error', 'is-success', 'is-info');
            if (!message) {
                drawerCommentsStatus.textContent = '';
                drawerCommentsStatus.setAttribute('hidden', '');
                return;
            }

            var normalizedType = type || 'info';
            drawerCommentsStatus.classList.add('is-' + normalizedType);
            drawerCommentsStatus.textContent = message;
            drawerCommentsStatus.removeAttribute('hidden');

            if (opts.autoHideMs) {
                drawerState.commentsStatusTimer = setTimeout(function () {
                    if (!drawerCommentsStatus) return;
                    drawerCommentsStatus.textContent = '';
                    drawerCommentsStatus.setAttribute('hidden', '');
                    drawerCommentsStatus.classList.remove('is-error', 'is-success', 'is-info');
                    drawerState.commentsStatusTimer = null;
                }, opts.autoHideMs);
            }
        }

        function getDrawerCommentTextarea() {
            return drawerCommentForm ? drawerCommentForm.querySelector('textarea[name="content"]') : null;
        }

        function getDrawerCommentSubmitButton() {
            return drawerCommentForm ? drawerCommentForm.querySelector('button[type="submit"]') : null;
        }

        function resizeDrawerDescTextarea() {
            if (!hasDrawer() || !drawerDesc) return;
            drawerDesc.style.height = '0px';
            var computed = window.getComputedStyle(drawerDesc);
            var lineHeight = parseFloat(computed.lineHeight || '20');
            if (!Number.isFinite(lineHeight) || lineHeight <= 0) lineHeight = 20;
            var minHeight = Math.round((lineHeight * 2) + 24);
            var nextHeight = Math.max(minHeight, drawerDesc.scrollHeight + 2);
            drawerDesc.style.height = nextHeight + 'px';
        }

        function resizeDrawerCommentTextarea() {
            var textarea = getDrawerCommentTextarea();
            if (!textarea) return;
            textarea.style.height = 'auto';
            var nextHeight = Math.min(180, Math.max(70, textarea.scrollHeight));
            textarea.style.height = nextHeight + 'px';
        }

        function refreshDrawerCommentComposer() {
            var textarea = getDrawerCommentTextarea();
            var submitBtn = getDrawerCommentSubmitButton();
            if (!textarea || !submitBtn) return;
            var hasContent = !!(textarea.value || '').trim();
            submitBtn.disabled = drawerState.isCommentBusy || isDeleting || !hasContent;
        }

        var drawerAuthorToneMap = Object.create(null);
        var drawerAuthorToneCursor = 0;
        var DRAWER_AUTHOR_TONE_TOTAL = 5;

        function getCommentAuthorToneClass(comment) {
            if (comment && Number.isFinite(comment.tone_index)) {
                return 'author-tone-' + (Math.abs(comment.tone_index) % DRAWER_AUTHOR_TONE_TOTAL);
            }
            var rawKey = '';
            if (comment && comment.author_name) rawKey = String(comment.author_name).trim().toLowerCase();
            if (!rawKey && comment && Number.isFinite(comment.user_id)) rawKey = String(comment.user_id);
            if (!rawKey && comment && Number.isFinite(comment.id)) rawKey = 'autor-id-' + String(comment.id);
            if (!rawKey) rawKey = 'autor-indefinido';

            if (!Object.prototype.hasOwnProperty.call(drawerAuthorToneMap, rawKey)) {
                drawerAuthorToneMap[rawKey] = drawerAuthorToneCursor % DRAWER_AUTHOR_TONE_TOTAL;
                drawerAuthorToneCursor += 1;
            }
            return 'author-tone-' + drawerAuthorToneMap[rawKey];
        }

        function scrollDrawerCommentsToBottom(force) {
            if (!hasDrawer()) return;
            var list = drawerCommentsList;
            if (!list) return;
            var distanceFromBottom = list.scrollHeight - list.scrollTop - list.clientHeight;
            var shouldPin = force || distanceFromBottom <= 56;
            if (!shouldPin) return;
            requestAnimationFrame(function () {
                list.scrollTop = list.scrollHeight;
            });
        }

        function setDrawerSaving(isSaving) {
            drawerState.isSaving = !!isSaving;
            if (!hasDrawer()) return;
            drawer.classList.toggle('is-saving', drawerState.isSaving);
            refreshDrawerActionControls();
        }

        function setDrawerCommentsBusy(isBusy) {
            drawerState.isCommentBusy = !!isBusy;
            if (!hasDrawer()) return;
            drawer.classList.toggle('is-comments-busy', drawerState.isCommentBusy);
            if (drawerCommentsSection) {
                drawerCommentsSection.classList.toggle('is-busy', drawerState.isCommentBusy);
            }
            var textarea = getDrawerCommentTextarea();
            if (textarea) textarea.disabled = drawerState.isCommentBusy || isDeleting;
            drawerCommentsList.querySelectorAll('button').forEach(function (btn) {
                btn.disabled = drawerState.isCommentBusy;
            });
            refreshDrawerCommentComposer();
            refreshDrawerActionControls();
        }

        function setDrawerStatus(status) {
            if (!hasDrawer()) return;
            var normalized = normalizeStatus(status);
            drawerStatusBadge.classList.remove('status-programado', 'status-em_andamento', 'status-validacao', 'status-finalizado');
            drawerStatusBadge.classList.add('status-' + normalized);
            drawerStatusBadge.textContent = getStatusLabel(normalized);
        }

        function setDrawerResponsavel(names) {
            drawerState.responsavelNames = (names || []).slice();
            if (!hasDrawer()) return;
            renderResponsavelPickerTrigger(drawerResponsavelTrigger, drawerState.responsavelNames, 'Responsável');
        }

        function buildDrawerPayload(itemId) {
            if (!hasDrawer() || !itemId) return null;
            var row = getTaskItemRowById(itemId);
            if (!row) return null;
            return {
                descricao: (drawerDesc.value || '').trim(),
                status: getTaskItemStatus(row),
                responsavel: drawerState.responsavelNames.join(', '),
                prioridade: drawerPrioridade ? drawerPrioridade.value : '',
                tipo_pedido: drawerTipoPedido ? drawerTipoPedido.value : '',
            };
        }

        function scheduleDrawerAutosave(options) {
            if (!hasDrawer() || !drawerState.itemId || isDeleting) return;
            var opts = options || {};
            clearDrawerAutosaveTimer();

            var payload = buildDrawerPayload(drawerState.itemId);
            if (!payload) return;
            if (!payload.descricao) {
                drawerState.hasUnsavedChanges = true;
                setDrawerAutosaveStatus('invalid');
                return;
            }

            var snapshot = payloadSnapshot(payload);
            if (snapshot !== drawerState.lastSavedSnapshot) {
                drawerState.hasUnsavedChanges = true;
            } else if (!drawerState.isSaving && !drawerState.hasPendingSave) {
                drawerState.hasUnsavedChanges = false;
                setDrawerAutosaveStatus('saved');
            }

            if (opts.immediate) {
                flushDrawerAutosave('immediate');
                return;
            }

            drawerState.autosaveTimer = setTimeout(function () {
                flushDrawerAutosave('debounce');
            }, drawerState.autosaveDebounceMs);
        }

        function flushDrawerAutosave(source) {
            clearDrawerAutosaveTimer();
            if (!hasDrawer() || !drawerState.itemId || isDeleting) return Promise.resolve(false);

            var itemId = String(drawerState.itemId);
            var payload = buildDrawerPayload(itemId);
            if (!payload) return Promise.resolve(false);

            if (!payload.descricao) {
                drawerState.hasUnsavedChanges = true;
                setDrawerAutosaveStatus('invalid');
                return Promise.resolve(false);
            }

            var snapshot = payloadSnapshot(payload);
            if (snapshot === drawerState.lastSavedSnapshot) {
                drawerState.hasUnsavedChanges = false;
                setDrawerAutosaveStatus('saved');
                return Promise.resolve(true);
            }

            if (drawerState.isSaving) {
                drawerState.hasPendingSave = true;
                return Promise.resolve(false);
            }

            var token = ++drawerState.saveToken;
            var saveReason = source || 'unknown';
            setDrawerSaving(true);
            setDrawerAutosaveStatus('saving');

            return persistTaskItemDetails(itemId, payload)
                .then(function (data) {
                    if (token !== drawerState.saveToken) return false;
                    if (!data || !data.item) {
                        throw new Error('Erro ao salvar tarefa.');
                    }

                    updateTaskItemRowFromPayload(data.item);
                    syncCardFromRow(itemId);
                    drawerState.lastSavedSnapshot = payloadSnapshot({
                        descricao: data.item.descricao || payload.descricao,
                        status: data.item.status || payload.status,
                        responsavel: typeof data.item.responsavel === 'string' ? data.item.responsavel : payload.responsavel,
                        prioridade: typeof data.item.prioridade === 'string' ? data.item.prioridade : payload.prioridade,
                        tipo_pedido: typeof data.item.tipo_pedido === 'string' ? data.item.tipo_pedido : payload.tipo_pedido,
                    });
                    drawerState.hasUnsavedChanges = false;
                    setDrawerAutosaveStatus('saved', saveReason === 'blur' ? 'Salvo' : '');
                    syncDrawerFromCurrentRow();
                    return true;
                })
                .catch(function (error) {
                    if (token !== drawerState.saveToken) return false;
                    drawerState.hasUnsavedChanges = true;
                    var message = (error && error.message) || '';
                    if (/descri[cç][aã]o.*obrigat[óo]ria/i.test(message)) {
                        setDrawerAutosaveStatus('invalid');
                    } else {
                        setDrawerAutosaveStatus('error', message || 'Não foi possível salvar.');
                    }
                    return false;
                })
                .finally(function () {
                    if (token !== drawerState.saveToken) return;
                    setDrawerSaving(false);
                    if (drawerState.hasPendingSave) {
                        drawerState.hasPendingSave = false;
                        flushDrawerAutosave('queued');
                    }
                });
        }

        function renderDrawerCommentsFromRow(row, opts) {
            if (!hasDrawer() || !row) return;
            var options = opts || {};
            var comments = collectTaskItemCommentsFromRow(row);
            var shouldPinBottom = options.forceBottom === true;
            if (!shouldPinBottom) {
                var distanceFromBottom = drawerCommentsList.scrollHeight - drawerCommentsList.scrollTop - drawerCommentsList.clientHeight;
                shouldPinBottom = distanceFromBottom <= 56;
            }
            drawerCommentsList.innerHTML = '';

            if (!comments.length) {
                var empty = document.createElement('div');
                empty.className = 'task-item-drawer-comments-empty';
                empty.textContent = 'Sem comentários nesta tarefa.';
                drawerCommentsList.appendChild(empty);
            } else {
                comments.forEach(function (comment) {
                    var node = document.createElement('article');
                    node.className = 'task-item-drawer-comment ' + getCommentAuthorToneClass(comment);
                    node.setAttribute('data-comment-id', String(comment.id));

                    var head = document.createElement('div');
                    head.className = 'task-item-drawer-comment-head';

                    var author = document.createElement('span');
                    author.className = 'task-item-drawer-comment-author';
                    author.textContent = comment.author_name || 'Usuário';
                    head.appendChild(author);

                    var time = document.createElement('span');
                    time.className = 'task-item-drawer-comment-time';
                    time.textContent = comment.created_at || '';
                    head.appendChild(time);

                    if (comment.is_own || (currentUserId && comment.user_id === currentUserId)) {
                        node.classList.add('is-own');
                        var actions = document.createElement('span');
                        actions.className = 'task-item-drawer-comment-actions';

                        var editBtn = document.createElement('button');
                        editBtn.type = 'button';
                        editBtn.className = 'task-item-drawer-comment-action';
                        editBtn.setAttribute('data-action', 'edit-comment');
                        editBtn.setAttribute('data-comment-id', String(comment.id));
                        editBtn.setAttribute('title', 'Editar comentário');
                        editBtn.setAttribute('aria-label', 'Editar comentário');
                        editBtn.innerHTML = '<i class="fas fa-pen" aria-hidden="true"></i><span class="visually-hidden">Editar comentário</span>';
                        actions.appendChild(editBtn);

                        var delBtn = document.createElement('button');
                        delBtn.type = 'button';
                        delBtn.className = 'task-item-drawer-comment-action is-danger';
                        delBtn.setAttribute('data-action', 'delete-comment');
                        delBtn.setAttribute('data-comment-id', String(comment.id));
                        delBtn.setAttribute('title', 'Excluir comentário');
                        delBtn.setAttribute('aria-label', 'Excluir comentário');
                        delBtn.innerHTML = '<i class="fas fa-trash-alt" aria-hidden="true"></i><span class="visually-hidden">Excluir comentário</span>';
                        actions.appendChild(delBtn);

                        head.appendChild(actions);
                    }

                    var text = document.createElement('p');
                    text.className = 'task-item-drawer-comment-text';
                    text.textContent = comment.content || '';
                    node.appendChild(head);
                    node.appendChild(text);
                    drawerCommentsList.appendChild(node);
                });
            }

            var commentsCount = comments.length;
            drawerCommentsCount.textContent = String(commentsCount);
            if (drawerState.isCommentsExpanded) {
                scrollDrawerCommentsToBottom(shouldPinBottom);
            }
        }

        function syncDrawerFromCurrentRow() {
            if (!hasDrawer() || !drawerState.itemId) return;
            var row = getTaskItemRowById(drawerState.itemId);
            if (!row) {
                closeDrawer();
                return;
            }

            var descricao = getTaskItemDescricao(row);
            var responsavel = getTaskItemResponsavel(row);
            var status = getTaskItemStatus(row);
            var prioridade = getTaskItemPrioridade(row);
            var tipoPedido = getTaskItemTipoPedido(row);
            var anexosCount = getTaskItemAnexosCount(row);

            if (!drawerState.isSaving && !drawerState.hasUnsavedChanges) {
                drawerDesc.value = descricao;
                resizeDrawerDescTextarea();
                setDrawerResponsavel(splitResponsavelNames(responsavel));
                if (drawerPrioridade) drawerPrioridade.value = prioridade || '';
                if (drawerTipoPedido) drawerTipoPedido.value = tipoPedido || '';
                drawerState.lastSavedSnapshot = payloadSnapshot({
                    descricao: descricao,
                    status: status,
                    responsavel: responsavel,
                    prioridade: prioridade,
                    tipo_pedido: tipoPedido,
                });
            }
            setDrawerStatus(status);
            if (drawerAnexosCount) drawerAnexosCount.textContent = String(anexosCount);
            drawerTitle.textContent = (drawerDesc.value || '').trim() || descricao || 'Item sem descrição';
            renderDrawerCommentsFromRow(row, { forceBottom: drawerState.forceCommentsBottom });
            drawerState.forceCommentsBottom = false;
        }

        function openDrawer(itemId) {
            if (!hasDrawer()) return;
            var row = getTaskItemRowById(itemId);
            if (!row) return;
            drawerState.itemId = String(itemId);
            drawerState.hasPendingSave = false;
            drawerState.hasUnsavedChanges = false;
            drawerState.forceCommentsBottom = true;
            clearDrawerAutosaveTimer();
            clearDrawerCommentsStatusTimer();
            syncDrawerFromCurrentRow();
            setDrawerSaving(false);
            setDrawerCommentsBusy(false);
            setDrawerDeleteConfirmVisible(false);
            setDrawerAutosaveStatus('saved');
            drawerCommentForm.reset();
            resizeDrawerCommentTextarea();
            resizeDrawerDescTextarea();
            refreshDrawerCommentComposer();
            setDrawerCommentsStatus();
            setDrawerCommentsExpanded(false, { instant: true });

            // Reset attachments section so loadDrawerAnexos is always triggered for the new task
            if (drawerAnexosToggle) {
                drawerAnexosToggle.setAttribute('aria-expanded', 'false');
                drawerAnexosToggle.classList.remove('is-expanded');
            }
            if (drawerAnexosBody) drawerAnexosBody.setAttribute('hidden', '');
            if (drawerAnexosList) drawerAnexosList.innerHTML = '';
            if (drawerAnexosCount) drawerAnexosCount.textContent = '0';

            drawer.removeAttribute('hidden');
            drawerBackdrop.removeAttribute('hidden');
            drawer.setAttribute('aria-hidden', 'false');
            document.body.classList.add('task-item-drawer-open');
            requestAnimationFrame(function () {
                drawer.classList.add('is-open');
                drawerBackdrop.classList.add('is-open');
                resizeDrawerDescTextarea();
                setTimeout(function () {
                    resizeDrawerDescTextarea();
                }, 180);
            });
        }

        function performDrawerClose() {
            if (!hasDrawer()) return;
            clearDrawerAutosaveTimer();
            clearDrawerCommentsStatusTimer();
            drawerState.isClosing = false;
            drawerState.hasPendingSave = false;
            drawerState.hasUnsavedChanges = false;
            drawerState.forceCommentsBottom = false;
            drawerState.isCommentsExpanded = false;
            drawerState.itemId = null;
            drawer.classList.remove('is-open');
            drawerBackdrop.classList.remove('is-open');
            drawer.setAttribute('aria-hidden', 'true');
            setDrawerDeleteConfirmVisible(false);
            setDrawerCommentsExpanded(false, { instant: true });
            clearDrawerCommentsTransitionTimer();
            document.body.classList.remove('task-item-drawer-open');
            setTimeout(function () {
                if (drawerState.itemId) return;
                drawer.setAttribute('hidden', '');
                drawerBackdrop.setAttribute('hidden', '');
                drawerCommentsList.innerHTML = '';
                if (drawerAnexosList) drawerAnexosList.innerHTML = '';
                if (drawerAnexosCount) drawerAnexosCount.textContent = '0';
                drawerTitle.textContent = 'Item';
                setDrawerAutosaveStatus('saved');
                setDrawerCommentsStatus();
                drawerCommentForm.reset();
                resizeDrawerCommentTextarea();
                resizeDrawerDescTextarea();
                refreshDrawerCommentComposer();
            }, 160);
        }

        function closeDrawer(options) {
            if (!hasDrawer()) return;
            var opts = options || {};
            var force = opts.force === true;
            var currentItemId = drawerState.itemId ? String(drawerState.itemId) : '';

            if (!currentItemId) {
                performDrawerClose();
                return;
            }

            if (!force && !isDeleting) {
                if (drawerState.isClosing) return;
                drawerState.isClosing = true;
                flushDrawerAutosave('close')
                    .catch(function () {})
                    .finally(function () {
                        if (drawerState.itemId && String(drawerState.itemId) !== currentItemId) {
                            drawerState.isClosing = false;
                            return;
                        }
                        performDrawerClose();
                    });
                return;
            }

            performDrawerClose();
        }

        function openDrawerAnexos(itemId) {
            openDrawer(itemId);
            setTimeout(function () {
                if (drawerAnexosToggle && drawerAnexosToggle.getAttribute('aria-expanded') !== 'true') {
                    drawerAnexosToggle.click();
                }
            }, 80);
        }

        function openDrawerComments(itemId) {
            openDrawer(itemId);
            setTimeout(function () {
                if (drawerCommentsToggle && drawerCommentsToggle.getAttribute('aria-expanded') !== 'true') {
                    setDrawerCommentsExpanded(true);
                }
            }, 80);
        }

        function performQuickAnexoUpload(itemId, file) {
            if (!itemId || !file) return Promise.resolve(false);
            var formData = new FormData();
            formData.append('file', file);
            return fetch('/tarefas/' + itemId + '/anexos/add', {
                method: 'POST',
                headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' },
                body: formData,
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (!data.success) throw new Error(data.message || 'Erro ao enviar anexo.');
                    var row = getTaskItemRowById(itemId);
                    if (row) setTaskItemAnexosCount(row, data.anexos_count);
                    if (window.taskItemsKanban && typeof window.taskItemsKanban.syncItemFromRow === 'function') {
                        window.taskItemsKanban.syncItemFromRow(itemId);
                    }
                    openDrawerAnexos(itemId);
                    return true;
                });
        }

        function requestQuickAnexoUpload(itemId) {
            if (!itemId) return;
            if (!quickAnexoInput) {
                openDrawerAnexos(itemId);
                return;
            }
            quickUploadState.itemId = String(itemId);
            quickAnexoInput.value = '';
            quickAnexoInput.click();
        }

        function openItemAnexoAction(itemId) {
            if (!itemId) return;
            var row = getTaskItemRowById(itemId);
            if (!row) {
                openDrawerAnexos(itemId);
                return;
            }
            var anexosCount = getTaskItemAnexosCount(row);
            if (anexosCount > 0) {
                openDrawerAnexos(itemId);
                return;
            }
            requestQuickAnexoUpload(itemId);
        }

        function hasAnexoPreviewModal() {
            return !!(
                anexoPreviewModal &&
                anexoPreviewBackdrop &&
                anexoPreviewBody &&
                anexoPreviewTitle &&
                anexoPreviewOpen &&
                anexoPreviewDownload
            );
        }

        function clearAnexoPreviewContent() {
            if (!hasAnexoPreviewModal()) return;
            anexoPreviewBody.innerHTML = '';
            anexoPreviewTitle.textContent = 'Anexo';
            anexoPreviewOpen.setAttribute('href', '#');
            anexoPreviewDownload.setAttribute('href', '#');
            anexoPreviewDownload.removeAttribute('download');
        }

        function closeAnexoPreviewModal() {
            if (!hasAnexoPreviewModal() || !previewState.isOpen) return;
            previewState.isOpen = false;
            anexoPreviewModal.classList.remove('is-open');
            anexoPreviewBackdrop.classList.remove('is-open');
            anexoPreviewModal.setAttribute('aria-hidden', 'true');
            if (previewState.hideTimer) clearTimeout(previewState.hideTimer);
            previewState.hideTimer = setTimeout(function () {
                if (previewState.isOpen) return;
                anexoPreviewModal.setAttribute('hidden', '');
                anexoPreviewBackdrop.setAttribute('hidden', '');
                clearAnexoPreviewContent();
                previewState.hideTimer = null;
            }, 150);
        }

        function openAnexoPreviewModal(payload) {
            if (!hasAnexoPreviewModal()) return;
            var data = payload || {};
            var url = data.url || '';
            if (!url) return;
            var filename = data.filename || 'Anexo';
            var contentType = String(data.contentType || '').toLowerCase();
            var isImage = !!data.isImage || contentType.indexOf('image/') === 0;
            var isPdf = contentType.indexOf('pdf') !== -1 || /\.pdf($|\?)/i.test(url);

            clearAnexoPreviewContent();
            anexoPreviewTitle.textContent = filename;
            anexoPreviewOpen.setAttribute('href', url);
            anexoPreviewDownload.setAttribute('href', url);
            anexoPreviewDownload.setAttribute('download', filename);

            if (isImage) {
                var img = document.createElement('img');
                img.className = 'task-anexo-preview-image';
                img.src = url;
                img.alt = filename;
                img.loading = 'lazy';
                anexoPreviewBody.appendChild(img);
            } else if (isPdf) {
                var iframe = document.createElement('iframe');
                iframe.className = 'task-anexo-preview-pdf';
                iframe.src = url;
                iframe.setAttribute('title', filename);
                anexoPreviewBody.appendChild(iframe);
            } else {
                var fallback = document.createElement('div');
                fallback.className = 'task-anexo-preview-fallback';
                fallback.innerHTML =
                    '<i class="fas fa-file" aria-hidden="true"></i>' +
                    '<p>Preview não disponível para este tipo de arquivo.</p>' +
                    '<span>' + escapeAnexoHtml(filename) + '</span>';
                anexoPreviewBody.appendChild(fallback);
            }

            if (previewState.hideTimer) {
                clearTimeout(previewState.hideTimer);
                previewState.hideTimer = null;
            }
            previewState.isOpen = true;
            anexoPreviewModal.removeAttribute('hidden');
            anexoPreviewBackdrop.removeAttribute('hidden');
            anexoPreviewModal.setAttribute('aria-hidden', 'false');
            requestAnimationFrame(function () {
                anexoPreviewModal.classList.add('is-open');
                anexoPreviewBackdrop.classList.add('is-open');
            });
        }

        function bindAnexoPreviewModalEvents() {
            if (!hasAnexoPreviewModal()) return;
            if (anexoPreviewClose) {
                anexoPreviewClose.addEventListener('click', function () {
                    closeAnexoPreviewModal();
                });
            }
            if (anexoPreviewBackdrop) {
                anexoPreviewBackdrop.addEventListener('click', function () {
                    closeAnexoPreviewModal();
                });
            }
            document.addEventListener('keydown', function (event) {
                if (event.key === 'Escape' && previewState.isOpen) {
                    closeAnexoPreviewModal();
                }
            });
        }

        function postCommentAdd(itemId, content) {
            var formData = new FormData();
            formData.append('content', content);
            return fetch('/tarefas/' + itemId + '/comentarios/add', {
                method: 'POST',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json',
                },
                body: formData,
            }).then(function (response) {
                return response.json().catch(function () { return {}; }).then(function (data) {
                    if (!response.ok || !data.success) {
                        throw new Error((data && data.message) || 'Erro ao adicionar comentário.');
                    }
                    return data;
                });
            });
        }

        function postCommentEdit(commentId, content) {
            var formData = new FormData();
            formData.append('content', content);
            return fetch('/tarefas/comentarios/' + commentId + '/edit', {
                method: 'POST',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json',
                },
                body: formData,
            }).then(function (response) {
                return response.json().catch(function () { return {}; }).then(function (data) {
                    if (!response.ok || !data.success) {
                        throw new Error((data && data.message) || 'Erro ao editar comentário.');
                    }
                    return data;
                });
            });
        }

        function postCommentDelete(commentId) {
            return fetch('/tarefas/comentarios/' + commentId + '/delete', {
                method: 'POST',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json',
                },
            }).then(function (response) {
                return response.json().catch(function () { return {}; }).then(function (data) {
                    if (!response.ok || !data.success) {
                        throw new Error((data && data.message) || 'Erro ao excluir comentário.');
                    }
                    return data;
                });
            });
        }

        function handleDrawerAddComment(event) {
            if (!hasDrawer() || !drawerState.itemId) return;
            event.preventDefault();
            if (drawerState.isCommentBusy || isDeleting) return;

            var textarea = getDrawerCommentTextarea();
            var content = (textarea && textarea.value ? textarea.value : '').trim();
            if (!content) {
                if (textarea) textarea.focus();
                refreshDrawerCommentComposer();
                return;
            }

            setDrawerCommentsBusy(true);
            setDrawerCommentsStatus('info', 'Enviando comentário...');
            postCommentAdd(drawerState.itemId, content)
                .then(function (data) {
                    var row = getTaskItemRowById(drawerState.itemId);
                    if (!row) return;
                    appendCommentToTaskItemRow(row, data.comment);
                    syncTaskItemRowMetadata(row);
                    syncCardFromRow(drawerState.itemId);
                    drawerState.forceCommentsBottom = true;
                    syncDrawerFromCurrentRow();
                    if (textarea) {
                        textarea.value = '';
                        resizeDrawerCommentTextarea();
                    }
                    setDrawerCommentsStatus('success', 'Comentário adicionado.', { autoHideMs: 1600 });
                })
                .catch(function (error) {
                    setDrawerCommentsStatus('error', (error && error.message) || 'Erro ao adicionar comentário.');
                })
                .finally(function () {
                    setDrawerCommentsBusy(false);
                    refreshDrawerCommentComposer();
                    if (textarea) textarea.focus();
                });
        }

        function startDrawerCommentEdit(commentId) {
            if (!hasDrawer() || !drawerState.itemId || drawerState.isCommentBusy || isDeleting) return;
            var commentEl = drawerCommentsList.querySelector('.task-item-drawer-comment[data-comment-id="' + commentId + '"]');
            if (!commentEl || commentEl.querySelector('.task-item-drawer-comment-editor')) return;

            var textEl = commentEl.querySelector('.task-item-drawer-comment-text');
            if (!textEl) return;
            var originalText = (textEl.textContent || '').trim();

            textEl.setAttribute('hidden', '');
            var editor = document.createElement('div');
            editor.className = 'task-item-drawer-comment-editor';
            editor.innerHTML =
                '<textarea rows="3" class="task-item-drawer-comment-editor-input"></textarea>' +
                '<div class="task-item-drawer-comment-editor-actions">' +
                '<button type="button" class="task-item-drawer-comment-editor-save">Salvar</button>' +
                '<button type="button" class="task-item-drawer-comment-editor-cancel">Cancelar</button>' +
                '</div>';
            commentEl.appendChild(editor);

            var input = editor.querySelector('.task-item-drawer-comment-editor-input');
            var saveBtn = editor.querySelector('.task-item-drawer-comment-editor-save');
            var cancelBtn = editor.querySelector('.task-item-drawer-comment-editor-cancel');
            input.value = originalText;
            input.focus();

            function closeEditor() {
                if (editor.parentNode) editor.parentNode.removeChild(editor);
                textEl.removeAttribute('hidden');
            }

            function saveEdit() {
                var nextContent = (input.value || '').trim();
                if (!nextContent) {
                    input.focus();
                    return;
                }
                if (nextContent === originalText) {
                    closeEditor();
                    return;
                }

                setDrawerCommentsBusy(true);
                setDrawerCommentsStatus('info', 'Atualizando comentário...');
                postCommentEdit(commentId, nextContent)
                    .then(function (data) {
                        if (!data || !data.comment) {
                            throw new Error('Erro ao editar comentário.');
                        }
                        updateTaskCommentInRow(commentId, data.comment.content, data.comment.updated_at);
                        syncCardFromRow(drawerState.itemId);
                        syncDrawerFromCurrentRow();
                        setDrawerCommentsStatus('success', 'Comentário atualizado.', { autoHideMs: 1400 });
                    })
                    .catch(function (error) {
                        setDrawerCommentsStatus('error', (error && error.message) || 'Erro ao editar comentário.');
                    })
                    .finally(function () {
                        setDrawerCommentsBusy(false);
                    });
            }

            saveBtn.addEventListener('click', saveEdit);
            cancelBtn.addEventListener('click', closeEditor);
            input.addEventListener('keydown', function (event) {
                if (event.key === 'Escape') {
                    event.preventDefault();
                    closeEditor();
                    return;
                }
                if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    saveEdit();
                }
            });
        }

        function handleDrawerDeleteComment(commentId) {
            if (!hasDrawer() || !drawerState.itemId || drawerState.isCommentBusy || isDeleting) return;
            if (!confirm('Excluir comentário?')) return;

            setDrawerCommentsBusy(true);
            setDrawerCommentsStatus('info', 'Excluindo comentário...');
            postCommentDelete(commentId)
                .then(function () {
                    var row = deleteTaskCommentFromRow(commentId);
                    if (row) {
                        syncTaskItemRowMetadata(row);
                        syncCardFromRow(row.getAttribute('data-item-id'));
                    } else {
                        syncCardFromRow(drawerState.itemId);
                    }
                    syncDrawerFromCurrentRow();
                    setDrawerCommentsStatus('success', 'Comentário excluído.', { autoHideMs: 1400 });
                })
                .catch(function (error) {
                    setDrawerCommentsStatus('error', (error && error.message) || 'Erro ao excluir comentário.');
                })
                .finally(function () {
                    setDrawerCommentsBusy(false);
                });
        }

        function getDragAfterElement(dropzone, y) {
            var cards = Array.prototype.slice.call(
                dropzone.querySelectorAll('.task-items-kanban-card:not(.is-dragging)')
            );
            return cards.reduce(function (closest, child) {
                var box = child.getBoundingClientRect();
                var offset = y - box.top - box.height / 2;
                if (offset < 0 && offset > closest.offset) {
                    return { offset: offset, element: child };
                }
                return closest;
            }, { offset: Number.NEGATIVE_INFINITY, element: null }).element;
        }

        function clearDropzoneHover() {
            board.querySelectorAll('.task-items-kanban-dropzone.is-drag-over').forEach(function (zone) {
                zone.classList.remove('is-drag-over');
            });
        }

        function persistKanbanChange(itemId, previousStatus) {
            if (isPersisting || isDeleting) return;
            isPersisting = true;
            board.classList.add('is-persisting');

            var card = board.querySelector('.task-items-kanban-card[data-item-id="' + itemId + '"]');
            if (!card) {
                isPersisting = false;
                board.classList.remove('is-persisting');
                renderKanbanFromList();
                return;
            }

            var nextStatus = normalizeStatus(card.getAttribute('data-status'));
            var statusChanged = normalizeStatus(previousStatus) !== nextStatus;

            var statusPromise = statusChanged
                ? updateItemStatus(itemId, nextStatus, { skipKanbanSync: true, showAlert: false })
                : Promise.resolve();

            statusPromise
                .then(function () {
                    return persistKanbanOrder();
                })
                .then(function () {
                    syncListOrderFromKanban();
                    renderKanbanFromList();
                })
                .catch(function (error) {
                    console.error('Erro ao persistir kanban:', error);
                    renderKanbanFromList();
                    alert('Nao foi possivel persistir a movimentacao no Kanban.');
                })
                .finally(function () {
                    isPersisting = false;
                    board.classList.remove('is-persisting');
                });
        }

        function bindDropzones() {
            var dropzones = board.querySelectorAll('.task-items-kanban-dropzone[data-status]');
            dropzones.forEach(function (dropzone) {
                dropzone.addEventListener('dragenter', function (event) {
                    if (!dragContext || isPersisting || isDeleting) return;
                    event.preventDefault();
                    dropzone.classList.add('is-drag-over');
                });

                dropzone.addEventListener('dragover', function (event) {
                    if (!dragContext || isPersisting || isDeleting) return;
                    event.preventDefault();
                    dropzone.classList.add('is-drag-over');

                    var dragging = board.querySelector('.task-items-kanban-card.is-dragging');
                    if (!dragging) return;
                    var afterElement = getDragAfterElement(dropzone, event.clientY);
                    if (afterElement) {
                        dropzone.insertBefore(dragging, afterElement);
                    } else {
                        dropzone.appendChild(dragging);
                    }
                    setCardStatus(dragging, dropzone.getAttribute('data-status') || 'programado');
                });

                dropzone.addEventListener('dragleave', function (event) {
                    if (!dropzone.contains(event.relatedTarget)) {
                        dropzone.classList.remove('is-drag-over');
                    }
                });

                dropzone.addEventListener('drop', function (event) {
                    if (!dragContext || isPersisting || isDeleting) return;
                    event.preventDefault();
                    dropzone.classList.remove('is-drag-over');
                    suppressCardClickUntil = Date.now() + 220;

                    var itemId = dragContext.itemId;
                    var previousStatus = dragContext.previousStatus;
                    dragContext = null;
                    persistKanbanChange(itemId, previousStatus);
                    updateColumnMeta();
                });
            });
        }

        function bindKanbanComposers() {
            composerControllers = {};
            var composers = kanbanView.querySelectorAll('.task-items-kanban-composer[data-status]');
            var selectedProjectFromFilter = (
                window.TASK_HUB_CONFIG &&
                String(window.TASK_HUB_CONFIG.selectedProject || '').trim()
            ) || '';

            function ensureComposerVisible(composerEl, focusEl, attempt) {
                if (!composerEl || typeof composerEl.getBoundingClientRect !== 'function') return;
                requestAnimationFrame(function () {
                    var tries = Number.isFinite(attempt) ? attempt : 0;
                    var verticalTarget = focusEl && !focusEl.hasAttribute('hidden') ? focusEl : composerEl;
                    var rect = verticalTarget.getBoundingClientRect();
                    var viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
                    var viewportWidth = window.innerWidth || document.documentElement.clientWidth || 0;
                    if (!viewportHeight) return;
                    var topLimit = 90;
                    var bottomLimit = viewportHeight - 22;
                    var deltaY = 0;
                    if (rect.top < topLimit) {
                        deltaY = rect.top - topLimit;
                    } else if (rect.bottom > bottomLimit) {
                        deltaY = rect.bottom - bottomLimit;
                    }
                    if (Math.abs(deltaY) > 1) {
                        window.scrollTo({
                            top: Math.max(0, (window.scrollY || window.pageYOffset || 0) + deltaY),
                            behavior: 'smooth'
                        });
                        if (tries < 2) {
                            setTimeout(function () {
                                ensureComposerVisible(composerEl, focusEl, tries + 1);
                            }, 220);
                        }
                    }

                    var needsInlineAdjust = viewportWidth && (rect.left < 12 || rect.right > (viewportWidth - 12));
                    if (needsInlineAdjust && typeof composerEl.scrollIntoView === 'function') {
                        composerEl.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
                    }
                    var isBaseVisible = rect.bottom <= bottomLimit;
                    if (!isBaseVisible && tries < 2) {
                        setTimeout(function () {
                            ensureComposerVisible(composerEl, focusEl, tries + 1);
                        }, 180);
                    }
                });
            }

            composers.forEach(function (composer) {
                var status = normalizeStatus(composer.getAttribute('data-status') || 'programado');
                var addBtn = composer.querySelector('.task-items-kanban-add-btn[data-status]');
                var form = composer.querySelector('.task-items-kanban-add-form[data-status]');
                var desc = form ? form.querySelector('.task-items-kanban-add-desc') : null;
                var ownerTrigger = form ? form.querySelector('.task-items-kanban-add-owner[data-role="responsavel-trigger"]') : null;
                var cancelBtn = form ? form.querySelector('.task-items-kanban-add-cancel') : null;
                if (!addBtn || !form || !desc || !ownerTrigger || !cancelBtn) return;

                var selectedNames = [];
                var isSaving = false;
                var prioSelect = form.querySelector('.task-items-kanban-add-prioridade');
                var tipoSelect = form.querySelector('.task-items-kanban-add-tipo');
                var projectInput = form.querySelector('.task-items-kanban-add-project-input[data-role="project-input"]');
                var projectValueInput = form.querySelector('.task-items-kanban-add-project-value[data-role="project-value"]');
                var projectDropdown = form.querySelector('.task-hub-kanban-project-dropdown[data-role="project-dropdown"]');
                renderResponsavelPickerTrigger(ownerTrigger, selectedNames, 'Responsável');

                function getComposerProjectValue() {
                    if (selectedProjectFromFilter) return selectedProjectFromFilter;
                    if (projectValueInput) return (projectValueInput.value || '').trim();
                    return '';
                }

                function setupComposerProjectPicker() {
                    if (!projectInput || !projectValueInput || !projectDropdown) return;
                    var options = Array.prototype.slice.call(projectDropdown.querySelectorAll('.project-search-option[data-value]'));
                    var emptyState = projectDropdown.querySelector('[data-empty-state="1"]');

                    function filterOptions() {
                        var q = (projectInput.value || '').trim().toLowerCase();
                        var visibleCount = 0;
                        options.forEach(function (opt) {
                            var label = (opt.getAttribute('data-label') || opt.textContent || '').toLowerCase();
                            var isVisible = !q || label.indexOf(q) !== -1;
                            opt.classList.toggle('hidden-by-filter', !isVisible);
                            if (isVisible) visibleCount += 1;
                        });
                        if (emptyState) {
                            emptyState.hidden = visibleCount > 0;
                        }
                    }

                    function showDrop() {
                        filterOptions();
                        projectDropdown.removeAttribute('hidden');
                        projectInput.setAttribute('aria-expanded', 'true');
                    }

                    function hideDrop() {
                        projectDropdown.setAttribute('hidden', '');
                        projectInput.setAttribute('aria-expanded', 'false');
                    }

                    function selectOption(optionEl) {
                        var value = (optionEl.getAttribute('data-value') || '').trim();
                        var label = optionEl.getAttribute('data-label') || optionEl.textContent || '';
                        projectValueInput.value = value;
                        projectInput.value = label;
                        hideDrop();
                    }

                    projectInput.addEventListener('focus', showDrop);
                    projectInput.addEventListener('input', showDrop);
                    projectInput.addEventListener('keydown', function (event) {
                        if (event.key === 'Escape') {
                            hideDrop();
                            return;
                        }

                        var visibleOptions = options.filter(function (opt) {
                            return !opt.classList.contains('hidden-by-filter');
                        });
                        if (!visibleOptions.length) return;

                        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                            event.preventDefault();
                            var active = projectDropdown.querySelector('.project-search-option.active');
                            var idx = visibleOptions.indexOf(active);
                            if (event.key === 'ArrowDown') {
                                idx = idx < 0 ? 0 : Math.min(idx + 1, visibleOptions.length - 1);
                            } else {
                                idx = idx < 0 ? visibleOptions.length - 1 : Math.max(idx - 1, 0);
                            }
                            visibleOptions.forEach(function (opt, i) {
                                opt.classList.toggle('active', i === idx);
                            });
                            visibleOptions[idx].scrollIntoView({ block: 'nearest' });
                        } else if (event.key === 'Enter') {
                            var current = projectDropdown.querySelector('.project-search-option.active');
                            if (current && !current.classList.contains('hidden-by-filter')) {
                                event.preventDefault();
                                selectOption(current);
                            }
                        }
                    });

                    options.forEach(function (opt) {
                        opt.addEventListener('click', function () {
                            selectOption(opt);
                        });
                    });

                    document.addEventListener('mousedown', function (event) {
                        if (!composer.contains(event.target)) hideDrop();
                    });
                }

                setupComposerProjectPicker();

                function openComposer() {
                    if (isDeleting || isPersisting) return;
                    Object.keys(composerControllers).forEach(function (key) {
                        if (key === status || !composerControllers[key]) return;
                        composerControllers[key].close(true);
                    });
                    addBtn.setAttribute('hidden', '');
                    form.removeAttribute('hidden');
                    ensureComposerVisible(composer, form, 0);
                    setTimeout(function () {
                        desc.focus();
                        ensureComposerVisible(composer, form, 0);
                    }, 30);
                    setTimeout(function () {
                        ensureComposerVisible(composer, form, 0);
                    }, 180);
                }

                function closeComposer(resetValues) {
                    form.setAttribute('hidden', '');
                    addBtn.removeAttribute('hidden');
                    responsavelPickerManager.closeIfAnchor(ownerTrigger);
                    if (resetValues) {
                        desc.value = '';
                        if (prioSelect) prioSelect.value = '';
                        if (tipoSelect) tipoSelect.value = '';
                        if (!selectedProjectFromFilter && projectInput && projectValueInput) {
                            projectInput.value = '';
                            projectValueInput.value = '';
                        }
                        selectedNames = [];
                        renderResponsavelPickerTrigger(ownerTrigger, selectedNames, 'Responsável');
                    }
                }

                function isComposerOpen() {
                    return !form.hasAttribute('hidden');
                }

                function hasComposerValue() {
                    if ((desc.value || '').trim()) return true;
                    if (selectedNames.length) return true;
                    if (prioSelect && (prioSelect.value || '').trim()) return true;
                    if (tipoSelect && (tipoSelect.value || '').trim()) return true;
                    return false;
                }

                function submitComposer(event) {
                    if (event && typeof event.preventDefault === 'function') {
                        event.preventDefault();
                    }
                    if (isSaving || isDeleting || isPersisting) return;
                    if (!window.taskItemsListBridge || typeof window.taskItemsListBridge.requestAddItem !== 'function') {
                        alert('Fluxo de adição indisponível.');
                        return;
                    }

                    var descricao = (desc.value || '').trim();
                    if (!descricao) {
                        desc.focus();
                        return;
                    }
                    var composerProject = getComposerProjectValue();
                    if (!composerProject) {
                        if (projectInput) {
                            projectInput.focus();
                        }
                        alert('Selecione um projeto para criar a tarefa.');
                        return;
                    }

                    isSaving = true;
                    composer.classList.add('is-saving');
                    window.taskItemsListBridge.requestAddItem({
                        project: composerProject,
                        descricao: descricao,
                        status: status,
                        responsavel: selectedNames.join(', '),
                        prioridade: prioSelect ? prioSelect.value : '',
                        tipo_pedido: tipoSelect ? tipoSelect.value : '',
                    })
                        .then(function (data) {
                            window.taskItemsListBridge.insertItemFromPayload(data, { projectValue: composerProject });
                            closeComposer(true);
                            if (currentView === 'kanban') renderKanbanFromList();
                        })
                        .catch(function (error) {
                            alert((error && error.message) || 'Erro ao adicionar tarefa.');
                        })
                        .finally(function () {
                            isSaving = false;
                            composer.classList.remove('is-saving');
                        });
                }

                function trySubmitComposerOutside() {
                    if (isSaving || isDeleting || isPersisting) return false;
                    var descricao = (desc.value || '').trim();
                    if (!descricao) return false;
                    submitComposer();
                    return true;
                }

                addBtn.addEventListener('click', function () {
                    openComposer();
                });
                cancelBtn.addEventListener('click', function () {
                    closeComposer(true);
                });
                form.addEventListener('submit', submitComposer);
                desc.addEventListener('keydown', function (event) {
                    if (event.key === 'Escape') {
                        event.preventDefault();
                        closeComposer(true);
                        return;
                    }
                    if (event.key === 'Enter' && !event.shiftKey) {
                        event.preventDefault();
                        submitComposer(event);
                    }
                });
                ownerTrigger.addEventListener('click', function (event) {
                    event.preventDefault();
                    event.stopPropagation();
                    if (isSaving || isDeleting || isPersisting) return;
                    var composerProject = getComposerProjectValue();
                    if (!composerProject) {
                        if (projectInput) projectInput.focus();
                        alert('Selecione um projeto para escolher responsáveis.');
                        return;
                    }
                    responsavelPickerManager.open({
                        anchorEl: ownerTrigger,
                        taskId: taskId,
                        sugestoesUrl: listEl.getAttribute('data-sugestoes-url') || '',
                        projectValue: composerProject,
                        initialRawValue: selectedNames.join(', '),
                        onApply: function (payload) {
                            selectedNames = payload.names.slice();
                            renderResponsavelPickerTrigger(ownerTrigger, selectedNames, 'Responsável');
                            return true;
                        },
                    });
                });

                composerControllers[status] = {
                    open: openComposer,
                    close: closeComposer,
                    isOpen: isComposerOpen,
                    hasValue: hasComposerValue,
                    trySubmitOutside: trySubmitComposerOutside,
                    containsTarget: function (target) {
                        return !!(target && composer.contains(target));
                    },
                    focus: function () {
                        openComposer();
                        setTimeout(function () { desc.focus(); }, 20);
                    },
                };
            });

            document.addEventListener('mousedown', function (event) {
                if (currentView !== 'kanban') return;
                if (responsavelPickerManager.isEventInsidePopover(event.target)) return;
                Object.keys(composerControllers).forEach(function (key) {
                    var controller = composerControllers[key];
                    if (!controller || typeof controller.isOpen !== 'function' || !controller.isOpen()) return;
                    if (typeof controller.containsTarget === 'function' && controller.containsTarget(event.target)) return;
                    if (typeof controller.hasValue === 'function' && controller.hasValue()) {
                        if (typeof controller.trySubmitOutside === 'function' && controller.trySubmitOutside()) return;
                        return;
                    }
                    controller.close(true);
                });
            });
        }

        function focusComposerForStatus(status) {
            if (currentView !== 'kanban') return false;
            var normalized = normalizeStatus(status || 'programado');
            var controller = composerControllers[normalized];
            if (!controller || typeof controller.focus !== 'function') return false;
            var column = kanbanView.querySelector('.task-items-kanban-column[data-status="' + normalized + '"]');
            if (column && typeof column.scrollIntoView === 'function') {
                column.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
            }
            controller.focus();
            return true;
        }

        function escapeAnexoHtml(s) {
            var d = document.createElement('div');
            d.textContent = s;
            return d.innerHTML;
        }

        function renderDrawerAnexoItem(anexo) {
            var el = document.createElement('div');
            el.className = 'task-item-drawer-anexo-item';
            el.setAttribute('data-anexo-id', anexo.id);

            var isImg = !!anexo.is_image;
            var preview = '';
            if (isImg) {
                preview = '<img class="task-item-drawer-anexo-thumb" src="' + escapeAnexoHtml(anexo.url) + '" alt="' + escapeAnexoHtml(anexo.filename) + '" loading="lazy">';
            } else {
                preview = '<span class="task-item-drawer-anexo-icon"><i class="fas fa-file" aria-hidden="true"></i></span>';
            }

            el.innerHTML =
                '<a class="task-item-drawer-anexo-link" href="' + escapeAnexoHtml(anexo.url) + '" target="_blank" rel="noopener" data-filename="' + escapeAnexoHtml(anexo.filename) + '" data-content-type="' + escapeAnexoHtml(anexo.content_type || '') + '" data-is-image="' + (isImg ? '1' : '0') + '">' +
                preview +
                '<span class="task-item-drawer-anexo-name">' + escapeAnexoHtml(anexo.filename) + '</span>' +
                '</a>' +
                '<button type="button" class="task-item-drawer-anexo-del" data-action="delete-anexo" data-anexo-id="' + anexo.id + '" title="Remover anexo">' +
                '<i class="fas fa-times" aria-hidden="true"></i>' +
                '</button>';
            return el;
        }

        function loadDrawerAnexos(itemId) {
            if (!drawerAnexosList) return;
            drawerAnexosList.innerHTML = '<span class="task-item-drawer-anexos-loading">Carregando...</span>';

            fetch('/tarefas/' + itemId + '/anexos', {
                headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' },
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (!data.success) throw new Error(data.message || 'Erro ao carregar anexos.');
                    drawerAnexosList.innerHTML = '';
                    if (!data.anexos.length) {
                        var empty = document.createElement('p');
                        empty.className = 'task-item-drawer-anexos-empty';
                        empty.textContent = 'Nenhum anexo nesta tarefa.';
                        drawerAnexosList.appendChild(empty);
                    } else {
                        data.anexos.forEach(function (a) {
                            drawerAnexosList.appendChild(renderDrawerAnexoItem(a));
                        });
                    }
                    var row = getTaskItemRowById(itemId);
                    if (row) setTaskItemAnexosCount(row, data.count);
                    if (drawerAnexosCount) drawerAnexosCount.textContent = String(data.count);
                })
                .catch(function (e) {
                    if (drawerAnexosList) drawerAnexosList.innerHTML = '<p class="task-item-drawer-anexos-error">' + (e && e.message || 'Erro') + '</p>';
                });
        }

        function uploadDrawerAnexo(itemId, file) {
            if (!file || !itemId) return;
            var formData = new FormData();
            formData.append('file', file);

            var uploadingEl = document.createElement('div');
            uploadingEl.className = 'task-item-drawer-anexo-uploading';
            uploadingEl.textContent = 'Enviando ' + file.name + '...';
            if (drawerAnexosList) drawerAnexosList.appendChild(uploadingEl);

            fetch('/tarefas/' + itemId + '/anexos/add', {
                method: 'POST',
                headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' },
                body: formData,
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (!data.success) throw new Error(data.message || 'Erro ao enviar.');
                    if (uploadingEl.parentNode) uploadingEl.parentNode.removeChild(uploadingEl);
                    var emptyEl = drawerAnexosList ? drawerAnexosList.querySelector('.task-item-drawer-anexos-empty') : null;
                    if (emptyEl) emptyEl.parentNode.removeChild(emptyEl);
                    if (drawerAnexosList) drawerAnexosList.appendChild(renderDrawerAnexoItem(data.anexo));
                    var row = getTaskItemRowById(itemId);
                    if (row) setTaskItemAnexosCount(row, data.anexos_count);
                    if (drawerAnexosCount) drawerAnexosCount.textContent = String(data.anexos_count);
                    if (window.taskItemsKanban && typeof window.taskItemsKanban.syncItemFromRow === 'function') {
                        window.taskItemsKanban.syncItemFromRow(itemId);
                    }
                })
                .catch(function (e) {
                    if (uploadingEl.parentNode) uploadingEl.parentNode.removeChild(uploadingEl);
                    alert((e && e.message) || 'Erro ao enviar anexo.');
                });
        }

        function handleDrawerAnexoDelete(anexoId) {
            if (!anexoId || !drawerState.itemId) return;
            if (!confirm('Remover este anexo?')) return;

            fetch('/tarefas/anexos/' + anexoId + '/delete', {
                method: 'POST',
                headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' },
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (!data.success) throw new Error(data.message || 'Erro ao excluir.');
                    var itemEl = drawerAnexosList ? drawerAnexosList.querySelector('[data-anexo-id="' + anexoId + '"]') : null;
                    if (itemEl) itemEl.parentNode.removeChild(itemEl);
                    var row = getTaskItemRowById(drawerState.itemId);
                    if (row) setTaskItemAnexosCount(row, data.anexos_count);
                    if (drawerAnexosCount) drawerAnexosCount.textContent = String(data.anexos_count);
                    if (drawerAnexosList && !drawerAnexosList.querySelector('.task-item-drawer-anexo-item')) {
                        var empty = document.createElement('p');
                        empty.className = 'task-item-drawer-anexos-empty';
                        empty.textContent = 'Nenhum anexo nesta tarefa.';
                        drawerAnexosList.appendChild(empty);
                    }
                    if (window.taskItemsKanban && typeof window.taskItemsKanban.syncItemFromRow === 'function') {
                        window.taskItemsKanban.syncItemFromRow(drawerState.itemId);
                    }
                })
                .catch(function (e) {
                    alert((e && e.message) || 'Erro ao remover anexo.');
                });
        }

        function bindDrawerEvents() {
            if (!hasDrawer()) return;

            drawerClose.addEventListener('click', closeDrawer);
            drawerBackdrop.addEventListener('click', closeDrawer);
            drawerDeleteIcon.addEventListener('click', function () {
                if (!drawerState.itemId || drawerState.isSaving || isDeleting) return;
                setDrawerDeleteConfirmVisible(true);
            });
            drawerDeleteCancel.addEventListener('click', function () {
                setDrawerDeleteConfirmVisible(false);
            });
            drawerDeleteConfirmBtn.addEventListener('click', function () {
                if (!drawerState.itemId || isDeleting || drawerState.isSaving) return;
                deleteKanbanItem(String(drawerState.itemId));
            });

            drawerCommentsToggle.addEventListener('click', function () {
                if (!drawerState.itemId || isDeleting) return;
                setDrawerCommentsExpanded(!drawerState.isCommentsExpanded);
            });
            drawerCommentsToggle.addEventListener('keydown', function (event) {
                if (event.key !== 'Enter' && event.key !== ' ') return;
                event.preventDefault();
                drawerCommentsToggle.click();
            });

            drawerResponsavelTrigger.addEventListener('click', function (event) {
                event.preventDefault();
                event.stopPropagation();
                if (!drawerState.itemId || isDeleting) return;
                var drawerProjectValue = getTaskItemProjectValue(drawerState.itemId);
                if (!drawerProjectValue) {
                    alert('Projeto não encontrado para esta tarefa.');
                    return;
                }

                responsavelPickerManager.open({
                    anchorEl: drawerResponsavelTrigger,
                    taskId: taskId,
                    sugestoesUrl: listEl.getAttribute('data-sugestoes-url') || '',
                    projectValue: drawerProjectValue,
                    initialRawValue: drawerState.responsavelNames.join(', '),
                    onApply: function (payload) {
                        setDrawerResponsavel(payload.names.slice());
                        if (payload && payload.dirty) {
                            scheduleDrawerAutosave({ immediate: true });
                        }
                        return true;
                    },
                });
            });

            drawerDesc.addEventListener('input', function () {
                if (!drawerState.itemId || isDeleting) return;
                drawerTitle.textContent = (drawerDesc.value || '').trim() || 'Item sem descrição';
                resizeDrawerDescTextarea();
                scheduleDrawerAutosave();
            });
            drawerDesc.addEventListener('change', function () {
                if (!drawerState.itemId || isDeleting) return;
                resizeDrawerDescTextarea();
            });
            drawerDesc.addEventListener('keyup', function () {
                if (!drawerState.itemId || isDeleting) return;
                resizeDrawerDescTextarea();
            });
            drawerDesc.addEventListener('blur', function () {
                if (!drawerState.itemId || isDeleting) return;
                flushDrawerAutosave('blur');
            });

            if (drawerPrioridade) {
                drawerPrioridade.addEventListener('change', function () {
                    if (!drawerState.itemId || isDeleting) return;
                    scheduleDrawerAutosave({ immediate: true });
                });
            }
            if (drawerTipoPedido) {
                drawerTipoPedido.addEventListener('change', function () {
                    if (!drawerState.itemId || isDeleting) return;
                    scheduleDrawerAutosave({ immediate: true });
                });
            }

            if (drawerAnexosToggle) {
                drawerAnexosToggle.addEventListener('click', function () {
                    if (!drawerState.itemId) return;
                    var expanded = drawerAnexosToggle.getAttribute('aria-expanded') === 'true';
                    drawerAnexosToggle.setAttribute('aria-expanded', expanded ? 'false' : 'true');
                    drawerAnexosToggle.classList.toggle('is-expanded', !expanded);
                    if (drawerAnexosBody) {
                        if (expanded) {
                            drawerAnexosBody.setAttribute('hidden', '');
                        } else {
                            drawerAnexosBody.removeAttribute('hidden');
                            loadDrawerAnexos(drawerState.itemId);
                        }
                    }
                });
            }

            if (drawerAnexoInput) {
                drawerAnexoInput.addEventListener('change', function () {
                    if (!drawerState.itemId || !drawerAnexoInput.files || !drawerAnexoInput.files.length) return;
                    var file = drawerAnexoInput.files[0];
                    uploadDrawerAnexo(drawerState.itemId, file);
                    drawerAnexoInput.value = '';
                });
            }

            if (quickAnexoInput) {
                quickAnexoInput.addEventListener('change', function () {
                    if (!quickAnexoInput.files || !quickAnexoInput.files.length) {
                        quickUploadState.itemId = null;
                        return;
                    }
                    var itemId = quickUploadState.itemId;
                    var file = quickAnexoInput.files[0];
                    quickAnexoInput.value = '';
                    quickUploadState.itemId = null;
                    if (!itemId || !file) return;
                    performQuickAnexoUpload(itemId, file).catch(function (error) {
                        alert((error && error.message) || 'Erro ao enviar anexo.');
                    });
                });
            }

            var commentTextarea = getDrawerCommentTextarea();
            if (commentTextarea) {
                commentTextarea.addEventListener('input', function () {
                    resizeDrawerCommentTextarea();
                    refreshDrawerCommentComposer();
                    if (!drawerState.isCommentBusy) {
                        setDrawerCommentsStatus();
                    }
                });
            }

            drawerCommentForm.addEventListener('submit', handleDrawerAddComment);
            drawerCommentForm.addEventListener('keydown', function (event) {
                if (!(event.target && event.target.matches('textarea[name="content"]'))) return;
                if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    if (drawerCommentForm.requestSubmit) drawerCommentForm.requestSubmit();
                    else drawerCommentForm.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
                }
            });

            drawerCommentsList.addEventListener('click', function (event) {
                var editBtn = event.target.closest('[data-action="edit-comment"][data-comment-id]');
                if (editBtn) {
                    event.preventDefault();
                    startDrawerCommentEdit(editBtn.getAttribute('data-comment-id'));
                    return;
                }

                var delBtn = event.target.closest('[data-action="delete-comment"][data-comment-id]');
                if (delBtn) {
                    event.preventDefault();
                    handleDrawerDeleteComment(delBtn.getAttribute('data-comment-id'));
                }
            });

            if (drawerAnexosList) {
                drawerAnexosList.addEventListener('click', function (event) {
                    var delBtn = event.target.closest('[data-action="delete-anexo"][data-anexo-id]');
                    if (delBtn) {
                        event.preventDefault();
                        handleDrawerAnexoDelete(delBtn.getAttribute('data-anexo-id'));
                        return;
                    }
                    var anexoLink = event.target.closest('.task-item-drawer-anexo-link');
                    if (anexoLink) {
                        event.preventDefault();
                        openAnexoPreviewModal({
                            url: anexoLink.getAttribute('href') || '',
                            filename: anexoLink.getAttribute('data-filename') || 'Anexo',
                            contentType: anexoLink.getAttribute('data-content-type') || '',
                            isImage: anexoLink.getAttribute('data-is-image') === '1',
                        });
                    }
                });
            }

            document.addEventListener('keydown', function (event) {
                if (event.key === 'Escape' && drawerState.itemId) {
                    if (previewState.isOpen) return;
                    if (!drawerDeleteConfirm.hasAttribute('hidden')) {
                        setDrawerDeleteConfirmVisible(false);
                        return;
                    }
                    closeDrawer();
                }
            });

            resizeDrawerCommentTextarea();
            resizeDrawerDescTextarea();
            refreshDrawerCommentComposer();
        }

        function bindBoardEvents() {
            board.addEventListener('click', function (event) {
                var openCommentsBtn = event.target.closest('.task-items-kanban-comments[data-action="kanban-open-comments"][data-item-id]');
                if (openCommentsBtn) {
                    event.preventDefault();
                    event.stopPropagation();
                    if (isDeleting || isPersisting) return;
                    closeAllCardDeleteConfirms();
                    openDrawerComments(openCommentsBtn.getAttribute('data-item-id'));
                    return;
                }

                var openAnexosBtn = event.target.closest('.task-items-kanban-anexos[data-action="kanban-open-anexos"][data-item-id]');
                if (openAnexosBtn) {
                    event.preventDefault();
                    event.stopPropagation();
                    if (isDeleting || isPersisting) return;
                    closeAllCardDeleteConfirms();
                    openItemAnexoAction(openAnexosBtn.getAttribute('data-item-id'));
                    return;
                }

                var deleteTrigger = event.target.closest('.task-items-kanban-delete-btn[data-action="kanban-delete"][data-item-id]');
                if (deleteTrigger) {
                    event.preventDefault();
                    event.stopPropagation();
                    if (isDeleting || isPersisting) return;
                    var triggerCard = deleteTrigger.closest('.task-items-kanban-card[data-item-id]');
                    if (!triggerCard) return;
                    var triggerConfirmBox = triggerCard.querySelector('.task-items-kanban-delete-confirm[data-role="delete-confirm"]');
                    var shouldOpen = !!(triggerConfirmBox && triggerConfirmBox.hasAttribute('hidden'));
                    closeAllCardDeleteConfirms(triggerCard);
                    if (triggerConfirmBox) {
                        if (shouldOpen) {
                            triggerCard.classList.add('is-delete-confirming');
                            triggerConfirmBox.removeAttribute('hidden');
                        } else {
                            closeCardDeleteConfirm(triggerCard);
                        }
                    }
                    return;
                }

                var cancelDeleteBtn = event.target.closest('[data-action="kanban-delete-cancel"]');
                if (cancelDeleteBtn) {
                    event.preventDefault();
                    var cancelCard = cancelDeleteBtn.closest('.task-items-kanban-card[data-item-id]');
                    closeCardDeleteConfirm(cancelCard);
                    return;
                }

                var confirmDeleteBtn = event.target.closest('[data-action="kanban-delete-confirm"]');
                if (confirmDeleteBtn) {
                    event.preventDefault();
                    var confirmCard = confirmDeleteBtn.closest('.task-items-kanban-card[data-item-id]');
                    if (!confirmCard || isDeleting || isPersisting) return;
                    deleteKanbanItem(confirmCard.getAttribute('data-item-id'));
                    return;
                }

                if (event.target.closest('.task-items-kanban-delete-confirm[data-role="delete-confirm"]')) {
                    return;
                }

                var card = event.target.closest('.task-items-kanban-card[data-item-id]');
                if (!card) {
                    closeAllCardDeleteConfirms();
                    return;
                }

                if (!card || isDeleting || isPersisting || Date.now() < suppressCardClickUntil) return;
                closeAllCardDeleteConfirms();
                openDrawer(card.getAttribute('data-item-id'));
            });

            board.addEventListener('keydown', function (event) {
                if (event.key === 'Escape') {
                    closeAllCardDeleteConfirms();
                    return;
                }
                var card = event.target.closest('.task-items-kanban-card[data-item-id]');
                if (!card) return;
                if (event.target.closest('.task-items-kanban-delete-btn, .task-items-kanban-delete-confirm, .task-items-kanban-comments, .task-items-kanban-anexos')) return;
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    if (!isDeleting && !isPersisting && Date.now() >= suppressCardClickUntil) {
                        openDrawer(card.getAttribute('data-item-id'));
                    }
                }
            });

            board.addEventListener('dragstart', function (event) {
                var card = event.target.closest('.task-items-kanban-card[data-item-id]');
                if (!card || isPersisting || isDeleting) return;
                if (event.target.closest('.task-items-kanban-delete-btn, .task-items-kanban-delete-confirm, .task-items-kanban-comments, .task-items-kanban-anexos')) {
                    event.preventDefault();
                    return;
                }
                closeAllCardDeleteConfirms();

                dragContext = {
                    itemId: card.getAttribute('data-item-id'),
                    previousStatus: card.getAttribute('data-status') || 'programado',
                };
                card.classList.add('is-dragging');
                if (event.dataTransfer) {
                    event.dataTransfer.effectAllowed = 'move';
                    event.dataTransfer.setData('text/plain', dragContext.itemId || '');
                }
            });

            board.addEventListener('dragend', function () {
                var dragging = board.querySelector('.task-items-kanban-card.is-dragging');
                if (dragging) dragging.classList.remove('is-dragging');
                suppressCardClickUntil = Date.now() + 140;
                clearDropzoneHover();
                updateColumnMeta();
            });
        }

        function applyView(mode, opts) {
            var targetMode = mode === 'kanban' ? 'kanban' : 'list';
            var options = opts || {};
            currentView = targetMode;

            listView.hidden = targetMode !== 'list';
            kanbanView.hidden = targetMode !== 'kanban';
            listView.classList.toggle('is-active', targetMode === 'list');
            kanbanView.classList.toggle('is-active', targetMode === 'kanban');
            setToggleActiveState(targetMode, { animate: options.animateToggle !== false });

            if (targetMode === 'kanban') {
                renderKanbanFromList();
            } else {
                closeAllCardDeleteConfirms();
                closeDrawer();
            }

            if (options.persist !== false) {
                saveStoredView(targetMode);
            }
        }

        function handleToggleClick(event) {
            var button = event.target.closest('.task-items-view-btn[data-view]');
            if (!button) return;
            event.preventDefault();
            applyView(button.getAttribute('data-view'), { animateToggle: true });
        }

        function init() {
            toggleRoot.addEventListener('click', handleToggleClick);
            bindBoardEvents();
            bindDropzones();
            bindKanbanComposers();
            bindDrawerEvents();
            bindAnexoPreviewModalEvents();
            renderKanbanFromList();
            applyView(readStoredView(), { persist: false, animateToggle: false });
        }

        init();

        return {
            applyView: applyView,
            getCurrentView: function () { return currentView; },
            rebuildFromList: renderKanbanFromList,
            focusComposerForStatus: focusComposerForStatus,
            syncItemFromRow: function (itemId) {
                if (itemId) {
                    syncCardFromRow(String(itemId));
                    if (drawerState.itemId && drawerState.itemId === String(itemId)) {
                        syncDrawerFromCurrentRow();
                    }
                    return;
                }

                if (currentView === 'kanban') {
                    renderKanbanFromList();
                }
                if (drawerState.itemId) {
                    syncDrawerFromCurrentRow();
                }
            },
            openDrawerAnexos: openDrawerAnexos,
            openDrawerComments: openDrawerComments,
            openItemAnexoAction: openItemAnexoAction,
        };
    })();

    window.taskItemsKanban = taskItemsKanbanManager;

    (function initArchiveFinalizedTasksForm() {
        var root = document.getElementById('taskHubPage');
        var archiveForm = document.getElementById('archiveFinalizedTasksForm');
        if (!root || !archiveForm) return;

        archiveForm.addEventListener('submit', function (event) {
            if (event.defaultPrevented) return;
            event.preventDefault();

            var formData = new FormData(archiveForm);
            fetch(archiveForm.action, {
                method: 'POST',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json',
                },
                body: formData,
            })
                .then(function (response) {
                    return response.json().catch(function () { return {}; }).then(function (data) {
                        if (!response.ok || !data.success) {
                            throw new Error((data && data.message) || 'Erro ao arquivar tarefas.');
                        }
                        return data;
                    });
                })
                .then(function (data) {
                    var archivedIds = Array.isArray(data.archived_task_ids) ? data.archived_task_ids : [];
                    if (!archivedIds.length) {
                        alert((data && data.message) || 'Nenhuma tarefa finalizada para arquivar no escopo atual.');
                        return;
                    }

                    archivedIds.forEach(function (itemId) {
                        removeTaskItemFromDom(String(itemId));
                    });

                    if (window.taskItemsKanban && typeof window.taskItemsKanban.rebuildFromList === 'function') {
                        window.taskItemsKanban.rebuildFromList();
                    }

                    ensureTaskHubEmptyState(root);
                })
                .catch(function (error) {
                    alert((error && error.message) || 'Erro ao arquivar tarefas.');
                });
        });
    })();

    (function initArchivedTaskActions() {
        var root = document.getElementById('taskHubPage');
        if (!root || root.getAttribute('data-archived-mode') !== '1') return;

        document.addEventListener('submit', function (event) {
            var form = event.target;
            if (!form || !form.classList || !form.classList.contains('task-item-unarchive-form')) return;
            if (event.defaultPrevented) return;
            event.preventDefault();

            var itemRow = form.closest('.task-item-row[data-item-id]');
            var itemId = itemRow ? String(itemRow.getAttribute('data-item-id') || '') : '';
            if (!itemId) return;

            var formData = new FormData(form);
            fetch(form.action, {
                method: 'POST',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json',
                },
                body: formData,
            })
                .then(function (response) {
                    return response.json().catch(function () { return {}; }).then(function (data) {
                        if (!response.ok || !data.success) {
                            throw new Error((data && data.message) || 'Erro ao desarquivar tarefa.');
                        }
                        return data;
                    });
                })
                .then(function () {
                    removeTaskItemFromDom(itemId);
                    updateTaskHubArchiveCounter(1);
                    ensureTaskHubEmptyState(root);
                })
                .catch(function (error) {
                    alert((error && error.message) || 'Erro ao desarquivar tarefa.');
                });
        });
    })();

    // Expandir/recolher comentários com animação suave
    function clearCommentsTransition(body) {
        if (body && body._commentsTransitionEndHandler) {
            body.removeEventListener('transitionend', body._commentsTransitionEndHandler);
            body._commentsTransitionEndHandler = null;
        }
    }

    function isReducedMotionPreferred() {
        return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    }

    function expandComments(body) {
        if (!body) return;

        if (isReducedMotionPreferred()) {
            body.removeAttribute('hidden');
            body.classList.add('is-open');
            body.style.maxHeight = '';
            return;
        }

        clearCommentsTransition(body);
        body.removeAttribute('hidden');
        body.classList.add('is-open');
        body.style.maxHeight = '0px';
        body.offsetHeight; // força reflow para garantir início da transição
        body.style.maxHeight = body.scrollHeight + 'px';

        body._commentsTransitionEndHandler = function (event) {
            if (event.target !== body || event.propertyName !== 'max-height') return;
            body.style.maxHeight = 'none';
            clearCommentsTransition(body);
        };
        body.addEventListener('transitionend', body._commentsTransitionEndHandler);
    }

    function collapseComments(body) {
        if (!body) return;

        if (isReducedMotionPreferred()) {
            body.classList.remove('is-open');
            body.setAttribute('hidden', '');
            body.style.maxHeight = '';
            return;
        }

        clearCommentsTransition(body);
        if (body.hasAttribute('hidden')) return;

        body.style.maxHeight = body.scrollHeight + 'px';
        body.offsetHeight; // fixa altura atual antes de recolher
        body.classList.remove('is-open');
        body.style.maxHeight = '0px';

        body._commentsTransitionEndHandler = function (event) {
            if (event.target !== body || event.propertyName !== 'max-height') return;
            body.setAttribute('hidden', '');
            body.style.maxHeight = '';
            clearCommentsTransition(body);
        };
        body.addEventListener('transitionend', body._commentsTransitionEndHandler);
    }

    function toggleComments(btn) {
        var targetId = btn.getAttribute('data-target');
        var body = document.getElementById(targetId);
        if (!body) return;

        var isExpanded = btn.getAttribute('aria-expanded') === 'true';

        if (isExpanded) {
            btn.setAttribute('aria-expanded', 'false');
            collapseComments(body);
        } else {
            btn.setAttribute('aria-expanded', 'true');
            expandComments(body);
        }
    }

    // ===== EDIÇÃO INLINE DA DESCRIÇÃO =====
    function inlineEditDesc(descEl) {
        var itemId = descEl.getAttribute('data-item-id');
        if (!itemId) return;
        var row = descEl.closest('.task-item-row');
        if (!row) return;
        var descWrap = descEl.closest('.task-item-desc-wrap');
        if (!descWrap || descWrap.classList.contains('editing')) return;
        descWrap.classList.add('editing');
        descEl.classList.add('task-item-desc-editing-active');

        var originalText = descEl.textContent.trim();

        var input = document.createElement('textarea');
        input.rows = 1;
        input.className = 'task-item-desc-editing';
        input.value = originalText;

        function resizeEditor() {
            input.style.height = 'auto';
            input.style.height = Math.max(32, input.scrollHeight) + 'px';
        }

        descEl.setAttribute('hidden', '');
        descEl.parentNode.insertBefore(input, descEl.nextSibling);
        input.focus();
        resizeEditor();
        input.setSelectionRange(input.value.length, input.value.length);

        var saving = false;
        var finished = false;

        function handlePointerDownOutside(event) {
            if (saving || finished) return;
            if (descWrap.contains(event.target)) return;
            saveDesc();
        }

        function restoreUi(text) {
            if (finished) return;
            finished = true;
            document.removeEventListener('pointerdown', handlePointerDownOutside, true);
            descEl.textContent = text;
            descEl.removeAttribute('hidden');
            descEl.classList.remove('task-item-desc-editing-active');
            descWrap.classList.remove('editing');
            if (input.parentNode) input.parentNode.removeChild(input);
        }

        function saveDesc() {
            if (saving || finished) return;
            var newText = (input.value || '').trim();
            if (!newText) {
                restoreUi(originalText);
                return;
            }
            if (newText === originalText) {
                restoreUi(originalText);
                return;
            }

            saving = true;
            input.disabled = true;

            var payload = {
                descricao: newText,
                status: getTaskItemStatus(row),
                responsavel: getTaskItemResponsavel(row),
            };

            persistTaskItemDetails(itemId, payload)
                .then(function (data) {
                    if (!data || !data.item) {
                        throw new Error('Erro ao salvar.');
                    }
                    updateTaskItemRowFromPayload(data.item);
                    restoreUi(data.item.descricao);
                    if (window.taskItemsKanban && typeof window.taskItemsKanban.syncItemFromRow === 'function') {
                        window.taskItemsKanban.syncItemFromRow(itemId);
                    }
                })
                .catch(function (error) {
                    alert((error && error.message) || 'Erro ao salvar.');
                    restoreUi(originalText);
                });
        }

        input.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); saveDesc(); }
            if (e.key === 'Escape') { e.preventDefault(); restoreUi(originalText); }
        });
        input.addEventListener('input', resizeEditor);

        input.addEventListener('blur', function () {
            setTimeout(function () {
                if (!saving && !finished && document.body.contains(input)) {
                    saveDesc();
                }
            }, 150);
        });

        document.addEventListener('pointerdown', handlePointerDownOutside, true);
    }

    function setResponsavelCellText(respSpan, text) {
        if (!respSpan) return;
        var value = normalizeResponsavelName(text || '');
        if (value) {
            respSpan.textContent = value;
        } else {
            respSpan.innerHTML = '<em class="responsavel-placeholder">Responsável não informado</em>';
        }
    }

    // ===== EDIÇÃO INLINE DO RESPONSÁVEL =====
    function inlineEditResponsavel(respSpan) {
        var itemId = respSpan.getAttribute('data-item-id');
        if (!itemId) return;
        var row = respSpan.closest('.task-item-row');
        if (!row) return;
        if (respSpan.classList.contains('task-item-resp-editing-active')) return;

        var listEl = row.closest('.task-items-list');
        if (!listEl) return;
        var sugestoesUrl = listEl.getAttribute('data-sugestoes-url');
        var taskId = listEl.getAttribute('data-task-id');
        if (!sugestoesUrl) return;
        var projectValue = String(row.getAttribute('data-project-value') || '').trim();
        if (!projectValue) return;

        var placeholderEl = respSpan.querySelector('.responsavel-placeholder');
        var originalText = placeholderEl ? '' : respSpan.textContent.trim();
        if (originalText === '\u00a0') originalText = '';

        respSpan.classList.add('task-item-resp-editing-active');

        responsavelPickerManager.open({
            anchorEl: respSpan,
            taskId: taskId,
            sugestoesUrl: sugestoesUrl,
            projectValue: projectValue,
            initialRawValue: originalText,
            onCancel: function () {
                respSpan.classList.remove('task-item-resp-editing-active');
            },
            onApply: function (payload) {
                if (!payload.dirty) {
                    respSpan.classList.remove('task-item-resp-editing-active');
                    return true;
                }

                return persistTaskItemDetails(itemId, {
                    descricao: getTaskItemDescricao(row),
                    status: getTaskItemStatus(row),
                    responsavel: payload.value || '',
                })
                    .then(function (data) {
                        if (!data || !data.item) {
                            throw new Error('Erro ao salvar.');
                        }
                        updateTaskItemRowFromPayload(data.item);
                        if (window.taskItemsKanban && typeof window.taskItemsKanban.syncItemFromRow === 'function') {
                            window.taskItemsKanban.syncItemFromRow(itemId);
                        }
                        respSpan.classList.remove('task-item-resp-editing-active');
                        return true;
                    })
                    .catch(function (error) {
                        respSpan.classList.remove('task-item-resp-editing-active');
                        throw error;
                    });
            },
        });
    }

    // ===== DELEGAÇÃO DE EVENTOS PARA EDIÇÃO INLINE =====
    var taskItemsListEl = document.querySelector('.task-items-list');
    if (taskItemsListEl) {
        taskItemsListEl.addEventListener('click', function (e) {
            // Edição da descrição somente pelo botão de caneta
            var editBtn = e.target.closest('.task-item-desc-edit-btn[data-item-id]');
            if (editBtn) {
                e.preventDefault();
                var row = editBtn.closest('.task-item-row');
                var desc = row ? row.querySelector('.task-item-desc[data-item-id]') : null;
                if (desc && !desc.classList.contains('task-item-desc-editing-active')) {
                    inlineEditDesc(desc);
                }
                return;
            }
            // Edição inline do responsável
            var resp = e.target.closest('.task-item-responsavel[data-item-id]');
            if (resp && !resp.classList.contains('task-item-resp-editing-active')) {
                e.preventDefault();
                inlineEditResponsavel(resp);
                return;
            }
            // Botão de anexos - ação contextual (upload direto sem anexo; drawer se já houver anexo)
            var anexosBtn = e.target.closest('.task-item-anexos-btn[data-item-id]');
            if (anexosBtn) {
                e.preventDefault();
                var itemId = anexosBtn.getAttribute('data-item-id');
                if (itemId && window.taskItemsKanban) {
                    if (typeof window.taskItemsKanban.openItemAnexoAction === 'function') {
                        window.taskItemsKanban.openItemAnexoAction(itemId);
                    } else if (typeof window.taskItemsKanban.openDrawerAnexos === 'function') {
                        window.taskItemsKanban.openDrawerAnexos(itemId);
                    }
                }
                return;
            }
        });
    }

    // Enviar comentário via AJAX (sem recarregar e sem recolher a seção)
    function handleCommentFormSubmit(form) {
        var textarea = form.querySelector('textarea');
        var content = (textarea && textarea.value) ? textarea.value.trim() : '';
        if (!content) return;

        var btn = form.querySelector('button[type="submit"]');
        if (btn) btn.disabled = true;
        var formData = new FormData(form);

        fetch(form.action, {
            method: 'POST',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'Accept': 'application/json',
            },
            body: formData,
        })
            .then(function (response) {
                return response.json().catch(function () { return {}; }).then(function (data) {
                    if (!response.ok || !data.success) {
                        throw new Error((data && data.message) || 'Erro ao enviar comentário.');
                    }
                    return data;
                });
            })
            .then(function (data) {
                var row = form.closest('.task-item-row');
                if (!row) return;
                appendCommentToTaskItemRow(row, data.comment);
                syncTaskItemRowMetadata(row);
                if (window.taskItemsKanban && typeof window.taskItemsKanban.syncItemFromRow === 'function') {
                    window.taskItemsKanban.syncItemFromRow(row.getAttribute('data-item-id'));
                }
                if (textarea) textarea.value = '';
            })
            .catch(function (error) {
                alert((error && error.message) || 'Erro ao enviar comentário. Tente novamente.');
            })
            .finally(function () {
                if (btn) btn.disabled = false;
            });
    }

    document.addEventListener('submit', function (e) {
        if (!e.target || !e.target.classList || !e.target.classList.contains('task-comment-form')) return;
        e.preventDefault();
        handleCommentFormSubmit(e.target);
    });

    // Enter no textarea de comentário envia o formulário (Shift+Enter = nova linha). Delegação para funcionar em formulários adicionados depois.
    (document.querySelector('.task-items-list') || document.body).addEventListener('keydown', function (e) {
        if (e.target.matches && e.target.matches('.task-comment-form textarea')) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                var form = e.target.closest('form');
                if (form) {
                    if (form.requestSubmit) form.requestSubmit(); else form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
                }
            }
        }
    });

    // Edição inline de comentário (sem modal). Enter = salvar, Esc = cancelar
    function openEditComment(commentId, content) {
        var commentEl = document.getElementById('comment-' + commentId);
        if (!commentEl) return;
        var textEl = commentEl.querySelector('.task-comment-text');
        if (!textEl) return;
        if (commentEl.querySelector('.task-comment-edit-wrap')) return;

        var originalContent = content || '';
        var wrap = document.createElement('div');
        wrap.className = 'task-comment-edit-wrap';
        var textarea = document.createElement('textarea');
        textarea.className = 'task-comment-edit-input';
        textarea.rows = 3;
        textarea.placeholder = 'Editar comentário...';
        textarea.setAttribute('data-comment-id', commentId);
        var hint = document.createElement('span');
        hint.className = 'task-comment-edit-hint';
        hint.textContent = 'Enter para salvar, Esc para cancelar';
        wrap.appendChild(textarea);
        wrap.appendChild(hint);
        textEl.parentNode.replaceChild(wrap, textEl);
        textarea.value = originalContent;
        textarea.focus();

        function restoreText(text) {
            var p = document.createElement('p');
            p.className = 'task-comment-text';
            p.textContent = text;
            wrap.parentNode.replaceChild(p, wrap);
        }

        function saveComment() {
            var newContent = (textarea.value || '').trim();
            if (!newContent) return;
            var formData = new FormData();
            formData.append('content', newContent);

            fetch('/tarefas/comentarios/' + commentId + '/edit', {
                method: 'POST',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json',
                },
                body: formData,
            })
                .then(function (response) {
                    return response.json().catch(function () { return {}; }).then(function (data) {
                        if (!response.ok || !data.success) {
                            throw new Error((data && data.message) || 'Erro ao atualizar comentário.');
                        }
                        return data;
                    });
                })
                .then(function (data) {
                    if (!data || !data.comment) return;
                    updateTaskCommentInRow(commentId, data.comment.content, data.comment.updated_at);
                    restoreText(data.comment.content);
                    var row = commentEl.closest('.task-item-row');
                    if (row) {
                        syncTaskItemRowMetadata(row);
                        if (window.taskItemsKanban && typeof window.taskItemsKanban.syncItemFromRow === 'function') {
                            window.taskItemsKanban.syncItemFromRow(row.getAttribute('data-item-id'));
                        }
                    }
                })
                .catch(function (error) {
                    alert((error && error.message) || 'Erro ao atualizar comentário.');
                });
        }

        textarea.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                saveComment();
            }
            if (e.key === 'Escape') {
                e.preventDefault();
                restoreText(originalContent);
            }
        });
    }

    // Botões de editar comentário (delegado para também cobrir comentários criados via AJAX)
    document.addEventListener('click', function (event) {
        var btn = event.target.closest('.btn-edit-comment[data-comment-id]');
        if (!btn) return;
        event.preventDefault();
        openEditComment(btn.getAttribute('data-comment-id'), btn.getAttribute('data-comment-content'));
    });

    (function initTaskHubAutoFilters() {
        var form = document.getElementById('filterTasksForm');
        if (!form) return;

        var submitTimer = null;

        function submitFilters() {
            if (submitTimer) {
                window.clearTimeout(submitTimer);
                submitTimer = null;
            }
            form.submit();
        }

        function submitFiltersDebounced(delay) {
            if (submitTimer) window.clearTimeout(submitTimer);
            submitTimer = window.setTimeout(function () {
                submitTimer = null;
                form.submit();
            }, typeof delay === 'number' ? delay : 220);
        }

        Array.prototype.slice.call(form.querySelectorAll('select[name="area"], select[name="prioridade"], select[name="tipo"], select[name="status"], select[name="responsavel"]'))
            .forEach(function (field) {
                field.addEventListener('change', submitFilters);
            });

        // Filtro de projeto (combobox ABEP-like)
        var wrap = document.querySelector('.tasks-filters .project-search-wrap');
        var input = document.getElementById('filter_project_input');
        var hidden = document.getElementById('filter_project');
        var dropdown = document.getElementById('filterProjectDropdown');
        if (!wrap || !input || !hidden || !dropdown) return;

        var options = Array.prototype.slice.call(dropdown.querySelectorAll('.project-search-option[data-value]'));
        var emptyState = dropdown.querySelector('[data-empty-state="1"]');

        function filterOptions() {
            var q = (input.value || '').trim().toLowerCase();
            var visibleCount = 0;
            options.forEach(function (opt) {
                var label = (opt.getAttribute('data-label') || opt.textContent || '').toLowerCase();
                var isVisible = !q || label.indexOf(q) !== -1;
                opt.classList.toggle('hidden-by-filter', !isVisible);
                if (isVisible) visibleCount += 1;
            });
            if (emptyState) {
                emptyState.hidden = visibleCount > 0;
            }
        }

        function showDropdown() {
            filterOptions();
            dropdown.removeAttribute('hidden');
            input.setAttribute('aria-expanded', 'true');
        }

        function hideDropdown() {
            dropdown.setAttribute('hidden', '');
            input.setAttribute('aria-expanded', 'false');
        }

        function selectOption(opt) {
            var value = (opt.getAttribute('data-value') || '').trim();
            var label = opt.getAttribute('data-label') || opt.textContent || '';
            hidden.value = value;
            input.value = label;
            hideDropdown();
            submitFilters();
        }

        input.addEventListener('focus', showDropdown);
        input.addEventListener('input', showDropdown);
        input.addEventListener('search', function () {
            if ((input.value || '').trim()) return;
            if (!hidden.value) return;
            hidden.value = '';
            submitFiltersDebounced(80);
        });

        input.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') {
                hideDropdown();
                return;
            }

            var visibleOptions = options.filter(function (opt) {
                return !opt.classList.contains('hidden-by-filter');
            });
            if (!visibleOptions.length) return;

            if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                event.preventDefault();
                var active = dropdown.querySelector('.project-search-option.active');
                var idx = visibleOptions.indexOf(active);
                if (event.key === 'ArrowDown') {
                    idx = idx < 0 ? 0 : Math.min(idx + 1, visibleOptions.length - 1);
                } else {
                    idx = idx < 0 ? visibleOptions.length - 1 : Math.max(idx - 1, 0);
                }
                visibleOptions.forEach(function (opt, i) {
                    opt.classList.toggle('active', i === idx);
                });
                visibleOptions[idx].scrollIntoView({ block: 'nearest' });
            } else if (event.key === 'Enter') {
                var current = dropdown.querySelector('.project-search-option.active');
                if (current && !current.classList.contains('hidden-by-filter')) {
                    event.preventDefault();
                    selectOption(current);
                }
            }
        });

        options.forEach(function (opt) {
            opt.addEventListener('click', function () {
                selectOption(opt);
            });
        });

        document.addEventListener('mousedown', function (event) {
            if (!wrap.contains(event.target)) hideDropdown();
        });
    })();

    (function applyFocusItemFromUrl() {
        var configFocusTask = window.TASK_HUB_CONFIG && window.TASK_HUB_CONFIG.focusTask
            ? String(window.TASK_HUB_CONFIG.focusTask)
            : '';
        var focusItemId = configFocusTask || new URLSearchParams(window.location.search).get('focus_task');
        if (!focusItemId) {
            focusItemId = new URLSearchParams(window.location.search).get('focus_item');
        }
        if (!focusItemId) return;
        if (window.taskItemsKanban && typeof window.taskItemsKanban.applyView === 'function') {
            window.taskItemsKanban.applyView('list');
        }
        focusTaskItemRow(focusItemId);
    })();
