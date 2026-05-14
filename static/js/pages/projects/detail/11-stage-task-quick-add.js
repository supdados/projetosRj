(function () {
    'use strict';

    const overlay = document.getElementById('stageTaskQuickAdd');
    if (!overlay) {
        return;
    }

    const config = window.__PROJECT_DETAIL_CONFIG__ || {};
    const addTaskUrl = config.addTaskUrl;
    if (!addTaskUrl) {
        return;
    }

    const stagePanels = Array.from(overlay.querySelectorAll('[data-stage-panel]'));
    const stageTitleEl = overlay.querySelector('[data-stage-quick-add-title]');
    const errorEl = overlay.querySelector('[data-stage-quick-add-error]');
    const templateEl = document.getElementById('stageTaskQuickAddRowTemplate');
    const stageCountMap = new Map();

    let activePanel = null;
    let currentEtapaId = null;
    let currentProjectId = null;
    let responsavelNames = [];
    let isSubmitting = false;

    function getPanel(stageId) {
        return stagePanels.find((panel) => panel.getAttribute('data-stage-panel') === String(stageId)) || null;
    }

    function getPanelRoot() {
        return activePanel;
    }

    function getPanelField(name) {
        const panel = getPanelRoot();
        return panel ? panel.querySelector(`[data-role="${name}"]`) : null;
    }

    function getPanelPlaceholder() {
        const panel = getPanelRoot();
        return panel ? panel.querySelector('[data-role="open-add-form"]') : null;
    }

    function getPanelFormWrap() {
        const panel = getPanelRoot();
        return panel ? panel.querySelector('[data-role="add-form"]') : null;
    }

    function getPanelResponsavelTrigger() {
        const panel = getPanelRoot();
        return panel ? panel.querySelector('[data-role="responsavel-trigger"]') : null;
    }

    function getPanelRowsContainer() {
        const panel = getPanelRoot();
        return panel ? panel.querySelector('[data-stage-task-rows]') : null;
    }

    function getPanelCountEl() {
        const panel = getPanelRoot();
        return panel ? panel.querySelector('[data-stage-panel-count]') : null;
    }

    function syncPanelCounts(stageId, delta) {
        const key = String(stageId);
        const current = stageCountMap.has(key) ? stageCountMap.get(key) : parseInt((getPanelCountEl() && getPanelCountEl().textContent) || '0', 10) || 0;
        const next = Math.max(0, current + delta);
        stageCountMap.set(key, next);
        const panel = getPanel(stageId);
        if (!panel) {
            return;
        }
        const countEl = panel.querySelector('[data-stage-panel-count]');
        if (countEl) {
            countEl.textContent = `${next} ${next === 1 ? 'tarefa' : 'tarefas'}`;
        }
    }

    function setActivePanel(stageId, stageTitle) {
        activePanel = getPanel(stageId);
        stagePanels.forEach((panel) => {
            panel.hidden = panel !== activePanel;
        });
        if (stageTitleEl) {
            stageTitleEl.textContent = stageTitle || 'Etapa';
        }
        if (activePanel) {
            const countText = (activePanel.querySelector('[data-stage-panel-count]') || {}).textContent || '';
            const countValue = parseInt(countText, 10);
            if (Number.isFinite(countValue)) {
                stageCountMap.set(String(stageId), countValue);
            }
        }
        return activePanel;
    }

    function showForm() {
        const placeholder = getPanelPlaceholder();
        const formWrap = getPanelFormWrap();
        if (placeholder) {
            placeholder.hidden = true;
            placeholder.style.display = 'none';
        }
        if (formWrap) {
            formWrap.hidden = false;
            formWrap.removeAttribute('hidden');
        }
    }

    function hideForm() {
        const placeholder = getPanelPlaceholder();
        const formWrap = getPanelFormWrap();
        if (formWrap) {
            formWrap.hidden = true;
            formWrap.setAttribute('hidden', '');
        }
        if (placeholder) {
            placeholder.hidden = false;
            placeholder.style.display = 'flex';
        }
        closeResponsavelPicker();
    }

    function resetFields() {
        const descricao = getPanelField('descricao');
        const prioridade = getPanelField('prioridade');
        const tipo = getPanelField('tipo_pedido');
        const status = getPanelField('status');
        const responsavel = getPanelField('responsavel');
        if (descricao) descricao.value = '';
        if (prioridade) prioridade.value = '';
        if (tipo) tipo.value = '';
        if (status) status.value = 'nao_iniciada';
        if (responsavel) responsavel.value = '';
        responsavelNames = [];
        renderResponsavel();
        resizeTextarea();
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
        errorEl.textContent = message;
        errorEl.hidden = false;
    }

    function resizeTextarea() {
        const descricao = getPanelField('descricao');
        if (!descricao) {
            return;
        }
        descricao.style.height = 'auto';
        descricao.style.height = `${Math.max(32, descricao.scrollHeight)}px`;
    }

    function renderResponsavel() {
        const trigger = getPanelResponsavelTrigger();
        if (typeof renderResponsavelPickerTrigger === 'function') {
            renderResponsavelPickerTrigger(trigger, responsavelNames, 'Responsável');
            return;
        }
        const contentEl = trigger ? trigger.querySelector('.responsavel-picker-trigger-content') : null;
        if (!contentEl) {
            return;
        }
        if (!responsavelNames.length) {
            contentEl.innerHTML = '<em class="responsavel-placeholder">Responsável</em>';
            return;
        }
        contentEl.textContent = responsavelNames.join(', ');
    }

    function closeResponsavelPicker() {
        const trigger = getPanelResponsavelTrigger();
        if (
            trigger
            && window.responsavelPickerManager
            && typeof window.responsavelPickerManager.closeIfAnchor === 'function'
        ) {
            window.responsavelPickerManager.closeIfAnchor(trigger);
        }
    }

    function buildDeleteModal(item) {
        const modal = document.createElement('div');
        modal.className = 'modal fade task-detail-v2-modal';
        modal.id = `deleteItemModal-${item.id}`;
        modal.tabIndex = -1;
        modal.setAttribute('aria-hidden', 'true');
        modal.innerHTML = `
            <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content modal-clean">
                    <div class="modal-header-clean">
                        <div>
                            <h5 class="modal-title-clean ds-type-section-title">Excluir Tarefa</h5>
                            <p class="modal-subtitle-clean ds-type-body-sm">Esta ação não pode ser desfeita</p>
                        </div>
                        <button type="button" class="btn-close-clean" data-bs-dismiss="modal">&times;</button>
                    </div>
                    <div class="modal-body-clean">
                        <p>Confirma a exclusão desta tarefa?</p>
                        <p class="text-muted small">${window.escapeHtml((item.descricao || '').slice(0, 100))}${(item.descricao || '').length > 100 ? '...' : ''}</p>
                    </div>
                    <div class="modal-footer-clean">
                        <button type="button" class="btn-modal-clean btn-cancel-clean" data-bs-dismiss="modal">Cancelar</button>
                        <form action="/tarefas/${encodeURIComponent(item.id)}/delete" method="POST" class="inline-form">
                            <button type="submit" class="btn-modal-clean btn-confirm-delete">Excluir</button>
                        </form>
                    </div>
                </div>
            </div>`;
        return modal;
    }

    function createRowFromItem(item) {
        const template = templateEl ? templateEl.content.firstElementChild : null;
        if (!template) {
            return null;
        }
        const row = template.cloneNode(true);
        let deleteModal = null;
        const itemId = String(item.id);
        const commentsCount = Number(item.comments_count || 0);
        const anexosCount = Number(item.anexos_count || 0);
        const prioridade = item.prioridade || '';
        const tipoPedido = item.tipo_pedido || '';
        const status = item.status || 'nao_iniciada';
        const canDelete = item.can_delete !== false;
        const canFinalize = item.can_finalize !== false;

        row.setAttribute('data-item-id', itemId);
        row.setAttribute('data-item-status', status);
        row.setAttribute('data-can-delete', canDelete ? '1' : '0');
        row.setAttribute('data-can-finalize', canFinalize ? '1' : '0');
        row.setAttribute('data-comments-count', String(commentsCount));
        row.setAttribute('data-item-prioridade', prioridade);
        row.setAttribute('data-item-tipo', tipoPedido);
        row.setAttribute('data-anexos-count', String(anexosCount));
        row.setAttribute('data-task-id', itemId);
        row.setAttribute('data-task-titulo', item.descricao || '');
        row.setAttribute('data-project-value', String(item.project_id || currentProjectId || ''));
        row.setAttribute('data-project-id', String(item.project_id || currentProjectId || ''));
        row.setAttribute('data-stage-value', String(currentEtapaId || ''));
        row.setAttribute('data-stage-id', String(currentEtapaId || ''));
        row.setAttribute('data-stage-legacy', '0');
        row.setAttribute('data-project-titulo', item.project_titulo || '');

        const descEl = row.querySelector('.task-item-desc');
        if (descEl) {
            descEl.textContent = item.descricao || '';
            descEl.setAttribute('data-item-id', itemId);
        }
        const editBtn = row.querySelector('.task-item-desc-edit-btn');
        if (editBtn) {
            editBtn.setAttribute('data-item-id', itemId);
        }
        const prioritySelect = row.querySelector('.task-item-prioridade-select');
        if (prioritySelect) {
            prioritySelect.value = prioridade;
            prioritySelect.classList.remove('prioridade-none', 'prioridade-baixa', 'prioridade-media', 'prioridade-alta', 'prioridade-urgente');
            prioritySelect.classList.add(`prioridade-${prioridade || 'none'}`);
            prioritySelect.setAttribute('data-item-id', itemId);
            prioritySelect.setAttribute('data-action-args', itemId);
        }
        const tipoSelect = row.querySelector('.task-item-tipo-select');
        if (tipoSelect) {
            tipoSelect.value = tipoPedido;
            tipoSelect.setAttribute('data-item-id', itemId);
            tipoSelect.setAttribute('data-action-args', itemId);
        }
        const statusSelect = row.querySelector('.task-item-status');
        if (statusSelect) {
            statusSelect.value = status;
            statusSelect.className = `task-item-status status-${status}`;
            statusSelect.setAttribute('data-action-args', itemId);
            if (!canFinalize && status === 'finalizada') {
                const opt = Array.from(statusSelect.options).find((option) => option.value === 'finalizada');
                if (opt) {
                    opt.disabled = true;
                }
            }
        }
        const responsavelEl = row.querySelector('.task-item-responsavel');
        if (responsavelEl) {
            responsavelEl.setAttribute('data-item-id', itemId);
            responsavelEl.innerHTML = item.responsavel
                ? window.escapeHtml(item.responsavel)
                : '<em class="responsavel-placeholder">Responsável não informado</em>';
        }
        const commentsNum = row.querySelector('.task-item-comments-num');
        if (commentsNum) commentsNum.textContent = String(commentsCount);
        const anexosNum = row.querySelector('.task-item-anexos-num');
        if (anexosNum) anexosNum.textContent = String(anexosCount);
        const commentsBtn = row.querySelector('.task-item-comments-btn');
        if (commentsBtn) {
            commentsBtn.setAttribute('data-target', `comments-body-${itemId}`);
            commentsBtn.setAttribute('aria-expanded', 'false');
        }
        const anexosBtn = row.querySelector('.task-item-anexos-btn');
        if (anexosBtn) anexosBtn.setAttribute('data-item-id', itemId);
        const delBtn = row.querySelector('.task-item-del');
        if (delBtn) {
            delBtn.setAttribute('data-bs-target', `#deleteItemModal-${itemId}`);
            if (!canDelete) {
                delBtn.remove();
            } else {
                deleteModal = buildDeleteModal(item);
            }
        }
        const commentsWrap = row.querySelector('.task-item-comments');
        if (commentsWrap) {
            commentsWrap.id = `comments-body-${itemId}`;
            commentsWrap.hidden = false;
            const inner = commentsWrap.querySelector('.task-item-comments-inner');
            if (inner) {
                inner.innerHTML = `
                    <div class="task-comment task-comment-empty">
                        <p class="task-comment-text">Nenhum comentário registrado.</p>
                    </div>
                    <form class="task-comment-form" action="/tarefas/${encodeURIComponent(itemId)}/comentarios/add" method="POST" data-item-id="${itemId}">
                        <textarea name="content" rows="1" placeholder="Comentar... (Enter para enviar)" required></textarea>
                        <button type="submit" title="Enviar comentário">
                            <i class="fas fa-paper-plane" aria-hidden="true"></i>
                            <span class="visually-hidden">Enviar</span>
                        </button>
                    </form>`;
            }
        }

        return { row, deleteModal };
    }

    function insertCreatedItem(item) {
        const rowsContainer = getPanelRowsContainer();
        if (!rowsContainer) {
            return;
        }
        const built = createRowFromItem(item);
        if (!built || !built.row) {
            return;
        }
        const row = built.row;
        rowsContainer.appendChild(row);
        if (built.deleteModal) {
            row.after(built.deleteModal);
        }
        syncPanelCounts(currentEtapaId, 1);
        if (typeof updateTaskItemsHeaderCount === 'function') {
            updateTaskItemsHeaderCount();
        }
        if (typeof updateTaskItemsTotalPill === 'function') {
            updateTaskItemsTotalPill();
        }
    }

    function updateFromResponse(payload) {
        if (!payload) {
            return;
        }
        const item = payload.item || payload.task;
        if (!item) {
            return;
        }
        insertCreatedItem(item);
    }

    async function submit(keepOpen) {
        if (isSubmitting) {
            return;
        }
        clearError();

        const descricao = (getPanelField('descricao') && getPanelField('descricao').value || '').trim();
        if (!descricao) {
            showError('Descrição é obrigatória.');
            const field = getPanelField('descricao');
            if (field) field.focus();
            return;
        }

        const formData = new FormData();
        formData.append('descricao', descricao);
        formData.append('project', currentProjectId || '');
        formData.append('etapa', currentEtapaId || '');
        if (getPanelField('responsavel')) {
            getPanelField('responsavel').value = responsavelNames.join(', ');
        }
        ['prioridade', 'tipo_pedido', 'status'].forEach((name) => {
            const field = getPanelField(name);
            if (field) {
                formData.append(name, field.value || '');
            }
        });
        formData.append('responsavel', responsavelNames.join(', '));

        isSubmitting = true;
        const submitButton = getPanelFormWrap() ? getPanelFormWrap().querySelector('[data-role="submit-add"]') : null;
        if (submitButton) {
            submitButton.disabled = true;
        }

        try {
            const response = await fetch(addTaskUrl, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json',
                },
            });
            const payload = await response.json().catch(() => ({}));
            if (!response.ok || !payload.success) {
                showError(payload.message || 'Não foi possível criar a tarefa.');
                return;
            }

            updateFromResponse(payload);
            resetFields();
            if (keepOpen) {
                showForm();
                const field = getPanelField('descricao');
                if (field) field.focus();
            } else {
                hideForm();
            }
        } catch (err) {
            showError('Erro de rede ao criar a tarefa.');
        } finally {
            isSubmitting = false;
            if (submitButton) {
                submitButton.disabled = false;
            }
        }
    }

    function open(triggerButton) {
        const stageId = triggerButton.dataset.etapaId;
        const stageTitle = triggerButton.dataset.etapaDescricao || 'Etapa';
        const projectId = triggerButton.dataset.projectId;
        if (!stageId || !projectId) {
            return;
        }

        currentEtapaId = stageId;
        currentProjectId = projectId;
        setActivePanel(stageId, stageTitle);
        clearError();
        resetFields();
        hideForm();
        overlay.classList.remove('ds-hidden');
        overlay.setAttribute('aria-hidden', 'false');
        document.body.classList.add('stage-task-quick-add-open');
    }

    function close() {
        overlay.classList.add('ds-hidden');
        overlay.setAttribute('aria-hidden', 'true');
        document.body.classList.remove('stage-task-quick-add-open');
        closeResponsavelPicker();
        clearError();
        currentEtapaId = null;
        currentProjectId = null;
        activePanel = null;
        stagePanels.forEach((panel) => {
            panel.hidden = true;
        });
    }

    function handleKeydown(event) {
        if (event.key === 'Escape') {
            event.preventDefault();
            close();
            return;
        }
        if (event.key === 'Enter' && !event.shiftKey && event.target === getPanelField('descricao')) {
            event.preventDefault();
            submit(false);
        }
    }

    document.addEventListener('click', (event) => {
        const trigger = event.target.closest('[data-stage-quick-add-trigger]');
        if (trigger) {
            event.preventDefault();
            open(trigger);
            return;
        }

        const dismiss = event.target.closest('[data-stage-quick-add-dismiss]');
        if (dismiss && overlay.contains(dismiss)) {
            event.preventDefault();
            close();
            return;
        }

        const openAddForm = event.target.closest('[data-role="open-add-form"]');
        if (openAddForm && overlay.contains(openAddForm)) {
            event.preventDefault();
            showForm();
            const field = getPanelField('descricao');
            if (field) field.focus();
            return;
        }

        const cancelAdd = event.target.closest('[data-role="cancel-add"]');
        if (cancelAdd && overlay.contains(cancelAdd)) {
            event.preventDefault();
            hideForm();
            return;
        }

        const submitAdd = event.target.closest('[data-role="submit-add"]');
        if (submitAdd && overlay.contains(submitAdd)) {
            event.preventDefault();
            submit(false);
            return;
        }

        const responsavelTrigger = event.target.closest('[data-role="responsavel-trigger"]');
        if (responsavelTrigger && overlay.contains(responsavelTrigger)) {
            event.preventDefault();
            event.stopPropagation();
            if (!currentProjectId) {
                return;
            }
            if (!window.responsavelPickerManager || typeof window.responsavelPickerManager.open !== 'function') {
                showError('Picker de responsáveis indisponível.');
                return;
            }
            window.responsavelPickerManager.open({
                anchorEl: responsavelTrigger,
                sugestoesUrl: config.assignableUsersUrl,
                projectValue: currentProjectId,
                initialRawValue: responsavelNames.join(', '),
                onApply(payload) {
                    responsavelNames = payload.names.slice();
                    const respField = getPanelField('responsavel');
                    if (respField) {
                        respField.value = responsavelNames.join(', ');
                    }
                    renderResponsavel();
                    return true;
                },
            });
        }
    });

    const descField = () => getPanelField('descricao');
    overlay.addEventListener('keydown', handleKeydown);
    overlay.addEventListener('input', () => {
        if (document.activeElement === descField()) {
            resizeTextarea();
        }
    }, true);

})();
