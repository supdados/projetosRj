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
    // Indicador de loading "lento": só aparece se a requisição passar de
    // ~180ms. Evita o flash de "Carregando..." em respostas instantâneas
    // (cache hit do navegador / queries rápidas).
    const LOADING_DELAY_MS = 180;
    let loadingTimer = null;
    function clearPendingLoading() {
        if (loadingTimer) {
            clearTimeout(loadingTimer);
            loadingTimer = null;
        }
    }
    function scheduleLoadingIndicator() {
        clearPendingLoading();
        if (!contentHost) return;
        loadingTimer = window.setTimeout(() => {
            loadingTimer = null;
            if (!contentHost) return;
            // Soft: marca o host como "reloading" para CSS aplicar opacidade
            // reduzida; só substitui pelo placeholder se o host estiver vazio.
            contentHost.classList.add('is-reloading');
            if (!contentHost.firstElementChild) {
                contentHost.innerHTML = '<p class="stage-task-quick-add__loading" data-stage-task-loading>Carregando tarefas...</p>';
            }
        }, LOADING_DELAY_MS);
    }
    function endLoadingIndicator() {
        clearPendingLoading();
        if (contentHost) {
            contentHost.classList.remove('is-reloading');
        }
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
    // Contagem do cabeçalho do painel ("N tarefas").
    function updatePanelCount(delta) {
        const countEl = overlay.querySelector('[data-stage-quick-add-count]');
        if (countEl && !countEl.hidden) {
            const current = parseInt((countEl.textContent || '').replace(/[^0-9]/g, ''), 10) || 0;
            const next = Math.max(0, current + delta);
            const suffix = next === 1 ? 'tarefa' : 'tarefas';
            countEl.textContent = next + ' ' + suffix;
        }
    }
    // Pílula "concluídas/total" na linha da etapa (só no modo etapa).
    function updateStageProgress(totalDelta, doneDelta) {
        if (currentMode === 'stage') {
            rows.updateStageProgress(currentEtapaId, totalDelta, doneDelta);
        }
    }
    // Modais de delete dos rows injetados precisam viver no <body> para que
    // o Bootstrap consiga exibi-los sem ser cortado pelo overflow do panel.
    // Trackeamos os modais "adotados" para limpar ao trocar de painel.
    const adoptedDeleteModals = [];
    function adoptDeleteModalsToBody() {
        if (!contentHost) return;
        const modals = contentHost.querySelectorAll('.task-detail-v2-modal[id^="deleteItemModal-"]');
        modals.forEach((modal) => {
            // Marca o form de delete para que o listener de submit em document
            // (definido mais abaixo) consiga interceptar via AJAX e remover a
            // row sem reload.
            const form = modal.querySelector('form.inline-form[action*="/delete"]');
            if (form) {
                const idMatch = (modal.id || '').replace('deleteItemModal-', '');
                form.setAttribute('data-stage-quick-add-delete', idMatch);
            }
            document.body.appendChild(modal);
            adoptedDeleteModals.push(modal);
        });
    }
    function cleanupAdoptedDeleteModals() {
        while (adoptedDeleteModals.length) {
            const modal = adoptedDeleteModals.pop();
            if (modal && modal.parentNode) {
                modal.parentNode.removeChild(modal);
            }
        }
    }
    function injectHtml(html) {
        // HTML vem do endpoint server-side (Jinja com autoescape).
        // Confiável; equivalente ao SSR original que esse modal substituiu.
        cleanupAdoptedDeleteModals();
        if (contentHost) {
            contentHost.innerHTML = html || '';
        }
        adoptDeleteModalsToBody();
        // Notifica o kanban-manager sobre o `.task-items-list` injetado, para
        // que o drawer compartilhado consiga ler `data-sugestoes-url` etc.
        if (contentHost && window.taskItemsKanban && typeof window.taskItemsKanban.attachListEl === 'function') {
            const listEl = contentHost.querySelector('.task-items-list');
            if (listEl) window.taskItemsKanban.attachListEl(listEl);
        }
    }
    function updateHeaderCount(count, hasMore) {
        const countEl = overlay.querySelector('[data-stage-quick-add-count]');
        if (!countEl) return;
        if (count == null) {
            countEl.hidden = true;
            countEl.textContent = '';
            return;
        }
        const suffix = (count === 1 && !hasMore) ? 'tarefa' : 'tarefas';
        countEl.textContent = String(count) + (hasMore ? '+' : '') + ' ' + suffix;
        countEl.hidden = false;
    }
    function renderHtml(html, opts) {
        const options = opts || {};
        // Em recargas (refresh pós-create, refetch silencioso) preservamos a
        // posição. Em abertura inicial (resetScroll), forçamos topo — caso
        // contrário, reabrir uma etapa restaura o scroll do fechamento anterior.
        const previousScrollTop = contentHost ? contentHost.scrollTop : 0;
        injectHtml(html);
        if (contentHost) {
            contentHost.scrollTop = options.resetScroll ? 0 : previousScrollTop;
        }
        resetFields();
        rows.highlightCreatedRow(contentHost, options.highlightTaskId, {
            scroll: !options.focusAdd,
        });
        // Lê contagem persistida no markup do painel (data-stage-count / has-more)
        const section = contentHost && contentHost.querySelector('[data-stage-count]');
        if (section) {
            const count = parseInt(section.getAttribute('data-stage-count') || '0', 10);
            const hasMore = section.getAttribute('data-stage-has-more') === '1';
            updateHeaderCount(Number.isFinite(count) ? count : 0, hasMore);
        }
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
        // Modo silencioso (ex.: refresh pós-create): mantém o conteúdo atual
        // visível e só substitui quando o novo HTML chegar — sem placeholder
        // de loading no meio.
        if (!opts.silent) {
            scheduleLoadingIndicator();
        }
        if (requestController) {
            requestController.abort();
        }
        requestController = new AbortController();
        const url = buildRequestUrl();
        if (!url) {
            endLoadingIndicator();
            showError('URL de carregamento indisponível.');
            return Promise.resolve();
        }
        const fetcher = currentMode === 'legacy' ? fetchApi.fetchLegacyTasks : fetchApi.fetchStageTasks;
        return fetcher(url, requestController)
            .then((payload) => {
                const html = payload.html || '';
                setCache(key, html);
                endLoadingIndicator();
                renderHtml(html, opts);
                return payload;
            })
            .catch((error) => {
                endLoadingIndicator();
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
                const createdStatus = payload && payload.task ? payload.task.status : status ? status.value : '';
                const createdFinalizada = createdStatus === 'finalizada';
                if (!createdFinalizada) {
                    updatePanelCount(1);
                }
                updateStageProgress(1, createdFinalizada ? 1 : 0);
                if (typeof window.showFlash === 'function') {
                    window.showFlash('Tarefa criada com sucesso.', 'success');
                }
                clearCache();
                // Reload silencioso: mantém a UI atual visível enquanto busca
                // o novo HTML, evitando piscada do placeholder de loading.
                return loadPanel({
                    focusAdd: true,
                    forceReload: true,
                    silent: true,
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
        const formRoot = rows.getFormRoot(contentHost);
        if (!formRoot || !formRoot.contains(trigger)) {
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
        const fallbackTitle = mode === 'legacy' ? 'Tarefas sem etapa' : 'Etapa';
        const stageDescricao = trigger.getAttribute('data-etapa-descricao') || fallbackTitle;
        const projectTitle = trigger.getAttribute('data-project-titulo') || config.projectTitle || '';
        const orgaoSigla = trigger.getAttribute('data-orgao-sigla') || '';
        const etapaDatas = trigger.getAttribute('data-etapa-datas') || '';
        if (stageTitleEl) stageTitleEl.textContent = stageDescricao;
        const eyebrowCtx = overlay.querySelector('[data-stage-quick-add-eyebrow-context]');
        const eyebrowSep = overlay.querySelector('.stage-task-quick-add__eyebrow-sep');
        if (eyebrowCtx) {
            eyebrowCtx.textContent = projectTitle;
            eyebrowCtx.hidden = !projectTitle;
        }
        if (eyebrowSep) {
            eyebrowSep.hidden = !projectTitle;
        }
        const orgaoChip = overlay.querySelector('[data-stage-quick-add-orgao]');
        const orgaoLabel = overlay.querySelector('[data-stage-quick-add-orgao-label]');
        if (orgaoChip && orgaoLabel) {
            if (orgaoSigla) {
                orgaoLabel.textContent = 'Órgão · ' + orgaoSigla;
                orgaoChip.hidden = false;
            } else {
                orgaoChip.hidden = true;
            }
        }
        const datasEl = overlay.querySelector('[data-stage-quick-add-datas]');
        if (datasEl) datasEl.textContent = etapaDatas;
        const countEl = overlay.querySelector('[data-stage-quick-add-count]');
        if (countEl) {
            countEl.hidden = true;
            countEl.textContent = '';
        }
        overlay.classList.remove('is-closed');
        overlay.setAttribute('aria-hidden', 'false');
        lifecycle.setOverlayInert(overlay, false);
        document.body.classList.add('stage-task-quick-add-open');
        if (contentHost) {
            contentHost.scrollTop = 0;
        }
        loadPanel({ focusAdd: false, resetScroll: true });
        window.setTimeout(() => {
            focusInitialControl();
        }, 0);
    }
    function close(skipConfirm) {
        if (!skipConfirm && hasUnsavedDraft() && !window.confirm('Descartar o que foi digitado?')) {
            return;
        }
        overlay.classList.add('is-closed');
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
        cleanupAdoptedDeleteModals();
        closeAnexosDrawer();
        endLoadingIndicator();
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
    // Anexos: reaproveitamos o drawer do hub via window.taskItemsKanban.
    // O markup do drawer está incluído na página por
    // templates/partials/_task_item_drawer.html, e o kanban-manager.js opera
    // em "modo drawer-only" quando não há board kanban presente.
    function closeAnexosDrawer() {
        // mantido como hook para o close() do overlay; o drawer real é
        // controlado pelo kanban-manager via clique no seu próprio backdrop.
    }
    overlay.addEventListener('click', (event) => {
        const anexosBtn = event.target.closest('.task-item-anexos-btn[data-item-id]');
        if (!anexosBtn) return;
        const itemId = anexosBtn.getAttribute('data-item-id');
        if (!itemId) return;
        event.preventDefault();
        event.stopPropagation();
        const api = window.taskItemsKanban;
        if (api && typeof api.openItemAnexoAction === 'function') {
            api.openItemAnexoAction(itemId);
        }
    }, true);
    document.addEventListener('click', (event) => {
        const trigger = event.target.closest('[data-stage-quick-add-trigger]');
        if (trigger) {
            event.preventDefault();
            if (trigger.getAttribute('data-stage-done') === '1' || trigger.getAttribute('aria-disabled') === 'true') {
                if (typeof window.showFlash === 'function') {
                    window.showFlash('Etapa concluída — desfaça a conclusão para criar tarefas.', 'info');
                }
                return;
            }
            open(trigger);
            return;
        }
        const dismiss = event.target.closest('[data-stage-quick-add-dismiss]');
        if (dismiss) {
            event.preventDefault();
            close(false);
            return;
        }
        if (!overlay.contains(event.target) || overlay.classList.contains('is-closed')) {
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
            const formRoot = rows.getFormRoot(contentHost);
            if (!formRoot || !formRoot.contains(responsavelTrigger)) {
                return;
            }
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
    // Exclusão de tarefa: o form vive no modal Bootstrap que foi adotado
    // pelo <body> (fora do overlay). Interceptamos no document para que o
    // POST vire AJAX e a row some sem reload da página.
    document.addEventListener('submit', (event) => {
        const form = event.target;
        if (!(form instanceof HTMLFormElement)) return;
        const taskId = form.getAttribute('data-stage-quick-add-delete');
        if (!taskId) return;
        event.preventDefault();
        const submitBtn = form.querySelector('button[type="submit"]');
        if (submitBtn) submitBtn.disabled = true;
        const formData = new FormData(form);
        fetch(form.action, {
            method: 'POST',
            headers: {
                'Accept': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
            },
            body: formData,
        })
            .then((r) => r.json().catch(() => ({ success: r.ok })))
            .then((data) => {
                if (data && data.success === false) {
                    showError(data.message || 'Falha ao excluir tarefa.');
                    return;
                }
                // Fecha o modal Bootstrap antes de remover a row para evitar
                // backdrop órfão.
                const modal = document.getElementById('deleteItemModal-' + taskId);
                if (modal && window.bootstrap && window.bootstrap.Modal) {
                    const inst = window.bootstrap.Modal.getInstance(modal);
                    if (inst) inst.hide();
                }
                // Remove a row, decrementa contador da etapa.
                const row = contentHost && contentHost.querySelector('.task-item-row[data-item-id="' + taskId + '"]');
                const wasFinalizada = Boolean(row && row.dataset.itemStatus === 'finalizada');
                if (row && row.parentNode) row.parentNode.removeChild(row);
                updatePanelCount(-1);
                updateStageProgress(-1, wasFinalizada ? -1 : 0);
                clearCache();
                if (typeof window.showFlash === 'function') {
                    window.showFlash('Tarefa excluída.', 'success');
                }
            })
            .catch(() => showError('Erro de rede ao excluir tarefa.'))
            .finally(() => {
                if (submitBtn) submitBtn.disabled = false;
            });
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
