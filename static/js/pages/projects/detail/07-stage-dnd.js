(function () {
    const page = window.ProjectDetailPage;
    if (!page || typeof page.registerInit !== 'function') {
        return;
    }

    page.registerInit('stageDnd', function initStageDnd(currentPage) {
        const refs = currentPage.refs;
        const shared = currentPage.shared;
        const config = currentPage.config;
        const mainContent = document.querySelector('.etapa-list');
        const contextMenu = document.getElementById('date-context-menu');
        const cascadeModal = document.getElementById('cascade-confirm-modal');
        const cascadeConfirmBtn = document.getElementById('cascade-confirm-btn');
        const cascadeCancelBtn = document.getElementById('cascade-cancel-btn');
        let currentTargetElement = null;
        let cascadeUpdateInfo = {};

        function parseIsoDateToUtc(isoDate) {
            if (!isoDate || typeof isoDate !== 'string') {
                return null;
            }
            const parts = isoDate.split('-').map(Number);
            if (parts.length !== 3 || parts.some(Number.isNaN)) {
                return null;
            }
            const year = parts[0];
            const month = parts[1];
            const day = parts[2];
            return new Date(Date.UTC(year, month - 1, day));
        }

        function formatUtcDateToIso(dateValue) {
            if (!(dateValue instanceof Date) || Number.isNaN(dateValue.getTime())) {
                return '';
            }
            const year = dateValue.getUTCFullYear();
            const month = String(dateValue.getUTCMonth() + 1).padStart(2, '0');
            const day = String(dateValue.getUTCDate()).padStart(2, '0');
            return `${year}-${month}-${day}`;
        }

        function isBusinessDayUtc(dateValue) {
            const weekday = dateValue.getUTCDay();
            return weekday !== 0 && weekday !== 6;
        }

        function addBusinessDaysToIsoDate(isoDate, businessDays) {
            const baseDate = parseIsoDateToUtc(isoDate);
            const delta = Number(businessDays);
            if (!baseDate || !Number.isFinite(delta)) {
                return '';
            }

            let remaining = Math.abs(Math.trunc(delta));
            const step = delta >= 0 ? 1 : -1;
            while (remaining > 0) {
                baseDate.setUTCDate(baseDate.getUTCDate() + step);
                if (isBusinessDayUtc(baseDate)) {
                    remaining -= 1;
                }
            }
            return formatUtcDateToIso(baseDate);
        }

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
            if (!textarea.isConnected) {
                window.requestAnimationFrame(function () {
                    resizeMultilineEditor(textarea);
                });
                return;
            }
            textarea.style.height = 'auto';
            textarea.style.height = `${textarea.scrollHeight}px`;
        }

        function showCascadeConfirmModal(etapaId, daysDiff) {
            cascadeUpdateInfo = { etapaId: etapaId, daysDiff: daysDiff };
            if (cascadeModal) {
                cascadeModal.style.display = 'flex';
            }
        }

        function hideCascadeConfirmModal() {
            if (cascadeModal) {
                cascadeModal.style.display = 'none';
            }
        }

        function updateIniciadaButton(button, iniciada) {
            if (!button) {
                return;
            }
            shared.setStatusToggleVariant(button, iniciada ? 'started' : 'idle');
            if (iniciada) {
                button.innerHTML = '<i class="fas fa-stop-circle"></i><span>Iniciada</span>';
                button.title = 'Marcar como não iniciada';
            } else {
                button.innerHTML = '<i class="fas fa-play-circle"></i><span>Iniciar</span>';
                button.title = 'Marcar como iniciada';
            }
        }

        function updateDoneButton(button, done, iniciada) {
            if (!button) {
                return;
            }
            if (done) {
                shared.setStatusToggleVariant(button, 'done');
                button.innerHTML = '<i class="fas fa-check-circle"></i><span>Concluída</span>';
                button.title = 'Marcar como pendente';
            } else {
                shared.setStatusToggleVariant(button, iniciada ? 'ready' : 'blocked');
                button.innerHTML = '<i class="fas fa-check-circle"></i><span>Concluir</span>';
                button.title = iniciada ? 'Marcar como concluída' : 'Marcar como concluída (necessário iniciar primeiro)';
            }
            button.disabled = !iniciada && !done;
        }

        function updateStageCreateTaskButton(etapaId, done) {
            const button = document.querySelector(`.etapa-action-create-task[data-etapa-id="${etapaId}"]`);
            if (!button) return;
            button.dataset.stageDone = done ? '1' : '0';
            if (done) {
                button.classList.add('is-stage-done');
                button.setAttribute('aria-disabled', 'true');
                button.setAttribute('tabindex', '-1');
                button.setAttribute('title', 'Etapa concluída — desfaça a conclusão para criar tarefas');
            } else {
                button.classList.remove('is-stage-done');
                button.removeAttribute('aria-disabled');
                button.removeAttribute('tabindex');
                button.setAttribute('title', 'Criar tarefa nesta etapa');
            }
        }

        function updateRowAppearance(etapaId, iniciada, done) {
            const tableRow = document.querySelector(`#etapas-tbody tr[data-etapa-id="${etapaId}"]`);
            if (tableRow) {
                if (tableRow.dataset.entryType === 'google_meeting') {
                    return;
                }
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

        function verificarEAtualizarBotaoConcluir() {
            const btnConcluir = document.getElementById('btn-concluir-projeto');
            if (!btnConcluir) {
                return;
            }

            const todasEtapas = document.querySelectorAll('.toggle-iniciada');
            const totalEtapas = parseInt(btnConcluir.dataset.totalEtapas, 10) || todasEtapas.length;

            if (totalEtapas === 0) {
                btnConcluir.disabled = true;
                btnConcluir.title = 'O projeto não possui etapas';
                return;
            }

            let todasConcluidas = true;
            const etapasUnicas = new Set();

            todasEtapas.forEach(btn => {
                const etapaId = btn.dataset.etapaId;
                if (!etapasUnicas.has(etapaId)) {
                    etapasUnicas.add(etapaId);
                    const isIniciada = btn.dataset.state === 'started';
                    const btnDone = btn.closest('tr') ? btn.closest('tr').querySelector(`.toggle-done[data-etapa-id="${etapaId}"]`) : null;
                    const isDone = btnDone ? btnDone.dataset.state === 'done' : false;
                    if (!isIniciada || !isDone) {
                        todasConcluidas = false;
                    }
                }
            });

            if (todasConcluidas && etapasUnicas.size === totalEtapas) {
                btnConcluir.disabled = false;
                btnConcluir.title = 'Concluir projeto';
            } else {
                btnConcluir.disabled = true;
                btnConcluir.title = 'Todas as etapas devem estar iniciadas e concluídas';
            }
        }

        function refreshConcludeButtonCounters() {
            const btnConcluir = document.getElementById('btn-concluir-projeto');
            shared.syncImportModelButtonVisibility();
            if (btnConcluir) {
                btnConcluir.dataset.totalEtapas = String(shared.getWorkflowStageRows().length);
            }
            verificarEAtualizarBotaoConcluir();
        }

        shared.showCascadeConfirmModal = showCascadeConfirmModal;
        shared.verificarEAtualizarBotaoConcluir = verificarEAtualizarBotaoConcluir;
        shared.refreshConcludeButtonCounters = refreshConcludeButtonCounters;

        if (cascadeCancelBtn) {
            cascadeCancelBtn.addEventListener('click', hideCascadeConfirmModal);
        }

        if (cascadeConfirmBtn) {
            cascadeConfirmBtn.addEventListener('click', function () {
                const etapaId = cascadeUpdateInfo.etapaId;
                const daysDiff = cascadeUpdateInfo.daysDiff;

                fetch(`/project/${config.projectId}/cascade_update`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Requested-With': 'XMLHttpRequest',
                        'X-CSRFToken': config.csrfToken || '',
                    },
                    body: JSON.stringify({ etapa_id: etapaId, days_diff: daysDiff }),
                })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            shared.showAjaxFlashMessage(data.message, 'success');
                            window.location.reload();
                        } else {
                            shared.showAjaxFlashMessage(data.message, 'danger');
                        }
                    })
                    .catch(error => {
                        shared.showAjaxFlashMessage('Erro de comunicação na atualização em cascata.', 'danger');
                        console.error('Cascade update error:', error);
                    });

                hideCascadeConfirmModal();
            });
        }

        if (mainContent) {
            mainContent.addEventListener('contextmenu', function (event) {
                const target = event.target.closest('.editable-field[data-field*="data"]');

                if (!target) {
                    hideContextMenu();
                    return;
                }

                const targetRow = target.closest('tr.etapa-draggable-row');
                if (targetRow && targetRow.dataset.entryType === 'google_meeting') {
                    event.preventDefault();
                    hideContextMenu();
                    shared.showAjaxFlashMessage('Reuniões do Google não usam o atalho de dias úteis.', 'info');
                    return;
                }

                if (target.closest('tr.etapa-done')) {
                    return;
                }

                event.preventDefault();
                currentTargetElement = target;
                const originalDate = currentTargetElement.dataset.originalValue;
                if (!originalDate) {
                    shared.showAjaxFlashMessage('Defina uma data inicial antes de adicionar dias.', 'warning');
                    return;
                }

                showContextMenuAt(event.clientX, event.clientY);
            });

            if (contextMenu) {
                contextMenu.addEventListener('click', function (event) {
                    const selectedOption = event.target.closest('li[data-days]');
                    if (selectedOption && currentTargetElement) {
                        const elementToUpdate = currentTargetElement;
                        const daysToAdd = parseInt(selectedOption.dataset.days, 10);
                        const originalDateStr = elementToUpdate.dataset.originalValue;
                        const field = elementToUpdate.dataset.field;
                        const etapaId = elementToUpdate.dataset.etapaId;

                        const newDateValue = addBusinessDaysToIsoDate(originalDateStr, daysToAdd);
                        if (!newDateValue) {
                            shared.showAjaxFlashMessage('Não foi possível calcular a nova data útil.', 'danger');
                            hideContextMenu();
                            return;
                        }

                        fetch(`/etapa/${etapaId}/update_field`, {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'X-Requested-With': 'XMLHttpRequest',
                                'X-CSRFToken': config.csrfToken || '',
                            },
                            body: JSON.stringify({ field: field, value: newDateValue }),
                        })
                            .then(response => response.json())
                            .then(data => {
                                if (data.success) {
                                    shared.updateDateFieldDisplay(elementToUpdate, data.newValue || '', data.displayValue || '');
                                    elementToUpdate.dataset.originalValue = data.newValue || '';

                                    if (field === 'data_inicio' && data.updatedEndDate) {
                                        const etapaRow = elementToUpdate.closest('tr');
                                        const endDateElement = etapaRow ? etapaRow.querySelector('.editable-field[data-field="data_fim"]') : null;
                                        if (endDateElement) {
                                            shared.updateDateFieldDisplay(endDateElement, data.updatedEndDate || '', data.updatedEndDateDisplay || '');
                                            endDateElement.dataset.originalValue = data.updatedEndDate || '';
                                        }
                                    }

                                    if (typeof shared.syncStageQuickAddTriggerFromRow === 'function') {
                                        shared.syncStageQuickAddTriggerFromRow(elementToUpdate.closest('tr'));
                                    }

                                    if (field === 'data_inicio' && daysToAdd !== 0) {
                                        showCascadeConfirmModal(etapaId, daysToAdd);
                                    } else {
                                        shared.showAjaxFlashMessage(`Data atualizada: +${daysToAdd} dia(s) útil(eis)`, 'success');
                                    }
                                } else {
                                    shared.showAjaxFlashMessage(data.message || 'Falha ao atualizar data.', 'danger');
                                }
                            })
                            .catch(error => {
                                shared.showAjaxFlashMessage('Erro de comunicação.', 'danger');
                                console.error('Error updating date field:', error);
                            });
                    }
                    hideContextMenu();
                });
            }

            window.addEventListener('click', hideContextMenu);
            window.addEventListener('keydown', function (event) {
                if (event.key === 'Escape') {
                    hideContextMenu();
                }
            });

            mainContent.addEventListener('click', function (event) {
                const target = event.target.closest('.editable-field');

                if (document.querySelector('.editable-field-input, .editable-field-textarea')) {
                    return;
                }
                if (!target) {
                    return;
                }
                if (target.closest('tr.etapa-done')) {
                    shared.showAjaxFlashMessage('Não é possível editar uma etapa concluída.', 'warning');
                    return;
                }

                const field = target.dataset.field;
                const etapaId = target.dataset.etapaId;
                let originalValue = target.textContent.trim();
                if (field === 'responsavel' && target.classList.contains('editable-field-empty')) {
                    originalValue = '';
                }
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
                        if (window.CalDatetimePicker) {
                            CalDatetimePicker.initDatePicker(input);
                        }
                    } else {
                        input.type = 'text';
                        input.value = originalValue === '-' ? '' : originalValue;
                    }
                }

                if (field === 'responsavel') {
                    shared.lockInlineEditorToDisplayWidth(target, input);
                }

                target.style.display = 'none';
                target.insertAdjacentElement('afterend', input);
                input.focus();
                if (input.tagName === 'TEXTAREA') {
                    window.requestAnimationFrame(function () {
                        resizeMultilineEditor(input);
                    });
                }

                function saveChanges() {
                    const newValue = input.value;

                    input.remove();
                    target.style.display = '';

                    const valueToCheck = field.includes('data')
                        ? originalDateValue
                        : (originalValue === '-' ? '' : originalValue);
                    if (newValue === valueToCheck) {
                        return;
                    }

                    fetch(`/etapa/${etapaId}/update_field`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-Requested-With': 'XMLHttpRequest',
                            'X-CSRFToken': config.csrfToken || '',
                        },
                        body: JSON.stringify({ field: field, value: newValue }),
                    })
                        .then(response => response.json())
                            .then(data => {
                                if (data.success) {
                                    if (field.includes('data')) {
                                        shared.updateDateFieldDisplay(target, data.newValue || '', data.displayValue || '');
                                        target.dataset.originalValue = data.newValue || '';
                                } else if (field === 'responsavel') {
                                    shared.updateResponsavelFieldDisplay(target, data.newValue || '');
                                } else {
                                    target.textContent = data.displayValue;
                                }

                                if (field === 'data_inicio' && data.updatedEndDate) {
                                    const etapaRow = target.closest('tr');
                                    const endDateElement = etapaRow ? etapaRow.querySelector('.editable-field[data-field="data_fim"]') : null;
                                    if (endDateElement) {
                                        shared.updateDateFieldDisplay(endDateElement, data.updatedEndDate || '', data.updatedEndDateDisplay || '');
                                        endDateElement.dataset.originalValue = data.updatedEndDate || '';
                                    }
                                }

                                if (typeof shared.syncStageQuickAddTriggerFromRow === 'function') {
                                    shared.syncStageQuickAddTriggerFromRow(target.closest('tr'));
                                }

                                const isMeetingField = Boolean(
                                    data.isMeeting || (
                                        target.closest('tr.etapa-draggable-row') &&
                                        target.closest('tr.etapa-draggable-row').dataset.entryType === 'google_meeting'
                                    )
                                );
                                if (!isMeetingField && field === 'data_inicio' && data.daysDiff !== undefined && data.daysDiff !== 0) {
                                    showCascadeConfirmModal(etapaId, data.daysDiff);
                                } else {
                                    shared.showAjaxFlashMessage(
                                        data.message || (isMeetingField ? 'Data da reunião atualizada com sucesso!' : 'Alteração salva com sucesso!'),
                                        'success'
                                    );
                                }
                            } else {
                                if (field === 'responsavel') {
                                    shared.updateResponsavelFieldDisplay(target, originalValue);
                                } else {
                                    target.textContent = originalValue;
                                }
                                shared.showAjaxFlashMessage(data.message || 'Falha ao salvar.', 'danger');
                            }
                        })
                        .catch(error => {
                            if (field === 'responsavel') {
                                shared.updateResponsavelFieldDisplay(target, originalValue);
                            } else {
                                target.textContent = originalValue;
                            }
                            shared.showAjaxFlashMessage('Erro de comunicação.', 'danger');
                            console.error('Error updating field:', error);
                        });
                }

                input.addEventListener('blur', function () {
                    if (window.CalDatetimePicker && CalDatetimePicker.isOpen()) {
                        return;
                    }
                    saveChanges();
                });

                input.addEventListener('keydown', function (keyEvent) {
                    if (keyEvent.key === 'Enter' && field !== 'descricao' && !keyEvent.shiftKey) {
                        keyEvent.preventDefault();
                        saveChanges();
                    } else if (keyEvent.key === 'Escape') {
                        input.remove();
                        target.style.display = '';
                    }
                });
            });
        }

        if (refs.tbody) {
            let draggedItem = null;
            let ghostElement = null;
            let dropIndicator = null;

            function createDropIndicator() {
                if (!dropIndicator) {
                    dropIndicator = document.createElement('div');
                    dropIndicator.className = 'drop-indicator';
                    document.body.appendChild(dropIndicator);
                }
                return dropIndicator;
            }

            function showDropIndicator(targetRow, position) {
                const indicator = createDropIndicator();
                const rect = targetRow.getBoundingClientRect();
                const tableRect = refs.tbody.getBoundingClientRect();

                indicator.style.position = 'fixed';
                indicator.style.left = `${tableRect.left}px`;
                indicator.style.width = `${tableRect.width}px`;
                indicator.style.top = position === 'top' ? `${rect.top - 2}px` : `${rect.bottom - 1}px`;
                indicator.classList.add('show');
            }

            function hideDropIndicator() {
                if (dropIndicator) {
                    dropIndicator.classList.remove('show');
                }
            }

            refs.tbody.addEventListener('dragstart', function (event) {
                const handle = event.target.closest('.drag-handle');
                if (!handle) {
                    event.preventDefault();
                    return;
                }

                draggedItem = handle.closest('tr.etapa-draggable-row');
                if (!draggedItem) {
                    return;
                }

                event.dataTransfer.effectAllowed = 'move';
                event.dataTransfer.setData('text/plain', draggedItem.dataset.etapaId);

                ghostElement = document.createElement('div');
                ghostElement.classList.add('drag-ghost-custom');
                const descricaoEtapa = draggedItem.querySelector('.etapa-descricao');
                const descricaoTexto = descricaoEtapa ? descricaoEtapa.innerText.trim() : 'Movendo etapa...';
                const resumo = descricaoTexto.substring(0, 60) + (descricaoTexto.length > 60 ? '...' : '');
                ghostElement.innerHTML = `<i class="fas fa-arrows-alt me-2"></i>${resumo}`;
                document.body.appendChild(ghostElement);

                event.dataTransfer.setDragImage(ghostElement, 20, 20);

                setTimeout(function () {
                    if (draggedItem) {
                        draggedItem.classList.add('dragging');
                    }
                    if (ghostElement && ghostElement.parentNode) {
                        ghostElement.parentNode.removeChild(ghostElement);
                        ghostElement = null;
                    }
                }, 0);
            });

            refs.tbody.addEventListener('dragend', function () {
                if (draggedItem) {
                    draggedItem.classList.remove('dragging');
                    draggedItem = null;
                }
                if (ghostElement && ghostElement.parentNode) {
                    ghostElement.parentNode.removeChild(ghostElement);
                    ghostElement = null;
                }
                hideDropIndicator();
                refs.tbody.querySelectorAll('tr.etapa-draggable-row.drag-over').forEach(row => row.classList.remove('drag-over'));
                shared.renumberEtapaRows();
            });

            refs.tbody.addEventListener('dragover', function (event) {
                event.preventDefault();
                const targetRow = event.target.closest('tr.etapa-draggable-row');
                if (targetRow && targetRow !== draggedItem) {
                    const rect = targetRow.getBoundingClientRect();
                    const mouseY = event.clientY;
                    const rowMiddle = rect.top + rect.height / 2;
                    const position = mouseY < rowMiddle ? 'top' : 'bottom';

                    refs.tbody.querySelectorAll('tr.etapa-draggable-row.drag-over').forEach(row => row.classList.remove('drag-over'));
                    showDropIndicator(targetRow, position);
                    event.dataTransfer.dropEffect = 'move';
                }
            });

            refs.tbody.addEventListener('dragleave', function (event) {
                const relatedTarget = event.relatedTarget;
                if (!refs.tbody.contains(relatedTarget) && draggedItem) {
                    hideDropIndicator();
                    refs.tbody.querySelectorAll('tr.etapa-draggable-row.drag-over').forEach(row => row.classList.remove('drag-over'));
                }
            });

            refs.tbody.addEventListener('drop', function (event) {
                event.preventDefault();
                const targetRow = event.target.closest('tr.etapa-draggable-row');
                hideDropIndicator();
                refs.tbody.querySelectorAll('tr.etapa-draggable-row.drag-over').forEach(row => row.classList.remove('drag-over'));

                if (draggedItem && targetRow && targetRow !== draggedItem) {
                    const rect = targetRow.getBoundingClientRect();
                    const mouseY = event.clientY;
                    const insertBefore = mouseY < rect.top + rect.height / 2;
                    if (insertBefore) {
                        targetRow.parentNode.insertBefore(draggedItem, targetRow);
                    } else {
                        targetRow.parentNode.insertBefore(draggedItem, targetRow.nextSibling);
                    }

                    const etapaIdsOrdenadas = Array.from(refs.tbody.querySelectorAll('tr.etapa-draggable-row'))
                        .map(row => row.dataset.etapaId);

                    fetch(`/project/${config.projectId}/etapas/reordenar`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-Requested-With': 'XMLHttpRequest',
                            'X-CSRFToken': config.csrfToken || '',
                        },
                        body: JSON.stringify({ etapa_ids: etapaIdsOrdenadas }),
                    })
                        .then(response => response.json())
                        .then(data => {
                            if (data.success) {
                                shared.showAjaxFlashMessage(data.message || 'Ordem das etapas atualizada com sucesso!', 'success');
                            } else {
                                shared.showAjaxFlashMessage(data.message || 'Erro ao reordenar etapas.', 'danger');
                            }
                        })
                        .catch(error => {
                            console.error('Erro na requisição de reordenar:', error);
                            shared.showAjaxFlashMessage('Erro de comunicação ao reordenar etapas.', 'danger');
                        });
                }
            });

            refs.tbody.addEventListener('submit', async function (event) {
                const deleteForm = event.target.closest('form[data-etapa-delete-form]');
                if (!deleteForm || !refs.tbody.contains(deleteForm) || event.defaultPrevented) {
                    return;
                }

                event.preventDefault();

                const deleteButton = deleteForm.querySelector('[data-etapa-delete-btn]');
                const row = deleteForm.closest('tr.etapa-draggable-row');
                if (row && row.dataset.entryType === 'google_meeting') {
                    await shared.deleteProjectMeeting(row.dataset.etapaId, {
                        triggerButton: deleteButton,
                        confirm: false,
                    });
                    return;
                }

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
                            'X-CSRFToken': config.csrfToken || '',
                        },
                    });

                    let data = null;
                    try {
                        data = await response.json();
                    } catch (error) {
                        data = null;
                    }

                    if (!response.ok || !data || !data.success) {
                        shared.showAjaxFlashMessage((data && data.message) || 'Erro ao excluir etapa.', 'danger');
                        if (deleteButton) {
                            deleteButton.disabled = false;
                            deleteButton.innerHTML = originalButtonHtml;
                        }
                        return;
                    }

                    if (row) {
                        row.remove();
                    }
                    shared.renumberEtapaRows();
                    refreshConcludeButtonCounters();
                    shared.showAjaxFlashMessage(data.message || 'Etapa excluída com sucesso.', 'success');
                } catch (error) {
                    console.error('Erro ao excluir etapa:', error);
                    shared.showAjaxFlashMessage('Erro de comunicação ao excluir etapa.', 'danger');
                    if (deleteButton) {
                        deleteButton.disabled = false;
                        deleteButton.innerHTML = originalButtonHtml;
                    }
                }
            });

            refs.tbody.addEventListener('click', function (event) {
                const meetingRow = event.target.closest('tr.etapa-row-google-meeting');
                const interactiveMeetingTarget = event.target.closest('a, button, form, .editable-field, input, textarea, select, .drag-handle');
                if (meetingRow && refs.tbody.contains(meetingRow) && !interactiveMeetingTarget) {
                    const meetingEventData = shared.getMeetingEventDataFromRow(meetingRow);
                    if (meetingEventData) {
                        event.preventDefault();
                        event.stopPropagation();
                        shared.openMeetingPopover(
                            meetingEventData,
                            event.target.closest('td') || meetingRow.querySelector('.etapa-meeting-description-cell') || meetingRow
                        );
                        return;
                    }
                }

                const iniciadaButton = event.target.closest('.toggle-iniciada');
                if (iniciadaButton && refs.tbody.contains(iniciadaButton)) {
                    if (iniciadaButton.dataset.inFlight === '1') {
                        return;
                    }
                    iniciadaButton.dataset.inFlight = '1';
                    const etapaId = iniciadaButton.dataset.etapaId;

                    fetch(`/etapa/${etapaId}/toggle_iniciada`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/x-www-form-urlencoded',
                            'X-Requested-With': 'XMLHttpRequest',
                            'X-CSRFToken': config.csrfToken || '',
                        },
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
                                updateStageCreateTaskButton(etapaId, data.done);
                                if (data.message) {
                                    shared.showAjaxFlashMessage(data.message, 'info');
                                } else {
                                    shared.showAjaxFlashMessage(data.iniciada ? 'Iniciada.' : 'Não iniciada.', 'success');
                                }
                                verificarEAtualizarBotaoConcluir();
                            } else {
                                shared.showAjaxFlashMessage(data.message || 'Erro ao atualizar etapa.', 'danger');
                            }
                        })
                        .catch(error => {
                            console.error('Erro ao alternar iniciada:', error);
                            shared.showAjaxFlashMessage('Erro de comunicação com o servidor.', 'danger');
                        })
                        .finally(function () {
                            delete iniciadaButton.dataset.inFlight;
                        });
                    return;
                }

                const doneButton = event.target.closest('.toggle-done');
                if (doneButton && refs.tbody.contains(doneButton)) {
                    if (doneButton.disabled || doneButton.dataset.inFlight === '1') {
                        return;
                    }
                    doneButton.dataset.inFlight = '1';
                    const etapaId = doneButton.dataset.etapaId;

                    fetch(`/etapa/${etapaId}/toggle`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/x-www-form-urlencoded',
                            'X-Requested-With': 'XMLHttpRequest',
                            'X-CSRFToken': config.csrfToken || '',
                        },
                    })
                        .then(response => response.json())
                        .then(data => {
                            if (data.success) {
                                updateDoneButton(doneButton, data.done, data.iniciada);
                                updateRowAppearance(etapaId, data.iniciada, data.done);
                                updateStageCreateTaskButton(etapaId, data.done);
                                if (data.message) {
                                    shared.showAjaxFlashMessage(data.message, 'info');
                                } else {
                                    shared.showAjaxFlashMessage(data.done ? 'Concluída.' : 'Pendente.', 'success');
                                }
                                verificarEAtualizarBotaoConcluir();
                            } else {
                                const feedbackType = data.success === false && data.message && data.message.includes('não foi iniciada')
                                    ? 'warning'
                                    : 'danger';
                                shared.showAjaxFlashMessage(data.message || 'Erro ao atualizar etapa.', feedbackType);
                            }
                        })
                        .catch(error => {
                            console.error('Erro ao alternar concluída:', error);
                            shared.showAjaxFlashMessage('Erro de comunicação com o servidor.', 'danger');
                        })
                        .finally(function () {
                            delete doneButton.dataset.inFlight;
                        });
                }
            });
        }

        verificarEAtualizarBotaoConcluir();
        shared.syncImportModelButtonVisibility();
    });
})();
