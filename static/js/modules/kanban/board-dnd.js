(function (global) {
    var registry = global.TaskItemsKanbanModules = global.TaskItemsKanbanModules || {};

    registry.boardDnd = function registerBoardDnd(ctx) {
        var refs = ctx.refs;
        var state = ctx.state;

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

        function getColumnDropzone(column) {
            if (!column) return null;
            return column.querySelector('.task-items-kanban-dropzone[data-status]');
        }

        function getDropzoneByHorizontalPointer(clientX) {
            if (!Number.isFinite(clientX)) return null;
            var columns = Array.prototype.slice.call(
                refs.board.querySelectorAll('.task-items-kanban-column[data-status]')
            );
            var insideMatch = null;
            var nearestMatch = null;

            columns.forEach(function (column) {
                var dropzone = getColumnDropzone(column);
                if (!dropzone) return;

                var rect = column.getBoundingClientRect();
                if (!rect || rect.width <= 0) return;

                if (clientX >= rect.left && clientX <= rect.right) {
                    insideMatch = dropzone;
                    return;
                }

                var distance = clientX < rect.left
                    ? (rect.left - clientX)
                    : (clientX - rect.right);
                if (!nearestMatch || distance < nearestMatch.distance) {
                    nearestMatch = { distance: distance, dropzone: dropzone };
                }
            });

            return insideMatch || (nearestMatch ? nearestMatch.dropzone : null);
        }

        function resolveDropzoneFromEvent(event) {
            if (!event || !event.target || typeof event.target.closest !== 'function') return null;

            var targetDropzone = event.target.closest('.task-items-kanban-dropzone[data-status]');
            if (targetDropzone) return targetDropzone;

            var targetColumn = event.target.closest('.task-items-kanban-column[data-status]');
            var columnDropzone = getColumnDropzone(targetColumn);
            if (columnDropzone) return columnDropzone;

            return getDropzoneByHorizontalPointer(event.clientX);
        }

        function clearDropzoneHover() {
            refs.board.querySelectorAll('.task-items-kanban-dropzone.is-drag-over').forEach(function (zone) {
                zone.classList.remove('is-drag-over');
            });
            refs.board.querySelectorAll('.task-items-kanban-column.is-column-drag-target').forEach(function (column) {
                column.classList.remove('is-column-drag-target');
            });
        }

        function setDropzoneHover(dropzone) {
            if (!dropzone) return;
            clearDropzoneHover();
            dropzone.classList.add('is-drag-over');
            var column = dropzone.closest('.task-items-kanban-column[data-status]');
            if (column) column.classList.add('is-column-drag-target');
        }

        function getDraggingCard() {
            if (state.dragContext && state.dragContext.itemId) {
                var contextualCard = refs.board.querySelector('.task-items-kanban-card[data-item-id="' + state.dragContext.itemId + '"]');
                if (contextualCard) return contextualCard;
            }
            return refs.board.querySelector('.task-items-kanban-card.is-dragging');
        }

        function createDragPlaceholder(card) {
            removeDragPlaceholder();
            if (!card) return null;

            var placeholderHeight = (
                state.dragContext &&
                Number.isFinite(state.dragContext.cardHeight) &&
                state.dragContext.cardHeight > 0
            ) ? state.dragContext.cardHeight : card.getBoundingClientRect().height;
            state.dragPlaceholder = document.createElement('div');
            state.dragPlaceholder.className = 'task-items-kanban-placeholder';
            state.dragPlaceholder.setAttribute('aria-hidden', 'true');
            state.dragPlaceholder.style.height = Math.max(Math.round(placeholderHeight), 40) + 'px';
            return state.dragPlaceholder;
        }

        function removeDragPlaceholder() {
            if (!state.dragPlaceholder) return;
            if (state.dragPlaceholder.parentNode) {
                state.dragPlaceholder.parentNode.removeChild(state.dragPlaceholder);
            }
            state.dragPlaceholder = null;
        }

        function createDragGhost(card) {
            removeDragGhost();
            if (!card || !refs.pageRoot) return null;

            var rect = card.getBoundingClientRect();
            state.dragGhost = card.cloneNode(true);
            state.dragGhost.classList.remove('is-dragging', 'is-drop-settling', 'is-delete-confirming');
            state.dragGhost.classList.add('is-drag-ghost');
            state.dragGhost.style.position = 'fixed';
            state.dragGhost.style.top = '-9999px';
            state.dragGhost.style.left = '-9999px';
            state.dragGhost.style.width = Math.round(rect.width) + 'px';
            state.dragGhost.style.pointerEvents = 'none';
            state.dragGhost.style.zIndex = '9999';
            refs.pageRoot.appendChild(state.dragGhost);
            return state.dragGhost;
        }

        function removeDragGhost() {
            if (!state.dragGhost) return;
            if (state.dragGhost.parentNode) {
                state.dragGhost.parentNode.removeChild(state.dragGhost);
            }
            state.dragGhost = null;
        }

        function restoreDraggedCardPosition() {
            var card = getDraggingCard();
            if (card) {
                ctx.setCardStatus(card, (state.dragContext && state.dragContext.previousStatus) || 'nao_iniciada');
                card.classList.remove('is-dragging');
                card.classList.remove('is-drop-settling');
            }
            removeDragPlaceholder();
            removeDragGhost();
        }

        function triggerDropSettle(card) {
            if (!card || ctx.prefersReducedMotion()) return;

            card.classList.remove('is-drop-settling');
            void card.offsetWidth;
            card.classList.add('is-drop-settling');

            var handleAnimationEnd = function () {
                card.classList.remove('is-drop-settling');
                card.removeEventListener('animationend', handleAnimationEnd);
            };
            card.addEventListener('animationend', handleAnimationEnd);
        }

        function autoScrollDropzoneOnDrag(dropzone, clientY) {
            if (!dropzone || !Number.isFinite(clientY)) return;
            var rect = dropzone.getBoundingClientRect();
            if (!rect || rect.height <= 0) return;

            var threshold = Math.max(24, Math.min(72, rect.height * 0.22));
            var delta = 0;
            if (clientY < (rect.top + threshold)) {
                var ratioUp = (rect.top + threshold - clientY) / threshold;
                delta = -Math.max(6, Math.round(18 * ratioUp));
            } else if (clientY > (rect.bottom - threshold)) {
                var ratioDown = (clientY - (rect.bottom - threshold)) / threshold;
                delta = Math.max(6, Math.round(18 * ratioDown));
            }

            if (!delta) return;
            dropzone.scrollTop += delta;
        }

        function placeDragPlaceholder(dropzone, clientY) {
            if (!dropzone) return;
            setDropzoneHover(dropzone);
            autoScrollDropzoneOnDrag(dropzone, clientY);

            var dragging = getDraggingCard();
            if (!dragging) return;

            var afterElement = getDragAfterElement(dropzone, clientY);
            var placeholder = state.dragPlaceholder || createDragPlaceholder(dragging);
            if (!placeholder) return;
            if (afterElement) {
                dropzone.insertBefore(placeholder, afterElement);
            } else {
                dropzone.appendChild(placeholder);
            }
        }

        function persistKanbanChange(itemId, previousStatus) {
            if (state.isPersisting || state.isDeleting) return;
            state.isPersisting = true;
            refs.board.classList.add('is-persisting');

            var card = refs.board.querySelector('.task-items-kanban-card[data-item-id="' + itemId + '"]');
            if (!card) {
                state.isPersisting = false;
                refs.board.classList.remove('is-persisting');
                ctx.renderKanbanFromList();
                return;
            }

            var nextStatus = ctx.normalizeStatus(card.getAttribute('data-status'));
            var statusChanged = ctx.normalizeStatus(previousStatus) !== nextStatus;

            var statusPromise = statusChanged
                ? updateItemStatus(itemId, nextStatus, {
                    skipKanbanSync: true,
                    showAlert: false,
                    celebrationOrigin: card,
                })
                : Promise.resolve();

            statusPromise
                .then(function () {
                    return ctx.persistKanbanOrder();
                })
                .then(function () {
                    ctx.syncListOrderFromKanban();
                    ctx.updateColumnMeta();
                    ctx.writeStoredKanbanOrder(ctx.serializeKanbanOrder());
                })
                .catch(function (error) {
                    console.error('Erro ao persistir kanban:', error);
                    ctx.renderKanbanFromList();
                    alert((error && error.message) || 'Nao foi possivel persistir a movimentacao no Kanban.');
                })
                .finally(function () {
                    state.isPersisting = false;
                    refs.board.classList.remove('is-persisting');
                });
        }

        function finalizeDrop(event, dropzone) {
            if (!dropzone) return;
            event.preventDefault();
            state.suppressCardClickUntil = Date.now() + 220;

            if (!ctx.canDragItemMoveToStatus(dropzone.getAttribute('data-status') || 'nao_iniciada')) {
                if (state.dragContext) {
                    state.dragContext.didDrop = true;
                }
                restoreDraggedCardPosition();
                clearDropzoneHover();
                alert('Apenas o criador da tarefa pode movê-la para Finalizada.');
                return;
            }

            var dragging = getDraggingCard();
            var itemId = state.dragContext.itemId;
            var previousStatus = state.dragContext.previousStatus;
            state.dragContext.didDrop = true;

            if (dragging) {
                ctx.setCardStatus(dragging, dropzone.getAttribute('data-status') || 'nao_iniciada');
                if (state.dragPlaceholder && state.dragPlaceholder.parentNode === dropzone) {
                    dropzone.insertBefore(dragging, state.dragPlaceholder);
                } else {
                    var afterElement = getDragAfterElement(dropzone, event.clientY);
                    if (afterElement) {
                        dropzone.insertBefore(dragging, afterElement);
                    } else {
                        dropzone.appendChild(dragging);
                    }
                }
                dragging.classList.remove('is-dragging');
            }

            removeDragPlaceholder();
            removeDragGhost();
            clearDropzoneHover();
            triggerDropSettle(dragging);
            persistKanbanChange(itemId, previousStatus);
            ctx.updateColumnMeta();
        }

        function bindDropzones() {
            var dropzones = refs.board.querySelectorAll('.task-items-kanban-dropzone[data-status]');
            dropzones.forEach(function (dropzone) {
                dropzone.addEventListener('dragenter', function (event) {
                    if (!state.dragContext || state.isPersisting || state.isDeleting) return;
                    event.preventDefault();
                    if (!ctx.canDragItemMoveToStatus(dropzone.getAttribute('data-status') || 'nao_iniciada')) return;
                    setDropzoneHover(dropzone);
                });

                dropzone.addEventListener('dragover', function (event) {
                    if (!state.dragContext || state.isPersisting || state.isDeleting) return;
                    event.preventDefault();
                    if (!ctx.canDragItemMoveToStatus(dropzone.getAttribute('data-status') || 'nao_iniciada')) return;
                    placeDragPlaceholder(dropzone, event.clientY);
                });

                dropzone.addEventListener('dragleave', function (event) {
                    if (!dropzone.contains(event.relatedTarget)) {
                        dropzone.classList.remove('is-drag-over');
                        var column = dropzone.closest('.task-items-kanban-column[data-status]');
                        if (column) column.classList.remove('is-column-drag-target');
                    }
                });

                dropzone.addEventListener('drop', function (event) {
                    if (!state.dragContext || state.isPersisting || state.isDeleting) return;
                    finalizeDrop(event, dropzone);
                });
            });

            refs.board.addEventListener('dragover', function (event) {
                if (!state.dragContext || state.isPersisting || state.isDeleting || event.defaultPrevented) return;
                var dropzone = resolveDropzoneFromEvent(event);
                if (!dropzone) return;
                event.preventDefault();
                if (!ctx.canDragItemMoveToStatus(dropzone.getAttribute('data-status') || 'nao_iniciada')) return;
                placeDragPlaceholder(dropzone, event.clientY);
            });

            refs.board.addEventListener('drop', function (event) {
                if (!state.dragContext || state.isPersisting || state.isDeleting || event.defaultPrevented) return;
                var dropzone = resolveDropzoneFromEvent(event);
                if (!dropzone) return;
                finalizeDrop(event, dropzone);
            });

            refs.board.addEventListener('dragleave', function (event) {
                if (!state.dragContext || state.isPersisting || state.isDeleting) return;
                if (refs.board.contains(event.relatedTarget)) return;
                clearDropzoneHover();
            });
        }

        function bindBoardEvents() {
            refs.board.addEventListener('click', function (event) {
                var openCommentsBtn = event.target.closest('.task-items-kanban-comments[data-action="kanban-open-comments"][data-item-id]');
                if (openCommentsBtn) {
                    event.preventDefault();
                    event.stopPropagation();
                    if (state.isDeleting || state.isPersisting) return;
                    ctx.closeAllCardDeleteConfirms();
                    ctx.openDrawerComments(openCommentsBtn.getAttribute('data-item-id'));
                    return;
                }

                var openAnexosBtn = event.target.closest('.task-items-kanban-anexos[data-action="kanban-open-anexos"][data-item-id]');
                if (openAnexosBtn) {
                    event.preventDefault();
                    event.stopPropagation();
                    if (state.isDeleting || state.isPersisting) return;
                    ctx.closeAllCardDeleteConfirms();
                    ctx.openItemAnexoAction(openAnexosBtn.getAttribute('data-item-id'));
                    return;
                }

                var deleteTrigger = event.target.closest('.task-items-kanban-delete-btn[data-action="kanban-delete"][data-item-id]');
                if (deleteTrigger) {
                    event.preventDefault();
                    event.stopPropagation();
                    if (state.isDeleting || state.isPersisting) return;
                    var triggerCard = deleteTrigger.closest('.task-items-kanban-card[data-item-id]');
                    if (!triggerCard) return;
                    var triggerConfirmBox = triggerCard.querySelector('.task-items-kanban-delete-confirm[data-role="delete-confirm"]');
                    var shouldOpen = !!(triggerConfirmBox && triggerConfirmBox.hasAttribute('hidden'));
                    ctx.closeAllCardDeleteConfirms(triggerCard);
                    if (triggerConfirmBox) {
                        if (shouldOpen) {
                            triggerCard.classList.add('is-delete-confirming');
                            triggerConfirmBox.removeAttribute('hidden');
                        } else {
                            ctx.closeCardDeleteConfirm(triggerCard);
                        }
                    }
                    return;
                }

                var cancelDeleteBtn = event.target.closest('[data-action="kanban-delete-cancel"]');
                if (cancelDeleteBtn) {
                    event.preventDefault();
                    var cancelCard = cancelDeleteBtn.closest('.task-items-kanban-card[data-item-id]');
                    ctx.closeCardDeleteConfirm(cancelCard);
                    return;
                }

                var confirmDeleteBtn = event.target.closest('[data-action="kanban-delete-confirm"]');
                if (confirmDeleteBtn) {
                    event.preventDefault();
                    var confirmCard = confirmDeleteBtn.closest('.task-items-kanban-card[data-item-id]');
                    if (!confirmCard || state.isDeleting || state.isPersisting) return;
                    ctx.deleteKanbanItem(confirmCard.getAttribute('data-item-id'));
                    return;
                }

                if (event.target.closest('.task-items-kanban-delete-confirm[data-role="delete-confirm"]')) {
                    return;
                }

                var card = event.target.closest('.task-items-kanban-card[data-item-id]');
                if (!card) {
                    ctx.closeAllCardDeleteConfirms();
                    return;
                }

                if (state.isDeleting || state.isPersisting || Date.now() < state.suppressCardClickUntil) return;
                ctx.closeAllCardDeleteConfirms();
                ctx.openDrawer(card.getAttribute('data-item-id'));
            });

            refs.board.addEventListener('keydown', function (event) {
                if (event.key === 'Escape') {
                    ctx.closeAllCardDeleteConfirms();
                    return;
                }
                var card = event.target.closest('.task-items-kanban-card[data-item-id]');
                if (!card) return;
                if (event.target.closest('.task-items-kanban-delete-btn, .task-items-kanban-delete-confirm, .task-items-kanban-comments, .task-items-kanban-anexos')) return;
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    if (!state.isDeleting && !state.isPersisting && Date.now() >= state.suppressCardClickUntil) {
                        ctx.openDrawer(card.getAttribute('data-item-id'));
                    }
                }
            });

            refs.board.addEventListener('dragstart', function (event) {
                var card = event.target.closest('.task-items-kanban-card[data-item-id]');
                if (!card || state.isPersisting || state.isDeleting) return;
                if (event.target.closest('.task-items-kanban-delete-btn, .task-items-kanban-delete-confirm, .task-items-kanban-comments, .task-items-kanban-anexos')) {
                    event.preventDefault();
                    return;
                }
                ctx.closeAllCardDeleteConfirms();
                clearDropzoneHover();
                removeDragPlaceholder();
                card.classList.remove('is-drop-settling');

                state.dragContext = {
                    itemId: card.getAttribute('data-item-id'),
                    previousStatus: card.getAttribute('data-status') || 'nao_iniciada',
                    cardHeight: card.getBoundingClientRect().height,
                    originParent: card.parentNode,
                    originNextSibling: card.nextElementSibling,
                    didDrop: false,
                };
                if (event.dataTransfer) {
                    event.dataTransfer.effectAllowed = 'move';
                    event.dataTransfer.setData('text/plain', state.dragContext.itemId || '');
                    var ghost = createDragGhost(card);
                    if (ghost && typeof event.dataTransfer.setDragImage === 'function') {
                        event.dataTransfer.setDragImage(ghost, 24, 24);
                    }
                }
                setTimeout(function () {
                    if (!state.dragContext || state.dragContext.itemId !== card.getAttribute('data-item-id')) return;
                    card.classList.add('is-dragging');
                    removeDragGhost();
                }, 0);
            });

            refs.board.addEventListener('dragend', function () {
                var context = state.dragContext;
                if (context && !context.didDrop) {
                    restoreDraggedCardPosition();
                } else {
                    var dragging = getDraggingCard();
                    if (dragging) dragging.classList.remove('is-dragging');
                    removeDragPlaceholder();
                    removeDragGhost();
                }
                state.dragContext = null;
                state.suppressCardClickUntil = Date.now() + 140;
                clearDropzoneHover();
                ctx.updateColumnMeta();
            });
        }

        ctx.getDraggingCard = getDraggingCard;
        ctx.restoreDraggedCardPosition = restoreDraggedCardPosition;
        ctx.triggerDropSettle = triggerDropSettle;
        ctx.persistKanbanChange = persistKanbanChange;
        ctx.bindDropzones = bindDropzones;
        ctx.bindBoardEvents = bindBoardEvents;
    };
})(window);
