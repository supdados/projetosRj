(function (global) {
    var registry = global.TaskItemsKanbanModules = global.TaskItemsKanbanModules || {};

    registry.viewToggle = function registerViewToggle(ctx) {
        var refs = ctx.refs;
        var state = ctx.state;

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
            if (!refs.toggleVisual || !refs.toggleVisual.pathLeft || !refs.toggleVisual.pathRight || !refs.toggleVisual.divider) return;
            refs.toggleVisual.pathLeft.setAttribute('d', buildToggleLeftPath(direction));
            refs.toggleVisual.pathRight.setAttribute('d', buildToggleRightPath(direction));
            refs.toggleVisual.divider.setAttribute('d', buildToggleCurvePath(direction));
        }

        function syncToggleColors(mode) {
            if (!refs.toggleVisual) return;
            var isList = mode !== 'kanban';

            if (refs.toggleVisual.fillLeft) {
                refs.toggleVisual.fillLeft.setAttribute(
                    'fill',
                    isList ? 'url(#taskHubViewToggleActive)' : 'url(#taskHubViewToggleInactive)'
                );
            }
            if (refs.toggleVisual.fillRight) {
                refs.toggleVisual.fillRight.setAttribute(
                    'fill',
                    isList ? 'url(#taskHubViewToggleInactive)' : 'url(#taskHubViewToggleActive)'
                );
            }
            if (refs.toggleVisual.highlightLeft) {
                refs.toggleVisual.highlightLeft.setAttribute('opacity', isList ? '1' : '0');
            }
            if (refs.toggleVisual.highlightRight) {
                refs.toggleVisual.highlightRight.setAttribute('opacity', isList ? '0' : '1');
            }
            if (refs.toggleVisual.borderLeft) {
                refs.toggleVisual.borderLeft.setAttribute('opacity', isList ? '1' : '0');
            }
            if (refs.toggleVisual.labelList) {
                refs.toggleVisual.labelList.classList.toggle('is-active', isList);
            }
            if (refs.toggleVisual.labelKanban) {
                refs.toggleVisual.labelKanban.classList.toggle('is-active', !isList);
            }
        }

        function animateToggleVisual(targetDir) {
            var fromDir = state.toggleVisualDir;
            var start = performance.now();
            var duration = 500;

            if (state.toggleVisualFrame) {
                cancelAnimationFrame(state.toggleVisualFrame);
                state.toggleVisualFrame = null;
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
                state.toggleVisualDir = dir;
                syncTogglePaths(dir);

                if (progress < 1) {
                    state.toggleVisualFrame = requestAnimationFrame(frame);
                    return;
                }

                state.toggleVisualDir = targetDir;
                state.toggleVisualFrame = null;
            }

            state.toggleVisualFrame = requestAnimationFrame(frame);
        }

        function setToggleActiveState(mode, opts) {
            var targetMode = mode === 'kanban' ? 'kanban' : 'list';
            var options = opts || {};
            var targetDir = targetMode === 'kanban' ? -1 : 1;
            refs.toggleRoot.setAttribute('data-active-view', targetMode);
            refs.toggleButtons.forEach(function (button) {
                var isActive = button.getAttribute('data-view') === targetMode;
                button.classList.toggle('is-active', isActive);
                button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
            });
            syncToggleColors(targetMode);

            if (!refs.toggleVisual || !refs.toggleVisual.pathLeft || !refs.toggleVisual.pathRight || !refs.toggleVisual.divider) {
                state.toggleVisualDir = targetDir;
                return;
            }

            if (options.animate === false || ctx.prefersReducedMotion() || state.toggleVisualDir === targetDir) {
                if (state.toggleVisualFrame) {
                    cancelAnimationFrame(state.toggleVisualFrame);
                    state.toggleVisualFrame = null;
                }
                syncTogglePaths(targetDir);
                state.toggleVisualDir = targetDir;
                return;
            }

            animateToggleVisual(targetDir);
        }

        function applyView(mode, opts) {
            var targetMode = mode === 'kanban' ? 'kanban' : 'list';
            var options = opts || {};
            if (targetMode === 'kanban' && !refs.listEl.querySelector('.task-item-row[data-item-id]')) {
                targetMode = 'list';
            }
            state.currentView = targetMode;

            refs.listView.hidden = targetMode !== 'list';
            refs.kanbanView.hidden = targetMode !== 'kanban';
            refs.listView.classList.toggle('is-active', targetMode === 'list');
            refs.kanbanView.classList.toggle('is-active', targetMode === 'kanban');
            setToggleActiveState(targetMode, { animate: options.animateToggle !== false });

            if (targetMode === 'kanban') {
                ctx.renderKanbanFromList();
            } else {
                ctx.closeAllCardDeleteConfirms();
                ctx.closeDrawer();
            }

            if (options.persist !== false) {
                ctx.saveStoredView(targetMode);
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

        ctx.setToggleActiveState = setToggleActiveState;
        ctx.applyView = applyView;
        ctx.showNoTasksToast = showNoTasksToast;
        ctx.handleToggleClick = handleToggleClick;
    };
})(window);
