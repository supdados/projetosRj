(function () {
    const projectDetailConfig = window.__PROJECT_DETAIL_CONFIG__ || {};
    const page = window.ProjectDetailPage || {};

    page.config = projectDetailConfig;
    page.shared = page.shared || {};
    page.state = page.state || {};
    page.refs = page.refs || {};
    page._initQueue = page._initQueue || [];
    page._initRegistry = page._initRegistry || {};

    page.registerInit = function registerInit(name, fn) {
        if (!name || typeof fn !== 'function' || page._initRegistry[name]) {
            return;
        }
        page._initRegistry[name] = true;
        page._initQueue.push({ name: name, fn: fn });
    };

    window.ProjectDetailPage = page;

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

    function formatMeetingDateTimeRange(eventData) {
        const startsAt = eventData && eventData.starts_at ? new Date(eventData.starts_at) : null;
        const endsAt = eventData && eventData.ends_at ? new Date(eventData.ends_at) : null;
        if (!startsAt || !endsAt || Number.isNaN(startsAt.getTime()) || Number.isNaN(endsAt.getTime())) {
            return 'Data não disponível';
        }

        const sameDay = startsAt.toDateString() === endsAt.toDateString();
        const dateFmt = function (dt) {
            return dt.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric' });
        };
        const timeFmt = function (dt) {
            return dt.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
        };

        if (eventData.is_all_day) {
            if (sameDay) {
                return `${dateFmt(startsAt)} · Dia inteiro`;
            }
            return `${dateFmt(startsAt)} até ${dateFmt(endsAt)} · Dia inteiro`;
        }
        if (sameDay) {
            return `${dateFmt(startsAt)} · ${timeFmt(startsAt)} - ${timeFmt(endsAt)}`;
        }
        return `${dateFmt(startsAt)} ${timeFmt(startsAt)} até ${dateFmt(endsAt)} ${timeFmt(endsAt)}`;
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

    function buildMeetingDateDisplay(dateDisplay, timeDisplay) {
        const safeDateDisplay = String(dateDisplay || 'Sem data').trim() || 'Sem data';
        const safeTimeDisplay = String(timeDisplay || '').trim();
        if (safeDateDisplay === 'Sem data' || !safeTimeDisplay) {
            return safeDateDisplay;
        }
        return `${safeDateDisplay} ${safeTimeDisplay}`;
    }

    function updateDateFieldDisplay(target, rawValue, displayValue) {
        const hasValue = Boolean((rawValue || '').trim());
        const emptyDisplay = target && target.dataset ? (target.dataset.emptyDisplay || 'Sem data') : 'Sem data';
        let resolvedDisplay = hasValue ? String(displayValue || '').trim() : emptyDisplay;
        if (hasValue && target && target.closest('tr.etapa-draggable-row') && target.closest('tr.etapa-draggable-row').dataset.entryType === 'google_meeting') {
            resolvedDisplay = buildMeetingDateDisplay(resolvedDisplay, target.dataset.timeDisplay || '');
        }
        updateEditableFieldDisplay(target, hasValue, resolvedDisplay, emptyDisplay);
    }

    function buildStageDatesLabel(row) {
        if (!row) {
            return 'Etapa sem datas definidas';
        }
        const startField = row.querySelector('.editable-field[data-field="data_inicio"]');
        const endField = row.querySelector('.editable-field[data-field="data_fim"]');
        const startRaw = startField ? String(startField.dataset.originalValue || '').trim() : '';
        const endRaw = endField ? String(endField.dataset.originalValue || '').trim() : '';
        const startDisplay = startField ? String(startField.textContent || '').trim() : '';
        const endDisplay = endField ? String(endField.textContent || '').trim() : '';

        if (startRaw && endRaw) {
            return `${startDisplay} — ${endDisplay}`;
        }
        if (startRaw) {
            return `Início ${startDisplay}`;
        }
        if (endRaw) {
            return `Fim ${endDisplay}`;
        }
        return 'Etapa sem datas definidas';
    }

    function syncStageQuickAddTriggerFromRow(row) {
        if (!row) {
            return;
        }

        const trigger = row.querySelector('[data-stage-quick-add-trigger]');
        if (!trigger) {
            return;
        }

        const descricaoField = row.querySelector('.editable-field[data-field="descricao"]');
        const descricao = descricaoField ? String(descricaoField.textContent || '').trim() : '';

        trigger.setAttribute('data-etapa-descricao', descricao || 'Etapa');
        trigger.setAttribute('data-etapa-datas', buildStageDatesLabel(row));
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

    function getTopNavOffset() {
        const topNav = document.querySelector('.app-topnav');
        if (!topNav) {
            return 74;
        }
        const navHeight = topNav.getBoundingClientRect().height || 64;
        return Math.round(navHeight + 8);
    }

    function getEtapaRows() {
        const tbody = page.refs.tbody;
        return tbody ? Array.from(tbody.querySelectorAll('tr.etapa-draggable-row')) : [];
    }

    function getWorkflowStageRows() {
        return getEtapaRows().filter(row => row.dataset.entryType !== 'google_meeting');
    }

    function formatEtapaOrder(index) {
        const projectIdPrefix = String(projectDetailConfig.projectId || '');
        return projectIdPrefix ? `${projectIdPrefix}.${index}` : String(index);
    }

    function syncInlineOrderPreview() {
        const inlineOrderPreview = document.getElementById('etapaInlineOrderPreview');
        if (!inlineOrderPreview) {
            return;
        }
        inlineOrderPreview.textContent = formatEtapaOrder(getEtapaRows().length + 1);
    }

    function renumberEtapaRows() {
        const tbody = page.refs.tbody;
        if (!tbody) {
            return;
        }
        const rows = tbody.querySelectorAll('tr.etapa-draggable-row');
        rows.forEach((row, index) => {
            const numeroCelula = row.querySelector('.etapa-order-cell');
            if (numeroCelula) {
                numeroCelula.textContent = formatEtapaOrder(index + 1);
            }
        });
        syncInlineOrderPreview();
    }

    function ensureInlineComposerVisible() {
        const inlineAddFormRow = page.refs.inlineAddFormRow;
        if (!inlineAddFormRow) {
            return;
        }

        const rect = inlineAddFormRow.getBoundingClientRect();
        const topPadding = getTopNavOffset() + 12;
        const bottomPadding = 24;
        let targetTop = null;

        if (rect.top < topPadding) {
            targetTop = window.scrollY + rect.top - topPadding;
        } else if (rect.bottom > window.innerHeight - bottomPadding) {
            targetTop = window.scrollY + rect.bottom - window.innerHeight + bottomPadding;
        }

        if (targetTop === null) {
            return;
        }

        window.scrollTo({
            top: Math.max(0, Math.round(targetTop)),
            behavior: 'auto'
        });
    }

    function syncImportModelButtonVisibility() {
        const btnImportModel = page.refs.btnImportModel;
        const tbody = page.refs.tbody;
        if (!btnImportModel || !tbody) {
            return;
        }

        const totalRows = getWorkflowStageRows().length;
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

    function showAjaxFlashMessage(message, type) {
        if (typeof window.showFlash === 'function') {
            window.showFlash(message, type || 'info');
        }
    }

    function buildEtapaCommentHtml(etapaId, comentarios) {
        const hasComment = Boolean((comentarios || '').trim());
        if (hasComment) {
            return `
                <div class="small text-muted etapa-comentario-display ds-cursor-pointer" data-etapa-id="${etapaId}" title="Clique para editar">
                    ${escapeHtml(comentarios)}
                </div>
            `;
        }
        if (!page.shared.canEditEtapas) {
            return '';
        }
        return `
            <div class="small text-muted etapa-comentario-placeholder ds-cursor-pointer" data-etapa-id="${etapaId}" data-comentario="">
                <i class="fas fa-comment-medical me-1"></i> adicionar comentário
            </div>
        `;
    }

    function buildMeetingDateHtml(rawValue, displayValue, timeDisplay, meetingInfo) {
        const hasValue = Boolean((rawValue || '').trim());
        const safeDisplay = escapeHtml(buildMeetingDateDisplay(displayValue || 'Sem data', timeDisplay || ''));
        const syncStatus = String(meetingInfo && meetingInfo.sync_status || '').trim();
        const tooltip = syncStatus === 'error'
            ? (meetingInfo && meetingInfo.sync_error) || 'Evento indisponível no Google Calendar.'
            : 'Clique para abrir os detalhes da reunião.';

        return `
            <span class="etapa-meeting-readonly-field${hasValue ? '' : ' editable-field-empty'}" title="${escapeHtml(tooltip)}">${safeDisplay}</span>
        `;
    }

    function buildMeetingEventData(etapaPayload) {
        const meetingInfo = etapaPayload && etapaPayload.meeting ? etapaPayload.meeting : {};
        return {
            id: etapaPayload ? etapaPayload.id : null,
            title: meetingInfo.title || (etapaPayload && etapaPayload.descricao) || 'Reunião sem título',
            description: meetingInfo.description || '',
            location: meetingInfo.location || '',
            starts_at: meetingInfo.starts_at || '',
            ends_at: meetingInfo.ends_at || '',
            meet_link: meetingInfo.meet_link || '',
            is_all_day: Boolean(meetingInfo.is_all_day),
            owner_email: meetingInfo.owner_email || (etapaPayload && etapaPayload.responsavel) || 'Conta Google vinculada',
            sync_status: meetingInfo.sync_status || 'pending',
            sync_error: meetingInfo.sync_error || '',
            can_manage: Boolean(meetingInfo.can_manage),
            can_edit: Boolean(meetingInfo.can_edit),
        };
    }

    function getMeetingEventDataFromRow(row) {
        if (!row) {
            return null;
        }
        if (row._meetingEventData) {
            return row._meetingEventData;
        }
        const rawPayload = row.dataset.meetingEvent || '';
        if (!rawPayload) {
            return null;
        }
        try {
            row._meetingEventData = JSON.parse(rawPayload);
            return row._meetingEventData;
        } catch (error) {
            console.error('Erro ao ler payload da reunião do projeto:', error);
            return null;
        }
    }

    function buildMeetingActionHtml(etapaId, meetingInfo) {
        if (meetingInfo && meetingInfo.can_manage) {
            return `
                <form action="/etapa/${etapaId}/delete" method="post" class="inline-form" data-etapa-delete-form
                    data-confirm="Tem certeza que deseja excluir esta reunião?">
                    <button type="submit" class="btn btn-sm btn-floating" data-etapa-delete-btn title="Excluir reunião">
                        <i class="fas fa-trash"></i>
                    </button>
                </form>
            `;
        }

        return `
            <span class="btn btn-sm btn-floating etapa-meeting-action-lock" title="Somente a mesma conta Google conectada pode excluir esta reunião.">
                <i class="fas fa-lock"></i>
            </span>
        `;
    }

    function buildGoogleMeetingRow(etapaPayload) {
        const etapaId = etapaPayload.id;
        const descricao = etapaPayload.descricao || 'Reunião sem título';
        const responsavel = etapaPayload.responsavel || '';
        const dataInicio = etapaPayload.data_inicio || '';
        const dataInicioDisplay = getDateDisplayValue(dataInicio, etapaPayload.data_inicio_display || '');
        const dataFim = etapaPayload.data_fim || '';
        const dataFimDisplay = getDateDisplayValue(dataFim, etapaPayload.data_fim_display || '');
        const meetingInfo = etapaPayload.meeting || {};
        const ownerEmail = meetingInfo.owner_email || responsavel || 'Conta Google vinculada';
        const meetLinkHtml = meetingInfo.meet_link
            ? `
                <a href="${escapeHtml(meetingInfo.meet_link)}" target="_blank" rel="noopener noreferrer" class="btn btn-sm btn-floating etapa-meeting-action-btn" title="Abrir Meet">
                    <i class="fas fa-video"></i>
                </a>
            `
            : '';
        const startTimeDisplay = meetingInfo.start_time_display || '';
        const endTimeDisplay = meetingInfo.end_time_display || '';

        const row = document.createElement('tr');
        row.className = `etapa-draggable-row etapa-row-google-meeting${meetingInfo.sync_status === 'error' ? ' etapa-row-google-meeting-error' : ''}`;
        row.dataset.etapaId = String(etapaId);
        row.dataset.entryType = 'google_meeting';
        row.dataset.workflowStage = 'false';
        row.dataset.meetingSyncStatus = meetingInfo.sync_status || 'pending';
        row.dataset.meetingEvent = JSON.stringify(buildMeetingEventData(etapaPayload));
        row._meetingEventData = buildMeetingEventData(etapaPayload);

        row.innerHTML = `
            <td class="drag-handle etapa-drag-handle etapa-v4-cell-drag etapa-meeting-drag-cell" draggable="true">
                <i class="fab fa-google etapa-meeting-drag-icon"></i>
            </td>
            <td class="etapa-order-cell etapa-v4-cell-number"></td>
            <td class="etapa-descricao etapa-row-text etapa-v4-cell-description etapa-meeting-description-cell">
                <div class="etapa-descricao-main">
                    <span class="etapa-descricao">${escapeHtml(descricao)}</span>
                </div>
                <div class="etapa-meeting-owner" title="${escapeHtml(ownerEmail)}">
                    <i class="far fa-user" aria-hidden="true"></i>
                    <span>${escapeHtml(ownerEmail)}</span>
                </div>
                <button class="btn-comment-data ds-hidden" data-etapa-id="${etapaId}" data-comentario=""></button>
            </td>
            <td class="etapa-row-text etapa-v4-cell-date etapa-meeting-date-cell">
                ${buildMeetingDateHtml(dataInicio, dataInicioDisplay, startTimeDisplay, meetingInfo)}
            </td>
            <td class="etapa-row-text etapa-v4-cell-date etapa-meeting-date-cell">
                ${buildMeetingDateHtml(dataFim, dataFimDisplay, endTimeDisplay, meetingInfo)}
            </td>
            <td class="etapa-row-text etapa-v4-cell-responsavel text-muted small">-</td>
            <td class="text-center etapa-v4-cell-status text-muted small">-</td>
            <td class="text-center etapa-v4-cell-status text-muted small">-</td>
            <td class="actions text-center etapa-v4-actions-cell">
                <div class="etapa-meeting-actions">
                    ${meetLinkHtml}
                    ${buildMeetingActionHtml(etapaId, meetingInfo)}
                </div>
            </td>
        `;
        return row;
    }

    function buildEtapaRow(etapaPayload) {
        if (String(etapaPayload && etapaPayload.entry_type || 'manual') === 'google_meeting') {
            return buildGoogleMeetingRow(etapaPayload);
        }

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
        ].filter(Boolean).join(' ');

        const row = document.createElement('tr');
        row.className = rowClasses;
        row.dataset.etapaId = String(etapaId);
        row.dataset.entryType = 'manual';
        row.dataset.workflowStage = 'true';

        const doneButtonDisabled = (!iniciada && !done) || !page.shared.canEditEtapas ? 'disabled' : '';
        const iniciadaDisabled = page.shared.canEditEtapas ? '' : 'disabled';
        const doneTitle = done
            ? 'Marcar como pendente'
            : (iniciada ? 'Marcar como concluída' : 'Marcar como concluída (necessário iniciar primeiro)');
        // Botão de criar tarefa (mesma estrutura do template Jinja em
        // _project_stages_section.html). Para etapas concluídas o botão fica
        // visível mas com aria-disabled — o JS do quick-add ignora o click.
        const projectTitle = projectDetailConfig.projectTitle || '';
        const orgaoSigla = projectDetailConfig.projectOrgaoSigla || '';
        const datasLabel = (function () {
            if (dataInicioDisplay && dataFimDisplay) return `${dataInicioDisplay} — ${dataFimDisplay}`;
            if (dataInicioDisplay) return `Início ${dataInicioDisplay}`;
            if (dataFimDisplay) return `Fim ${dataFimDisplay}`;
            return 'Etapa sem datas definidas';
        })();
        const stageDoneAttr = done ? '1' : '0';
        const stageDoneClass = done ? ' is-stage-done' : '';
        const stageDoneAriaAttrs = done ? 'aria-disabled="true" tabindex="-1"' : '';
        const stageDoneTitle = done
            ? 'Etapa concluída — desfaça a conclusão para criar tarefas'
            : 'Criar tarefa nesta etapa';
        const stageDoneAriaLabel = done
            ? 'Criar tarefa (etapa concluída)'
            : 'Criar tarefa nesta etapa';
        const createTaskBtnHtml = `
            <button type="button"
                class="btn btn-sm btn-floating etapa-action-create-task${stageDoneClass}"
                data-stage-quick-add-trigger
                data-etapa-id="${etapaId}"
                data-etapa-descricao="${escapeHtml(descricao)}"
                data-etapa-datas="${escapeHtml(datasLabel)}"
                data-project-id="${escapeHtml(String(projectDetailConfig.projectId || ''))}"
                data-project-titulo="${escapeHtml(projectTitle)}"
                data-orgao-sigla="${escapeHtml(orgaoSigla)}"
                data-stage-done="${stageDoneAttr}"
                ${stageDoneAriaAttrs}
                title="${escapeHtml(stageDoneTitle)}"
                aria-label="${escapeHtml(stageDoneAriaLabel)}">
                <i class="fas fa-clipboard-list" aria-hidden="true"></i>
                <span class="etapa-action-task-count is-empty"
                      data-stage-task-count="${etapaId}">0</span>
            </button>
        `;
        const actionHtml = page.shared.canEditEtapas
            ? `
                ${createTaskBtnHtml}
                <form action="/etapa/${etapaId}/delete" method="post" class="inline-form" data-etapa-delete-form
                    data-confirm="Tem certeza que deseja excluir esta etapa?">
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
        const tbody = page.refs.tbody;
        if (!tbody || !etapaPayload || !etapaPayload.id) {
            return;
        }

        const row = buildEtapaRow(etapaPayload);
        if (page.refs.inlineAddEntryRow && page.refs.inlineAddEntryRow.parentNode === tbody) {
            tbody.insertBefore(row, page.refs.inlineAddEntryRow);
        } else if (page.refs.inlineAddFormRow && page.refs.inlineAddFormRow.parentNode === tbody) {
            tbody.insertBefore(row, page.refs.inlineAddFormRow);
        } else {
            tbody.appendChild(row);
        }
        renumberEtapaRows();
        if (typeof page.shared.refreshConcludeButtonCounters === 'function') {
            page.shared.refreshConcludeButtonCounters();
        }
    }

    function replaceEtapaRow(etapaPayload) {
        const tbody = page.refs.tbody;
        if (!tbody || !etapaPayload || !etapaPayload.id) {
            return;
        }

        const existingRow = tbody.querySelector(`tr.etapa-draggable-row[data-etapa-id="${etapaPayload.id}"]`);
        const nextRow = buildEtapaRow(etapaPayload);
        if (existingRow && existingRow.parentNode === tbody) {
            existingRow.replaceWith(nextRow);
        } else {
            appendEtapaRow(etapaPayload);
            return;
        }
        if (typeof page.shared.closeMeetingPopover === 'function') {
            page.shared.closeMeetingPopover();
        }
        renumberEtapaRows();
        if (typeof page.shared.refreshConcludeButtonCounters === 'function') {
            page.shared.refreshConcludeButtonCounters();
        }
    }

    function lockInlineEditorToDisplayWidth(target, input) {
        if (!target || !input) {
            return;
        }

        const cell = target.closest('td');
        const targetRect = target.getBoundingClientRect();
        const cellRect = cell ? cell.getBoundingClientRect() : null;
        const cellStyles = cell ? window.getComputedStyle(cell) : null;
        const cellPaddingX = cellStyles
            ? (parseFloat(cellStyles.paddingLeft) || 0) + (parseFloat(cellStyles.paddingRight) || 0)
            : 0;
        const targetWidth = Math.ceil(targetRect.width || 0);
        const fallbackWidth = Math.max(0, Math.floor((cellRect && cellRect.width || 0) - cellPaddingX));
        const lockedWidth = Math.max(targetWidth, fallbackWidth);

        if (!lockedWidth) {
            return;
        }

        input.style.display = 'block';
        input.style.boxSizing = 'border-box';
        input.style.width = `${lockedWidth}px`;
        input.style.minWidth = `${lockedWidth}px`;
        input.style.maxWidth = '100%';
    }

    function findAbepIndicatorOption(value) {
        const normalizedValue = String(value || '').trim();
        if (!normalizedValue) {
            return null;
        }
        return page.shared.abepIndicatorsOptions.find(item => (
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

        const optionNodes = page.shared.abepIndicatorsOptions.map(item => {
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

    window.showAjaxFlashMessage = showAjaxFlashMessage;

    document.addEventListener('DOMContentLoaded', function () {
        const tbody = document.getElementById('etapas-tbody');
        const projectStatusField = document.querySelector('[data-field="status"]');

        page.refs = {
            tbody: tbody,
            btnImportModel: document.getElementById('btnImportModel'),
            btnOpenInlineEtapaAdd: document.getElementById('btnOpenInlineEtapaAdd'),
            inlineAddEntryRow: document.getElementById('etapaInlineAddEntryRow'),
            inlineAddFormRow: document.getElementById('etapaInlineAddFormRow'),
            inlineAddForm: document.getElementById('etapaInlineAddForm'),
            inlineAddEntryBtn: document.getElementById('etapaInlineAddEntryRow')
                ? document.getElementById('etapaInlineAddEntryRow').querySelector('.etapa-inline-entry-btn-stage')
                : null,
            btnOpenInlineMeetingAdd: document.getElementById('btnOpenInlineMeetingAdd'),
            inlineAddCancelBtn: document.getElementById('btnCancelInlineEtapaAdd'),
            inlineAddSubmitBtn: document.getElementById('btnSubmitInlineEtapaAdd'),
            inlineOrderPreview: document.getElementById('etapaInlineOrderPreview'),
            inlineDescricaoInput: document.getElementById('etapa_inline_descricao'),
            inlineDateInputs: document.getElementById('etapaInlineAddFormRow')
                ? Array.from(document.getElementById('etapaInlineAddFormRow').querySelectorAll('[data-empty-state-input]'))
                : [],
            inlineIniciadaCheckbox: document.getElementById('etapa_inline_iniciada'),
            inlineDoneCheckbox: document.getElementById('etapa_inline_done'),
            inlineIniciadaToggle: document.getElementById('etapaInlineAddFormRow')
                ? document.getElementById('etapaInlineAddFormRow').querySelector('.inline-status-toggle-iniciada')
                : null,
            inlineDoneToggle: document.getElementById('etapaInlineAddFormRow')
                ? document.getElementById('etapaInlineAddFormRow').querySelector('.inline-status-toggle-done')
                : null,
            projectStatusField: projectStatusField,
            projectActionsFooter: document.getElementById('projectActionsFooter'),
            reactivateProjectModal: document.getElementById('reactivate-project-confirm-modal'),
            reactivateProjectConfirmBtn: document.getElementById('reactivate-project-confirm-btn'),
            reactivateProjectCancelBtn: document.getElementById('reactivate-project-cancel-btn'),
            editButton: document.querySelector('.btn-edit-project'),
            saveButton: document.querySelector('.btn-save-project'),
            cancelButton: document.querySelector('.btn-cancel-edit'),
            deleteButton: document.querySelector('.btn-delete-project'),
            historyButton: document.querySelector('.btn-history'),
            concludeButton: document.querySelector('.btn-conclude-project'),
            projectMainHeader: document.getElementById('projectMainHeader'),
            projectCompactHeader: document.getElementById('projectCompactHeader'),
            projectHeaderSentinel: document.getElementById('projectHeaderSentinel'),
        };

        page.state.currentProjectStatus = projectStatusField
            ? (projectStatusField.dataset.value || '').trim()
            : (projectDetailConfig.projectStatus || '');

        function updateProjectStatusDisplay(statusValue) {
            if (!page.refs.projectStatusField) {
                return;
            }
            page.refs.projectStatusField.dataset.value = statusValue || '';
            page.refs.projectStatusField.innerHTML = buildProjectStatusBadge(statusValue);
            page.state.currentProjectStatus = statusValue || '';
        }

        page.shared.escapeHtml = escapeHtml;
        page.shared.showAjaxFlashMessage = showAjaxFlashMessage;
        page.shared.getTopNavOffset = getTopNavOffset;
        page.shared.getEtapaRows = getEtapaRows;
        page.shared.getWorkflowStageRows = getWorkflowStageRows;
        page.shared.formatEtapaOrder = formatEtapaOrder;
        page.shared.syncInlineOrderPreview = syncInlineOrderPreview;
        page.shared.renumberEtapaRows = renumberEtapaRows;
        page.shared.syncImportModelButtonVisibility = syncImportModelButtonVisibility;
        page.shared.setStatusToggleVariant = setStatusToggleVariant;
        page.shared.updateProjectStatusDisplay = updateProjectStatusDisplay;
        page.shared.updateDateFieldDisplay = updateDateFieldDisplay;
        page.shared.updateResponsavelFieldDisplay = updateResponsavelFieldDisplay;
        page.shared.getDateDisplayValue = getDateDisplayValue;
        page.shared.buildMeetingDateDisplay = buildMeetingDateDisplay;
        page.shared.buildStageDatesLabel = buildStageDatesLabel;
        page.shared.formatMeetingDateTimeRange = formatMeetingDateTimeRange;
        page.shared.buildMeetingEventData = buildMeetingEventData;
        page.shared.getMeetingEventDataFromRow = getMeetingEventDataFromRow;
        page.shared.appendEtapaRow = appendEtapaRow;
        page.shared.replaceEtapaRow = replaceEtapaRow;
        page.shared.ensureInlineComposerVisible = ensureInlineComposerVisible;
        page.shared.lockInlineEditorToDisplayWidth = lockInlineEditorToDisplayWidth;
        page.shared.syncStageQuickAddTriggerFromRow = syncStageQuickAddTriggerFromRow;
        page.shared.createAbepIndicatorCombobox = createAbepIndicatorCombobox;
        page.shared.availableAreas = Array.isArray(projectDetailConfig.availableAreas) ? projectDetailConfig.availableAreas : [];
        page.shared.abepIndicatorsOptions = Array.isArray(projectDetailConfig.abepIndicatorsOptions)
            ? projectDetailConfig.abepIndicatorsOptions
            : [];
        page.shared.canEditAreaResponsavel = Boolean(projectDetailConfig.canEditAreaResponsavel);
        page.shared.canAddGoogleMeeting = Boolean(projectDetailConfig.canAddGoogleMeeting);
        page.shared.canEditEtapas = Boolean(tbody && tbody.dataset.canEdit === 'true');

        page._initQueue.forEach(item => {
            item.fn(page);
        });
    });
})();
