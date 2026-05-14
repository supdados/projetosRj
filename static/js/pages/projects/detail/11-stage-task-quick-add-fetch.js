(function () {
    'use strict';

    // Token literal usado no template Jinja para construir a URL. Veja
    // _PROJECT_DETAIL_CONFIG__.stageTasksUrlTemplate em templates/projects/detail.html.
    const STAGE_ID_PLACEHOLDER = '__ETAPA_ID__';

    function getCsrfToken(config) {
        const metaToken = document.querySelector('meta[name="csrf-token"]');
        return (config && config.csrfToken) || (metaToken ? metaToken.getAttribute('content') : '') || '';
    }

    function buildStageTasksUrl(stageTasksUrlTemplate, etapaId) {
        const template = String(stageTasksUrlTemplate || '');
        const stageId = encodeURIComponent(String(etapaId || ''));
        if (!stageId || template.indexOf(STAGE_ID_PLACEHOLDER) === -1) {
            return template;
        }
        return template.split(STAGE_ID_PLACEHOLDER).join(stageId);
    }

    function parseJsonResponse(response, fallbackMessage) {
        return response.json().catch(() => ({})).then((payload) => {
            if (!response.ok || !payload.success) {
                throw new Error(payload.message || fallbackMessage);
            }
            return payload;
        });
    }

    function fetchStageTasks(url, requestController) {
        return fetch(url, {
            method: 'GET',
            headers: {
                'Accept': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
            },
            signal: requestController ? requestController.signal : undefined,
        }).then((response) => parseJsonResponse(response, 'Não foi possível carregar as tarefas.'));
    }

    function fetchLegacyTasks(url, requestController) {
        return fetch(url, {
            method: 'GET',
            headers: {
                'Accept': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
            },
            signal: requestController ? requestController.signal : undefined,
        }).then((response) => parseJsonResponse(response, 'Não foi possível carregar as tarefas sem etapa.'));
    }

    function createTask(addTaskUrl, config, payload) {
        return fetch(addTaskUrl, {
            method: 'POST',
            headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': getCsrfToken(config || {}),
            },
            body: JSON.stringify(payload || {}),
        }).then((response) => parseJsonResponse(response, 'Não foi possível salvar a tarefa.'));
    }

    window.stageTaskQuickAddFetch = {
        STAGE_ID_PLACEHOLDER,
        buildStageTasksUrl,
        createTask,
        fetchStageTasks,
        fetchLegacyTasks,
        getCsrfToken,
    };
})();
