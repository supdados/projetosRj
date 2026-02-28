// === task-archive.js — Archive e comments toggle ===

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
