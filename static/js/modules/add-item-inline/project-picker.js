// === project-picker.js — Seletor de projeto no placeholder global ===
(function (global) {
    var registry = global.AddItemInlineModules = global.AddItemInlineModules || {};

    registry.projectPicker = function (ctx) {

        function setGlobalPlaceholderProject(groupEl, projectValue, projectLabel, projectOrgaoSigla) {
            if (!groupEl) return;

            var projectInfo = ctx.getProjectInfo(projectValue, projectLabel, projectOrgaoSigla);
            groupEl.setAttribute('data-project-value', projectInfo.value);
            groupEl.setAttribute('data-project-id', projectInfo.value === 'sem_projeto' ? '' : projectInfo.value);

            var hiddenValue = groupEl.querySelector('input[data-role="project-value"]');
            if (hiddenValue) {
                hiddenValue.value = projectInfo.value;
            }

            var input = groupEl.querySelector('input[data-role="project-input"]');
            if (input) {
                input.value = projectInfo.value ? projectInfo.label : '';
            }

            var orgaoEl = groupEl.querySelector('[data-role="project-orgao"]');
            if (orgaoEl) {
                orgaoEl.textContent = projectInfo.orgaoSigla || ctx.config.selectedOrgaoSigla || 'Selecione um projeto';
            }

            var addRow = groupEl.querySelector('.task-hub-add-row');
            if (addRow) {
                addRow.setAttribute('data-project-value', projectInfo.value);
                if (addRow._taskHubController && typeof addRow._taskHubController.refreshProjectState === 'function') {
                    addRow._taskHubController.refreshProjectState();
                }
            }
        }

        function setupGlobalPlaceholderProjectPicker(groupEl) {
            var wrap = groupEl.querySelector('.task-hub-group-project-wrap');
            var input = groupEl.querySelector('input[data-role="project-input"]');
            var hiddenValue = groupEl.querySelector('input[data-role="project-value"]');
            var dropdown = groupEl.querySelector('[data-role="project-dropdown"]');
            if (!wrap || !input || !hiddenValue || !dropdown) return;

            var options = Array.prototype.slice.call(dropdown.querySelectorAll('.project-search-option[data-value]'));
            var emptyState = dropdown.querySelector('[data-empty-state="1"]');

            function filterOptions() {
                var query = (input.value || '').trim().toLowerCase();
                var visibleCount = 0;
                options.forEach(function (optionEl) {
                    var label = (optionEl.getAttribute('data-label') || optionEl.textContent || '').toLowerCase();
                    var isVisible = !query || label.indexOf(query) !== -1;
                    optionEl.classList.toggle('hidden-by-filter', !isVisible);
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

            function selectOption(optionEl) {
                var value = ctx.normalizeProjectValue(optionEl.getAttribute('data-value'));
                var label = optionEl.getAttribute('data-label') || optionEl.textContent || '';
                var info = ctx.getProjectInfo(value, label);
                setGlobalPlaceholderProject(groupEl, info.value, info.label, info.orgaoSigla);
                hideDropdown();

                var addRow = groupEl.querySelector('.task-hub-add-row');
                if (addRow && addRow._taskHubController && typeof addRow._taskHubController.focusDescription === 'function') {
                    addRow._taskHubController.focusDescription();
                }
            }

            input.addEventListener('click', showDropdown);
            input.addEventListener('input', function () {
                if (!(input.value || '').trim()) {
                    hiddenValue.value = '';
                    setGlobalPlaceholderProject(groupEl, '', '', ctx.config.selectedOrgaoSigla);
                }
                showDropdown();
            });
            input.addEventListener('keydown', function (event) {
                if (event.key === 'Escape') {
                    hideDropdown();
                    return;
                }

                var visibleOptions = options.filter(function (optionEl) {
                    return !optionEl.classList.contains('hidden-by-filter');
                });
                if (!visibleOptions.length) return;

                if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                    event.preventDefault();
                    var active = dropdown.querySelector('.project-search-option.active');
                    var index = visibleOptions.indexOf(active);
                    if (event.key === 'ArrowDown') {
                        index = index < 0 ? 0 : Math.min(index + 1, visibleOptions.length - 1);
                    } else {
                        index = index < 0 ? visibleOptions.length - 1 : Math.max(index - 1, 0);
                    }
                    visibleOptions.forEach(function (optionEl, position) {
                        optionEl.classList.toggle('active', position === index);
                    });
                    visibleOptions[index].scrollIntoView({ block: 'nearest' });
                    return;
                }

                if (event.key === 'Enter') {
                    event.preventDefault();
                    var current = dropdown.querySelector('.project-search-option.active');
                    if (current && !current.classList.contains('hidden-by-filter')) {
                        selectOption(current);
                    }
                }
            });

            options.forEach(function (optionEl) {
                optionEl.addEventListener('click', function () {
                    selectOption(optionEl);
                });
            });

            document.addEventListener('mousedown', function (event) {
                if (!document.body.contains(groupEl)) return;
                if (!wrap.contains(event.target)) {
                    hideDropdown();
                }
            });
        }

        ctx.setGlobalPlaceholderProject = setGlobalPlaceholderProject;
        ctx.setupGlobalPlaceholderProjectPicker = setupGlobalPlaceholderProjectPicker;
    };
})(window);
