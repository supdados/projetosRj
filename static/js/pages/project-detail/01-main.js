    const projectDetailConfig = window.__PROJECT_DETAIL_CONFIG__ || {};
    const projectIdValue = String(projectDetailConfig.projectId || '');
    const csrfToken = projectDetailConfig.csrfToken || '';
    const concludeProjectUrl = projectDetailConfig.concludeProjectUrl || `/project/${projectIdValue}/concluir`;
    const projectTitle = projectDetailConfig.projectTitle || '';
    const canEditAreaResponsavel = Boolean(projectDetailConfig.canEditAreaResponsavel);
    const availableAreas = Array.isArray(projectDetailConfig.availableAreas) ? projectDetailConfig.availableAreas : [];
    const abepIndicatorsOptions = Array.isArray(projectDetailConfig.abepIndicatorsOptions)
        ? projectDetailConfig.abepIndicatorsOptions
        : [];

    document.addEventListener('DOMContentLoaded', function () {
        // INÍCIO: Script de Drag and Drop para Etapas
        const tbody = document.getElementById('etapas-tbody');
        const canEditEtapas = tbody ? tbody.dataset.canEdit === 'true' : false;
        const btnImportModel = document.getElementById('btnImportModel');
        const btnOpenInlineEtapaAdd = document.getElementById('btnOpenInlineEtapaAdd');
        const inlineAddEntryRow = document.getElementById('etapaInlineAddEntryRow');
        const inlineAddFormRow = document.getElementById('etapaInlineAddFormRow');
        const inlineAddForm = document.getElementById('etapaInlineAddForm');
        const inlineAddEntryBtn = inlineAddEntryRow ? inlineAddEntryRow.querySelector('.etapa-inline-entry-btn') : null;
        const inlineAddCancelBtn = document.getElementById('btnCancelInlineEtapaAdd');
        const inlineAddSubmitBtn = document.getElementById('btnSubmitInlineEtapaAdd');
        const inlineEmptyRow = document.getElementById('etapaInlineEmptyRow');
        const inlineDescricaoInput = document.getElementById('etapa_inline_descricao');
        const inlineDateInputs = inlineAddFormRow
            ? Array.from(inlineAddFormRow.querySelectorAll('[data-empty-state-input]'))
            : [];
        const inlineIniciadaCheckbox = document.getElementById('etapa_inline_iniciada');
        const inlineDoneCheckbox = document.getElementById('etapa_inline_done');
        const inlineIniciadaToggle = inlineAddFormRow
            ? inlineAddFormRow.querySelector('.inline-status-toggle-iniciada')
            : null;
        const inlineDoneToggle = inlineAddFormRow
            ? inlineAddFormRow.querySelector('.inline-status-toggle-done')
            : null;
        const projectStatusField = document.querySelector('[data-field="status"]');
        const projectActionsFooter = document.getElementById('projectActionsFooter');
        const reactivateProjectModal = document.getElementById('reactivate-project-confirm-modal');
        const reactivateProjectConfirmBtn = document.getElementById('reactivate-project-confirm-btn');
        const reactivateProjectCancelBtn = document.getElementById('reactivate-project-cancel-btn');
        const projectIdPrefix = projectIdValue;
        let currentProjectStatus = projectStatusField
            ? (projectStatusField.dataset.value || '').trim()
            : (projectDetailConfig.projectStatus || '');
        let inlineComposerSaving = false;
        let inlineDatePickerOpening = false;
        let reactivateProjectModalResolver = null;

        function escapeHtml(value) {
            return String(value || '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }

        function getResponsavelDisplayValue(value) {
            return (value || '').trim() ? String(value).trim() : 'Sem responsável';
        }

        function getDateDisplayValue(rawValue, displayValue) {
            return (rawValue || '').trim() ? String(displayValue || '').trim() : 'Sem data';
        }

        function isResponsavelEmptyValue(value) {
            return !String(value || '').trim() || String(value).trim() === 'Sem responsável';
        }

        function updateEditableFieldDisplay(target, hasValue, displayValue, emptyDisplay) {
            if (!target) {
                return;
            }

            target.textContent = hasValue ? String(displayValue || '').trim() : emptyDisplay;
            target.classList.toggle('editable-field-empty', !hasValue);
        }

        function updateResponsavelFieldDisplay(target, value) {
            const hasValue = !isResponsavelEmptyValue(value);
            updateEditableFieldDisplay(target, hasValue, value, 'Sem responsável');
        }

        function updateDateFieldDisplay(target, rawValue, displayValue) {
            const hasValue = Boolean((rawValue || '').trim());
            updateEditableFieldDisplay(target, hasValue, displayValue, 'Sem data');
        }

        function syncImportModelButtonVisibility() {
            if (!btnImportModel || !tbody) {
                return;
            }

            const totalRows = tbody.querySelectorAll('tr.etapa-draggable-row').length;
            btnImportModel.classList.toggle('ds-hidden', totalRows > 0);
        }

        function setStatusToggleVariant(button, variant) {
            if (!button) {
                return;
            }

            button.classList.remove(
                'etapa-status-toggle-idle',
                'etapa-status-toggle-started',
                'etapa-status-toggle-ready',
                'etapa-status-toggle-done',
                'etapa-status-toggle-blocked'
            );
            button.classList.add(`etapa-status-toggle-${variant}`);
            button.dataset.state = variant;
        }

        function renumberEtapaRows() {
            if (!tbody) return;
            const rows = tbody.querySelectorAll('tr.etapa-draggable-row');
            rows.forEach((row, index) => {
                const numeroCelula = row.querySelector('.etapa-order-cell');
                if (numeroCelula) {
                    numeroCelula.textContent = `${projectIdPrefix}.${index + 1}`;
                }
            });
        }

        function isInlineComposerOpen() {
            return Boolean(inlineAddFormRow && !inlineAddFormRow.classList.contains('ds-hidden'));
        }

        function syncInlineDateEmptyState(input) {
            const wrap = input ? input.closest('.etapa-inline-date-wrap') : null;
            if (!wrap) {
                return;
            }
            wrap.classList.toggle('is-empty', !(input.value || '').trim());
        }

        function syncAllInlineDateEmptyState() {
            inlineDateInputs.forEach(syncInlineDateEmptyState);
        }

        function resetInlineComposerDateValues() {
            inlineDateInputs.forEach(input => {
                input.value = '';
                syncInlineDateEmptyState(input);
            });
        }

        function resolveReactivateProjectModal(confirmed) {
            if (!reactivateProjectModalResolver) {
                return;
            }

            const resolver = reactivateProjectModalResolver;
            reactivateProjectModalResolver = null;
            reactivateProjectModal.style.display = 'none';
            reactivateProjectModal.setAttribute('aria-hidden', 'true');
            resolver(Boolean(confirmed));
        }

        function promptReactivateProjectConfirmation() {
            if (!reactivateProjectModal) {
                return Promise.resolve(window.confirm('Ao adicionar uma nova etapa, o projeto voltará para Vigente. Deseja continuar?'));
            }

            reactivateProjectModal.style.display = 'flex';
            reactivateProjectModal.setAttribute('aria-hidden', 'false');

            return new Promise((resolve) => {
                reactivateProjectModalResolver = resolve;
                requestAnimationFrame(() => {
                    if (reactivateProjectConfirmBtn) {
                        reactivateProjectConfirmBtn.focus();
                    }
                });
            });
        }

        function buildProjectStatusBadge(statusValue) {
            if (statusValue === 'Vigente') {
                return '<span class="badge bg-success text-uppercase"><i class="fas fa-check-circle me-1"></i>Vigente</span>';
            }
            if (statusValue === 'Finalizado') {
                return '<span class="badge bg-secondary text-uppercase"><i class="fas fa-flag-checkered me-1"></i>Finalizado</span>';
            }
            if (statusValue === 'Suspenso') {
                return '<span class="badge bg-warning text-dark text-uppercase"><i class="fas fa-pause-circle me-1"></i>Suspenso</span>';
            }
            return `<span class="badge bg-light text-dark">${escapeHtml(statusValue || 'Não definido')}</span>`;
        }

        function updateProjectStatusDisplay(statusValue) {
            if (!projectStatusField) {
                return;
            }

            projectStatusField.dataset.value = statusValue || '';
            projectStatusField.innerHTML = buildProjectStatusBadge(statusValue);
            currentProjectStatus = statusValue || '';
        }

        function ensureConcludeProjectButton() {
            if (document.getElementById('btn-concluir-projeto') || !projectActionsFooter) {
                return;
            }

            const form = document.createElement('form');
            form.method = 'POST';
            form.action = concludeProjectUrl;
            form.className = 'inline-form';
            form.id = 'concludeProjectForm';

            const totalEtapas = tbody ? tbody.querySelectorAll('tr.etapa-draggable-row').length : 0;
            form.innerHTML = `
                <button type="submit" id="btn-concluir-projeto" class="btn btn-success btn-sm btn-conclude-project"
                    disabled
                    data-total-etapas="${totalEtapas}"
                    data-project-title="${escapeHtml(projectTitle)}"
                    title="Todas as etapas devem estar iniciadas e concluídas">
                    <i class="fas fa-check-circle me-1"></i>Concluir Projeto
                </button>
            `;

            projectActionsFooter.appendChild(form);
            bindConcludeProjectControls();
            verificarEAtualizarBotaoConcluir();
        }

        function resizeInlineDescricaoTextarea() {
            if (!inlineDescricaoInput) {
                return;
            }
            const computed = window.getComputedStyle(inlineDescricaoInput);
            const lineHeight = parseFloat(computed.lineHeight) || 20;
            const minHeight = lineHeight + 12;
            inlineDescricaoInput.style.height = 'auto';
            inlineDescricaoInput.style.height = `${Math.max(inlineDescricaoInput.scrollHeight, minHeight)}px`;
        }

        function refreshConcludeButtonCounters() {
            if (!tbody) return;
            const totalEtapas = tbody.querySelectorAll('tr.etapa-draggable-row').length;
            const btnConcluir = document.getElementById('btn-concluir-projeto');
            syncImportModelButtonVisibility();
            if (!btnConcluir) return;
            btnConcluir.dataset.totalEtapas = String(totalEtapas);
            verificarEAtualizarBotaoConcluir();
        }

        function ensureInlineEmptyRowVisible() {
            if (!tbody) {
                return;
            }

            let emptyRow = document.getElementById('etapaInlineEmptyRow');
            if (!emptyRow) {
                emptyRow = document.createElement('tr');
                emptyRow.id = 'etapaInlineEmptyRow';
                emptyRow.className = 'etapa-inline-empty-row';
                emptyRow.innerHTML = '<td colspan="9">Nenhuma etapa adicionada ainda.</td>';

                if (inlineAddEntryRow && inlineAddEntryRow.parentNode === tbody) {
                    tbody.insertBefore(emptyRow, inlineAddEntryRow);
                } else if (inlineAddFormRow && inlineAddFormRow.parentNode === tbody) {
                    tbody.insertBefore(emptyRow, inlineAddFormRow);
                } else {
                    tbody.appendChild(emptyRow);
                }
            }

            emptyRow.classList.remove('ds-hidden');
        }

        function syncInlineStatusControls() {
            const isIniciada = Boolean(inlineIniciadaCheckbox && inlineIniciadaCheckbox.checked);
            const isDone = Boolean(inlineDoneCheckbox && inlineDoneCheckbox.checked);

            if (inlineIniciadaToggle) {
                updateIniciadaButton(inlineIniciadaToggle, isIniciada);
            }
            if (inlineDoneToggle) {
                updateDoneButton(inlineDoneToggle, isDone, isIniciada);
            }
        }

        function missingDatePickerViewportSpace(input) {
            if (!input || typeof input.getBoundingClientRect !== 'function') {
                return 0;
            }
            const minSpace = 340;
            const padding = 18;
            const rect = input.getBoundingClientRect();
            const availableSpaceBelow = window.innerHeight - rect.bottom - padding;
            return Math.max(0, minSpace - availableSpaceBelow);
        }

        function openInlineDatePicker(input) {
            if (!input) {
                return;
            }
            try {
                input.focus({ preventScroll: true });
            } catch (error) {
                input.focus();
            }
            if (typeof input.showPicker === 'function') {
                try {
                    input.showPicker();
                    return;
                } catch (error) {
                    // Fallback para navegadores sem suporte/permite showPicker
                }
            }
            input.click();
        }

        function buildEtapaCommentHtml(etapaId, comentarios) {
            const hasComment = Boolean((comentarios || '').trim());
            if (hasComment) {
                return `
                    <div class="small text-muted mt-1 etapa-comentario-display ds-cursor-pointer" data-etapa-id="${etapaId}" title="Clique para editar">
                        <i class="fas fa-comment-alt me-1"></i> ${escapeHtml(comentarios)}
                    </div>
                `;
            }
            if (!canEditEtapas) {
                return '';
            }
            return `
                <div class="small text-muted mt-1 etapa-comentario-placeholder ds-cursor-pointer" data-etapa-id="${etapaId}" data-comentario="">
                    <i class="fas fa-comment-medical me-1"></i> adicionar comentário
                </div>
            `;
        }

        function buildEtapaRow(etapaPayload) {
            const etapaId = etapaPayload.id;
            const descricao = etapaPayload.descricao || '-';
            const responsavel = getResponsavelDisplayValue(etapaPayload.responsavel || '');
            const comentarios = etapaPayload.comentarios || '';
            const dataInicio = etapaPayload.data_inicio || '';
            const dataInicioDisplay = getDateDisplayValue(dataInicio, etapaPayload.data_inicio_display || '');
            const dataFim = etapaPayload.data_fim || '';
            const dataFimDisplay = getDateDisplayValue(dataFim, etapaPayload.data_fim_display || '');
            const iniciada = Boolean(etapaPayload.iniciada);
            const done = Boolean(etapaPayload.done);
            const rowClasses = [
                'etapa-draggable-row',
                done ? 'etapa-done' : (iniciada ? 'etapa-iniciada' : ''),
            ]
                .filter(Boolean)
                .join(' ');

            const row = document.createElement('tr');
            row.className = rowClasses;
            row.dataset.etapaId = String(etapaId);

            const doneButtonDisabled = (!iniciada && !done) || !canEditEtapas ? 'disabled' : '';
            const iniciadaDisabled = canEditEtapas ? '' : 'disabled';
            const doneTitle = done
                ? 'Marcar como pendente'
                : (iniciada ? 'Marcar como concluída' : 'Marcar como concluída (necessário iniciar primeiro)');
            const actionHtml = canEditEtapas
                ? `
                    <form action="/etapa/${etapaId}/delete" method="post" class="inline-form" data-etapa-delete-form
                        onsubmit="return confirm('Tem certeza que deseja excluir esta etapa?');">
                        <button type="submit" class="btn btn-sm btn-floating" data-etapa-delete-btn title="Excluir Etapa">
                            <i class="fas fa-trash"></i>
                        </button>
                    </form>
                `
                : '<span class="text-muted small">-</span>';

            row.innerHTML = `
                <td class="drag-handle etapa-drag-handle etapa-v4-cell-drag" draggable="true"><i class="fas fa-grip-vertical"></i></td>
                <td class="etapa-order-cell etapa-v4-cell-number"></td>
                <td class="etapa-descricao etapa-row-text etapa-v4-cell-description ${done ? 'text-decoration-line-through text-muted' : ''} etapa-hover-container">
                    <div class="etapa-descricao-main">
                        <span class="editable-field" data-field="descricao" data-etapa-id="${etapaId}">${escapeHtml(descricao)}</span>
                    </div>
                    <div class="etapa-descricao-comment">
                        ${buildEtapaCommentHtml(etapaId, comentarios)}
                    </div>
                    <button class="btn-comment-data ds-hidden" data-etapa-id="${etapaId}" data-comentario="${escapeHtml(comentarios)}"></button>
                </td>
                <td class="etapa-row-text etapa-v4-cell-date ${done ? 'text-decoration-line-through text-muted' : ''}">
                    <span class="editable-field${dataInicio ? '' : ' editable-field-empty'}" data-field="data_inicio" data-etapa-id="${etapaId}" data-original-value="${escapeHtml(dataInicio)}" data-empty-display="Sem data">${escapeHtml(dataInicioDisplay)}</span>
                </td>
                <td class="etapa-row-text etapa-v4-cell-date ${done ? 'text-decoration-line-through text-muted' : ''}">
                    <span class="editable-field${dataFim ? '' : ' editable-field-empty'}" data-field="data_fim" data-etapa-id="${etapaId}" data-original-value="${escapeHtml(dataFim)}" data-empty-display="Sem data">${escapeHtml(dataFimDisplay)}</span>
                </td>
                <td class="etapa-row-text etapa-v4-cell-responsavel ${done ? 'text-decoration-line-through text-muted' : ''}">
                    <span class="editable-field${isResponsavelEmptyValue(responsavel) ? ' editable-field-empty' : ''}" data-field="responsavel" data-etapa-id="${etapaId}" data-empty-display="Sem responsável">${escapeHtml(responsavel)}</span>
                </td>
                <td class="text-center etapa-v4-cell-status">
                    <button type="button" class="btn btn-sm etapa-status-toggle toggle-iniciada etapa-status-toggle-${iniciada ? 'started' : 'idle'}"
                        data-etapa-id="${etapaId}"
                        data-state="${iniciada ? 'started' : 'idle'}"
                        title="${iniciada ? 'Marcar como não iniciada' : 'Marcar como iniciada'}" ${iniciadaDisabled}>
                        <i class="fas ${iniciada ? 'fa-stop-circle' : 'fa-play-circle'}"></i>
                        <span>${iniciada ? 'Iniciada' : 'Iniciar'}</span>
                    </button>
                </td>
                <td class="text-center etapa-v4-cell-status">
                    <button type="button" class="btn btn-sm etapa-status-toggle toggle-done etapa-status-toggle-${done ? 'done' : (iniciada ? 'ready' : 'blocked')}"
                        data-etapa-id="${etapaId}" data-state="${done ? 'done' : (iniciada ? 'ready' : 'blocked')}" ${doneButtonDisabled} title="${doneTitle}">
                        <i class="fas fa-check-circle"></i>
                        <span>${done ? 'Concluída' : 'Concluir'}</span>
                    </button>
                </td>
                <td class="actions text-center etapa-v4-actions-cell">
                    ${actionHtml}
                </td>
            `;
            return row;
        }

        function appendEtapaRow(etapaPayload) {
            if (!tbody || !etapaPayload || !etapaPayload.id) {
                return;
            }

            const row = buildEtapaRow(etapaPayload);
            if (inlineEmptyRow && inlineEmptyRow.parentNode) {
                inlineEmptyRow.remove();
            }
            if (inlineAddEntryRow && inlineAddEntryRow.parentNode === tbody) {
                tbody.insertBefore(row, inlineAddEntryRow);
            } else if (inlineAddFormRow && inlineAddFormRow.parentNode === tbody) {
                tbody.insertBefore(row, inlineAddFormRow);
            } else {
                tbody.appendChild(row);
            }
            renumberEtapaRows();
            refreshConcludeButtonCounters();
        }

        function openInlineEtapaComposer(source) {
            if (!canEditEtapas || !inlineAddFormRow || !inlineAddForm) {
                return;
            }
            if (isInlineComposerOpen()) {
                if (inlineDescricaoInput) {
                    inlineDescricaoInput.focus();
                }
                return;
            }
            inlineAddForm.reset();
            resetInlineComposerDateValues();
            syncInlineStatusControls();
            resizeInlineDescricaoTextarea();
            inlineAddFormRow.classList.remove('ds-hidden');
            if (inlineAddEntryRow) {
                inlineAddEntryRow.classList.add('ds-hidden');
            }
            if (inlineEmptyRow) {
                inlineEmptyRow.classList.add('ds-hidden');
            }
            requestAnimationFrame(() => {
                inlineAddFormRow.scrollIntoView({ behavior: 'smooth', block: 'end' });
                if (inlineDescricaoInput) {
                    inlineDescricaoInput.focus();
                }
            });
            if (source === 'entry') {
                inlineAddFormRow.dataset.openedFrom = 'entry';
            } else {
                inlineAddFormRow.dataset.openedFrom = 'button';
            }
        }

        function closeInlineEtapaComposer(reset = true) {
            if (!inlineAddFormRow) {
                return;
            }
            inlineAddFormRow.classList.add('ds-hidden');
            if (inlineAddEntryRow) {
                inlineAddEntryRow.classList.remove('ds-hidden');
            }
            if (reset && inlineAddForm) {
                inlineAddForm.reset();
                resetInlineComposerDateValues();
                syncInlineStatusControls();
                resizeInlineDescricaoTextarea();
            }
            if (inlineEmptyRow && tbody && tbody.querySelectorAll('tr.etapa-draggable-row').length === 0) {
                inlineEmptyRow.classList.remove('ds-hidden');
            }
            delete inlineAddFormRow.dataset.openedFrom;
        }

        async function submitInlineEtapaForm(options = {}) {
            if (!inlineAddForm || inlineComposerSaving) {
                return;
            }
            const keepComposerOpen = Boolean(options.keepComposerOpen);

            const descricao = (inlineDescricaoInput ? inlineDescricaoInput.value : '').trim();
            if (!descricao) {
                showAjaxFlashMessage('A descrição da etapa é obrigatória.', 'warning');
                if (inlineDescricaoInput) {
                    inlineDescricaoInput.focus();
                }
                return;
            }

            const shouldReactivateProject = currentProjectStatus === 'Finalizado';
            if (shouldReactivateProject && !options.reactivateProject) {
                const confirmed = await promptReactivateProjectConfirmation();
                if (!confirmed) {
                    closeInlineEtapaComposer(true);
                    showAjaxFlashMessage('A etapa não foi salva e o projeto permaneceu finalizado.', 'info');
                    return;
                }
            }

            const originalSubmitHtml = inlineAddSubmitBtn ? inlineAddSubmitBtn.innerHTML : '';
            inlineComposerSaving = true;
            if (inlineAddSubmitBtn) {
                inlineAddSubmitBtn.disabled = true;
                inlineAddSubmitBtn.innerHTML = '<i class="fas fa-spinner fa-spin" aria-hidden="true"></i>';
            }
            if (inlineAddCancelBtn) {
                inlineAddCancelBtn.disabled = true;
            }

            try {
                const formData = new FormData(inlineAddForm);
                if (shouldReactivateProject) {
                    formData.set('reactivate_project', '1');
                }

                const response = await fetch(inlineAddForm.action, {
                    method: 'POST',
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest',
                        'Accept': 'application/json',
                        'X-CSRFToken': csrfToken
                    },
                    body: formData
                });

                let data = null;
                try {
                    data = await response.json();
                } catch (error) {
                    data = null;
                }

                if (!response.ok || !data || !data.success || !data.etapa) {
                    if (response.status === 409 && data?.confirmation_required) {
                        showAjaxFlashMessage(data.message || 'Confirmação necessária para reativar o projeto.', 'warning');
                        return;
                    }
                    showAjaxFlashMessage(data?.message || 'Erro ao adicionar etapa.', 'danger');
                    return;
                }

                if (data.project_status) {
                    updateProjectStatusDisplay(data.project_status);
                }

                if (data.project_reactivated) {
                    ensureConcludeProjectButton();
                }

                appendEtapaRow(data.etapa);
                if (data.warning) {
                    showAjaxFlashMessage(data.warning, 'warning');
                }
                showAjaxFlashMessage(data.message || 'Etapa adicionada com sucesso!', 'success');
                if (keepComposerOpen) {
                    inlineAddForm.reset();
                    resetInlineComposerDateValues();
                    syncInlineStatusControls();
                    resizeInlineDescricaoTextarea();
                    requestAnimationFrame(() => {
                        inlineAddFormRow.scrollIntoView({ behavior: 'smooth', block: 'end' });
                        if (inlineDescricaoInput) {
                            inlineDescricaoInput.focus();
                        }
                    });
                } else {
                    closeInlineEtapaComposer(true);
                }
            } catch (error) {
                console.error('Erro ao adicionar etapa inline:', error);
                showAjaxFlashMessage('Erro de comunicação ao adicionar etapa.', 'danger');
            } finally {
                inlineComposerSaving = false;
                if (inlineAddSubmitBtn) {
                    inlineAddSubmitBtn.disabled = false;
                    inlineAddSubmitBtn.innerHTML = originalSubmitHtml;
                }
                if (inlineAddCancelBtn) {
                    inlineAddCancelBtn.disabled = false;
                }
            }
        }

        if (btnOpenInlineEtapaAdd) {
            btnOpenInlineEtapaAdd.addEventListener('click', function () {
                openInlineEtapaComposer('button');
            });
        }

        if (inlineAddEntryBtn) {
            inlineAddEntryBtn.addEventListener('click', function (event) {
                event.preventDefault();
                openInlineEtapaComposer('entry');
            });
        }

        if (inlineAddCancelBtn) {
            inlineAddCancelBtn.addEventListener('click', function () {
                closeInlineEtapaComposer(true);
            });
        }

        if (reactivateProjectCancelBtn) {
            reactivateProjectCancelBtn.addEventListener('click', function () {
                resolveReactivateProjectModal(false);
            });
        }

        if (reactivateProjectConfirmBtn) {
            reactivateProjectConfirmBtn.addEventListener('click', function () {
                resolveReactivateProjectModal(true);
            });
        }

        if (reactivateProjectModal) {
            reactivateProjectModal.addEventListener('click', function (event) {
                if (event.target === reactivateProjectModal) {
                    resolveReactivateProjectModal(false);
                }
            });
        }

        document.addEventListener('keydown', function (event) {
            if (event.key === 'Escape' && reactivateProjectModalResolver) {
                resolveReactivateProjectModal(false);
            }
        });

        if (inlineAddForm) {
            inlineAddForm.addEventListener('submit', function (event) {
                event.preventDefault();
                submitInlineEtapaForm();
            });
        }

        if (inlineDescricaoInput) {
            inlineDescricaoInput.addEventListener('input', function () {
                resizeInlineDescricaoTextarea();
            });
            resizeInlineDescricaoTextarea();
        }

        if (inlineAddFormRow) {
            inlineAddFormRow.addEventListener('keydown', function (event) {
                if (!isInlineComposerOpen() || inlineComposerSaving) {
                    return;
                }
                if (event.defaultPrevented) {
                    return;
                }

                if (event.key === 'Escape') {
                    event.preventDefault();
                    closeInlineEtapaComposer(true);
                    return;
                }

                if (event.key !== 'Enter' || event.shiftKey) {
                    return;
                }

                const target = event.target instanceof Element ? event.target : null;
                if (target && (target.closest('.etapa-inline-icon-btn') || target.closest('.inline-status-toggle'))) {
                    return;
                }

                event.preventDefault();
                const descricao = (inlineDescricaoInput ? inlineDescricaoInput.value : '').trim();
                if (!descricao) {
                    if (inlineDescricaoInput) {
                        inlineDescricaoInput.focus();
                    }
                    return;
                }
                submitInlineEtapaForm({ keepComposerOpen: true });
            });
        }

        inlineDateInputs.forEach(input => {
            input.addEventListener('input', function () {
                syncInlineDateEmptyState(input);
            });
            input.addEventListener('change', function () {
                syncInlineDateEmptyState(input);
            });
            input.addEventListener('pointerdown', function (event) {
                if (!isInlineComposerOpen() || event.button !== 0 || inlineDatePickerOpening) {
                    return;
                }
                const missingSpace = missingDatePickerViewportSpace(input);
                if (missingSpace <= 0) {
                    return;
                }
                event.preventDefault();
                const maxDelta = Math.round(window.innerHeight * 0.72);
                const delta = Math.min(maxDelta, missingSpace + 22);
                window.scrollBy(0, delta);
                inlineDatePickerOpening = true;
                requestAnimationFrame(function () {
                    openInlineDatePicker(input);
                    window.setTimeout(function () {
                        inlineDatePickerOpening = false;
                    }, 180);
                });
            });
            input.addEventListener('focus', function () {
                if (!isInlineComposerOpen() || inlineDatePickerOpening) {
                    return;
                }
                const missingSpace = missingDatePickerViewportSpace(input);
                if (missingSpace <= 0) {
                    return;
                }
                const maxDelta = Math.round(window.innerHeight * 0.72);
                const delta = Math.min(maxDelta, missingSpace + 22);
                window.scrollBy(0, delta);
            });
        });
        syncAllInlineDateEmptyState();
        syncInlineStatusControls();

        if (inlineIniciadaToggle && inlineIniciadaCheckbox) {
            inlineIniciadaToggle.addEventListener('click', function (event) {
                event.preventDefault();
                inlineIniciadaCheckbox.checked = !inlineIniciadaCheckbox.checked;
                if (!inlineIniciadaCheckbox.checked && inlineDoneCheckbox) {
                    inlineDoneCheckbox.checked = false;
                }
                syncInlineStatusControls();
            });
        }

        if (inlineDoneToggle && inlineDoneCheckbox) {
            inlineDoneToggle.addEventListener('click', function (event) {
                event.preventDefault();
                if (inlineDoneToggle.disabled) {
                    return;
                }
                inlineDoneCheckbox.checked = !inlineDoneCheckbox.checked;
                syncInlineStatusControls();
            });
        }

        document.addEventListener('pointerdown', function (event) {
            if (!isInlineComposerOpen() || inlineComposerSaving) {
                return;
            }
            if (event.button !== 0) {
                return;
            }

            const target = event.target instanceof Element ? event.target : null;

            if (
                target?.closest('#etapaInlineAddFormRow') ||
                target?.closest('#etapaInlineAddEntryRow') ||
                target?.closest('#btnOpenInlineEtapaAdd')
            ) {
                return;
            }

            const descricao = (inlineDescricaoInput ? inlineDescricaoInput.value : '').trim();
            if (descricao) {
                submitInlineEtapaForm();
            } else {
                closeInlineEtapaComposer(true);
            }
        });

        if (tbody) {
            let draggedItem = null;
            let originalIndex = -1;
            let ghostElement = null;
            let dropIndicator = null; // Indicador de drop

            // Criar o indicador de drop
            function createDropIndicator() {
                if (!dropIndicator) {
                    dropIndicator = document.createElement('div');
                    dropIndicator.className = 'drop-indicator';
                    document.body.appendChild(dropIndicator);
                }
                return dropIndicator;
            }

            // Mostrar indicador de drop
            function showDropIndicator(targetRow, position) {
                const indicator = createDropIndicator();
                const rect = targetRow.getBoundingClientRect();
                const tableRect = tbody.getBoundingClientRect();

                indicator.style.position = 'fixed';
                indicator.style.left = tableRect.left + 'px';
                indicator.style.width = tableRect.width + 'px';

                if (position === 'top') {
                    indicator.style.top = (rect.top - 2) + 'px';
                } else {
                    indicator.style.top = (rect.bottom - 1) + 'px';
                }

                indicator.classList.add('show');
            }

            // Esconder indicador de drop
            function hideDropIndicator() {
                if (dropIndicator) {
                    dropIndicator.classList.remove('show');
                }
            }

            tbody.addEventListener('dragstart', function (e) {
                const handle = e.target.closest('.drag-handle');
                if (handle) {
                    draggedItem = handle.closest('tr.etapa-draggable-row');
                    if (!draggedItem) return;

                    originalIndex = Array.from(draggedItem.parentNode.children).indexOf(draggedItem);
                    e.dataTransfer.effectAllowed = 'move';
                    e.dataTransfer.setData('text/plain', draggedItem.dataset.etapaId);

                    // Criação do ghost element customizado
                    ghostElement = document.createElement('div');
                    ghostElement.classList.add('drag-ghost-custom');
                    const descricaoEtapa = draggedItem.querySelector('.etapa-descricao');
                    ghostElement.innerHTML = `<i class="fas fa-arrows-alt me-2"></i>${descricaoEtapa ? descricaoEtapa.innerText.trim().substring(0, 60) + (descricaoEtapa.innerText.trim().length > 60 ? '...' : '') : 'Movendo etapa...'}`;
                    document.body.appendChild(ghostElement);

                    e.dataTransfer.setDragImage(ghostElement, 20, 20);

                    setTimeout(() => {
                        if (draggedItem) draggedItem.classList.add('dragging');
                        if (ghostElement && ghostElement.parentNode) {
                            ghostElement.parentNode.removeChild(ghostElement);
                            ghostElement = null;
                        }
                    }, 0);
                } else {
                    e.preventDefault(); // Impede o início do arraste se não for no handle
                }
            });

            tbody.addEventListener('dragend', function (e) {
                if (draggedItem) {
                    draggedItem.classList.remove('dragging');
                    draggedItem = null;
                }
                if (ghostElement && ghostElement.parentNode) {
                    ghostElement.parentNode.removeChild(ghostElement);
                    ghostElement = null;
                }

                hideDropIndicator();
                tbody.querySelectorAll('tr.etapa-draggable-row.drag-over').forEach(r => r.classList.remove('drag-over'));

                renumberEtapaRows();
            });

            tbody.addEventListener('dragover', function (e) {
                e.preventDefault();
                const targetRow = e.target.closest('tr.etapa-draggable-row');

                if (targetRow && targetRow !== draggedItem) {
                    const rect = targetRow.getBoundingClientRect();
                    const mouseY = e.clientY;
                    const rowMiddle = rect.top + rect.height / 2;

                    // Determinar se deve inserir antes ou depois
                    const position = mouseY < rowMiddle ? 'top' : 'bottom';

                    // Limpar classes anteriores
                    tbody.querySelectorAll('tr.etapa-draggable-row.drag-over').forEach(r => r.classList.remove('drag-over'));

                    // Mostrar indicador na posição correta
                    showDropIndicator(targetRow, position);

                    e.dataTransfer.dropEffect = 'move';
                }
            });

            tbody.addEventListener('dragleave', function (e) {
                const relatedTarget = e.relatedTarget;

                if (!tbody.contains(relatedTarget) && draggedItem) {
                    hideDropIndicator();
                    tbody.querySelectorAll('tr.etapa-draggable-row.drag-over').forEach(r => r.classList.remove('drag-over'));
                }
            });

            tbody.addEventListener('drop', function (e) {
                e.preventDefault();
                const targetRow = e.target.closest('tr.etapa-draggable-row');

                hideDropIndicator();
                tbody.querySelectorAll('tr.etapa-draggable-row.drag-over').forEach(r => r.classList.remove('drag-over'));

                if (draggedItem && targetRow && targetRow !== draggedItem) {
                    const rect = targetRow.getBoundingClientRect();
                    const mouseY = e.clientY;
                    const rowMiddle = rect.top + rect.height / 2;
                    const insertBefore = mouseY < rowMiddle;

                    // Inserir na posição correta baseado na posição do mouse
                    if (insertBefore) {
                        targetRow.parentNode.insertBefore(draggedItem, targetRow);
                    } else {
                        targetRow.parentNode.insertBefore(draggedItem, targetRow.nextSibling);
                    }

                    const etapaRows = tbody.querySelectorAll('tr.etapa-draggable-row');
                    const etapaIdsOrdenadas = Array.from(etapaRows).map(row => row.dataset.etapaId);

                    fetch(`/project/${projectIdValue}/etapas/reordenar`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-Requested-With': 'XMLHttpRequest',
                            'X-CSRFToken': csrfToken
                        },
                        body: JSON.stringify({ etapa_ids: etapaIdsOrdenadas })
                    })
                        .then(response => response.json())
                        .then(data => {
                            if (data.success) {
                                showAjaxFlashMessage(data.message || 'Ordem das etapas atualizada com sucesso!', 'success');
                            } else {
                                showAjaxFlashMessage(data.message || 'Erro ao reordenar etapas.', 'danger');
                            }
                        })
                        .catch(error => {
                            console.error('Erro na requisição de reordenar:', error);
                            showAjaxFlashMessage('Erro de comunicação ao reordenar etapas.', 'danger');
                        });
                }
            });
        }
        // FIM: Script de Drag and Drop para Etapas

        // --- INÍCIO: Lógica de Edição Inline ---
        const mainContent = document.querySelector('.etapa-list');
        const contextMenu = document.getElementById('date-context-menu');
        let currentTargetElement = null;

        if (mainContent) {
            function showContextMenuAt(x, y) {
                if (!contextMenu) {
                    return;
                }
                contextMenu.style.position = 'fixed';
                contextMenu.style.display = 'block';
                contextMenu.style.visibility = 'hidden';

                const menuRect = contextMenu.getBoundingClientRect();
                const viewportPadding = 10;
                const maxLeft = window.innerWidth - menuRect.width - viewportPadding;
                const maxTop = window.innerHeight - menuRect.height - viewportPadding;
                const left = Math.max(viewportPadding, Math.min(x, maxLeft));
                const top = Math.max(viewportPadding, Math.min(y, maxTop));

                contextMenu.style.left = `${left}px`;
                contextMenu.style.top = `${top}px`;
                contextMenu.style.visibility = 'visible';
            }

            // --- Lógica do Menu de Contexto para Datas ---
            mainContent.addEventListener('contextmenu', function (e) {
                const target = e.target.closest('.editable-field[data-field*="data"]');

                if (!target) {
                    hideContextMenu();
                    return;
                }

                // Impede se a etapa estiver concluída
                if (target.closest('tr.etapa-done')) {
                    return;
                }

                e.preventDefault();
                currentTargetElement = target; // Armazena o elemento alvo

                // Verifica se há uma data válida para exibir o menu
                const originalDate = currentTargetElement.dataset.originalValue;
                if (!originalDate) {
                    showAjaxFlashMessage('Defina uma data inicial antes de adicionar dias.', 'warning');
                    return;
                }

                showContextMenuAt(e.clientX, e.clientY);
            });

            // --- Lógica de clique no menu de contexto ---
            contextMenu.addEventListener('click', function (e) {
                const selectedOption = e.target.closest('li[data-days]');
                if (selectedOption && currentTargetElement) {
                    const elementToUpdate = currentTargetElement; // Guarda a referência antes de ser apagada
                    const daysToAdd = parseInt(selectedOption.dataset.days, 10);
                    const originalDateStr = elementToUpdate.dataset.originalValue;
                    const field = elementToUpdate.dataset.field;
                    const etapaId = elementToUpdate.dataset.etapaId;

                    // Calcula a nova data
                    const originalDate = new Date(originalDateStr + 'T00:00:00'); // Adiciona T00:00 para evitar problemas de fuso
                    originalDate.setDate(originalDate.getDate() + daysToAdd);

                    const year = originalDate.getFullYear();
                    const month = String(originalDate.getMonth() + 1).padStart(2, '0');
                    const day = String(originalDate.getDate()).padStart(2, '0');
                    const newDateValue = `${year}-${month}-${day}`;

                    // Envia a atualização para o backend
                    fetch(`/etapa/${etapaId}/update_field`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-Requested-With': 'XMLHttpRequest',
                            'X-CSRFToken': csrfToken
                        },
                        body: JSON.stringify({ field: field, value: newDateValue })
                    })
                        .then(response => response.json())
                        .then(data => {
                            if (data.success) {
                                // Atualiza o campo que foi clicado (data_inicio ou data_fim)
                                updateDateFieldDisplay(elementToUpdate, data.newValue || '', data.displayValue || '');
                                elementToUpdate.dataset.originalValue = data.newValue || '';

                                // Se a data de início foi alterada, atualiza também a data de fim da mesma etapa
                                if (field === 'data_inicio' && data.updatedEndDate) {
                                    const etapaRow = elementToUpdate.closest('tr');
                                    const endDateElement = etapaRow.querySelector('.editable-field[data-field="data_fim"]');
                                    if (endDateElement) {
                                        updateDateFieldDisplay(endDateElement, data.updatedEndDate || '', data.updatedEndDateDisplay || '');
                                        endDateElement.dataset.originalValue = data.updatedEndDate || '';
                                    }
                                }

                                // Se a data de início foi alterada, pergunta sobre a cascata
                                if (field === 'data_inicio' && daysToAdd !== 0) {
                                    showCascadeConfirmModal(etapaId, daysToAdd);
                                } else {
                                    showAjaxFlashMessage(`Data atualizada: +${daysToAdd} dias`, 'success');
                                }
                            } else {
                                showAjaxFlashMessage(data.message || 'Falha ao atualizar data.', 'danger');
                            }
                        })
                        .catch(error => {
                            showAjaxFlashMessage('Erro de comunicação.', 'danger');
                            console.error('Error updating date field:', error);
                        });
                }
                hideContextMenu();
            });

            // Esconde o menu ao clicar em qualquer lugar
            window.addEventListener('click', hideContextMenu);
            window.addEventListener('keydown', function (event) {
                if (event.key === 'Escape') {
                    hideContextMenu();
                }
            });

            function hideContextMenu() {
                if (contextMenu && contextMenu.style.display === 'block') {
                    contextMenu.style.display = 'none';
                    contextMenu.style.visibility = 'hidden';
                    currentTargetElement = null;
                }
            }

            function resizeMultilineEditor(textarea) {
                if (!textarea) {
                    return;
                }
                const computed = window.getComputedStyle(textarea);
                const lineHeight = parseFloat(computed.lineHeight) || 20;
                const minHeight = lineHeight + 12;
                textarea.style.height = 'auto';
                textarea.style.height = `${Math.max(textarea.scrollHeight, minHeight)}px`;
            }

            mainContent.addEventListener('click', function (e) {
                const target = e.target.closest('.editable-field');

                // Impede a edição se já houver um campo de edição aberto
                if (document.querySelector('.editable-field-input, .editable-field-textarea')) {
                    return;
                }

                if (!target) return;

                // Impede a edição se a etapa estiver concluída
                if (target.closest('tr.etapa-done')) {
                    showAjaxFlashMessage('Não é possível editar uma etapa concluída.', 'warning');
                    return;
                }

                const field = target.dataset.field;
                const etapaId = target.dataset.etapaId;
                let originalValue = target.textContent.trim();
                if (field === 'responsavel' && target.classList.contains('editable-field-empty')) {
                    originalValue = '';
                }
                // Para datas, o valor do input precisa ser no formato YYYY-MM-DD
                const originalDateValue = target.dataset.originalValue || '';

                let input;

                if (field === 'descricao') {
                    input = document.createElement('textarea');
                    input.className = 'editable-field-textarea';
                    input.value = originalValue;
                    input.rows = 1;
                    resizeMultilineEditor(input);
                    input.addEventListener('input', function () {
                        resizeMultilineEditor(input);
                    });
                } else if (field === 'responsavel') {
                    input = document.createElement('textarea');
                    input.className = 'editable-field-textarea editable-field-textarea-responsavel';
                    input.value = originalValue === '-' ? '' : originalValue;
                    input.rows = 1;
                    input.placeholder = 'Sem responsável';
                    resizeMultilineEditor(input);
                    input.addEventListener('input', function () {
                        resizeMultilineEditor(input);
                    });
                } else {
                    input = document.createElement('input');
                    input.className = 'editable-field-input';
                    if (field.includes('data')) {
                        input.type = 'date';
                        input.value = originalDateValue;
                    } else {
                        input.type = 'text';
                        input.value = originalValue === '-' ? '' : originalValue;
                    }
                }

                target.style.display = 'none';
                target.insertAdjacentElement('afterend', input);
                input.focus();

                function saveChanges() {
                    const newValue = input.value;

                    input.remove();
                    target.style.display = '';

                    // Verifica se o valor mudou antes de enviar
                    const valueToCheck = field.includes('data') ? originalDateValue : (originalValue === '-' ? '' : originalValue);
                    if (newValue === valueToCheck) {
                        return; // Nenhum valor alterado
                    }

                    fetch(`/etapa/${etapaId}/update_field`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-Requested-With': 'XMLHttpRequest',
                            'X-CSRFToken': csrfToken
                        },
                        body: JSON.stringify({ field: field, value: newValue })
                    })
                        .then(response => response.json())
                        .then(data => {
                            if (data.success) {
                                if (field.includes('data')) {
                                    updateDateFieldDisplay(target, data.newValue || '', data.displayValue || '');
                                    target.dataset.originalValue = data.newValue || '';
                                } else if (field === 'responsavel') {
                                    updateResponsavelFieldDisplay(target, data.newValue || '');
                                } else {
                                    target.textContent = data.displayValue;
                                }

                                // Lógica para data de fim e cascata
                                if (field === 'data_inicio' && data.updatedEndDate) {
                                    const etapaRow = target.closest('tr');
                                    const endDateElement = etapaRow.querySelector('.editable-field[data-field="data_fim"]');
                                    if (endDateElement) {
                                        updateDateFieldDisplay(endDateElement, data.updatedEndDate || '', data.updatedEndDateDisplay || '');
                                        endDateElement.dataset.originalValue = data.updatedEndDate || '';
                                    }
                                }

                                if (field === 'data_inicio' && data.daysDiff !== undefined && data.daysDiff !== 0) {
                                    showCascadeConfirmModal(etapaId, data.daysDiff);
                                } else {
                                    showAjaxFlashMessage('Alteração salva com sucesso!', 'success');
                                }

                            } else {
                                if (field === 'responsavel') {
                                    updateResponsavelFieldDisplay(target, originalValue);
                                } else {
                                    target.textContent = originalValue;
                                }
                                showAjaxFlashMessage(data.message || 'Falha ao salvar.', 'danger');
                            }
                        })
                        .catch(error => {
                            if (field === 'responsavel') {
                                updateResponsavelFieldDisplay(target, originalValue);
                            } else {
                                target.textContent = originalValue;
                            }
                            showAjaxFlashMessage('Erro de comunicação.', 'danger');
                            console.error('Error updating field:', error);
                        });
                }

                input.addEventListener('blur', saveChanges);

                input.addEventListener('keydown', function (event) {
                    if (event.key === 'Enter' && field !== 'descricao' && !event.shiftKey) {
                        event.preventDefault();
                        saveChanges();
                    } else if (event.key === 'Escape') {
                        input.remove();
                        target.style.display = '';
                    }
                });
            });
        }
        // --- FIM: Lógica de Edição Inline ---

        // --- INÍCIO: Lógica de Cascata de Datas ---
        const cascadeModal = document.getElementById('cascade-confirm-modal');
        const cascadeConfirmBtn = document.getElementById('cascade-confirm-btn');
        const cascadeCancelBtn = document.getElementById('cascade-cancel-btn');
        let cascadeUpdateInfo = {};

        function showCascadeConfirmModal(etapaId, daysDiff) {
            cascadeUpdateInfo = { etapaId, daysDiff };
            cascadeModal.style.display = 'flex';
        }

        function hideCascadeConfirmModal() {
            cascadeModal.style.display = 'none';
        }

        cascadeCancelBtn.addEventListener('click', hideCascadeConfirmModal);

        cascadeConfirmBtn.addEventListener('click', function () {
            const { etapaId, daysDiff } = cascadeUpdateInfo;
            const projectId = projectIdValue;

            fetch(`/project/${projectId}/cascade_update`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({ etapa_id: etapaId, days_diff: daysDiff })
            })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        showAjaxFlashMessage(data.message, 'success');
                        // Forçar recarregamento da página para ver as mudanças em cascata
                        // Uma implementação mais avançada poderia atualizar o DOM, mas isso é mais seguro.
                        window.location.reload();
                    } else {
                        showAjaxFlashMessage(data.message, 'danger');
                    }
                })
                .catch(error => {
                    showAjaxFlashMessage('Erro de comunicação na atualização em cascata.', 'danger');
                    console.error('Cascade update error:', error);
                });

            hideCascadeConfirmModal();
        });

        // --- FIM: Lógica de Cascata de Datas ---


        // INÍCIO: Scripts Originais Restaurados (toggle status, view toggle, etc.)
        function showAjaxFlashMessage(message, type = 'info', duration = 5000) {
            const containerId = 'ajax-flash-messages-container';
            let flashContainer = document.getElementById(containerId);

            if (!flashContainer) {
                flashContainer = document.createElement('div');
                flashContainer.id = containerId;
                document.body.appendChild(flashContainer);
            }

            if (!message) return;

            // Limitar a 3 notificações simultâneas
            const MAX_NOTIFICATIONS = 3;
            const existingAlerts = flashContainer.querySelectorAll('.alert');

            if (existingAlerts.length >= MAX_NOTIFICATIONS) {
                // Remove a primeira (mais antiga) notificação
                const oldestAlert = existingAlerts[0];

                // Usar Bootstrap Alert para fechar suavemente
                const bsAlert = bootstrap.Alert.getInstance(oldestAlert);
                if (bsAlert) {
                    bsAlert.close();
                } else {
                    oldestAlert.classList.remove('show');
                    setTimeout(() => {
                        if (oldestAlert.parentNode) {
                            oldestAlert.remove();
                        }
                    }, 150);
                }
            }

            const alertDiv = document.createElement('div');
            const normalizedType = type === 'error' ? 'danger' : type;
            const iconByType = {
                success: 'check-circle',
                danger: 'exclamation-circle',
                warning: 'exclamation-triangle',
                info: 'info-circle',
            };
            const iconName = iconByType[normalizedType] || 'info-circle';
            const safeMessage = escapeHtml(message);

            alertDiv.className = `alert alert-${normalizedType} alert-dismissible fade show app-flash-alert app-flash-alert-compact`;
            alertDiv.role = 'alert';
            alertDiv.innerHTML = `
                <div class="d-flex align-items-start gap-2">
                    <i class="fas fa-${iconName} app-flash-icon"></i>
                    <span class="app-flash-text">${safeMessage}</span>
                </div>
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
            `;

            flashContainer.appendChild(alertDiv);

            if (duration > 0) {
                setTimeout(() => {
                    const bsAlert = bootstrap.Alert.getInstance(alertDiv);
                    if (bsAlert) {
                        bsAlert.close();
                    } else {
                        alertDiv.remove();
                    }
                }, duration);
            }
        }

        let concludeProjectForm = document.getElementById('concludeProjectForm');
        let concludeProjectButton = document.getElementById('btn-concluir-projeto');
        const concludeCelebrationEl = document.getElementById('projectConcludeCelebration');
        const concludeCelebrationTitleEl = concludeCelebrationEl
            ? concludeCelebrationEl.querySelector('[data-celebration-title]')
            : null;
        const concludeCelebrationMessageEl = concludeCelebrationEl
            ? concludeCelebrationEl.querySelector('[data-celebration-message]')
            : null;
        const reduceMotionQuery = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;

        let concludeRequestInFlight = false;
        let concludeAudioContext = null;
        let concludeCelebrationTimeoutId = null;
        let concludeButtonDefaultHtml = concludeProjectButton ? concludeProjectButton.innerHTML : '<i class="fas fa-check-circle me-1"></i>Concluir Projeto';

        function bindConcludeProjectControls() {
            concludeProjectForm = document.getElementById('concludeProjectForm');
            concludeProjectButton = document.getElementById('btn-concluir-projeto');

            if (!concludeProjectForm || !concludeProjectButton) {
                return;
            }

            concludeButtonDefaultHtml = concludeProjectButton.innerHTML || '<i class="fas fa-check-circle me-1"></i>Concluir Projeto';

            if (concludeProjectButton.dataset.boundConclude === 'true') {
                return;
            }

            concludeProjectButton.addEventListener('pointerdown', function () {
                primeConcludeAudioContext();
            }, { passive: true });

            concludeProjectForm.addEventListener('submit', function (event) {
                if (concludeRequestInFlight || concludeProjectButton.disabled) {
                    event.preventDefault();
                    return;
                }

                event.preventDefault();
                primeConcludeAudioContext();
                submitConcludeProjectWithCelebration();
            });

            concludeProjectButton.dataset.boundConclude = 'true';
        }

        function getConcludeAudioContext() {
            if (concludeAudioContext) {
                return concludeAudioContext;
            }
            const AudioContextClass = window.AudioContext || window.webkitAudioContext;
            if (!AudioContextClass) {
                return null;
            }
            concludeAudioContext = new AudioContextClass();
            return concludeAudioContext;
        }

        async function primeConcludeAudioContext() {
            try {
                const context = getConcludeAudioContext();
                if (!context) {
                    return;
                }
                if (context.state === 'suspended') {
                    await context.resume();
                }
            } catch (error) {
                console.warn('Não foi possível preparar o áudio de conclusão.', error);
            }
        }

        function playConcludeSuccessChime() {
            const context = getConcludeAudioContext();
            if (!context) {
                return;
            }
            if (context.state === 'suspended') {
                context.resume().catch(() => { });
            }

            try {
                const now = context.currentTime + 0.012;

                // ===== Master =====
                const masterGain = context.createGain();
                masterGain.gain.setValueAtTime(0.75, now);

                // Lowpass principal (som "polido", nao espalhafatoso)
                const toneFilter = context.createBiquadFilter();
                toneFilter.type = "lowpass";
                toneFilter.frequency.setValueAtTime(2200, now);
                toneFilter.Q.value = 0.7;

                masterGain.connect(toneFilter);
                toneFilter.connect(context.destination);

                // ===== Sparkle Bus (so pro final ficar mais brilhante/feliz) =====
                // E um bus paralelo, bem baixo, filtrado pra nao "apitar".
                const sparkleGain = context.createGain();
                sparkleGain.gain.setValueAtTime(0.18, now); // 0.12..0.22 (ajuste fino)

                const sparkleHP = context.createBiquadFilter();
                sparkleHP.type = "highpass";
                sparkleHP.frequency.setValueAtTime(1400, now);

                const sparkleShelf = context.createBiquadFilter();
                sparkleShelf.type = "highshelf";
                sparkleShelf.frequency.setValueAtTime(2800, now);
                sparkleShelf.gain.setValueAtTime(3.5, now); // 2..5 (ajuste fino)

                sparkleGain.connect(sparkleHP);
                sparkleHP.connect(sparkleShelf);
                sparkleShelf.connect(context.destination);

                // ===== Helper =====
                function playNote(freq, start, duration, gain, opts = {}) {
                    const startAt = now + start;
                    const endAt = startAt + duration;

                    // Camada principal
                    const oscBody = context.createOscillator();
                    const oscTexture = context.createOscillator();
                    const gainBody = context.createGain();
                    const gainTexture = context.createGain();

                    oscBody.type = "sine";
                    oscBody.frequency.setValueAtTime(freq, startAt);

                    // Textura em oitava acima (fala mais sem ficar alta)
                    oscTexture.type = "triangle";
                    oscTexture.frequency.setValueAtTime(freq * 2, startAt);

                    // Envelope (rapido e satisfatorio)
                    gainBody.gain.setValueAtTime(0.0001, startAt);
                    gainBody.gain.exponentialRampToValueAtTime(gain, startAt + 0.010);
                    gainBody.gain.exponentialRampToValueAtTime(gain * 0.55, startAt + duration * 0.55);
                    gainBody.gain.exponentialRampToValueAtTime(0.0001, endAt + 0.03);

                    gainTexture.gain.setValueAtTime(0.0001, startAt);
                    gainTexture.gain.exponentialRampToValueAtTime(gain * 0.28, startAt + 0.008);
                    gainTexture.gain.exponentialRampToValueAtTime(0.0001, endAt + 0.02);

                    oscBody.connect(gainBody);
                    oscTexture.connect(gainTexture);
                    gainBody.connect(masterGain);
                    gainTexture.connect(masterGain);

                    // ===== Sparkle so no final da ultima nota (bem sutil) =====
                    // Oitava + "quinta" acima (freq*2 e freq*3) da sensacao mais "feliz".
                    if (opts.sparkle) {
                        const sparkleStart = startAt + duration * 0.55;
                        const sparkleEnd = endAt + 0.08;

                        const sp1 = context.createOscillator();
                        const sp2 = context.createOscillator();
                        const spGain = context.createGain();

                        sp1.type = "sine";
                        sp2.type = "triangle";

                        sp1.frequency.setValueAtTime(freq * 2, sparkleStart); // oitava acima
                        sp2.frequency.setValueAtTime(freq * 3, sparkleStart); // oitava + quinta (bem "happy")

                        spGain.gain.setValueAtTime(0.0001, sparkleStart);
                        spGain.gain.exponentialRampToValueAtTime(gain * 0.075, sparkleStart + 0.012); // 0.055..0.09
                        spGain.gain.exponentialRampToValueAtTime(0.0001, sparkleEnd);

                        sp1.connect(spGain);
                        sp2.connect(spGain);
                        spGain.connect(sparkleGain);

                        sp1.start(sparkleStart);
                        sp2.start(sparkleStart);
                        sp1.stop(sparkleEnd + 0.02);
                        sp2.stop(sparkleEnd + 0.02);
                    }
                    // =========================================================

                    oscBody.start(startAt);
                    oscTexture.start(startAt);
                    oscBody.stop(endAt + 0.06);
                    oscTexture.stop(endAt + 0.06);
                }

                // Leve sensacao de "subiu e concluiu"
                const notes = [
                    { freq: 196.0, start: 0.00, duration: 0.18, gain: 0.095, sparkle: false },
                    { freq: 246.94, start: 0.14, duration: 0.20, gain: 0.088, sparkle: false },
                    { freq: 329.63, start: 0.28, duration: 0.22, gain: 0.082, sparkle: true }, // brilho so aqui
                ];

                notes.forEach(n => playNote(n.freq, n.start, n.duration, n.gain, { sparkle: n.sparkle }));

                // Sub/impact (curto, perceptivel, sem virar kick)
                const subOsc = context.createOscillator();
                const subGain = context.createGain();
                subOsc.type = "sine";
                subOsc.frequency.setValueAtTime(110, now);
                subOsc.frequency.exponentialRampToValueAtTime(65, now + 0.11);

                subGain.gain.setValueAtTime(0.0001, now);
                subGain.gain.exponentialRampToValueAtTime(0.040, now + 0.010);
                subGain.gain.exponentialRampToValueAtTime(0.0001, now + 0.11);

                subOsc.connect(subGain);
                subGain.connect(masterGain);
                subOsc.start(now);
                subOsc.stop(now + 0.13);

                // Cleanup
                setTimeout(() => {
                    masterGain.disconnect();
                    toneFilter.disconnect();
                    sparkleGain.disconnect();
                    sparkleHP.disconnect();
                    sparkleShelf.disconnect();
                }, 1100);
            } catch (error) {
                console.error("Sound error:", error);
            }
        }

        function showConcludeCelebration(title, message, autoHideMs = 0) {
            if (!concludeCelebrationEl) {
                return;
            }

            if (concludeCelebrationTimeoutId) {
                window.clearTimeout(concludeCelebrationTimeoutId);
                concludeCelebrationTimeoutId = null;
            }

            if (concludeCelebrationTitleEl && title) {
                concludeCelebrationTitleEl.textContent = title;
            }
            if (concludeCelebrationMessageEl && message) {
                concludeCelebrationMessageEl.textContent = message;
            }

            concludeCelebrationEl.classList.add('is-active');
            concludeCelebrationEl.setAttribute('aria-hidden', 'false');

            if (autoHideMs > 0) {
                concludeCelebrationTimeoutId = window.setTimeout(() => {
                    hideConcludeCelebration();
                }, autoHideMs);
            }
        }

        function hideConcludeCelebration() {
            if (!concludeCelebrationEl) {
                return;
            }
            if (concludeCelebrationTimeoutId) {
                window.clearTimeout(concludeCelebrationTimeoutId);
                concludeCelebrationTimeoutId = null;
            }
            concludeCelebrationEl.classList.remove('is-active');
            concludeCelebrationEl.setAttribute('aria-hidden', 'true');
        }

        function setConcludeLoadingState(isLoading) {
            if (!concludeProjectButton) {
                return;
            }

            if (isLoading) {
                concludeProjectButton.disabled = true;
                concludeProjectButton.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Concluindo...';
                return;
            }

            concludeProjectButton.innerHTML = concludeButtonDefaultHtml;
            verificarEAtualizarBotaoConcluir();
        }

        function waitMs(duration) {
            return new Promise(resolve => window.setTimeout(resolve, duration));
        }

        async function submitConcludeProjectWithCelebration() {
            if (!concludeProjectForm || concludeRequestInFlight) {
                return;
            }

            concludeRequestInFlight = true;
            setConcludeLoadingState(true);
            showConcludeCelebration('Concluindo projeto...', 'Aguarde um instante.');

            try {
                const response = await fetch(concludeProjectForm.action, {
                    method: 'POST',
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest',
                        'Accept': 'application/json',
                        'X-CSRFToken': csrfToken
                    }
                });

                let data = null;
                try {
                    data = await response.json();
                } catch (error) {
                    data = null;
                }

                if (!response.ok || !data || !data.success) {
                    hideConcludeCelebration();
                    showAjaxFlashMessage(
                        data?.message || 'Não foi possível concluir o projeto.',
                        data?.category || (response.status === 403 ? 'danger' : 'warning')
                    );
                    setConcludeLoadingState(false);
                    concludeRequestInFlight = false;
                    return;
                }

                showConcludeCelebration('Objetivo concluído', data.message || 'Projeto finalizado com sucesso.');
                playConcludeSuccessChime();

                const celebrationDelay = reduceMotionQuery && reduceMotionQuery.matches ? 450 : 1250;
                await waitMs(celebrationDelay);
                window.location.href = data.redirect_url || concludeProjectForm.action;
            } catch (error) {
                console.error('Erro ao concluir projeto:', error);
                hideConcludeCelebration();
                showAjaxFlashMessage('Erro de comunicação com o servidor.', 'danger');
                setConcludeLoadingState(false);
                concludeRequestInFlight = false;
            }
        }

        bindConcludeProjectControls();

        function updateIniciadaButton(button, iniciada) {
            if (!button) return;
            setStatusToggleVariant(button, iniciada ? 'started' : 'idle');
            if (iniciada) {
                button.innerHTML = '<i class="fas fa-stop-circle"></i><span>Iniciada</span>';
                button.title = 'Marcar como não iniciada';
            } else {
                button.innerHTML = '<i class="fas fa-play-circle"></i><span>Iniciar</span>';
                button.title = 'Marcar como iniciada';
            }
        }

        function updateDoneButton(button, done, iniciada) {
            if (!button) return;
            if (done) {
                setStatusToggleVariant(button, 'done');
                button.innerHTML = '<i class="fas fa-check-circle"></i><span>Concluída</span>';
                button.title = 'Marcar como pendente';
            } else {
                setStatusToggleVariant(button, iniciada ? 'ready' : 'blocked');
                button.innerHTML = '<i class="fas fa-check-circle"></i><span>Concluir</span>';
                button.title = iniciada ? 'Marcar como concluída' : 'Marcar como concluída (necessário iniciar primeiro)';
            }
            button.disabled = !iniciada && !done;
        }

        function updateRowAppearance(etapaId, iniciada, done) {
            const tableRow = document.querySelector(`#etapas-tbody tr[data-etapa-id="${etapaId}"]`);
            if (tableRow) {
                tableRow.classList.remove('etapa-done', 'etapa-iniciada');
                const textElements = tableRow.querySelectorAll('.etapa-row-text');
                if (done) {
                    tableRow.classList.add('etapa-done');
                    textElements.forEach(el => el.classList.add('text-decoration-line-through', 'text-muted'));
                } else {
                    textElements.forEach(el => el.classList.remove('text-decoration-line-through', 'text-muted'));
                    if (iniciada) {
                        tableRow.classList.add('etapa-iniciada');
                    }
                }
            }
        }

        // Função para verificar se todas as etapas estão iniciadas e concluídas
        function verificarEAtualizarBotaoConcluir() {
            const btnConcluir = document.getElementById('btn-concluir-projeto');
            if (!btnConcluir) return; // Se o botão não existe, não faz nada

            // Pega todas as etapas da tabela
            const todasEtapas = document.querySelectorAll('.toggle-iniciada');
            const totalEtapas = parseInt(btnConcluir.dataset.totalEtapas) || todasEtapas.length;

            if (totalEtapas === 0) {
                // Se não há etapas, desabilita o botão
                btnConcluir.disabled = true;
                btnConcluir.title = 'O projeto não possui etapas';
                return;
            }

            // Verificar se todas as etapas estão iniciadas e concluídas
            let todasConcluidas = true;
            const etapasUnicas = new Set();

            todasEtapas.forEach(btn => {
                const etapaId = btn.dataset.etapaId;
                if (!etapasUnicas.has(etapaId)) {
                    etapasUnicas.add(etapaId);

                    // Verifica se a etapa está iniciada
                    const isIniciada = btn.dataset.state === 'started';

                    // Encontra o botão de concluída correspondente
                    const btnDone = btn.closest('tr')?.querySelector(`.toggle-done[data-etapa-id="${etapaId}"]`);
                    const isDone = btnDone?.dataset.state === 'done';

                    if (!isIniciada || !isDone) {
                        todasConcluidas = false;
                    }
                }
            });

            // Atualizar o estado do botão
            if (todasConcluidas && etapasUnicas.size === totalEtapas) {
                btnConcluir.disabled = false;
                btnConcluir.title = 'Concluir projeto';
            } else {
                btnConcluir.disabled = true;
                btnConcluir.title = 'Todas as etapas devem estar iniciadas e concluídas';
            }
        }

        if (tbody) {
            tbody.addEventListener('submit', async function (event) {
                const deleteForm = event.target.closest('form[data-etapa-delete-form]');
                if (!deleteForm || !tbody.contains(deleteForm)) {
                    return;
                }

                if (event.defaultPrevented) {
                    return;
                }

                event.preventDefault();

                const deleteButton = deleteForm.querySelector('[data-etapa-delete-btn]');
                const originalButtonHtml = deleteButton ? deleteButton.innerHTML : '';

                if (deleteButton) {
                    deleteButton.disabled = true;
                    deleteButton.innerHTML = '<i class="fas fa-spinner fa-spin" aria-hidden="true"></i>';
                }

                try {
                    const response = await fetch(deleteForm.action, {
                        method: 'POST',
                        headers: {
                            'X-Requested-With': 'XMLHttpRequest',
                            'Accept': 'application/json',
                            'X-CSRFToken': csrfToken
                        }
                    });

                    let data = null;
                    try {
                        data = await response.json();
                    } catch (error) {
                        data = null;
                    }

                    if (!response.ok || !data || !data.success) {
                        const errorMessage = data && data.message ? data.message : 'Erro ao excluir etapa.';
                        showAjaxFlashMessage(errorMessage, 'danger');
                        if (deleteButton) {
                            deleteButton.disabled = false;
                            deleteButton.innerHTML = originalButtonHtml;
                        }
                        return;
                    }

                    const row = deleteForm.closest('tr.etapa-draggable-row');
                    if (row) {
                        row.remove();
                    }

                    renumberEtapaRows();
                    refreshConcludeButtonCounters();

                    const remainingRows = tbody.querySelectorAll('tr.etapa-draggable-row').length;
                    if (remainingRows === 0) {
                        ensureInlineEmptyRowVisible();
                    }

                    showAjaxFlashMessage(data.message || 'Etapa excluída com sucesso.', 'success');
                } catch (error) {
                    console.error('Erro ao excluir etapa:', error);
                    showAjaxFlashMessage('Erro de comunicação ao excluir etapa.', 'danger');
                    if (deleteButton) {
                        deleteButton.disabled = false;
                        deleteButton.innerHTML = originalButtonHtml;
                    }
                }
            });

            tbody.addEventListener('click', function (event) {
                const iniciadaButton = event.target.closest('.toggle-iniciada');
                if (iniciadaButton && tbody.contains(iniciadaButton)) {
                    const etapaId = iniciadaButton.dataset.etapaId;

                    fetch(`/etapa/${etapaId}/toggle_iniciada`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/x-www-form-urlencoded',
                            'X-Requested-With': 'XMLHttpRequest',
                            'X-CSRFToken': csrfToken
                        }
                    })
                        .then(response => response.json())
                        .then(data => {
                            if (data.success) {
                                updateIniciadaButton(iniciadaButton, data.iniciada);

                                const commonAncestor = iniciadaButton.closest('tr.etapa-draggable-row');
                                if (commonAncestor) {
                                    const doneButton = commonAncestor.querySelector(`.toggle-done[data-etapa-id="${etapaId}"]`);
                                    if (doneButton) {
                                        updateDoneButton(doneButton, data.done, data.iniciada);
                                    }
                                }
                                updateRowAppearance(etapaId, data.iniciada, data.done);
                                if (data.message) {
                                    showAjaxFlashMessage(data.message, 'info');
                                } else {
                                    showAjaxFlashMessage(data.iniciada ? 'Iniciada.' : 'Não iniciada.', 'success');
                                }
                                verificarEAtualizarBotaoConcluir();
                            } else {
                                showAjaxFlashMessage(data.message || 'Erro ao atualizar etapa.', 'danger');
                            }
                        })
                        .catch(error => {
                            console.error('Erro ao alternar iniciada:', error);
                            showAjaxFlashMessage('Erro de comunicação com o servidor.', 'danger');
                        });
                    return;
                }

                const doneButton = event.target.closest('.toggle-done');
                if (doneButton && tbody.contains(doneButton)) {
                    if (doneButton.disabled) return;
                    const etapaId = doneButton.dataset.etapaId;

                    fetch(`/etapa/${etapaId}/toggle`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/x-www-form-urlencoded',
                            'X-Requested-With': 'XMLHttpRequest',
                            'X-CSRFToken': csrfToken
                        }
                    })
                        .then(response => response.json())
                        .then(data => {
                            if (data.success) {
                                updateDoneButton(doneButton, data.done, data.iniciada);
                                updateRowAppearance(etapaId, data.iniciada, data.done);
                                if (data.message) {
                                    showAjaxFlashMessage(data.message, 'info');
                                } else {
                                    showAjaxFlashMessage(data.done ? 'Concluída.' : 'Pendente.', 'success');
                                }
                                verificarEAtualizarBotaoConcluir();
                            } else {
                                showAjaxFlashMessage(data.message || 'Erro ao atualizar etapa.', data.success === false && data.message && data.message.includes("não foi iniciada") ? 'warning' : 'danger');
                            }
                        })
                        .catch(error => {
                            console.error('Erro ao alternar concluída:', error);
                            showAjaxFlashMessage('Erro de comunicação com o servidor.', 'danger');
                        });
                }
            });
        }

        // Verificar estado inicial do botão de concluir ao carregar a página
        verificarEAtualizarBotaoConcluir();
        syncImportModelButtonVisibility();

        // ===== EDIÇÃO INLINE DO PROJETO =====
        const editButton = document.querySelector('.btn-edit-project');
        const saveButton = document.querySelector('.btn-save-project');
        const cancelButton = document.querySelector('.btn-cancel-edit');
        const historyButton = document.querySelector('.btn-history');
        const concludeButton = document.querySelector('.btn-conclude-project');
        const projectMainHeader = document.getElementById('projectMainHeader');
        const projectCompactHeader = document.getElementById('projectCompactHeader');
        const projectHeaderSentinel = document.getElementById('projectHeaderSentinel');

        let compactHeaderObserver = null;
        let compactHeaderFallbackRaf = null;
        let compactHeaderPageReadyObserver = null;
        let compactHeaderTopnavResizeObserver = null;
        let compactHeaderTrackingStarted = false;
        let compactHeaderUsesFallback = false;
        let compactHeaderFallbackBound = false;

        function getTopNavOffset() {
            const topNav = document.querySelector('.app-topnav');
            if (!topNav) {
                return 74;
            }
            const navHeight = topNav.getBoundingClientRect().height || 64;
            return Math.round(navHeight + 8);
        }

        function syncCompactHeaderOffset() {
            const compactTop = getTopNavOffset();
            document.documentElement.style.setProperty('--project-compact-top', `${compactTop}px`);
            return compactTop;
        }

        function canUseCompactHeader() {
            if (!projectMainHeader || !projectCompactHeader || !projectHeaderSentinel) {
                return false;
            }
            if (window.innerWidth <= 991.98) {
                return false;
            }
            if (projectCompactHeader.classList.contains('is-hidden-by-edit')) {
                return false;
            }
            return true;
        }

        function forceCompactHeaderHidden() {
            if (!projectCompactHeader) {
                return;
            }
            projectCompactHeader.classList.remove('is-visible');
            projectCompactHeader.setAttribute('aria-hidden', 'true');
        }

        function setCompactHeaderVisible(shouldShow) {
            if (!projectCompactHeader) {
                return;
            }
            const visible = Boolean(shouldShow && canUseCompactHeader());
            projectCompactHeader.classList.toggle('is-visible', visible);
            projectCompactHeader.setAttribute('aria-hidden', visible ? 'false' : 'true');
        }

        function applyCompactHeaderVisibilityBySentinelState(sentinelIsIntersecting, compactTop) {
            if (typeof compactTop !== 'number') {
                syncCompactHeaderOffset();
            }
            setCompactHeaderVisible(!sentinelIsIntersecting);
        }

        function updateCompactHeaderBySentinelFallback() {
            if (!projectHeaderSentinel) {
                setCompactHeaderVisible(false);
                return;
            }
            const compactTop = syncCompactHeaderOffset();
            const sentinelRect = projectHeaderSentinel.getBoundingClientRect();
            const sentinelIsIntersecting = sentinelRect.bottom > compactTop && sentinelRect.top < window.innerHeight;
            applyCompactHeaderVisibilityBySentinelState(sentinelIsIntersecting, compactTop);
        }

        function requestFallbackUpdate() {
            if (compactHeaderFallbackRaf) {
                return;
            }
            compactHeaderFallbackRaf = window.requestAnimationFrame(() => {
                compactHeaderFallbackRaf = null;
                updateCompactHeaderBySentinelFallback();
            });
        }

        function bindFallbackScrollListener() {
            if (compactHeaderFallbackBound) {
                return;
            }
            window.addEventListener('scroll', requestFallbackUpdate, { passive: true });
            compactHeaderFallbackBound = true;
        }

        function unbindFallbackScrollListener() {
            if (!compactHeaderFallbackBound) {
                return;
            }
            window.removeEventListener('scroll', requestFallbackUpdate);
            compactHeaderFallbackBound = false;
        }

        function createIntersectionObserverTracking() {
            if (!('IntersectionObserver' in window) || !projectHeaderSentinel) {
                return false;
            }
            const compactTop = syncCompactHeaderOffset();
            compactHeaderObserver = new IntersectionObserver(
                (entries) => {
                    const entry = entries && entries[0];
                    if (!entry) {
                        return;
                    }
                    const offset = syncCompactHeaderOffset();
                    applyCompactHeaderVisibilityBySentinelState(entry.isIntersecting, offset);
                },
                {
                    root: null,
                    threshold: 0,
                    rootMargin: `-${compactTop}px 0px 0px 0px`,
                }
            );
            compactHeaderObserver.observe(projectHeaderSentinel);
            return true;
        }

        function destroyCompactHeaderTracking() {
            if (compactHeaderObserver) {
                compactHeaderObserver.disconnect();
                compactHeaderObserver = null;
            }
            unbindFallbackScrollListener();
            if (compactHeaderFallbackRaf) {
                window.cancelAnimationFrame(compactHeaderFallbackRaf);
                compactHeaderFallbackRaf = null;
            }
            if (compactHeaderTopnavResizeObserver) {
                compactHeaderTopnavResizeObserver.disconnect();
                compactHeaderTopnavResizeObserver = null;
            }
        }

        function refreshCompactHeaderTracking() {
            if (!compactHeaderTrackingStarted) {
                return;
            }
            destroyCompactHeaderTracking();
            compactHeaderUsesFallback = !createIntersectionObserverTracking();
            if (compactHeaderUsesFallback) {
                bindFallbackScrollListener();
                requestFallbackUpdate();
                return;
            }
            // Garantir estado correto sem aguardar o primeiro callback do observer.
            updateCompactHeaderBySentinelFallback();
        }

        function onViewportChanged() {
            if (!compactHeaderTrackingStarted) {
                return;
            }
            refreshCompactHeaderTracking();
        }

        function startCompactHeaderTracking() {
            if (compactHeaderTrackingStarted) {
                return;
            }
            compactHeaderTrackingStarted = true;
            setCompactHeaderVisible(false);
            refreshCompactHeaderTracking();
            window.addEventListener('resize', onViewportChanged);
            window.addEventListener('orientationchange', onViewportChanged);

            if ('ResizeObserver' in window) {
                const topNav = document.querySelector('.app-topnav');
                if (topNav) {
                    compactHeaderTopnavResizeObserver = new ResizeObserver(() => {
                        onViewportChanged();
                    });
                    compactHeaderTopnavResizeObserver.observe(topNav);
                }
            }
        }

        function waitForPageReadyAndStartCompactHeader() {
            forceCompactHeaderHidden();
            if (document.body.classList.contains('page-ready')) {
                window.requestAnimationFrame(() => {
                    window.requestAnimationFrame(() => {
                        startCompactHeaderTracking();
                    });
                });
                return;
            }

            compactHeaderPageReadyObserver = new MutationObserver(() => {
                if (!document.body.classList.contains('page-ready')) {
                    return;
                }
                if (compactHeaderPageReadyObserver) {
                    compactHeaderPageReadyObserver.disconnect();
                    compactHeaderPageReadyObserver = null;
                }
                window.requestAnimationFrame(() => {
                    window.requestAnimationFrame(() => {
                        startCompactHeaderTracking();
                    });
                });
            });
            compactHeaderPageReadyObserver.observe(document.body, {
                attributes: true,
                attributeFilter: ['class'],
            });
        }

        waitForPageReadyAndStartCompactHeader();

        window.addEventListener('pageshow', function (event) {
            if (!compactHeaderTrackingStarted) {
                return;
            }
            if (event.persisted) {
                forceCompactHeaderHidden();
                refreshCompactHeaderTracking();
            }
        });

        if (editButton) {
            editButton.addEventListener('click', function (e) {
                e.preventDefault();
                enterEditMode();
            });
        }

        if (saveButton) {
            saveButton.addEventListener('click', function (e) {
                e.preventDefault();
                saveProjectInline();
            });
        }

        if (cancelButton) {
            cancelButton.addEventListener('click', function (e) {
                e.preventDefault();
                exitEditMode();
            });
        }

        // Verificar se deve entrar em modo de edição automaticamente
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.get('edit') === 'true' && editButton) {
            // Entrar em modo de edição após a página carregar
            setTimeout(() => {
                enterEditMode();
                // Remover parâmetro da URL sem recarregar
                window.history.replaceState({}, document.title, window.location.pathname);
            }, 100);
        }

        async function enterEditMode() {
            if (projectCompactHeader) {
                projectCompactHeader.classList.add('is-hidden-by-edit');
                setCompactHeaderVisible(false);
            }

            // Mudar botões
            editButton.style.display = 'none';
            if (historyButton) historyButton.style.display = 'none';
            if (concludeButton) concludeButton.style.display = 'none';
            if (saveButton) {
                saveButton.classList.remove('ds-hidden');
                saveButton.style.display = 'inline-block';
            }
            if (cancelButton) {
                cancelButton.classList.remove('ds-hidden');
                cancelButton.style.display = 'inline-block';
            }

            // Esconder botão de voltar durante edição
            const backButton = document.querySelector('.btn-back-to-list');
            if (backButton) backButton.style.display = 'none';

            // Pré-carregar dados EEGG
            await loadEditData();

            // Guardar valores EEGG antes de processar
            const objetivoOriginal = document.querySelector('[data-field="objetivo_id"]')?.dataset.value;
            const resultadoOriginal = document.querySelector('[data-field="resultado_esperado_id"]')?.dataset.value;

            // Tornar campos editáveis
            for (const el of document.querySelectorAll('[data-field]:not([data-etapa-id])')) {
                const field = el.dataset.field;
                const currentValue = el.dataset.value || '';

                // Área responsável: admin ou usuário com múltiplas áreas pode editar
                if (field === 'area_responsavel' && !canEditAreaResponsavel) {
                    continue;
                }

                let input;

                // Objetivo
                if (field === 'objetivo_id') {
                    input = await createObjetivoSelect(currentValue);
                }
                // Resultado
                else if (field === 'resultado_esperado_id') {
                    input = await createResultadoSelect(currentValue, objetivoOriginal);
                }
                // Indicadores
                else if (field === 'indicadores_ids') {
                    let ids = [];
                    try {
                        ids = JSON.parse(currentValue || '[]');
                    } catch (e) {
                        ids = [];
                    }
                    input = await createIndicadoresContainer(ids, resultadoOriginal);
                }
                // Campos com select especial
                else if (field === 'status' || field === 'prioridade' || field === 'special_project' || field === 'delivery_type') {
                    input = createSelectForField(field, currentValue);
                }
                else if (field === 'abep_indicator') {
                    input = createAbepIndicatorCombobox(currentValue);
                }
                // Área responsável - dropdown com áreas
                else if (field === 'area_responsavel') {
                    input = createAreaSelect(currentValue);
                }
                // Observação - textarea
                else if (field === 'observacao') {
                    input = document.createElement('textarea');
                    input.className = 'form-control form-control-sm';
                    input.rows = 3;
                    input.value = currentValue === 'Nenhuma observação registrada.' ? '' : (currentValue || '');
                    input.placeholder = 'Nenhuma observação registrada.';
                }
                // Descrição curta - textarea pequena
                else if (field === 'short_description') {
                    input = document.createElement('textarea');
                    input.className = 'form-control form-control-sm project-inline-input project-inline-input-description';
                    input.rows = 2;
                    input.value = currentValue || '';
                    input.placeholder = 'Adicione uma descrição...';
                }


                // Título - input maior
                else if (field === 'titulo') {
                    input = document.createElement('input');
                    input.type = 'text';
                    input.className = 'form-control form-control-sm project-inline-input project-inline-input-title';
                    input.value = currentValue;
                    input.placeholder = 'Nome do projeto';
                }
                // Campos de texto normais (órgão, processo SEI, github, documentação, etc.)
                else {
                    input = document.createElement('input');
                    input.type = 'text';
                    input.className = 'form-control form-control-sm';
                    input.value = currentValue || '';
                    if (!currentValue || String(currentValue).trim() === '') {
                        input.placeholder = 'Não informado';
                    }
                }

                if (input) {
                    input.dataset.field = field;
                    input.dataset.originalValue = currentValue;
                    el.replaceWith(input);
                }
            }
        }



        function createAreaSelect(currentValue) {
            const select = document.createElement('select');
            select.className = 'form-select form-select-sm';
            select.dataset.field = 'area_responsavel';
            select.dataset.originalValue = currentValue;

            // Admin vê todas as áreas, não-admin vê apenas suas áreas
            const areas = availableAreas;

            areas.forEach(area => {
                const option = document.createElement('option');
                option.value = area;
                option.textContent = area;
                if (area === currentValue) {
                    option.selected = true;
                }
                select.appendChild(option);
            });

            return select;
        }

        // Variáveis globais para dados EEGG
        let editDataCache = null;
        const ABEP_INDICADORES_OPTIONS = abepIndicatorsOptions;

        function findAbepIndicatorOption(value) {
            const normalizedValue = String(value || '').trim();
            if (!normalizedValue) {
                return null;
            }
            return ABEP_INDICADORES_OPTIONS.find(item => (
                item.value === normalizedValue || item.label === normalizedValue
            )) || null;
        }

        function createAbepIndicatorCombobox(currentValue) {
            const wrapper = document.createElement('div');
            wrapper.className = 'project-detail-abep-combobox';
            wrapper.dataset.field = 'abep_indicator';
            wrapper.dataset.originalValue = currentValue || '';
            wrapper.innerHTML = `
                <input
                    type="text"
                    class="project-detail-abep-input form-control form-control-sm"
                    placeholder="Busque por número ou título..."
                    autocomplete="off"
                    role="combobox"
                    aria-expanded="false"
                    aria-haspopup="listbox">
                <input type="hidden" class="project-detail-abep-hidden">
            `;

            const input = wrapper.querySelector('.project-detail-abep-input');
            const hiddenInput = wrapper.querySelector('.project-detail-abep-hidden');
            const dropdown = document.createElement('div');
            dropdown.className = 'project-detail-abep-dropdown';
            dropdown.setAttribute('role', 'listbox');
            dropdown.setAttribute('hidden', '');
            document.body.appendChild(dropdown);
            const emptyState = document.createElement('div');
            emptyState.className = 'project-detail-abep-option project-detail-abep-empty';
            emptyState.hidden = true;
            emptyState.textContent = 'Nenhum indicador encontrado';

            Object.defineProperty(wrapper, 'value', {
                configurable: true,
                get() {
                    return hiddenInput.value || '';
                },
                set(nextValue) {
                    hiddenInput.value = nextValue || '';
                },
            });

            const optionNodes = ABEP_INDICADORES_OPTIONS.map(item => {
                const option = document.createElement('div');
                option.className = 'project-detail-abep-option';
                option.dataset.value = item.value;
                option.dataset.label = item.label;
                option.setAttribute('role', 'option');
                option.textContent = item.label;
                dropdown.appendChild(option);
                return option;
            });
            dropdown.appendChild(emptyState);

            function syncSelectedValue(nextValue) {
                wrapper.value = nextValue || '';
            }

            function clearActiveOption() {
                optionNodes.forEach(option => option.classList.remove('active'));
            }

            function getVisibleOptions() {
                return optionNodes.filter(option => !option.classList.contains('hidden-by-filter'));
            }

            function filterOptions() {
                const searchTerm = (input.value || '').trim().toLowerCase();
                let visibleCount = 0;

                optionNodes.forEach(option => {
                    const label = (option.dataset.label || '').toLowerCase();
                    const value = (option.dataset.value || '').toLowerCase();
                    const matches = !searchTerm || label.includes(searchTerm) || value.includes(searchTerm);
                    option.classList.toggle('hidden-by-filter', !matches);
                    option.classList.remove('active');
                    if (matches) {
                        visibleCount += 1;
                    }
                });

                emptyState.hidden = visibleCount > 0;
            }

            function updateDropdownPlacement() {
                const rect = input.getBoundingClientRect();
                const maxWidth = Math.max(220, window.innerWidth - 24);
                const width = Math.min(Math.max(rect.width, 280), maxWidth);
                const left = Math.max(12, Math.min(rect.left, window.innerWidth - width - 12));
                const availableBelow = Math.max(96, window.innerHeight - rect.bottom - 16);

                dropdown.style.left = `${left}px`;
                dropdown.style.top = `${rect.bottom + 4}px`;
                dropdown.style.width = `${width}px`;
                dropdown.style.maxHeight = `${Math.min(220, availableBelow)}px`;
            }

            function showDropdown() {
                filterOptions();
                updateDropdownPlacement();
                dropdown.removeAttribute('hidden');
                input.setAttribute('aria-expanded', 'true');
            }

            function hideDropdown() {
                dropdown.setAttribute('hidden', '');
                input.setAttribute('aria-expanded', 'false');
                clearActiveOption();
            }

            function selectOption(option) {
                syncSelectedValue(option.dataset.value || '');
                input.value = option.dataset.label || option.textContent || '';
                hideDropdown();
            }

            const currentOption = findAbepIndicatorOption(currentValue);
            syncSelectedValue(currentOption ? currentOption.value : (currentValue || ''));
            input.value = currentOption ? currentOption.label : (currentValue || '');

            input.addEventListener('focus', showDropdown);
            input.addEventListener('click', showDropdown);
            input.addEventListener('input', function () {
                syncSelectedValue('');
                showDropdown();
            });

            input.addEventListener('keydown', function (event) {
                if (event.key === 'Escape') {
                    hideDropdown();
                    return;
                }

                const visibleOptions = getVisibleOptions();
                if (!visibleOptions.length) {
                    if (event.key === 'Enter') {
                        event.preventDefault();
                    }
                    return;
                }

                if (event.key === 'ArrowDown') {
                    event.preventDefault();
                    const activeOption = dropdown.querySelector('.project-detail-abep-option.active');
                    let index = visibleOptions.indexOf(activeOption);
                    index = index < 0 ? 0 : Math.min(index + 1, visibleOptions.length - 1);
                    clearActiveOption();
                    visibleOptions[index].classList.add('active');
                    visibleOptions[index].scrollIntoView({ block: 'nearest' });
                    return;
                }

                if (event.key === 'ArrowUp') {
                    event.preventDefault();
                    const activeOption = dropdown.querySelector('.project-detail-abep-option.active');
                    let index = visibleOptions.indexOf(activeOption);
                    index = index < 0 ? visibleOptions.length - 1 : Math.max(index - 1, 0);
                    clearActiveOption();
                    visibleOptions[index].classList.add('active');
                    visibleOptions[index].scrollIntoView({ block: 'nearest' });
                    return;
                }

                if (event.key === 'Enter') {
                    const activeOption = dropdown.querySelector('.project-detail-abep-option.active');
                    if (activeOption && !activeOption.classList.contains('hidden-by-filter')) {
                        event.preventDefault();
                        selectOption(activeOption);
                    }
                }
            });

            optionNodes.forEach(option => {
                option.addEventListener('mousedown', function (event) {
                    event.preventDefault();
                });
                option.addEventListener('click', function () {
                    selectOption(option);
                });
            });

            document.addEventListener('click', function (event) {
                if (!wrapper.contains(event.target) && !dropdown.contains(event.target)) {
                    hideDropdown();
                }
            });

            window.addEventListener('resize', function () {
                if (!dropdown.hasAttribute('hidden')) {
                    updateDropdownPlacement();
                }
            });

            window.addEventListener('scroll', function () {
                if (!dropdown.hasAttribute('hidden')) {
                    updateDropdownPlacement();
                }
            }, true);

            input.addEventListener('blur', function () {
                setTimeout(function () {
                    if (!wrapper.contains(document.activeElement) && !dropdown.contains(document.activeElement)) {
                        hideDropdown();
                    }
                }, 120);
            });

            return wrapper;
        }

        async function loadEditData() {
            if (editDataCache) return editDataCache;

            try {
                const response = await fetch(`/project/${projectIdValue}/edit_data`);
                const data = await response.json();
                if (data.success) {
                    editDataCache = data;
                    return data;
                }
            } catch (error) {
                console.error('Erro ao carregar dados:', error);
            }
            return null;
        }

        async function createObjetivoSelect(currentValue) {
            const data = await loadEditData();
            if (!data) return null;

            const select = document.createElement('select');
            select.className = 'form-select form-select-sm';
            select.dataset.field = 'objetivo_id';
            select.dataset.originalValue = currentValue;
            select.id = 'edit_objetivo_select';

            const emptyOption = document.createElement('option');
            emptyOption.value = '';
            emptyOption.textContent = 'Selecione um objetivo';
            select.appendChild(emptyOption);

            data.objetivos.forEach(obj => {
                const option = document.createElement('option');
                option.value = obj.id;
                option.textContent = obj.descricao;
                if (obj.id == currentValue) {
                    option.selected = true;
                }
                select.appendChild(option);
            });

            // Event listener para carregar resultados APENAS quando usuário mudar manualmente
            select.addEventListener('change', function (e) {
                // Limpa resultado e indicadores APENAS se usuário trocou o objetivo
                const resultadoEl = document.querySelector('[data-field="resultado_esperado_id"]');
                const indicadoresEl = document.querySelector('[data-field="indicadores_ids"]');

                if (resultadoEl && resultadoEl.tagName === 'SELECT') {
                    resultadoEl.innerHTML = '<option value="">Carregando...</option>';
                }
                if (indicadoresEl) {
                    indicadoresEl.innerHTML = '<p class="text-muted mb-0 small">Selecione um resultado para ver indicadores</p>';
                }

                updateResultadoSelect(this.value);
            });

            return select;
        }

        async function updateResultadoSelect(objetivoId, preserveValue = false) {
            const data = await loadEditData();
            if (!data) return;

            const resultadoEl = document.querySelector('[data-field="resultado_esperado_id"]');
            if (!resultadoEl || !resultadoEl.tagName || resultadoEl.tagName !== 'SELECT') return;

            const resultadoSelect = resultadoEl;
            const currentValue = preserveValue ? resultadoSelect.dataset.originalValue : null;

            resultadoSelect.innerHTML = '<option value="">Selecione um resultado esperado</option>';

            if (objetivoId && data.resultados_por_objetivo[objetivoId]) {
                data.resultados_por_objetivo[objetivoId].forEach(res => {
                    const option = document.createElement('option');
                    option.value = res.id;
                    option.textContent = res.descricao;
                    resultadoSelect.appendChild(option);
                });
            }

            // Limpar indicadores APENAS se não estamos preservando valores
            if (!preserveValue) {
                updateIndicadoresContainer(null);
            }
        }

        async function createResultadoSelect(currentValue, objetivoId) {
            const data = await loadEditData();
            if (!data) return null;

            const select = document.createElement('select');
            select.className = 'form-select form-select-sm';
            select.dataset.field = 'resultado_esperado_id';
            select.dataset.originalValue = currentValue;
            select.id = 'edit_resultado_select';

            const emptyOption = document.createElement('option');
            emptyOption.value = '';
            emptyOption.textContent = 'Selecione um resultado esperado';
            select.appendChild(emptyOption);

            if (objetivoId && data.resultados_por_objetivo[objetivoId]) {
                data.resultados_por_objetivo[objetivoId].forEach(res => {
                    const option = document.createElement('option');
                    option.value = res.id;
                    option.textContent = res.descricao;
                    if (res.id == currentValue) {
                        option.selected = true;
                    }
                    select.appendChild(option);
                });
            }

            // Event listener para carregar indicadores APENAS quando usuário mudar manualmente
            select.addEventListener('change', function (e) {
                // Limpa indicadores APENAS se usuário trocou o resultado
                const indicadoresEl = document.querySelector('[data-field="indicadores_ids"]');
                if (indicadoresEl) {
                    indicadoresEl.innerHTML = '<p class="text-muted mb-0 small">Carregando...</p>';
                }

                updateIndicadoresContainer(this.value, false);
            });

            return select;
        }

        async function updateIndicadoresContainer(resultadoId, preserveSelection = false) {
            const data = await loadEditData();
            if (!data) return;

            const indicadoresEl = document.querySelector('[data-field="indicadores_ids"]');
            if (!indicadoresEl) return;

            // Preserva seleção anterior se necessário
            let selectedIds = [];
            if (preserveSelection) {
                try {
                    selectedIds = JSON.parse(indicadoresEl.dataset.originalValue || '[]');
                } catch (e) {
                    selectedIds = [];
                }
            }

            indicadoresEl.innerHTML = '';

            if (resultadoId && data.indicadores_por_resultado[resultadoId]) {
                data.indicadores_por_resultado[resultadoId].forEach(ind => {
                    const div = document.createElement('div');
                    div.className = 'form-check form-check-sm';

                    const checkbox = document.createElement('input');
                    checkbox.type = 'checkbox';
                    checkbox.className = 'form-check-input indicador-checkbox';
                    checkbox.value = ind.id;
                    checkbox.id = `ind_${ind.id}`;

                    // Marca checkbox se estava selecionado antes
                    if (preserveSelection && selectedIds.includes(ind.id)) {
                        checkbox.checked = true;
                    }

                    const label = document.createElement('label');
                    label.className = 'form-check-label';
                    label.htmlFor = `ind_${ind.id}`;
                    label.style.fontSize = '0.75rem';
                    label.textContent = ind.descricao;

                    div.appendChild(checkbox);
                    div.appendChild(label);
                    indicadoresEl.appendChild(div);
                });
            } else {
                indicadoresEl.innerHTML = '<p class="text-muted mb-0 small">Selecione um resultado para ver indicadores</p>';
            }
        }

        async function createIndicadoresContainer(currentValue, resultadoId) {
            const data = await loadEditData();
            if (!data) return null;

            const container = document.createElement('div');
            container.dataset.field = 'indicadores_ids';
            container.dataset.originalValue = JSON.stringify(currentValue);

            if (resultadoId && data.indicadores_por_resultado[resultadoId]) {
                let selectedIds = currentValue;
                if (typeof selectedIds === 'string') {
                    try {
                        selectedIds = JSON.parse(selectedIds);
                    } catch (e) {
                        selectedIds = [];
                    }
                }

                data.indicadores_por_resultado[resultadoId].forEach(ind => {
                    const div = document.createElement('div');
                    div.className = 'form-check form-check-sm';

                    const checkbox = document.createElement('input');
                    checkbox.type = 'checkbox';
                    checkbox.className = 'form-check-input indicador-checkbox';
                    checkbox.value = ind.id;
                    checkbox.id = `ind_${ind.id}`;
                    if (selectedIds && selectedIds.includes(ind.id)) {
                        checkbox.checked = true;
                    }

                    const label = document.createElement('label');
                    label.className = 'form-check-label';
                    label.htmlFor = `ind_${ind.id}`;
                    label.style.fontSize = '0.75rem';
                    label.textContent = ind.descricao;

                    div.appendChild(checkbox);
                    div.appendChild(label);
                    container.appendChild(div);
                });
            } else {
                container.innerHTML = '<p class="text-muted mb-0 small">Selecione um resultado para ver indicadores</p>';
            }

            return container;
        }

        function createSelectForField(field, currentValue) {
            const select = document.createElement('select');
            select.className = 'form-select form-select-sm';
            select.dataset.field = field;
            select.dataset.originalValue = currentValue;

            let options = [];
            if (field === 'status') {
                options = [
                    { value: 'Vigente', label: 'Vigente' },
                    { value: 'Finalizado', label: 'Finalizado' },
                    { value: 'Suspenso', label: 'Suspenso' }
                ];
            } else if (field === 'prioridade') {
                options = [
                    { value: 'urgente', label: 'Urgente' },
                    { value: 'alta', label: 'Alta' },
                    { value: 'media', label: 'Média' },
                    { value: 'baixa', label: 'Baixa' }
                ];
            } else if (field === 'special_project') {
                options = [
                    { value: '', label: 'Nenhum' },
                    { value: 'ABEP', label: 'ABEP' },
                    { value: 'TCE', label: 'TCE' }
                ];
            } else if (field === 'delivery_type') {
                options = [
                    { value: '', label: 'Não informado' },
                    { value: 'Sistema', label: 'Sistema' },
                    { value: 'Painel', label: 'Painel' },
                    { value: 'Norma', label: 'Norma' },
                    { value: 'Instrumento de parceria', label: 'Instrumento de parceria' },
                    { value: 'Fluxo Processual', label: 'Fluxo Processual' },
                    { value: 'Outro', label: 'Outro' }
                ];
            }

            options.forEach(opt => {
                const option = document.createElement('option');
                option.value = opt.value;
                option.textContent = opt.label;
                if (opt.value === currentValue || (opt.label === currentValue)) {
                    option.selected = true;
                }
                select.appendChild(option);
            });

            return select;
        }

        function saveProjectInline() {
            const formData = {};

            // Coletar dados dos campos editáveis
            document.querySelectorAll('[data-field]:not([data-etapa-id])').forEach(el => {
                const field = el.dataset.field;

                // Indicadores - coletar checkboxes marcados
                if (field === 'indicadores_ids') {
                    const checkboxes = el.querySelectorAll('.indicador-checkbox:checked');
                    formData[field] = Array.from(checkboxes).map(cb => parseInt(cb.value));
                }
                // Outros campos
                else if (el.value !== undefined) {
                    formData[field] = el.value || null;
                }
            });

            // Desabilitar botões durante salvamento
            saveButton.disabled = true;
            cancelButton.disabled = true;
            saveButton.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Salvando...';

            fetch(`/project/${projectIdValue}/update_inline`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify(formData)
            })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        showAjaxFlashMessage(data.message || 'Projeto atualizado com sucesso!', 'success');
                        // Recarregar a página para mostrar os dados atualizados
                        setTimeout(() => {
                            window.location.reload();
                        }, 1000);
                    } else {
                        showAjaxFlashMessage(data.message || 'Erro ao atualizar projeto.', 'danger');
                        saveButton.disabled = false;
                        cancelButton.disabled = false;
                        saveButton.innerHTML = '<i class="fas fa-save me-1"></i>Salvar';
                    }
                })
                .catch(error => {
                    console.error('Erro:', error);
                    showAjaxFlashMessage('Erro de comunicação com o servidor.', 'danger');
                    saveButton.disabled = false;
                    cancelButton.disabled = false;
                    saveButton.innerHTML = '<i class="fas fa-save me-1"></i>Salvar';
                });
        }

        function exitEditMode() {
            // Simplesmente recarregar a página para voltar ao estado original
            window.location.reload();
        }
    });

    // ============================================
    // IMPORTAR MODELO - Modal JavaScript
    // ============================================
