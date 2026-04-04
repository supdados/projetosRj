// === add-item-inline.js — Orquestrador de adição inline de tarefas ===
// Sub-módulos registrados em window.AddItemInlineModules:
//   domFactories, projectPicker, groupManager, inlineFormController

(function (global) {
    var moduleRegistry = global.AddItemInlineModules = global.AddItemInlineModules || {};

    var listEl = document.querySelector('.task-items-list');
    if (!listEl) return;

    var listView = document.getElementById('taskItemsListView');
    var createButton = document.getElementById('taskHubCreateButton');
    var addUrl = listEl.getAttribute('data-add-item-url');
    var sugestoesUrl = listEl.getAttribute('data-sugestoes-url');
    if (!addUrl) return;

    var hubConfig = global.TASK_HUB_CONFIG || {};

    // ── Helpers de normalização (compartilhados via ctx) ──────────────────────

    function normalizeProjectValue(value) {
        var normalized = String(value == null ? '' : value).trim();
        return normalized || '';
    }

    function normalizeProjectOption(option) {
        if (!option || typeof option !== 'object') return null;
        var value = normalizeProjectValue(option.value);
        if (!value) return null;
        return {
            value: value,
            label: String(option.label || '').trim() || 'Projeto',
            area: String(option.area || '').trim(),
        };
    }

    var selectedArea = String(hubConfig.selectedArea || '').trim();
    var selectedProject = normalizeProjectValue(hubConfig.selectedProject || '');
    var selectedProjectLabel = String(hubConfig.selectedProjectLabel || '').trim();
    var projectOptions = Array.isArray(hubConfig.projectOptions)
        ? hubConfig.projectOptions.map(normalizeProjectOption).filter(function (option) { return !!option; })
        : [];

    function getProjectOptionByValue(projectValue) {
        var normalized = normalizeProjectValue(projectValue);
        if (!normalized) return null;
        for (var i = 0; i < projectOptions.length; i += 1) {
            if (projectOptions[i].value === normalized) {
                return projectOptions[i];
            }
        }
        return null;
    }

    function getProjectOptionsForPicker() {
        if (!selectedArea) {
            return projectOptions.slice();
        }
        var selectedAreaKey = selectedArea.toLowerCase();
        return projectOptions.filter(function (option) {
            var optionArea = String(option && option.area || '').trim().toLowerCase();
            return !!optionArea && optionArea === selectedAreaKey;
        });
    }

    function getProjectInfo(projectValue, fallbackLabel, fallbackArea) {
        var normalized = normalizeProjectValue(projectValue);
        var option = getProjectOptionByValue(normalized);
        return {
            value: normalized,
            label: option ? option.label : (fallbackLabel || (normalized === 'sem_projeto' ? 'Sem projeto' : 'Projeto')),
            area: option ? option.area : String(fallbackArea || '').trim(),
        };
    }

    function buildProjectDetailUrl(projectValue) {
        var normalized = normalizeProjectValue(projectValue);
        if (!normalized || normalized === 'sem_projeto') return '';
        return '/project/' + encodeURIComponent(normalized);
    }

    // ── Contexto compartilhado ───────────────────────────────────────────────

    var ctx = {
        refs: {
            listEl: listEl,
            listView: listView,
            createButton: createButton,
        },
        config: {
            addUrl: addUrl,
            sugestoesUrl: sugestoesUrl,
            selectedArea: selectedArea,
            selectedProject: selectedProject,
            selectedProjectLabel: selectedProjectLabel,
            escapeHtml: global.escapeHtml,
        },
        normalizeProjectValue: normalizeProjectValue,
        normalizeProjectOption: normalizeProjectOption,
        getProjectOptionByValue: getProjectOptionByValue,
        getProjectOptionsForPicker: getProjectOptionsForPicker,
        getProjectInfo: getProjectInfo,
        buildProjectDetailUrl: buildProjectDetailUrl,
    };

    // ── Registra sub-módulos ─────────────────────────────────────────────────

    if (moduleRegistry.domFactories) moduleRegistry.domFactories(ctx);
    if (moduleRegistry.projectPicker) moduleRegistry.projectPicker(ctx);
    if (moduleRegistry.inlineFormController) moduleRegistry.inlineFormController(ctx);
    if (moduleRegistry.groupManager) moduleRegistry.groupManager(ctx);

    // ── Inicialização ────────────────────────────────────────────────────────

    Array.prototype.slice.call(listEl.querySelectorAll('.task-hub-add-row[data-project-value]')).forEach(function (addRow) {
        ctx.initializeAddRow(addRow, {
            getProjectValue: function () {
                return normalizeProjectValue(addRow.getAttribute('data-project-value'));
            },
        });
    });

    ctx.syncListScaffoldVisibility();
    ctx.bindCreateButton();

    // ── Bridge pública ───────────────────────────────────────────────────────

    global.taskItemsListBridge = {
        listEl: listEl,
        taskId: '',
        sugestoesUrl: sugestoesUrl,
        addItemUrl: addUrl,
        insertItemFromPayload: ctx.insertNewItem,
        requestAddItem: ctx.requestAddItem,
        focusInlineAdd: ctx.focusInlineAdd,
        focusGlobalCreateInList: ctx.focusGlobalCreateInList,
    };
})(window);
