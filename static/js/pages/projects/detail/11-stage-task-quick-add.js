(function () {
    'use strict';
    const overlay = document.getElementById('stageTaskQuickAdd');
    if (!overlay) {
        return;
    }
    const config = window.__PROJECT_DETAIL_CONFIG__ || {};
    const addTaskUrl = config.addTaskUrl;
    const stageTasksUrlTemplate = config.stageTasksUrlTemplate;
    const legacyTasksUrl = config.legacyTasksUrl;
    if (!addTaskUrl || !stageTasksUrlTemplate) {
        return;
    }
    const contentHost = overlay.querySelector('[data-stage-task-content]');
    const stageTitleEl = overlay.querySelector('[data-stage-quick-add-title]');
    const errorEl = overlay.querySelector('[data-stage-quick-add-error]');
    const fetchApi = window.stageTaskQuickAddFetch;
    const rows = window.stageTaskQuickAddRows;
    const lifecycle = window.stageTaskQuickAddLifecycle;
    if (!fetchApi || !rows || !lifecycle) {
        return;
    }

    // TTL curto evita refetch quando o usuário só fecha e reabre o mesmo modal.
    // Mutations invalidam via clearCache.
    const PANEL_CACHE_TTL_MS = 30 * 1000;
    const panelCache = new Map();

    let currentEtapaId = null;
    let currentMode = 'stage';
    let currentProjectId = config.projectId || null;
    let responsavelNames = [];
    let isSubmitting = false;
    let requestController = null;
    let lastTriggerEl = null;

    function cacheKey() {
        return currentMode === 'legacy' ? 'legacy' : `stage:${currentEtapaId || ''}`;
    }
    function setCache(key, html) {
        panelCache.set(key, { html, at: Date.now() });
    }
    function getCache(key) {
        const entry = panelCache.get(key);
        if (!entry) return null;
        if (Date.now() - entry.at > PANEL_CACHE_TTL_MS) {
            panelCache.delete(key);
            return null;
        }
        return entry;
    }
    function clearCache(key) {
        if (key) {
            panelCache.delete(key);
        } else {
            panelCache.clear();
        }
    }
    function clearError() {
        if (!errorEl) {
            return;
        }
        errorEl.hidden = true;
        errorEl.textContent = '';
    }
    function showError(message) {
        if (!errorEl) {
            return;
        }
        errorEl.textContent = message || 'Não foi possível carregar as tarefas.';
        errorEl.hidden = false;
    }
    function setLoading() {
        if (!contentHost) {
            return;
        }
        contentHost.innerHTML = '<p class="stage-task-quick-add__loading" data-stage-task-loading>Carregando tarefas...</p>';
    }
    function hasUnsavedDraft() {
        return lifecycle.hasUnsavedDraft(contentHost, rows, responsavelNames);
    }
    function focusInitialControl() {
        lifecycle.focusInitialControl(overlay, contentHost, rows);
    }
    function closeResponsavelPicker() {
        const trigger = rows.getResponsavelTrigger(contentHost);
        if (
            trigger
            && window.responsavelPickerManager
            && typeof window.responsavelPickerManager.closeIfAnchor === 'function'
        ) {
            window.responsavelPickerManager.closeIfAnchor(trigger);
        }
    }
    function showForm() {
        rows.showForm(contentHost, responsavelNames);
    }
    function hideForm() {
        rows.hideForm(contentHost, closeResponsavelPicker);
    }
    function resetFields() {
        rows.resetFields(contentHost, responsavelNames);
    }
    function updateStageBadge(delta) {
        if (currentMode === 'stage') {
            rows.updateStageBadge(currentEtapaId, delta);
        }
    }
    function injectHtml(html) {
        // HTML vem do endpoint server-side (Jinja com autoescape).
        // Confiável; equivalente ao SSR original que esse modal substituiu.
        if (contentHost) {
            contentHost.innerHTML = html || '';
        }
    }
    function renderHtml(html, opts) {
        const options = opts || {};
        injectHtml(html);
        resetFields();
        rows.highlightCreatedRow(contentHost, options.highlightTaskId);
        if (options.focusAdd) {
            showForm();
        } else {
            focusInitialControl();
        }
    }
    function buildRequestUrl() {
        if (currentMode === 'legacy') {
            return legacyTasksUrl || '';
        }
        return fetchApi.buildStageTasksUrl(stageTasksUrlTemplate, currentEtapaId);
    }
    function loadPanel(options) {
        const opts = options || {};
        clearError();
        const key = cacheKey();
        if (!opts.forceReload) {
            const cached = getCache(key);
            if (cached) {
                renderHtml(cached.html, opts);
                return Promise.resolve({ cached: true });
            }
        }
        setLoading();
        if (requestController) {
            requestController.abort();
        }
        requestController = new AbortController();
        const url = buildRequestUrl();
        if (!url) {
            showError('URL de carregamento indisponível.');
            return Promise.resolve();
        }
        const fetcher = currentMode === 'legacy' ? fetchApi.fetchLegacyTasks : fetchApi.fetchStageTasks;
        return fetcher(url, requestController)
            .then((payload) => {
                const html = payload.html || '';
                setCache(key, html);
                renderHtml(html, opts);
                return payload;
            })
            .catch((error) => {
                if (error && error.name === 'AbortError') {
                    return;
                }
                injectHtml('');
                showError((error && error.message) || 'Não foi possível carregar as tarefas.');
            });
    }
    function submitTask() {
        if (isSubmitting) {
            return;
        }
        if (currentMode === 'legacy') {
            showError('Selecione uma etapa para criar uma nova tarefa.');
            return;
        }
        const descricao = rows.getField(contentHost, 'descricao');
        const prioridade = rows.getField(contentHost, 'prioridade');
        const tipo = rows.getField(contentHost, 'tipo_pedido');
        const status = rows.getField(contentHost, 'status');
        const responsavel = rows.getField(contentHost, 'responsavel');
        const description = descricao ? descricao.value.trim() : '';
        if (!description) {
            showError('Descreva a tarefa antes de salvar.');
            if (descricao) {
                descricao.focus();
            }
            return;
        }
        clearError();
        isSubmitting = true;
        fetchApi.createTask(addTaskUrl, config, {
            project_id: currentProjectId,
            etapa_id: currentEtapaId,
            descricao: description,
            prioridade: prioridade ? prioridade.value : '',
            tipo_pedido: tipo ? tipo.value : '',
            status: status ? status.value : 'nao_iniciada',
            responsavel: responsavel ? responsavel.value : responsavelNames.join(', '),
        })
            .then((payload) => {
                updateStageBadge(1);
                if (typeof window.showFlash === 'function') {
                    window.showFlash('Tarefa criada com sucesso.', 'success');
                }
                clearCache();
                return loadPanel({
                    focusAdd: true,
                    forceReload: true,
                    highlightTaskId: payload && payload.task ? payload.task.id : null,
                });
            })
            .catch((error) => {
                showError((error && error.message) || 'Não foi possível salvar a tarefa.');
            })
            .finally(() => {
                isSubmitting = false;
            });
    }
    function openResponsavelPicker(trigger) {
        if (!trigger || !window.responsavelPickerManager || typeof window.responsavelPickerManager.open !== 'function') {
            return;
        }
        const responsavel = rows.getField(contentHost, 'responsavel');
        window.responsavelPickerManager.open({
            anchorEl: trigger,
            sugestoesUrl: config.assignableUsersUrl,
            projectValue: currentProjectId,
            initialRawValue: responsavel ? responsavel.value : responsavelNames.join(', '),
            onApply: (payload) => {
                responsavelNames = Array.isArray(payload.names) ? payload.names : [];
                if (responsavel) {
                    responsavel.value = payload.value || responsavelNames.join(', ');
                }
                rows.renderResponsavel(contentHost, responsavelNames);
                return true;
            },
        });
    }
    function open(trigger) {
        lastTriggerEl = trigger;
        const mode = trigger.getAttribute('data-stage-quick-add-mode') === 'legacy' ? 'legacy' : 'stage';
        currentMode = mode;
        currentEtapaId = mode === 'stage' ? trigger.getAttribute('data-etapa-id') : null;
        currentProjectId = trigger.getAttribute('data-project-id') || config.projectId || currentProjectId;
        responsavelNames = [];
        if (stageTitleEl) {
            const fallback = mode === 'legacy' ? 'Tarefas sem etapa' : 'Etapa';
            stageTitleEl.textContent = trigger.getAttribute('data-etapa-descricao') || fallback;
        }
        overlay.classList.remove('ds-hidden');
        overlay.setAttribute('aria-hidden', 'false');
        lifecycle.setOverlayInert(overlay, false);
        document.body.classList.add('stage-task-quick-add-open');
        loadPanel({ focusAdd: mode === 'stage' });
        window.setTimeout(() => {
            focusInitialControl();
        }, 0);
    }
    function close(skipConfirm) {
        if (!skipConfirm && hasUnsavedDraft() && !window.confirm('Descartar o que foi digitado?')) {
            return;
        }
        overlay.classList.add('ds-hidden');
        overlay.setAttribute('aria-hidden', 'true');
        lifecycle.setOverlayInert(overlay, true);
        document.body.classList.remove('stage-task-quick-add-open');
        closeResponsavelPicker();
        if (requestController) {
            requestController.abort();
            requestController = null;
        }
        currentEtapaId = null;
        currentMode = 'stage';
        responsavelNames = [];
        clearError();
        if (lastTriggerEl && typeof lastTriggerEl.focus === 'function') {
            lastTriggerEl.focus();
        }
        lastTriggerEl = null;
    }
    // Outros scripts podem invalidar o cache via evento de domínio
    // (ex.: delete/move task fora do fluxo do modal).
    document.addEventListener('stage-task-quick-add:invalidate', (event) => {
        const detail = event && event.detail;
        if (detail && detail.key) {
            clearCache(detail.key);
        } else {
            clearCache();
        }
    });
    document.addEventListener('click', (event) => {
        const trigger = event.target.closest('[data-stage-quick-add-trigger]');
        if (trigger) {
            event.preventDefault();
            open(trigger);
            return;
        }
        const dismiss = event.target.closest('[data-stage-quick-add-dismiss]');
        if (dismiss) {
            event.preventDefault();
            close(false);
            return;
        }
        if (!overlay.contains(event.target) || overlay.classList.contains('ds-hidden')) {
            return;
        }
        if (event.target.closest('[data-role="open-add-form"]')) {
            event.preventDefault();
            showForm();
            return;
        }
        if (event.target.closest('[data-role="cancel-add"]')) {
            event.preventDefault();
            resetFields();
            hideForm();
            return;
        }
        if (event.target.closest('[data-role="submit-add"]')) {
            event.preventDefault();
            submitTask();
            return;
        }
        const responsavelTrigger = event.target.closest('[data-role="responsavel-trigger"]');
        if (responsavelTrigger) {
            event.preventDefault();
            openResponsavelPicker(responsavelTrigger);
        }
    });
    overlay.addEventListener('input', (event) => {
        if (event.target && event.target.matches('[data-role="descricao"]')) {
            rows.resizeTextarea(contentHost);
        }
    });
    // Mudanças nos selects de status/prioridade/tipo de uma tarefa dentro do
    // painel devem invalidar o cache — senão ao reabrir o modal o user veria
    // o estado servido originalmente.
    overlay.addEventListener('change', (event) => {
        const target = event.target;
        if (!target) return;
        if (
            target.matches('.task-item-status')
            || target.matches('.task-item-prioridade-select')
            || target.matches('.task-item-tipo-select')
        ) {
            clearCache(cacheKey());
        }
    });
    // Excluir tarefa, comentar, anexar etc. enviam form/POST — invalidamos
    // ao detectar submit de qualquer form dentro do painel.
    overlay.addEventListener('submit', () => {
        clearCache();
    });
    overlay.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            event.preventDefault();
            close(true);
            return;
        }
        lifecycle.trapFocus(overlay, event);
        if (event.key === 'Enter' && !event.shiftKey && event.target && event.target.matches('[data-role="descricao"]')) {
            event.preventDefault();
            submitTask();
            return;
        }
    });
})();
