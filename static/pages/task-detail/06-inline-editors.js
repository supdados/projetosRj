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
        if (!sugestoesUrl || !taskId) return;

        var placeholderEl = respSpan.querySelector('.responsavel-placeholder');
        var originalText = placeholderEl ? '' : respSpan.textContent.trim();
        if (originalText === '\u00a0') originalText = '';

        respSpan.classList.add('task-item-resp-editing-active');

        responsavelPickerManager.open({
            anchorEl: respSpan,
            taskId: taskId,
            sugestoesUrl: sugestoesUrl,
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

    // Reset do form quando modal é fechado
    var addItemModalEl = document.getElementById('addItemModal');
    if (addItemModalEl) {
        addItemModalEl.addEventListener('hidden.bs.modal', function () {
            var itemModalTitle = document.getElementById('itemModalTitle');
            var itemForm = document.getElementById('itemForm');
            if (itemModalTitle) itemModalTitle.textContent = 'Novo Item';
            if (itemForm) {
                itemForm.action = taskDetailConfig.addTaskItemUrl || itemForm.action;
                itemForm.reset();
            }
        });
    }

    (function applyFocusItemFromUrl() {
        var focusItemId = new URLSearchParams(window.location.search).get('focus_item');
        if (!focusItemId) return;
        if (window.taskItemsKanban && typeof window.taskItemsKanban.applyView === 'function') {
            window.taskItemsKanban.applyView('list');
        }
        focusTaskItemRow(focusItemId);
    })();
