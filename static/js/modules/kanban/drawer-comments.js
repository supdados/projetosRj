(function (global) {
    var registry = global.TaskItemsKanbanModules = global.TaskItemsKanbanModules || {};

    registry.drawerComments = function registerDrawerComments(ctx) {
        var refs = ctx.refs;
        var state = ctx.state;
        var drawerAuthorToneMap = Object.create(null);
        var drawerAuthorToneCursor = 0;
        var DRAWER_AUTHOR_TONE_TOTAL = 5;

        function clearDrawerCommentsStatusTimer() {
            if (!state.drawerState.commentsStatusTimer) return;
            clearTimeout(state.drawerState.commentsStatusTimer);
            state.drawerState.commentsStatusTimer = null;
        }

        function clearDrawerCommentsTransitionTimer() {
            if (!state.drawerState.commentsTransitionTimer) return;
            clearTimeout(state.drawerState.commentsTransitionTimer);
            state.drawerState.commentsTransitionTimer = null;
        }

        function getDrawerCommentTextarea() {
            return refs.drawerCommentForm ? refs.drawerCommentForm.querySelector('textarea[name="content"]') : null;
        }

        function getDrawerCommentSubmitButton() {
            return refs.drawerCommentForm ? refs.drawerCommentForm.querySelector('button[type="submit"]') : null;
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
            submitBtn.disabled = state.drawerState.isCommentBusy || state.isDeleting || !hasContent;
        }

        function scrollDrawerCommentsToBottom(force) {
            if (!ctx.hasDrawer()) return;
            var list = refs.drawerCommentsList;
            if (!list) return;
            var distanceFromBottom = list.scrollHeight - list.scrollTop - list.clientHeight;
            var shouldPin = force || distanceFromBottom <= 56;
            if (!shouldPin) return;
            requestAnimationFrame(function () {
                list.scrollTop = list.scrollHeight;
            });
        }

        function setDrawerCommentsExpanded(expanded, options) {
            if (!ctx.hasDrawer() || !refs.drawerCommentsSection || !refs.drawerCommentsBody || !refs.drawerCommentsToggle) return;
            var opts = options || {};
            var shouldExpand = !!expanded;
            var instant = !!opts.instant || ctx.prefersReducedMotion();

            clearDrawerCommentsTransitionTimer();
            state.drawerState.isCommentsExpanded = shouldExpand;
            refs.drawerCommentsSection.classList.toggle('is-expanded', shouldExpand);
            refs.drawerCommentsToggle.setAttribute('aria-expanded', shouldExpand ? 'true' : 'false');
            refs.drawerCommentsBody.setAttribute('aria-hidden', shouldExpand ? 'false' : 'true');

            if (shouldExpand) {
                if (refs.drawerCommentsBody.hasAttribute('hidden')) {
                    refs.drawerCommentsBody.removeAttribute('hidden');
                }

                if (instant) {
                    refs.drawerCommentsBody.classList.add('is-expanded');
                    scrollDrawerCommentsToBottom(true);
                    return;
                }

                requestAnimationFrame(function () {
                    if (!state.drawerState.isCommentsExpanded) return;
                    refs.drawerCommentsBody.classList.add('is-expanded');
                    scrollDrawerCommentsToBottom(true);
                });
                return;
            }

            refs.drawerCommentsBody.classList.remove('is-expanded');
            if (instant) {
                refs.drawerCommentsBody.setAttribute('hidden', '');
                return;
            }

            state.drawerState.commentsTransitionTimer = setTimeout(function () {
                if (state.drawerState.isCommentsExpanded || !refs.drawerCommentsBody) return;
                refs.drawerCommentsBody.setAttribute('hidden', '');
                state.drawerState.commentsTransitionTimer = null;
            }, state.drawerState.commentsTransitionMs);
        }

        function setDrawerCommentsStatus(type, message, options) {
            if (!ctx.hasDrawer() || !refs.drawerCommentsStatus) return;
            clearDrawerCommentsStatusTimer();
            var opts = options || {};

            refs.drawerCommentsStatus.classList.remove('is-error', 'is-success', 'is-info');
            if (!message) {
                refs.drawerCommentsStatus.textContent = '';
                refs.drawerCommentsStatus.setAttribute('hidden', '');
                return;
            }

            var normalizedType = type || 'info';
            refs.drawerCommentsStatus.classList.add('is-' + normalizedType);
            refs.drawerCommentsStatus.textContent = message;
            refs.drawerCommentsStatus.removeAttribute('hidden');

            if (opts.autoHideMs) {
                state.drawerState.commentsStatusTimer = setTimeout(function () {
                    if (!refs.drawerCommentsStatus) return;
                    refs.drawerCommentsStatus.textContent = '';
                    refs.drawerCommentsStatus.setAttribute('hidden', '');
                    refs.drawerCommentsStatus.classList.remove('is-error', 'is-success', 'is-info');
                    state.drawerState.commentsStatusTimer = null;
                }, opts.autoHideMs);
            }
        }

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

        function setDrawerCommentsBusy(isBusy) {
            state.drawerState.isCommentBusy = !!isBusy;
            if (!ctx.hasDrawer()) return;
            refs.drawer.classList.toggle('is-comments-busy', state.drawerState.isCommentBusy);
            if (refs.drawerCommentsSection) {
                refs.drawerCommentsSection.classList.toggle('is-busy', state.drawerState.isCommentBusy);
            }
            var textarea = getDrawerCommentTextarea();
            if (textarea) textarea.disabled = state.drawerState.isCommentBusy || state.isDeleting;
            refs.drawerCommentsList.querySelectorAll('button').forEach(function (btn) {
                btn.disabled = state.drawerState.isCommentBusy;
            });
            refreshDrawerCommentComposer();
            ctx.refreshDrawerActionControls();
        }

        function renderDrawerCommentsFromRow(row, opts) {
            if (!ctx.hasDrawer() || !row) return;
            var options = opts || {};
            var comments = collectTaskItemCommentsFromRow(row);
            var shouldPinBottom = options.forceBottom === true;
            if (!shouldPinBottom) {
                var distanceFromBottom = refs.drawerCommentsList.scrollHeight - refs.drawerCommentsList.scrollTop - refs.drawerCommentsList.clientHeight;
                shouldPinBottom = distanceFromBottom <= 56;
            }
            refs.drawerCommentsList.innerHTML = '';

            if (!comments.length) {
                var empty = document.createElement('div');
                empty.className = 'task-item-drawer-comments-empty';
                empty.textContent = 'Sem comentários nesta tarefa.';
                refs.drawerCommentsList.appendChild(empty);
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

                    if (comment.is_own || (ctx.currentUserId && comment.user_id === ctx.currentUserId)) {
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
                    refs.drawerCommentsList.appendChild(node);
                });
            }

            refs.drawerCommentsCount.textContent = String(comments.length);
            if (state.drawerState.isCommentsExpanded) {
                scrollDrawerCommentsToBottom(shouldPinBottom);
            }
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
            if (!ctx.hasDrawer() || !state.drawerState.itemId) return;
            event.preventDefault();
            if (state.drawerState.isCommentBusy || state.isDeleting) return;

            var textarea = getDrawerCommentTextarea();
            var content = (textarea && textarea.value ? textarea.value : '').trim();
            if (!content) {
                if (textarea) textarea.focus();
                refreshDrawerCommentComposer();
                return;
            }

            setDrawerCommentsBusy(true);
            setDrawerCommentsStatus('info', 'Enviando comentário...');
            postCommentAdd(state.drawerState.itemId, content)
                .then(function (data) {
                    var row = getTaskItemRowById(state.drawerState.itemId);
                    if (!row) return;
                    appendCommentToTaskItemRow(row, data.comment);
                    syncTaskItemRowMetadata(row);
                    ctx.syncCardFromRow(state.drawerState.itemId);
                    state.drawerState.forceCommentsBottom = true;
                    ctx.syncDrawerFromCurrentRow();
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
            if (!ctx.hasDrawer() || !state.drawerState.itemId || state.drawerState.isCommentBusy || state.isDeleting) return;
            var commentEl = refs.drawerCommentsList.querySelector('.task-item-drawer-comment[data-comment-id="' + commentId + '"]');
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
                        ctx.syncCardFromRow(state.drawerState.itemId);
                        ctx.syncDrawerFromCurrentRow();
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
            if (!ctx.hasDrawer() || !state.drawerState.itemId || state.drawerState.isCommentBusy || state.isDeleting) return;
            if (!confirm('Excluir comentário?')) return;

            setDrawerCommentsBusy(true);
            setDrawerCommentsStatus('info', 'Excluindo comentário...');
            postCommentDelete(commentId)
                .then(function () {
                    var row = deleteTaskCommentFromRow(commentId);
                    if (row) {
                        syncTaskItemRowMetadata(row);
                        ctx.syncCardFromRow(row.getAttribute('data-item-id'));
                    } else {
                        ctx.syncCardFromRow(state.drawerState.itemId);
                    }
                    ctx.syncDrawerFromCurrentRow();
                    setDrawerCommentsStatus('success', 'Comentário excluído.', { autoHideMs: 1400 });
                })
                .catch(function (error) {
                    setDrawerCommentsStatus('error', (error && error.message) || 'Erro ao excluir comentário.');
                })
                .finally(function () {
                    setDrawerCommentsBusy(false);
                });
        }

        ctx.clearDrawerCommentsStatusTimer = clearDrawerCommentsStatusTimer;
        ctx.clearDrawerCommentsTransitionTimer = clearDrawerCommentsTransitionTimer;
        ctx.setDrawerCommentsExpanded = setDrawerCommentsExpanded;
        ctx.setDrawerCommentsStatus = setDrawerCommentsStatus;
        ctx.getDrawerCommentTextarea = getDrawerCommentTextarea;
        ctx.getDrawerCommentSubmitButton = getDrawerCommentSubmitButton;
        ctx.resizeDrawerCommentTextarea = resizeDrawerCommentTextarea;
        ctx.refreshDrawerCommentComposer = refreshDrawerCommentComposer;
        ctx.scrollDrawerCommentsToBottom = scrollDrawerCommentsToBottom;
        ctx.setDrawerCommentsBusy = setDrawerCommentsBusy;
        ctx.renderDrawerCommentsFromRow = renderDrawerCommentsFromRow;
        ctx.handleDrawerAddComment = handleDrawerAddComment;
        ctx.startDrawerCommentEdit = startDrawerCommentEdit;
        ctx.handleDrawerDeleteComment = handleDrawerDeleteComment;
    };
})(window);
