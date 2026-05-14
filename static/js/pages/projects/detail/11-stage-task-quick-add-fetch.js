(function () {
    'use strict';

    function getCsrfToken(config) {
        const metaToken = document.querySelector('meta[name="csrf-token"]');
        return (config && config.csrfToken) || (metaToken ? metaToken.getAttribute('content') : '') || '';
    }

    function buildStageTasksUrl(stageTasksUrlTemplate, etapaId) {
        const stageId = encodeURIComponent(String(etapaId || ''));
        let url = String(stageTasksUrlTemplate || '');
        if (!stageId) {
            return url;
        }
        url = url.replace(/(\/etapa\/)0(\/tasks(?:\?|$))/, `$1${stageId}$2`);
        if (url === stageTasksUrlTemplate) {
            url = url.replace(/0(?=\/tasks(?:\?|$))/, stageId);
        }
        return url;
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
        buildStageTasksUrl,
        createTask,
        fetchStageTasks,
        getCsrfToken,
    };
})();
