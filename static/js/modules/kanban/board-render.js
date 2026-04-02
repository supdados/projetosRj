(function (global) {
    var registry = global.TaskItemsKanbanModules = global.TaskItemsKanbanModules || {};

    registry.boardRender = function registerBoardRender(ctx) {
        var refs = ctx.refs;
        var state = ctx.state;
        var statusOrder = ctx.statusOrder;

        function setCardStatus(card, status) {
            if (!card) return;
            var normalized = ctx.normalizeStatus(status);
            card.setAttribute('data-status', normalized);
            var badge = card.querySelector('.task-items-kanban-badge');
            if (badge) {
                badge.classList.remove('status-nao_iniciada', 'status-em_andamento', 'status-para_validacao', 'status-para_ajustes', 'status-finalizada');
                badge.classList.add('status-' + normalized);
                badge.textContent = ctx.getStatusLabel(normalized);
            }
        }

        function fillKanbanCardContent(card, item) {
            if (!card || !item) return;
            card.setAttribute('data-item-id', item.id);
            card.setAttribute('data-can-delete', item.canDelete ? '1' : '0');
            card.setAttribute('data-can-finalize', item.canFinalize ? '1' : '0');
            setCardStatus(card, item.status);

            var desc = card.querySelector('.task-items-kanban-desc');
            if (desc) desc.textContent = item.descricao || 'Sem descrição';

            var contextEl = card.querySelector('.task-hub-kanban-context');
            ctx.renderKanbanContext(contextEl, item);

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
            var canDelete = item.canDelete !== false;
            var card = document.createElement('article');
            card.className = 'task-items-kanban-card';
            card.setAttribute('draggable', 'true');
            card.setAttribute('data-item-id', item.id);
            card.setAttribute('data-status', item.status);
            card.setAttribute('data-can-delete', canDelete ? '1' : '0');
            card.setAttribute('data-can-finalize', item.canFinalize ? '1' : '0');
            card.tabIndex = 0;

            var top = document.createElement('div');
            top.className = 'task-items-kanban-card-top';

            var badge = document.createElement('span');
            badge.className = 'task-items-kanban-badge';
            top.appendChild(badge);

            var deleteBtn = null;
            if (canDelete) {
                deleteBtn = document.createElement('button');
                deleteBtn.type = 'button';
                deleteBtn.className = 'task-items-kanban-delete-btn';
                deleteBtn.setAttribute('data-action', 'kanban-delete');
                deleteBtn.setAttribute('data-item-id', item.id);
                deleteBtn.setAttribute('aria-label', 'Excluir tarefa');
                deleteBtn.innerHTML = '<i class="fas fa-trash-alt" aria-hidden="true"></i>';
                top.appendChild(deleteBtn);
            }

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

            if (deleteBtn) {
                top.insertBefore(chipsGroup, deleteBtn);
            } else {
                top.appendChild(chipsGroup);
            }

            card.appendChild(top);
            card.appendChild(desc);
            card.appendChild(contextEl);
            card.appendChild(meta);

            if (canDelete) {
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
            }

            fillKanbanCardContent(card, item);
            return card;
        }

        function updateColumnMeta() {
            var columns = refs.board.querySelectorAll('.task-items-kanban-column[data-status]');
            columns.forEach(function (column) {
                var status = ctx.normalizeStatus(column.getAttribute('data-status'));
                var dropzone = column.querySelector('.task-items-kanban-dropzone[data-status]');
                var count = dropzone ? dropzone.querySelectorAll('.task-items-kanban-card[data-item-id]').length : 0;
                var countEl = column.querySelector('.task-items-kanban-count[data-role="count"]');
                if (countEl) countEl.textContent = String(count);
                column.classList.toggle('is-empty', count === 0);
                column.classList.remove('status-nao_iniciada', 'status-em_andamento', 'status-para_validacao', 'status-para_ajustes', 'status-finalizada');
                column.classList.add('status-' + status);
            });
        }

        function serializeKanbanOrder() {
            var order = [];
            statusOrder.forEach(function (status) {
                var dropzone = ctx.getDropzone(status);
                if (!dropzone) return;
                dropzone.querySelectorAll('.task-items-kanban-card[data-item-id]').forEach(function (card) {
                    var id = parseInt(card.getAttribute('data-item-id'), 10);
                    if (Number.isFinite(id)) order.push(id);
                });
            });
            return order;
        }

        function syncGroupedListOrder(orderIds) {
            var groups = refs.listEl.querySelectorAll('.task-hub-group');
            groups.forEach(function (group) {
                var addRow = group.querySelector('.task-hub-add-row') || group.querySelector('#addItemRow');
                var fragment = document.createDocumentFragment();

                orderIds.forEach(function (id) {
                    var row = group.querySelector('.task-item-row[data-item-id="' + id + '"]');
                    if (row) fragment.appendChild(row);

                    var modal = group.querySelector('#deleteItemModal-' + id);
                    if (modal) fragment.appendChild(modal);
                });

                if (!fragment.childNodes.length) return;

                if (addRow && addRow.parentNode === group) {
                    group.insertBefore(fragment, addRow);
                } else {
                    group.appendChild(fragment);
                }
            });
        }

        function syncListOrderFromKanban() {
            if (!ctx.reorderUrl) return;
            var orderIds = serializeKanbanOrder();
            if (!orderIds.length) return;

            if (ctx.isTaskHubGroupedList()) {
                syncGroupedListOrder(orderIds);
                return;
            }

            var addRow = refs.listEl.querySelector('.task-hub-add-row') || refs.listEl.querySelector('#addItemRow');
            var fragment = document.createDocumentFragment();

            orderIds.forEach(function (id) {
                var row = refs.listEl.querySelector('.task-item-row[data-item-id="' + id + '"]');
                if (row) fragment.appendChild(row);

                var modal = refs.listEl.querySelector('#deleteItemModal-' + id);
                if (modal) fragment.appendChild(modal);
            });

            if (addRow && addRow.parentNode === refs.listEl) {
                refs.listEl.insertBefore(fragment, addRow);
            } else {
                refs.listEl.appendChild(fragment);
            }
        }

        function persistKanbanOrder() {
            if (!ctx.reorderUrl) return Promise.resolve();
            return fetch(ctx.reorderUrl, {
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

        function renderKanbanFromList() {
            var items = ctx.sortItemsForKanban(ctx.collectListItems());
            statusOrder.forEach(function (status) {
                var dropzone = ctx.getDropzone(status);
                if (dropzone) dropzone.innerHTML = '';
            });

            items.forEach(function (item) {
                var dropzone = ctx.getDropzone(item.status);
                if (!dropzone) return;
                dropzone.appendChild(buildKanbanCard(item));
            });

            updateColumnMeta();
            ctx.writeStoredKanbanOrder(serializeKanbanOrder());

            if (state.drawerState.itemId && !getTaskItemRowById(state.drawerState.itemId)) {
                ctx.closeDrawer();
            } else if (state.drawerState.itemId) {
                ctx.syncDrawerFromCurrentRow();
            }
        }

        function syncCardFromRow(itemId) {
            if (!itemId) return;
            var row = getTaskItemRowById(itemId);
            if (!row) {
                renderKanbanFromList();
                return;
            }

            var item = ctx.readRowItem(row);
            if (!item) return;

            var card = refs.board.querySelector('.task-items-kanban-card[data-item-id="' + item.id + '"]');
            if (!card) {
                if (state.currentView === 'kanban') renderKanbanFromList();
                return;
            }

            fillKanbanCardContent(card, item);
            var dropzone = ctx.getDropzone(item.status);
            if (dropzone && card.parentNode !== dropzone) {
                dropzone.appendChild(card);
            }
            updateColumnMeta();
            ctx.writeStoredKanbanOrder(serializeKanbanOrder());
        }

        function closeCardDeleteConfirm(card) {
            if (!card) return;
            card.classList.remove('is-delete-confirming');
            var confirmBox = card.querySelector('.task-items-kanban-delete-confirm[data-role="delete-confirm"]');
            if (confirmBox) confirmBox.setAttribute('hidden', '');
        }

        function closeAllCardDeleteConfirms(exceptCard) {
            refs.board.querySelectorAll('.task-items-kanban-card.is-delete-confirming').forEach(function (card) {
                if (exceptCard && card === exceptCard) return;
                closeCardDeleteConfirm(card);
            });
        }

        function setDeletingState(active) {
            state.isDeleting = !!active;
            refs.board.classList.toggle('is-deleting', state.isDeleting);
            if (ctx.hasDrawer()) {
                refs.drawer.classList.toggle('is-deleting', state.isDeleting);
                refreshDrawerActionControls();
            }
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

        function deleteKanbanItem(itemId) {
            if (!itemId || state.isDeleting || state.isPersisting) return;
            setDeletingState(true);

            deleteTaskItemAjax(itemId)
                .then(function () {
                    removeTaskItemFromDom(itemId);
                    closeAllCardDeleteConfirms();
                    if (state.drawerState.itemId && state.drawerState.itemId === String(itemId)) {
                        ctx.closeDrawer();
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
            if (!ctx.hasDrawer()) return;
            var row = state.drawerState.itemId ? getTaskItemRowById(state.drawerState.itemId) : null;
            var canDelete = !!(row && typeof getTaskItemCanDelete === 'function' && getTaskItemCanDelete(row));

            if (!canDelete) {
                ctx.setDrawerDeleteConfirmVisible(false);
                refs.drawerDeleteIcon.setAttribute('hidden', '');
            } else {
                refs.drawerDeleteIcon.removeAttribute('hidden');
            }

            var disableDelete = !canDelete || state.isDeleting || state.drawerState.isSaving || state.drawerState.isCommentBusy;
            refs.drawerDeleteIcon.disabled = disableDelete;
            refs.drawerDeleteCancel.disabled = disableDelete;
            refs.drawerDeleteConfirmBtn.disabled = disableDelete;
        }

        ctx.setCardStatus = setCardStatus;
        ctx.fillKanbanCardContent = fillKanbanCardContent;
        ctx.buildKanbanCard = buildKanbanCard;
        ctx.updateColumnMeta = updateColumnMeta;
        ctx.serializeKanbanOrder = serializeKanbanOrder;
        ctx.syncGroupedListOrder = syncGroupedListOrder;
        ctx.syncListOrderFromKanban = syncListOrderFromKanban;
        ctx.persistKanbanOrder = persistKanbanOrder;
        ctx.renderKanbanFromList = renderKanbanFromList;
        ctx.syncCardFromRow = syncCardFromRow;
        ctx.closeCardDeleteConfirm = closeCardDeleteConfirm;
        ctx.closeAllCardDeleteConfirms = closeAllCardDeleteConfirms;
        ctx.setDeletingState = setDeletingState;
        ctx.deleteTaskItemAjax = deleteTaskItemAjax;
        ctx.deleteKanbanItem = deleteKanbanItem;
        ctx.refreshDrawerActionControls = refreshDrawerActionControls;
    };
})(window);
