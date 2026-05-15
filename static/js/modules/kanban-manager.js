// === kanban-manager.js — Fachada Kanban com módulos compartilhados ===

(function (global) {
    var moduleRegistry = global.TaskItemsKanbanModules = global.TaskItemsKanbanModules || {};

    var taskItemsKanbanManager = (function () {
        var statusOrder = ['nao_iniciada', 'em_andamento', 'para_validacao', 'para_ajustes', 'finalizada'];
        var statusLabels = {
            nao_iniciada: 'Não iniciada',
            em_andamento: 'Em andamento',
            para_validacao: 'Para validação',
            para_ajustes: 'Para ajustes',
            finalizada: 'Finalizada',
        };
        var DRAWER_RESTRICTED_EDIT_MESSAGE = 'Somente o autor da tarefa ou um administrador pode editar descrição, prioridade e responsável.';

        var refs = {
            pageRoot: document.querySelector('.task-detail-v2'),
            toggleRoot: document.getElementById('taskItemsViewToggle'),
            listView: document.getElementById('taskItemsListView'),
            kanbanView: document.getElementById('taskItemsKanbanView'),
            board: document.getElementById('taskItemsKanbanBoard'),
            listEl: document.querySelector('.task-items-list'),
            drawer: document.getElementById('taskItemDrawer'),
            drawerBackdrop: document.getElementById('taskItemDrawerBackdrop'),
            drawerClose: document.getElementById('taskItemDrawerClose'),
            drawerTitle: document.getElementById('taskItemDrawerTitle'),
            drawerStatusBadge: document.getElementById('taskItemDrawerStatusBadge'),
            drawerDesc: document.getElementById('taskItemDrawerDesc'),
            drawerResponsavelTrigger: document.getElementById('taskItemDrawerResponsavelTrigger'),
            drawerAutosaveStatus: document.getElementById('taskItemDrawerAutosaveStatus'),
            drawerPermissionBanner: document.getElementById('taskItemDrawerPermissionBanner'),
            drawerDeleteIcon: document.getElementById('taskItemDrawerDeleteIcon'),
            drawerDeleteConfirm: document.getElementById('taskItemDrawerDeleteConfirm'),
            drawerDeleteCancel: document.getElementById('taskItemDrawerDeleteCancel'),
            drawerDeleteConfirmBtn: document.getElementById('taskItemDrawerDeleteConfirmBtn'),
            drawerCommentsStatus: document.getElementById('taskItemDrawerCommentsStatus'),
            drawerCommentsList: document.getElementById('taskItemDrawerCommentsList'),
            drawerCommentsCount: document.getElementById('taskItemDrawerCommentsCount'),
            drawerCommentForm: document.getElementById('taskItemDrawerCommentForm'),
            drawerCommentsToggle: document.getElementById('taskItemDrawerCommentsToggle'),
            drawerCommentsBody: document.getElementById('taskItemDrawerCommentsBody'),
            drawerPrioridade: document.getElementById('taskItemDrawerPrioridade'),
            drawerTipoPedido: document.getElementById('taskItemDrawerTipoPedido'),
            drawerAnexosToggle: document.getElementById('taskItemDrawerAnexosToggle'),
            drawerAnexosBody: document.getElementById('taskItemDrawerAnexosBody'),
            drawerAnexosList: document.getElementById('taskItemDrawerAnexosList'),
            drawerAnexosCount: document.getElementById('taskItemDrawerAnexosCount'),
            drawerAnexoInput: document.getElementById('taskItemDrawerAnexoInput'),
            quickAnexoInput: document.getElementById('taskQuickAnexoInput'),
            anexoPreviewModal: document.getElementById('taskAnexoPreviewModal'),
            anexoPreviewBackdrop: document.getElementById('taskAnexoPreviewBackdrop'),
            anexoPreviewClose: document.getElementById('taskAnexoPreviewClose'),
            anexoPreviewTitle: document.getElementById('taskAnexoPreviewTitle'),
            anexoPreviewBody: document.getElementById('taskAnexoPreviewBody'),
            anexoPreviewOpen: document.getElementById('taskAnexoPreviewOpen'),
            anexoPreviewDownload: document.getElementById('taskAnexoPreviewDownload'),
        };
        refs.toggleButtons = refs.toggleRoot ? refs.toggleRoot.querySelectorAll('.task-items-view-btn[data-view]') : [];
        refs.toggleVisual = refs.toggleRoot ? {
            pathLeft: refs.toggleRoot.querySelector('[data-role="path-left"]'),
            pathRight: refs.toggleRoot.querySelector('[data-role="path-right"]'),
            divider: refs.toggleRoot.querySelector('[data-role="divider"]'),
            fillLeft: refs.toggleRoot.querySelector('[data-role="fill-left"]'),
            fillRight: refs.toggleRoot.querySelector('[data-role="fill-right"]'),
            highlightLeft: refs.toggleRoot.querySelector('[data-role="highlight-left"]'),
            highlightRight: refs.toggleRoot.querySelector('[data-role="highlight-right"]'),
            borderLeft: refs.toggleRoot.querySelector('[data-role="border-left"]'),
            labelList: refs.toggleRoot.querySelector('[data-view-label="list"]'),
            labelKanban: refs.toggleRoot.querySelector('[data-view-label="kanban"]'),
        } : null;
        refs.drawerCommentsSection = refs.drawer ? refs.drawer.querySelector('.task-item-drawer-comments') : null;
        refs.anexoPreviewDialog = refs.anexoPreviewModal ? refs.anexoPreviewModal.querySelector('.task-anexo-preview-dialog') : null;

        var taskId = refs.listEl ? (refs.listEl.getAttribute('data-task-id') || '') : '';
        var reorderUrl = refs.listEl ? (refs.listEl.getAttribute('data-reorder-url') || '') : '';
        var storageKey = taskId ? ('task-items-view:' + taskId) : 'task-hub-items-view';
        var currentUserIdRaw = refs.pageRoot ? (refs.pageRoot.getAttribute('data-current-user-id') || '') : '';
        var currentUserId = parseInt(currentUserIdRaw, 10);
        if (!Number.isFinite(currentUserId)) currentUserId = null;

        function buildKanbanOrderStorageKey() {
            try {
                return 'task-hub-kanban-order:' + window.location.pathname + window.location.search;
            } catch (error) {
                return taskId ? ('task-items-kanban-order:' + taskId) : '';
            }
        }

        var state = {
            currentView: 'list',
            dragContext: null,
            dragPlaceholder: null,
            dragGhost: null,
            isPersisting: false,
            isDeleting: false,
            suppressCardClickUntil: 0,
            toggleVisualDir: 1,
            toggleVisualFrame: null,
            composerControllers: {},
            drawerState: {
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
                canEditRestricted: true,
                permissionBannerTimer: null,
            },
            quickUploadState: { itemId: null },
            previewState: {
                isOpen: false,
                hideTimer: null,
            },
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
            attachListEl: noop,
        };

        // Modo completo: hub /tarefas — requer toggle + board + listEl.
        // Modo drawer-only: página de detalhe do projeto — só precisa do
        // drawer (sem board, sem listEl no load; listEl é injetado depois
        // pelo modal). Em ambos os modos, o drawer DOM precisa existir.
        var hasBoardLayout = !!(refs.toggleRoot && refs.listView && refs.kanbanView && refs.board && refs.listEl);
        var hasDrawerDom = !!refs.drawer;
        if (!hasBoardLayout && !hasDrawerDom) {
            if (refs.toggleRoot) {
                refs.toggleRoot.addEventListener('click', function (event) {
                    var button = event.target.closest('.task-items-view-btn[data-no-tasks="1"]');
                    if (!button) return;
                    event.preventDefault();
                    var existing = document.querySelector('.tasks-no-tasks-toast');
                    if (existing) existing.remove();
                });
            }
            return fallbackApi;
        }

        var ctx = {
            refs: refs,
            state: state,
            statusOrder: statusOrder,
            statusLabels: statusLabels,
            taskId: taskId,
            reorderUrl: reorderUrl,
            storageKey: storageKey,
            kanbanOrderStorageKey: buildKanbanOrderStorageKey(),
            currentUserId: currentUserId,
            drawerRestrictedEditMessage: DRAWER_RESTRICTED_EDIT_MESSAGE,
        };

        function hasDrawer() {
            return !!(
                refs.drawer &&
                refs.drawerBackdrop &&
                refs.drawerDesc &&
                refs.drawerResponsavelTrigger &&
                refs.drawerCommentsList &&
                refs.drawerCommentForm &&
                refs.drawerCommentsToggle &&
                refs.drawerCommentsBody &&
                refs.drawerAutosaveStatus &&
                refs.drawerStatusBadge &&
                refs.drawerDeleteIcon &&
                refs.drawerDeleteConfirm &&
                refs.drawerDeleteCancel &&
                refs.drawerDeleteConfirmBtn &&
                refs.drawerCommentsStatus
            );
        }

        function clearDrawerAutosaveTimer() {
            if (!state.drawerState.autosaveTimer) return;
            clearTimeout(state.drawerState.autosaveTimer);
            state.drawerState.autosaveTimer = null;
        }

        function clearDrawerPermissionBannerTimer() {
            if (!state.drawerState.permissionBannerTimer) return;
            clearTimeout(state.drawerState.permissionBannerTimer);
            state.drawerState.permissionBannerTimer = null;
        }

        function hideDrawerPermissionBanner() {
            if (!refs.drawerPermissionBanner) return;
            clearDrawerPermissionBannerTimer();
            refs.drawerPermissionBanner.textContent = '';
            refs.drawerPermissionBanner.setAttribute('hidden', '');
        }

        function showDrawerPermissionBanner(message) {
            if (!refs.drawerPermissionBanner) return;
            clearDrawerPermissionBannerTimer();
            refs.drawerPermissionBanner.textContent = message || DRAWER_RESTRICTED_EDIT_MESSAGE;
            refs.drawerPermissionBanner.removeAttribute('hidden');
            state.drawerState.permissionBannerTimer = setTimeout(function () {
                hideDrawerPermissionBanner();
            }, 3200);
        }

        function setDrawerRestrictedFieldLocks(canEditRestricted) {
            var canEdit = !!canEditRestricted;
            state.drawerState.canEditRestricted = canEdit;
            if (!hasDrawer()) return;

            refs.drawer.classList.toggle('is-restricted-edit-blocked', !canEdit);

            if (refs.drawerDesc) {
                refs.drawerDesc.readOnly = !canEdit;
                refs.drawerDesc.classList.toggle('is-locked', !canEdit);
                refs.drawerDesc.setAttribute('aria-readonly', canEdit ? 'false' : 'true');
            }
            if (refs.drawerPrioridade) {
                refs.drawerPrioridade.classList.toggle('is-locked', !canEdit);
                refs.drawerPrioridade.setAttribute('aria-disabled', canEdit ? 'false' : 'true');
            }
            if (refs.drawerResponsavelTrigger) {
                refs.drawerResponsavelTrigger.classList.toggle('is-locked', !canEdit);
                refs.drawerResponsavelTrigger.setAttribute('aria-disabled', canEdit ? 'false' : 'true');
            }

            if (canEdit) {
                hideDrawerPermissionBanner();
            }
        }

        function handleDrawerRestrictedInteraction(event) {
            if (state.drawerState.canEditRestricted || !state.drawerState.itemId || state.isDeleting) return false;
            if (event) {
                event.preventDefault();
                event.stopPropagation();
            }
            showDrawerPermissionBanner(DRAWER_RESTRICTED_EDIT_MESSAGE);
            return true;
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
            if (!state.dragContext) return false;

            var dragging = typeof ctx.getDraggingCard === 'function'
                ? ctx.getDraggingCard()
                : null;
            var canFinalize = dragging
                ? parsePermissionFlag(dragging.getAttribute('data-can-finalize'), true)
                : true;

            return canItemMoveToStatus(
                { canFinalize: canFinalize, status: state.dragContext.previousStatus },
                targetStatus,
                state.dragContext.previousStatus
            );
        }

        function getDropzone(status) {
            if (!refs.board) return null;
            return refs.board.querySelector('.task-items-kanban-dropzone[data-status="' + normalizeStatus(status) + '"]');
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
            if (!ctx.kanbanOrderStorageKey) return [];
            try {
                return normalizeStoredKanbanOrder(JSON.parse(localStorage.getItem(ctx.kanbanOrderStorageKey) || '[]'));
            } catch (error) {
                return [];
            }
        }

        function writeStoredKanbanOrder(orderIds) {
            if (!ctx.kanbanOrderStorageKey) return;
            try {
                localStorage.setItem(
                    ctx.kanbanOrderStorageKey,
                    JSON.stringify(normalizeStoredKanbanOrder(orderIds))
                );
            } catch (error) {}
        }

        function isTaskHubGroupedList() {
            return !!refs.listEl.querySelector('.task-hub-group');
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
                refs.listEl.querySelectorAll('.task-item-row[data-item-id]'),
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

        ctx.hasDrawer = hasDrawer;
        ctx.clearDrawerAutosaveTimer = clearDrawerAutosaveTimer;
        ctx.clearDrawerPermissionBannerTimer = clearDrawerPermissionBannerTimer;
        ctx.hideDrawerPermissionBanner = hideDrawerPermissionBanner;
        ctx.showDrawerPermissionBanner = showDrawerPermissionBanner;
        ctx.setDrawerRestrictedFieldLocks = setDrawerRestrictedFieldLocks;
        ctx.handleDrawerRestrictedInteraction = handleDrawerRestrictedInteraction;
        ctx.prefersReducedMotion = prefersReducedMotion;
        ctx.payloadSnapshot = payloadSnapshot;
        ctx.buildKanbanOrderStorageKey = buildKanbanOrderStorageKey;
        ctx.normalizeStatus = normalizeStatus;
        ctx.getStatusLabel = getStatusLabel;
        ctx.parsePermissionFlag = parsePermissionFlag;
        ctx.canItemMoveToStatus = canItemMoveToStatus;
        ctx.canDragItemMoveToStatus = canDragItemMoveToStatus;
        ctx.getDropzone = getDropzone;
        ctx.buildKanbanProjectUrl = buildKanbanProjectUrl;
        ctx.renderKanbanContext = renderKanbanContext;
        ctx.readStoredView = readStoredView;
        ctx.saveStoredView = saveStoredView;
        ctx.normalizeStoredKanbanOrder = normalizeStoredKanbanOrder;
        ctx.readStoredKanbanOrder = readStoredKanbanOrder;
        ctx.writeStoredKanbanOrder = writeStoredKanbanOrder;
        ctx.isTaskHubGroupedList = isTaskHubGroupedList;
        ctx.readRowItem = readRowItem;
        ctx.collectListItems = collectListItems;
        ctx.sortItemsForKanban = sortItemsForKanban;

        function installModule(name) {
            var installer = moduleRegistry[name];
            if (typeof installer !== 'function') {
                throw new Error('TaskItemsKanban module missing: ' + name);
            }
            installer(ctx);
        }

        installModule('boardRender');
        installModule('drawerComments');
        installModule('drawerAnexos');
        installModule('drawerCore');
        installModule('boardDnd');
        installModule('composer');
        installModule('viewToggle');

        function init() {
            if (refs.toggleRoot && typeof ctx.handleToggleClick === 'function') {
                refs.toggleRoot.addEventListener('click', ctx.handleToggleClick);
            }
            if (hasBoardLayout) {
                if (typeof ctx.bindBoardEvents === 'function') ctx.bindBoardEvents();
                if (typeof ctx.bindDropzones === 'function') ctx.bindDropzones();
                if (typeof ctx.bindKanbanComposers === 'function') ctx.bindKanbanComposers();
            }
            if (typeof ctx.bindDrawerEvents === 'function') ctx.bindDrawerEvents();
            if (typeof ctx.bindAnexoPreviewModalEvents === 'function') ctx.bindAnexoPreviewModalEvents();
            if (hasBoardLayout && typeof ctx.renderKanbanFromList === 'function') {
                ctx.renderKanbanFromList();
            }
            if (hasBoardLayout && typeof ctx.applyView === 'function') {
                ctx.applyView(ctx.readStoredView(), { persist: false, animateToggle: false });
            }
        }

        init();

        return {
            applyView: ctx.applyView,
            getCurrentView: function () { return state.currentView; },
            rebuildFromList: ctx.renderKanbanFromList,
            focusComposerForStatus: ctx.focusComposerForStatus,
            syncItemFromRow: function (itemId) {
                if (itemId) {
                    if (hasBoardLayout && typeof ctx.syncCardFromRow === 'function') {
                        ctx.syncCardFromRow(String(itemId));
                    }
                    if (state.drawerState.itemId && state.drawerState.itemId === String(itemId)) {
                        ctx.syncDrawerFromCurrentRow();
                    }
                    return;
                }

                if (hasBoardLayout && state.currentView === 'kanban' && typeof ctx.renderKanbanFromList === 'function') {
                    ctx.renderKanbanFromList();
                }
                if (state.drawerState.itemId) {
                    ctx.syncDrawerFromCurrentRow();
                }
            },
            openDrawerAnexos: ctx.openDrawerAnexos,
            openDrawerComments: ctx.openDrawerComments,
            openItemAnexoAction: ctx.openItemAnexoAction,
            // Permite que a página de projeto, que injeta a lista de tarefas
            // dinamicamente via fetch, registre o `.task-items-list` recém
            // inserido. Sem isso, refs.listEl fica null e o drawer não
            // consegue ler `data-sugestoes-url` ao abrir o picker de
            // responsável.
            attachListEl: function (listEl) {
                if (!listEl) return;
                refs.listEl = listEl;
            },
        };
    })();

    global.taskItemsKanban = taskItemsKanbanManager;
})(window);
