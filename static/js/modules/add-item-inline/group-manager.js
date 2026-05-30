// === group-manager.js — CRUD de grupos de projeto no hub de tarefas ===
(function (global) {
    var registry = global.AddItemInlineModules = global.AddItemInlineModules || {};

    registry.groupManager = function (ctx) {
        var listEl = ctx.refs.listEl;
        var listView = ctx.refs.listView;

        function getEmptyState() {
            return listView ? listView.querySelector('[data-role="task-hub-empty-state"]') : null;
        }

        function syncListScaffoldVisibility() {
            var hasGroups = !!listEl.querySelector('.task-hub-group');
            listEl.hidden = !hasGroups;

            var emptyState = getEmptyState();
            if (emptyState) {
                emptyState.hidden = hasGroups;
            }
        }

        function getGlobalPlaceholderGroup() {
            return listEl.querySelector('.task-hub-group[data-global-placeholder="1"]');
        }

        function getGroupByProject(projectValue, options) {
            var normalized = ctx.normalizeProjectValue(projectValue);
            if (!normalized) return null;

            var opts = options || {};
            var groups = Array.prototype.slice.call(listEl.querySelectorAll('.task-hub-group[data-project-value]'));
            for (var i = 0; i < groups.length; i += 1) {
                var groupEl = groups[i];
                if (opts.excludeGroup && groupEl === opts.excludeGroup) continue;
                if (!opts.includePlaceholder && groupEl.getAttribute('data-global-placeholder') === '1') continue;
                if (ctx.normalizeProjectValue(groupEl.getAttribute('data-project-value')) === normalized) {
                    return groupEl;
                }
            }
            return null;
        }

        function getAddRowByProject(projectValue, options) {
            var groupEl = getGroupByProject(projectValue, options);
            if (!groupEl) return null;
            return groupEl.querySelector('.task-hub-add-row[data-project-value]');
        }

        function updateGroupCount(groupEl) {
            if (!groupEl) return;
            var count = groupEl.querySelectorAll('.task-item-row[data-item-id]').length;
            var countLabel = count + (count === 1 ? ' tarefa' : ' tarefas');
            var metaCountEl = groupEl.querySelector('[data-role="group-task-count"]');
            if (metaCountEl) {
                metaCountEl.textContent = countLabel;
            }
        }

        function getSortedInsertBefore(projectInfo) {
            var groups = Array.prototype.slice.call(listEl.querySelectorAll('.task-hub-group:not([data-global-placeholder="1"])'));
            if (!groups.length) return null;

            var isOrphan = projectInfo.value === 'sem_projeto';
            var targetTitle = String(projectInfo.label || '').toLowerCase();

            for (var i = 0; i < groups.length; i += 1) {
                var current = groups[i];
                var currentProjectValue = ctx.normalizeProjectValue(current.getAttribute('data-project-value'));
                var currentTitleEl = current.querySelector('.task-hub-group-title, .task-hub-group-title-link');
                var currentTitle = currentTitleEl ? (currentTitleEl.textContent || '').trim() : '';
                var currentNormalizedTitle = String(currentTitle || '').toLowerCase();

                if (isOrphan) {
                    continue;
                }
                if (currentProjectValue === 'sem_projeto') {
                    return current;
                }
                if (currentNormalizedTitle > targetTitle) {
                    return current;
                }
            }
            return null;
        }

        function createRegularGroup(projectInfo) {
            var groupEl = ctx.createElementFromMarkup(ctx.buildRegularGroupMarkup(projectInfo));
            var beforeNode = getSortedInsertBefore(projectInfo);
            if (beforeNode) {
                listEl.insertBefore(groupEl, beforeNode);
            } else {
                listEl.appendChild(groupEl);
            }

            ctx.initializeAddRow(groupEl.querySelector('.task-hub-add-row[data-project-value]'), {
                getProjectValue: function () {
                    return ctx.normalizeProjectValue(groupEl.getAttribute('data-project-value'));
                },
            });
            syncListScaffoldVisibility();
            return groupEl;
        }

        function convertGlobalPlaceholderGroupToRegular(groupEl, projectInfo) {
            if (!groupEl) return null;

            groupEl.removeAttribute('data-global-placeholder');
            groupEl.classList.remove('task-hub-group-global-placeholder');
            groupEl.setAttribute('data-project-value', projectInfo.value);
            groupEl.setAttribute('data-project-id', projectInfo.value === 'sem_projeto' ? '' : projectInfo.value);

            var header = groupEl.querySelector('.task-hub-group-header');
            if (header) {
                header.insertAdjacentHTML('afterbegin', '');
                header.textContent = '';
                header.insertAdjacentHTML('afterbegin', ctx.buildGroupHeaderMarkup(projectInfo));
            }

            var addRow = groupEl.querySelector('.task-hub-add-row[data-project-value]');
            if (addRow) {
                addRow.setAttribute('data-project-value', projectInfo.value);
                addRow.removeAttribute('data-global-add');
            }

            updateGroupCount(groupEl);
            return groupEl;
        }

        function removeGlobalPlaceholderGroup(groupEl) {
            var targetGroup = groupEl || getGlobalPlaceholderGroup();
            if (targetGroup && targetGroup.parentNode) {
                targetGroup.parentNode.removeChild(targetGroup);
            }
            syncListScaffoldVisibility();
        }

        function ensureGlobalPlaceholderGroup(options) {
            var opts = options || {};
            var existing = getGlobalPlaceholderGroup();
            var preferredValue = ctx.config.selectedProject || ctx.normalizeProjectValue(opts.projectValue);
            if (existing) {
                if (!ctx.config.selectedProject && preferredValue) {
                    ctx.setGlobalPlaceholderProject(existing, preferredValue);
                }
                return existing;
            }

            if (!preferredValue && !ctx.getProjectOptionsForPicker().length) {
                alert('Nenhum projeto dispon\u00edvel para criar tarefas neste escopo.');
                return null;
            }

            var projectInfo = ctx.getProjectInfo(preferredValue, ctx.config.selectedProjectLabel, ctx.config.selectedOrgaoSigla);
            var groupEl = ctx.createElementFromMarkup(ctx.buildGlobalPlaceholderMarkup(projectInfo, { lockProject: !!ctx.config.selectedProject }));
            listEl.insertBefore(groupEl, listEl.firstChild);

            var addRow = groupEl.querySelector('.task-hub-add-row[data-project-value]');
            ctx.initializeAddRow(addRow, {
                isGlobalPlaceholder: true,
                getProjectValue: function () {
                    return ctx.normalizeProjectValue(groupEl.getAttribute('data-project-value'));
                },
                containsTarget: function (target) {
                    return !!(target && groupEl.contains(target));
                },
                focusProjectSelector: function () {
                    var input = groupEl.querySelector('input[data-role="project-input"]');
                    if (input) {
                        input.focus();
                    }
                },
                onCancel: function () {
                    removeGlobalPlaceholderGroup(groupEl);
                },
            });

            if (!ctx.config.selectedProject) {
                ctx.setupGlobalPlaceholderProjectPicker(groupEl);
            }

            syncListScaffoldVisibility();
            return groupEl;
        }

        function resolveTargetGroupForItem(item, options) {
            var opts = options || {};
            var projectInfo = ctx.getProjectInfo(item.project_value || item.project_id || opts.projectValue || '', item.project_titulo, item.project_orgao_sigla);
            var sourceGroup = opts.sourceGroup || null;
            var existingGroup = getGroupByProject(projectInfo.value, {
                includePlaceholder: false,
                excludeGroup: sourceGroup,
            });

            if (sourceGroup && sourceGroup.getAttribute('data-global-placeholder') === '1') {
                var sourceProjectValue = ctx.normalizeProjectValue(sourceGroup.getAttribute('data-project-value'));
                if (sourceProjectValue === projectInfo.value) {
                    if (existingGroup) {
                        removeGlobalPlaceholderGroup(sourceGroup);
                        return existingGroup;
                    }
                    return convertGlobalPlaceholderGroupToRegular(sourceGroup, projectInfo);
                }
            }

            if (sourceGroup) {
                var srcVal = ctx.normalizeProjectValue(sourceGroup.getAttribute('data-project-value'));
                if (srcVal === projectInfo.value) {
                    return sourceGroup;
                }
            }

            if (existingGroup) {
                return existingGroup;
            }
            return createRegularGroup(projectInfo);
        }

        function insertNewItem(data, options) {
            var payload = data || {};
            var opts = options || {};
            var item = payload.item || {};
            if (!item || !item.id) return null;

            var targetGroup = resolveTargetGroupForItem(item, opts);
            if (!targetGroup) return null;

            var targetAddRow = resolveTargetAddRow(targetGroup, item);
            if (!targetAddRow || !targetAddRow.parentNode) return null;

            var markup = ctx.buildItemRowMarkup(item);
            ctx.insertNodesBefore(targetAddRow, markup.rowHtml + markup.modalHtml);

            updateGroupCount(targetGroup);
            syncListScaffoldVisibility();
            if (typeof window.updateTaskItemsHeaderCount === 'function') window.updateTaskItemsHeaderCount();
            if (typeof window.updateTaskItemsTotalPill === 'function') window.updateTaskItemsTotalPill();
            if (typeof window.updateTaskHubStageAndProjectProgress === 'function') window.updateTaskHubStageAndProjectProgress();
            if (window.taskItemsKanban && typeof window.taskItemsKanban.rebuildFromList === 'function') {
                window.taskItemsKanban.rebuildFromList();
            }
            if (opts.focusInserted !== false) {
                if (typeof window.focusTaskItemRow === 'function') window.focusTaskItemRow(String(item.id), { scrollDelay: 100 });
            }
            if (typeof window.getTaskItemRowById === 'function') return window.getTaskItemRowById(item.id);
            return null;
        }

        function resolveTargetAddRow(targetGroup, item) {
            if (!targetGroup) return null;
            var etapaValue = String(item.etapa_value || item.etapa_id || '').trim() || 'sem_etapa';
            var rows = Array.prototype.slice.call(targetGroup.querySelectorAll('.task-hub-add-row[data-project-value]'));
            for (var i = 0; i < rows.length; i += 1) {
                var rowStageValue = String(rows[i].getAttribute('data-stage-value') || '').trim();
                if (rowStageValue && rowStageValue === etapaValue) {
                    return rows[i];
                }
            }
            for (var j = 0; j < rows.length; j += 1) {
                if (!rows[j].hasAttribute('data-stage-value')) {
                    return rows[j];
                }
            }
            return rows[0] || null;
        }

        ctx.getEmptyState = getEmptyState;
        ctx.syncListScaffoldVisibility = syncListScaffoldVisibility;
        ctx.getGlobalPlaceholderGroup = getGlobalPlaceholderGroup;
        ctx.getGroupByProject = getGroupByProject;
        ctx.getAddRowByProject = getAddRowByProject;
        ctx.updateGroupCount = updateGroupCount;
        ctx.getSortedInsertBefore = getSortedInsertBefore;
        ctx.createRegularGroup = createRegularGroup;
        ctx.convertGlobalPlaceholderGroupToRegular = convertGlobalPlaceholderGroupToRegular;
        ctx.removeGlobalPlaceholderGroup = removeGlobalPlaceholderGroup;
        ctx.ensureGlobalPlaceholderGroup = ensureGlobalPlaceholderGroup;
        ctx.resolveTargetGroupForItem = resolveTargetGroupForItem;
        ctx.insertNewItem = insertNewItem;
    };
})(window);
