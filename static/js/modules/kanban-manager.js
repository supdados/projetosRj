// === kanban-manager.js — Kanban completo (IIFE grande) ===

    var taskItemsKanbanManager = (function () {
        var statusOrder = ['nao_iniciada', 'em_andamento', 'para_validacao', 'para_ajustes', 'finalizada'];
        var statusLabels = {
            nao_iniciada: 'Não iniciada',
            em_andamento: 'Em andamento',
            para_validacao: 'Para validação',
            para_ajustes: 'Para ajustes',
            finalizada: 'Finalizada',
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
        var kanbanOrderStorageKey = buildKanbanOrderStorageKey();
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
        var dragPlaceholder = null;
        var dragGhost = null;
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
            if (toggleRoot) {
                toggleRoot.addEventListener('click', function (event) {
                    var button = event.target.closest('.task-items-view-btn[data-no-tasks="1"]');
                    if (!button) return;
                    event.preventDefault();
                    showNoTasksToast();
                });
            }
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
            var status = normalizeStatus(data.status || 'nao_iniciada');
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
            return statusOrder.indexOf(status) !== -1 ? status : 'nao_iniciada';
        }

        function getStatusLabel(status) {
            return statusLabels[normalizeStatus(status)] || 'Não iniciada';
        }

        function parsePermissionFlag(value, fallbackValue) {
            if (value == null) return !!fallbackValue;
            var normalized = String(value).trim().toLowerCase();
            if (!normalized) return !!fallbackValue;
            if (normalized === '1' || normalized === 'true' || normalized === 'yes') return true;
            if (normalized === '0' || normalized === 'false' || normalized === 'no') return false;
            return !!fallbackValue;
        }

        function canItemMoveToStatus(item, targetStatus, previousStatus) {
            var normalizedTargetStatus = normalizeStatus(targetStatus);
            if (normalizedTargetStatus !== 'finalizada') {
                return true;
            }

            var normalizedPreviousStatus = normalizeStatus(previousStatus || (item && item.status));
            if (normalizedPreviousStatus === 'finalizada') {
                return true;
            }

            return !!(item && item.canFinalize);
        }

        function canDragItemMoveToStatus(targetStatus) {
            if (!dragContext) return false;

            var dragging = getDraggingCard();
            var canFinalize = dragging
                ? parsePermissionFlag(dragging.getAttribute('data-can-finalize'), true)
                : true;

            return canItemMoveToStatus(
                { canFinalize: canFinalize, status: dragContext.previousStatus },
                targetStatus,
                dragContext.previousStatus
            );
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
            link.setAttribute('draggable', 'false');
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

        function buildKanbanOrderStorageKey() {
            try {
                return 'task-hub-kanban-order:' + window.location.pathname + window.location.search;
            } catch (error) {
                return taskId ? ('task-items-kanban-order:' + taskId) : '';
            }
        }

        function normalizeStoredKanbanOrder(rawOrder) {
            if (!Array.isArray(rawOrder)) return [];

            var normalized = [];
            var seen = {};
            rawOrder.forEach(function (value) {
                var id = String(value == null ? '' : value).trim();
                if (!id || seen[id]) return;
                seen[id] = true;
                normalized.push(id);
            });
            return normalized;
        }

        function readStoredKanbanOrder() {
            if (!kanbanOrderStorageKey) return [];
            try {
                return normalizeStoredKanbanOrder(JSON.parse(localStorage.getItem(kanbanOrderStorageKey) || '[]'));
            } catch (error) {
                return [];
            }
        }

        function writeStoredKanbanOrder(orderIds) {
            if (!kanbanOrderStorageKey) return;
            try {
                localStorage.setItem(
                    kanbanOrderStorageKey,
                    JSON.stringify(normalizeStoredKanbanOrder(orderIds))
                );
            } catch (error) {}
        }

        function isTaskHubGroupedList() {
            return !!listEl.querySelector('.task-hub-group');
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
                canDelete: typeof getTaskItemCanDelete === 'function' ? getTaskItemCanDelete(row) : true,
                canFinalize: typeof getTaskItemCanFinalize === 'function' ? getTaskItemCanFinalize(row) : true,
            };
        }

        function collectListItems() {
            return Array.prototype.map.call(
                listEl.querySelectorAll('.task-item-row[data-item-id]'),
                function (row) { return readRowItem(row); }
            ).filter(function (item) { return !!item; });
        }

        function sortItemsForKanban(items) {
            var storedOrder = readStoredKanbanOrder();
            if (!storedOrder.length) return items;

            var orderIndex = {};
            storedOrder.forEach(function (id, index) {
                orderIndex[String(id)] = index;
            });

            return items
                .map(function (item, index) {
                    var itemId = String(item && item.id != null ? item.id : '');
                    var storedIndex = Object.prototype.hasOwnProperty.call(orderIndex, itemId)
                        ? orderIndex[itemId]
                        : Number.MAX_SAFE_INTEGER;
                    return {
                        item: item,
                        index: index,
                        storedIndex: storedIndex,
                    };
                })
                .sort(function (left, right) {
                    if (left.storedIndex !== right.storedIndex) {
                        return left.storedIndex - right.storedIndex;
                    }
                    return left.index - right.index;
                })
                .map(function (entry) { return entry.item; });
        }

        function setCardStatus(card, status) {
            if (!card) return;
            var normalized = normalizeStatus(status);
            card.setAttribute('data-status', normalized);
            var badge = card.querySelector('.task-items-kanban-badge');
            if (badge) {
                badge.classList.remove('status-nao_iniciada', 'status-em_andamento', 'status-para_validacao', 'status-para_ajustes', 'status-finalizada');
                badge.classList.add('status-' + normalized);
                badge.textContent = getStatusLabel(normalized);
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
            var columns = board.querySelectorAll('.task-items-kanban-column[data-status]');
            columns.forEach(function (column) {
                var status = normalizeStatus(column.getAttribute('data-status'));
                var dropzone = column.querySelector('.task-items-kanban-dropzone[data-status]');
                var count = dropzone ? dropzone.querySelectorAll('.task-items-kanban-card[data-item-id]').length : 0;
                var countEl = column.querySelector('.task-items-kanban-count[data-role="count"]');
                if (countEl) countEl.textContent = String(count);
                column.classList.toggle('is-empty', count === 0);
                column.classList.remove('status-nao_iniciada', 'status-em_andamento', 'status-para_validacao', 'status-para_ajustes', 'status-finalizada');
                column.classList.add('status-' + status);
            });
        }

        function renderKanbanFromList() {
            var items = sortItemsForKanban(collectListItems());
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
            writeStoredKanbanOrder(serializeKanbanOrder());

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
            writeStoredKanbanOrder(serializeKanbanOrder());
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

        function syncGroupedListOrder(orderIds) {
            var groups = listEl.querySelectorAll('.task-hub-group');
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
            if (!reorderUrl) return;
            var orderIds = serializeKanbanOrder();
            if (!orderIds.length) return;

            if (isTaskHubGroupedList()) {
                syncGroupedListOrder(orderIds);
                return;
            }

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
            var row = drawerState.itemId ? getTaskItemRowById(drawerState.itemId) : null;
            var canDelete = !!(row && typeof getTaskItemCanDelete === 'function' && getTaskItemCanDelete(row));

            if (!canDelete) {
                setDrawerDeleteConfirmVisible(false);
                drawerDeleteIcon.setAttribute('hidden', '');
            } else {
                drawerDeleteIcon.removeAttribute('hidden');
            }

            var disableDelete = !canDelete || isDeleting || drawerState.isSaving || drawerState.isCommentBusy;
            drawerDeleteIcon.disabled = disableDelete;
            drawerDeleteCancel.disabled = disableDelete;
            drawerDeleteConfirmBtn.disabled = disableDelete;
        }

        function setDrawerAutosaveStatus(state, message) {
            if (!hasDrawer() || !drawerAutosaveStatus) return;
            var normalizedState = state || 'idle';
            drawerAutosaveStatus.classList.remove('is-saving', 'is-saved', 'is-error', 'is-invalid');

            if (message) {
                if (normalizedState !== 'idle') {
                    drawerAutosaveStatus.classList.add('is-' + normalizedState);
                }
                drawerAutosaveStatus.textContent = message;
                return;
            }

            if (normalizedState === 'idle') {
                drawerAutosaveStatus.textContent = '';
            } else if (normalizedState === 'saving') {
                drawerAutosaveStatus.classList.add('is-saving');
                drawerAutosaveStatus.textContent = 'Salvando...';
            } else if (normalizedState === 'error') {
                drawerAutosaveStatus.classList.add('is-error');
                drawerAutosaveStatus.textContent = 'Não foi possível salvar.';
            } else if (normalizedState === 'invalid') {
                drawerAutosaveStatus.classList.add('is-invalid');
                drawerAutosaveStatus.textContent = 'Descrição é obrigatória.';
            } else {
                drawerAutosaveStatus.classList.add('is-saved');
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
            drawerStatusBadge.classList.remove('status-nao_iniciada', 'status-em_andamento', 'status-para_validacao', 'status-para_ajustes', 'status-finalizada');
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
                setDrawerAutosaveStatus();
            } else if (!drawerState.isSaving && !drawerState.hasPendingSave) {
                drawerState.hasUnsavedChanges = false;
                setDrawerAutosaveStatus();
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
                setDrawerAutosaveStatus();
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
            refreshDrawerActionControls();
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
            setDrawerAutosaveStatus();
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
                setDrawerAutosaveStatus();
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

        function getColumnDropzone(column) {
            if (!column) return null;
            return column.querySelector('.task-items-kanban-dropzone[data-status]');
        }

        function getDropzoneByHorizontalPointer(clientX) {
            if (!Number.isFinite(clientX)) return null;
            var columns = Array.prototype.slice.call(
                board.querySelectorAll('.task-items-kanban-column[data-status]')
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

        function placeDragPlaceholder(dropzone, clientY) {
            if (!dropzone) return;
            setDropzoneHover(dropzone);
            autoScrollDropzoneOnDrag(dropzone, clientY);

            var dragging = getDraggingCard();
            if (!dragging) return;

            var afterElement = getDragAfterElement(dropzone, clientY);
            var placeholder = dragPlaceholder || createDragPlaceholder(dragging);
            if (!placeholder) return;
            if (afterElement) {
                dropzone.insertBefore(placeholder, afterElement);
            } else {
                dropzone.appendChild(placeholder);
            }
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

        function finalizeDrop(event, dropzone) {
            if (!dropzone) return;
            event.preventDefault();
            suppressCardClickUntil = Date.now() + 220;

            if (!canDragItemMoveToStatus(dropzone.getAttribute('data-status') || 'nao_iniciada')) {
                if (dragContext) {
                    dragContext.didDrop = true;
                }
                restoreDraggedCardPosition();
                clearDropzoneHover();
                alert('Apenas o criador da tarefa pode movê-la para Finalizada.');
                return;
            }

            var dragging = getDraggingCard();
            var itemId = dragContext.itemId;
            var previousStatus = dragContext.previousStatus;
            dragContext.didDrop = true;

            if (dragging) {
                setCardStatus(dragging, dropzone.getAttribute('data-status') || 'nao_iniciada');
                if (dragPlaceholder && dragPlaceholder.parentNode === dropzone) {
                    dropzone.insertBefore(dragging, dragPlaceholder);
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
            updateColumnMeta();
        }

        function clearDropzoneHover() {
            board.querySelectorAll('.task-items-kanban-dropzone.is-drag-over').forEach(function (zone) {
                zone.classList.remove('is-drag-over');
            });
            board.querySelectorAll('.task-items-kanban-column.is-column-drag-target').forEach(function (column) {
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
            if (dragContext && dragContext.itemId) {
                var contextualCard = board.querySelector('.task-items-kanban-card[data-item-id="' + dragContext.itemId + '"]');
                if (contextualCard) return contextualCard;
            }
            return board.querySelector('.task-items-kanban-card.is-dragging');
        }

        function createDragPlaceholder(card) {
            removeDragPlaceholder();
            if (!card) return null;

            var placeholderHeight = (
                dragContext &&
                Number.isFinite(dragContext.cardHeight) &&
                dragContext.cardHeight > 0
            ) ? dragContext.cardHeight : card.getBoundingClientRect().height;
            dragPlaceholder = document.createElement('div');
            dragPlaceholder.className = 'task-items-kanban-placeholder';
            dragPlaceholder.setAttribute('aria-hidden', 'true');
            dragPlaceholder.style.height = Math.max(Math.round(placeholderHeight), 40) + 'px';
            return dragPlaceholder;
        }

        function removeDragPlaceholder() {
            if (!dragPlaceholder) return;
            if (dragPlaceholder.parentNode) {
                dragPlaceholder.parentNode.removeChild(dragPlaceholder);
            }
            dragPlaceholder = null;
        }

        function createDragGhost(card) {
            removeDragGhost();
            if (!card || !pageRoot) return null;

            var rect = card.getBoundingClientRect();
            dragGhost = card.cloneNode(true);
            dragGhost.classList.remove('is-dragging', 'is-drop-settling', 'is-delete-confirming');
            dragGhost.classList.add('is-drag-ghost');
            dragGhost.style.position = 'fixed';
            dragGhost.style.top = '-9999px';
            dragGhost.style.left = '-9999px';
            dragGhost.style.width = Math.round(rect.width) + 'px';
            dragGhost.style.pointerEvents = 'none';
            dragGhost.style.zIndex = '9999';
            pageRoot.appendChild(dragGhost);
            return dragGhost;
        }

        function removeDragGhost() {
            if (!dragGhost) return;
            if (dragGhost.parentNode) {
                dragGhost.parentNode.removeChild(dragGhost);
            }
            dragGhost = null;
        }

        function restoreDraggedCardPosition() {
            var card = getDraggingCard();
            if (card) {
                setCardStatus(card, (dragContext && dragContext.previousStatus) || 'nao_iniciada');
                card.classList.remove('is-dragging');
                card.classList.remove('is-drop-settling');
            }
            removeDragPlaceholder();
            removeDragGhost();
        }

        function triggerDropSettle(card) {
            if (!card || prefersReducedMotion()) return;

            card.classList.remove('is-drop-settling');
            void card.offsetWidth;
            card.classList.add('is-drop-settling');

            var handleAnimationEnd = function () {
                card.classList.remove('is-drop-settling');
                card.removeEventListener('animationend', handleAnimationEnd);
            };
            card.addEventListener('animationend', handleAnimationEnd);
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
                ? updateItemStatus(itemId, nextStatus, {
                    skipKanbanSync: true,
                    showAlert: false,
                    celebrationOrigin: card,
                })
                : Promise.resolve();

            statusPromise
                .then(function () {
                    return persistKanbanOrder();
                })
                .then(function () {
                    syncListOrderFromKanban();
                    updateColumnMeta();
                    writeStoredKanbanOrder(serializeKanbanOrder());
                })
                .catch(function (error) {
                    console.error('Erro ao persistir kanban:', error);
                    renderKanbanFromList();
                    alert((error && error.message) || 'Nao foi possivel persistir a movimentacao no Kanban.');
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
                    if (!canDragItemMoveToStatus(dropzone.getAttribute('data-status') || 'nao_iniciada')) return;
                    setDropzoneHover(dropzone);
                });

                dropzone.addEventListener('dragover', function (event) {
                    if (!dragContext || isPersisting || isDeleting) return;
                    event.preventDefault();
                    if (!canDragItemMoveToStatus(dropzone.getAttribute('data-status') || 'nao_iniciada')) return;
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
                    if (!dragContext || isPersisting || isDeleting) return;
                    finalizeDrop(event, dropzone);
                });
            });

            board.addEventListener('dragover', function (event) {
                if (!dragContext || isPersisting || isDeleting || event.defaultPrevented) return;
                var dropzone = resolveDropzoneFromEvent(event);
                if (!dropzone) return;
                event.preventDefault();
                if (!canDragItemMoveToStatus(dropzone.getAttribute('data-status') || 'nao_iniciada')) return;
                placeDragPlaceholder(dropzone, event.clientY);
            });

            board.addEventListener('drop', function (event) {
                if (!dragContext || isPersisting || isDeleting || event.defaultPrevented) return;
                var dropzone = resolveDropzoneFromEvent(event);
                if (!dropzone) return;
                finalizeDrop(event, dropzone);
            });

            board.addEventListener('dragleave', function (event) {
                if (!dragContext || isPersisting || isDeleting) return;
                if (board.contains(event.relatedTarget)) return;
                clearDropzoneHover();
            });
        }

        function bindKanbanComposers() {
            composerControllers = {};
            var composers = kanbanView.querySelectorAll('.task-items-kanban-composer[data-status]');
            var selectedProjectFromFilter = (
                window.TASK_HUB_CONFIG &&
                String(window.TASK_HUB_CONFIG.selectedProject || '').trim()
            ) || '';
            var selectedAreaFromFilter = (
                window.TASK_HUB_CONFIG &&
                String(window.TASK_HUB_CONFIG.selectedArea || '').trim()
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
                var status = normalizeStatus(composer.getAttribute('data-status') || 'nao_iniciada');
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
                            if (currentView === 'kanban') {
                                renderKanbanFromList();
                                var newItemId = data && data.item && String(data.item.id);
                                if (newItemId) {
                                    var newCard = board.querySelector('.task-items-kanban-card[data-item-id="' + newItemId + '"]');
                                    var targetDropzone = getDropzone(status);
                                    if (newCard && targetDropzone) {
                                        targetDropzone.appendChild(newCard);
                                    }
                                }
                            }
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
                    if (!composerProject && !selectedAreaFromFilter) {
                        if (projectInput) projectInput.focus();
                        alert('Selecione um projeto para escolher responsáveis.');
                        return;
                    }
                    responsavelPickerManager.open({
                        anchorEl: ownerTrigger,
                        taskId: taskId,
                        sugestoesUrl: listEl.getAttribute('data-sugestoes-url') || '',
                        projectValue: composerProject,
                        areaValue: !composerProject ? selectedAreaFromFilter : '',
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
            var normalized = normalizeStatus(status || 'nao_iniciada');
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
                clearDropzoneHover();
                removeDragPlaceholder();
                card.classList.remove('is-drop-settling');

                dragContext = {
                    itemId: card.getAttribute('data-item-id'),
                    previousStatus: card.getAttribute('data-status') || 'nao_iniciada',
                    cardHeight: card.getBoundingClientRect().height,
                    originParent: card.parentNode,
                    originNextSibling: card.nextElementSibling,
                    didDrop: false,
                };
                if (event.dataTransfer) {
                    event.dataTransfer.effectAllowed = 'move';
                    event.dataTransfer.setData('text/plain', dragContext.itemId || '');
                    var ghost = createDragGhost(card);
                    if (ghost && typeof event.dataTransfer.setDragImage === 'function') {
                        event.dataTransfer.setDragImage(ghost, 24, 24);
                    }
                }
                setTimeout(function () {
                    if (!dragContext || dragContext.itemId !== card.getAttribute('data-item-id')) return;
                    card.classList.add('is-dragging');
                    removeDragGhost();
                }, 0);
            });

            board.addEventListener('dragend', function () {
                var context = dragContext;
                if (context && !context.didDrop) {
                    restoreDraggedCardPosition();
                } else {
                    var dragging = getDraggingCard();
                    if (dragging) dragging.classList.remove('is-dragging');
                    removeDragPlaceholder();
                    removeDragGhost();
                }
                dragContext = null;
                suppressCardClickUntil = Date.now() + 140;
                clearDropzoneHover();
                updateColumnMeta();
            });
        }

        function applyView(mode, opts) {
            var targetMode = mode === 'kanban' ? 'kanban' : 'list';
            var options = opts || {};
            if (targetMode === 'kanban' && !listEl.querySelector('.task-item-row[data-item-id]')) {
                targetMode = 'list';
            }
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

        function showNoTasksToast() {
            var existing = document.querySelector('.tasks-no-tasks-toast');
            if (existing) {
                clearTimeout(existing._hideTimer);
                clearTimeout(existing._removeTimer);
                existing.remove();
            }
            var toast = document.createElement('div');
            toast.className = 'tasks-no-tasks-toast';
            toast.textContent = 'Adicione tarefas para usar o Kanban.';
            document.body.appendChild(toast);
            toast._hideTimer = setTimeout(function () {
                toast.classList.add('is-hiding');
                toast._removeTimer = setTimeout(function () { toast.remove(); }, 320);
            }, 2800);
        }

        function handleToggleClick(event) {
            var button = event.target.closest('.task-items-view-btn[data-view]');
            if (!button) return;
            event.preventDefault();
            if (button.getAttribute('data-no-tasks') === '1') {
                showNoTasksToast();
                return;
            }
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
