// === task-header-editor.js — Editar título e projeto no header da tarefa ===
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

        var escapeHtml = window.escapeHtml || function (value) {
            return String(value == null ? '' : value)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        };

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
