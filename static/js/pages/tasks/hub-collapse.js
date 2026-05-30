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

    function getBody(element) {
        if (element.classList.contains('task-hub-group')) {
            return element.querySelector(':scope > .task-hub-group-body');
        }
        return element.querySelector(':scope > .task-hub-stage-body');
    }

    function clampScrollRegion() {
        var scrollRegion = view.closest('.app-scroll-region');
        if (!scrollRegion) {
            return;
        }
        var maxScrollTop = Math.max(0, scrollRegion.scrollHeight - scrollRegion.clientHeight);
        if (scrollRegion.scrollTop > maxScrollTop) {
            scrollRegion.scrollTop = maxScrollTop;
        }
    }

    function finishBodyTransition(body, open) {
        delete body.dataset.collapseTransition;
        if (open) {
            body.style.height = '';
        } else {
            body.hidden = true;
        }
        window.requestAnimationFrame(clampScrollRegion);
    }

    function setBodyOpen(element, open, animate) {
        var body = getBody(element);
        if (!body) {
            return;
        }

        body.dataset.collapseTransition = open ? 'opening' : 'closing';

        if (!animate) {
            body.hidden = !open;
            body.style.height = open ? '' : '0px';
            delete body.dataset.collapseTransition;
            window.requestAnimationFrame(clampScrollRegion);
            return;
        }

        if (open) {
            body.hidden = false;
            body.style.height = '0px';
            body.offsetHeight;
            body.style.height = body.scrollHeight + 'px';
        } else {
            body.style.height = body.getBoundingClientRect().height + 'px';
            body.offsetHeight;
            body.style.height = '0px';
        }

        window.setTimeout(function () {
            if (body.dataset.collapseTransition === (open ? 'opening' : 'closing')) {
                finishBodyTransition(body, open);
            }
        }, 360);
    }

    function setOpen(element, open, animate) {
        element.setAttribute('data-open', open ? 'true' : 'false');
        var header = element.querySelector('[aria-expanded]');
        if (header) {
            header.setAttribute('aria-expanded', open ? 'true' : 'false');
        }
        setBodyOpen(element, open, animate !== false);
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
                setOpen(group, false, false);
            }
        });
        view.querySelectorAll('.task-hub-stage').forEach(function (stage) {
            if (collapseState[stageKey(stage)] === false) {
                setOpen(stage, false, false);
            }
        });
    }

    view.addEventListener('transitionend', function (event) {
        var body = event.target;
        if (
            event.propertyName !== 'height'
            || !body.matches('.task-hub-group-body, .task-hub-stage-body')
            || !body.dataset.collapseTransition
        ) {
            return;
        }
        finishBodyTransition(body, body.dataset.collapseTransition === 'opening');
    });

    applyPersistedState();
})();
