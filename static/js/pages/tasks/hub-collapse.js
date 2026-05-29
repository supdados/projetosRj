// === hub-collapse.js — abrir/fechar projetos e etapas no hub de tarefas ===
// Estrutura alvo (ver templates/tasks/hub.html):
//   .task-hub-group[data-open]            → projeto colapsável
//     > .task-hub-group-header[data-role="group-toggle"]
//     > .task-hub-group-body
//   .task-hub-stage[data-open]            → etapa colapsável
//     > .task-hub-stage-header[data-role="stage-toggle"]
//     > .task-hub-stage-body
// O estado fechado é persistido em localStorage por projeto/etapa para que a
// navegação entre páginas (reload após editar tarefa) preserve o que o usuário
// recolheu.
(function () {
    'use strict';

    var view = document.getElementById('taskItemsListView');
    if (!view) {
        return;
    }

    var STORAGE_KEY = 'taskHubCollapse:v1';

    function readState() {
        try {
            return JSON.parse(window.localStorage.getItem(STORAGE_KEY)) || {};
        } catch (_err) {
            return {};
        }
    }

    function writeState(state) {
        try {
            window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
        } catch (_err) {
            // localStorage indisponível (modo privado/quota) — colapso vira
            // apenas runtime, sem persistência. Não é erro fatal.
        }
    }

    var collapseState = readState();

    function groupKey(group) {
        return 'p:' + (group.getAttribute('data-project-value') || '');
    }

    function stageKey(stage) {
        var group = stage.closest('.task-hub-group');
        var header = stage.querySelector('[data-stage-drop-zone]');
        var stageValue = header ? header.getAttribute('data-stage-value') || '' : '';
        var projectValue = group ? group.getAttribute('data-project-value') || '' : '';
        return 'p:' + projectValue + '|s:' + stageValue;
    }

    function setOpen(element, open) {
        element.setAttribute('data-open', open ? 'true' : 'false');
        var header = element.querySelector('[aria-expanded]');
        if (header) {
            header.setAttribute('aria-expanded', open ? 'true' : 'false');
        }
    }

    function persist(key, open) {
        if (open) {
            delete collapseState[key];
        } else {
            collapseState[key] = false;
        }
        writeState(collapseState);
    }

    function toggleGroup(group) {
        var open = group.getAttribute('data-open') !== 'false';
        setOpen(group, !open);
        persist(groupKey(group), !open);
    }

    function toggleStage(stage) {
        var open = stage.getAttribute('data-open') !== 'false';
        setOpen(stage, !open);
        persist(stageKey(stage), !open);
    }

    // Cliques em links/controles internos do cabeçalho não devem colapsar
    // (ex.: o título do projeto navega para o detalhe).
    function isInteractive(target, toggleEl) {
        var hit = target.closest('a, button, input, select, textarea, [data-role="group-toggle-skip"]');
        return hit && hit !== toggleEl;
    }

    view.addEventListener('click', function (event) {
        var stageHeader = event.target.closest('[data-role="stage-toggle"]');
        if (stageHeader) {
            if (isInteractive(event.target, stageHeader)) {
                return;
            }
            var stage = stageHeader.closest('.task-hub-stage');
            if (stage) {
                toggleStage(stage);
            }
            return;
        }

        var groupHeader = event.target.closest('[data-role="group-toggle"]');
        if (groupHeader) {
            if (isInteractive(event.target, groupHeader)) {
                return;
            }
            var group = groupHeader.closest('.task-hub-group');
            if (group) {
                toggleGroup(group);
            }
        }
    });

    view.addEventListener('keydown', function (event) {
        if (event.key !== 'Enter' && event.key !== ' ' && event.key !== 'Spacebar') {
            return;
        }
        var header = event.target.closest('[data-role="group-toggle"], [data-role="stage-toggle"]');
        if (!header || header !== event.target) {
            return;
        }
        event.preventDefault();
        if (header.matches('[data-role="stage-toggle"]')) {
            var stage = header.closest('.task-hub-stage');
            if (stage) {
                toggleStage(stage);
            }
        } else {
            var group = header.closest('.task-hub-group');
            if (group) {
                toggleGroup(group);
            }
        }
    });

    function applyPersistedState() {
        view.querySelectorAll('.task-hub-group').forEach(function (group) {
            if (collapseState[groupKey(group)] === false) {
                setOpen(group, false);
            }
        });
        view.querySelectorAll('.task-hub-stage').forEach(function (stage) {
            if (collapseState[stageKey(stage)] === false) {
                setOpen(stage, false);
            }
        });
    }

    applyPersistedState();
})();
