// === inline-editors.js — Inline editors, filtros e focus item ===
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
        var contentEl = respSpan.querySelector('.responsavel-picker-trigger-content');
        if (value) {
            if (contentEl) {
                contentEl.innerHTML = '<span class="responsavel-picker-chip responsavel-picker-chip-0">' + escapeHtml(value) + '</span>';
            } else {
                respSpan.textContent = value;
            }
        } else {
            if (contentEl) {
                contentEl.innerHTML = '<em class="responsavel-placeholder">Responsável não informado</em>';
            } else {
                respSpan.innerHTML = '<em class="responsavel-placeholder">Responsável não informado</em>';
            }
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

        Array.prototype.slice.call(form.querySelectorAll('select[name="orgao"], select[name="prioridade"], select[name="tipo"], select[name="status"], select[name="responsavel"]'))
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

        function clearProjectFilter(shouldSubmit) {
            hidden.value = '';
            hideDropdown();
            if (shouldSubmit) {
                submitFilters();
            }
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
        input.addEventListener('input', function () {
            if (!(input.value || '').trim()) {
                hidden.value = '';
            }
            showDropdown();
        });
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
                if (!(input.value || '').trim()) {
                    event.preventDefault();
                    clearProjectFilter(true);
                    return;
                }
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
