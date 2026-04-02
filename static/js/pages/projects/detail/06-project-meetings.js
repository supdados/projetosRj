(function () {
    const page = window.ProjectDetailPage;
    if (!page || typeof page.registerInit !== 'function') {
        return;
    }

    page.registerInit('projectMeetings', function initProjectMeetings(currentPage) {
        const refs = currentPage.refs;
        const shared = currentPage.shared;
        const config = currentPage.config;

        let projectMeetingModal = null;
        let currentMeetingPopover = null;

        function closeMeetingPopover() {
            if (currentMeetingPopover) {
                currentMeetingPopover.remove();
                currentMeetingPopover = null;
            }
        }

        function openMeetingPopover(eventData, anchor) {
            if (!eventData || !anchor) {
                return;
            }

            const rect = typeof anchor.getBoundingClientRect === 'function'
                ? anchor.getBoundingClientRect()
                : anchor;
            if (!rect) {
                return;
            }

            closeMeetingPopover();

            const pop = document.createElement('div');
            pop.className = 'cal-event-popover';
            currentMeetingPopover = pop;

            const head = document.createElement('div');
            head.className = 'cal-event-popover-head';

            const title = document.createElement('div');
            title.className = 'cal-event-popover-title';
            title.textContent = eventData.title || 'Sem título';
            head.appendChild(title);

            const closeBtn = document.createElement('button');
            closeBtn.type = 'button';
            closeBtn.className = 'cal-event-popover-close';
            closeBtn.setAttribute('aria-label', 'Fechar');
            closeBtn.textContent = '×';
            closeBtn.addEventListener('click', function (event) {
                event.stopPropagation();
                closeMeetingPopover();
            });
            head.appendChild(closeBtn);
            pop.appendChild(head);

            const body = document.createElement('div');
            body.className = 'cal-event-popover-body';

            const when = document.createElement('div');
            when.className = 'cal-event-popover-info';
            when.innerHTML = '<i class="fas fa-clock" aria-hidden="true"></i><span></span>';
            when.querySelector('span').textContent = shared.formatMeetingDateTimeRange(eventData);
            body.appendChild(when);

            if (eventData.owner_email) {
                const owner = document.createElement('div');
                owner.className = 'cal-event-popover-info';
                owner.innerHTML = '<i class="far fa-user" aria-hidden="true"></i><span></span>';
                owner.querySelector('span').textContent = eventData.owner_email;
                body.appendChild(owner);
            }

            if (eventData.location) {
                const loc = document.createElement('div');
                loc.className = 'cal-event-popover-info';
                loc.innerHTML = '<i class="fas fa-map-marker-alt" aria-hidden="true"></i><span></span>';
                loc.querySelector('span').textContent = eventData.location;
                body.appendChild(loc);
            }

            if (eventData.description) {
                const desc = document.createElement('div');
                desc.className = 'cal-event-popover-description';
                desc.textContent = eventData.description;
                body.appendChild(desc);
            }

            if (eventData.sync_status === 'error') {
                const warning = document.createElement('div');
                warning.className = 'cal-event-popover-info cal-event-popover-info--warning';
                warning.innerHTML = '<i class="fas fa-triangle-exclamation" aria-hidden="true"></i><span></span>';
                warning.querySelector('span').textContent = eventData.sync_error || 'Evento indisponível no Google Calendar.';
                body.appendChild(warning);
            }

            if (eventData.meet_link) {
                const meet = document.createElement('a');
                meet.className = 'cal-event-popover-meet';
                meet.href = eventData.meet_link;
                meet.target = '_blank';
                meet.rel = 'noopener noreferrer';
                meet.textContent = 'Abrir Meet';
                meet.addEventListener('click', function (event) {
                    event.stopPropagation();
                });
                body.appendChild(meet);
            }

            if (eventData.can_manage) {
                const actions = document.createElement('div');
                actions.className = 'cal-event-popover-actions';

                if (eventData.can_edit && projectMeetingModal) {
                    const editBtn = document.createElement('button');
                    editBtn.type = 'button';
                    editBtn.className = 'cal-event-popover-action';
                    editBtn.innerHTML = '<i class="fas fa-pen" aria-hidden="true"></i><span>Editar</span>';
                    editBtn.addEventListener('click', function (event) {
                        event.stopPropagation();
                        closeMeetingPopover();
                        projectMeetingModal.openEditModal(eventData);
                    });
                    actions.appendChild(editBtn);
                }

                const delBtn = document.createElement('button');
                delBtn.type = 'button';
                delBtn.className = 'cal-event-popover-action cal-event-popover-action--danger';
                delBtn.innerHTML = '<i class="fas fa-trash" aria-hidden="true"></i><span>Apagar</span>';
                delBtn.addEventListener('click', function (event) {
                    event.stopPropagation();
                    closeMeetingPopover();
                    deleteProjectMeeting(eventData.id);
                });
                actions.appendChild(delBtn);
                body.appendChild(actions);
            } else {
                const readonlyInfo = document.createElement('div');
                readonlyInfo.className = 'cal-event-popover-info';
                readonlyInfo.innerHTML = '<i class="fas fa-lock" aria-hidden="true"></i><span></span>';
                readonlyInfo.querySelector('span').textContent = 'Somente a mesma conta Google conectada pode editar ou apagar.';
                body.appendChild(readonlyInfo);
            }

            pop.appendChild(body);
            pop.addEventListener('click', function (event) {
                event.stopPropagation();
            });
            document.body.appendChild(pop);

            const popW = pop.offsetWidth || 320;
            const popH = pop.offsetHeight || 220;
            const viewW = window.innerWidth;
            const viewH = window.innerHeight;

            let left = rect.left;
            let top = rect.bottom + 8;

            if (left + popW > viewW - 8) {
                left = viewW - popW - 8;
            }
            if (left < 8) {
                left = 8;
            }
            if (top + popH > viewH - 8) {
                top = rect.top - popH - 8;
            }
            if (top < 8) {
                top = 8;
            }

            pop.style.left = `${left}px`;
            pop.style.top = `${top}px`;

            window.setTimeout(function () {
                document.addEventListener('click', closeMeetingPopover, { once: true });
            }, 0);
        }

        async function deleteProjectMeeting(etapaId, options) {
            const settings = options || {};
            const shouldConfirm = settings.confirm !== false;
            if (!etapaId) {
                return false;
            }

            if (shouldConfirm && !window.confirm('Tem certeza que deseja excluir esta reunião?')) {
                return false;
            }

            const triggerButton = settings.triggerButton || null;
            const originalButtonHtml = triggerButton ? triggerButton.innerHTML : '';
            if (triggerButton) {
                triggerButton.disabled = true;
                triggerButton.innerHTML = '<i class="fas fa-spinner fa-spin" aria-hidden="true"></i>';
            }

            try {
                const response = await fetch(`/etapa/${etapaId}/delete`, {
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
                    shared.showAjaxFlashMessage((data && data.message) || 'Erro ao excluir reunião.', 'danger');
                    if (triggerButton) {
                        triggerButton.disabled = false;
                        triggerButton.innerHTML = originalButtonHtml;
                    }
                    return false;
                }

                const row = refs.tbody ? refs.tbody.querySelector(`tr.etapa-draggable-row[data-etapa-id="${etapaId}"]`) : null;
                if (row) {
                    row.remove();
                }
                closeMeetingPopover();
                if (settings.api && typeof settings.api.closeModal === 'function') {
                    settings.api.closeModal();
                }
                shared.renumberEtapaRows();
                shared.refreshConcludeButtonCounters();
                shared.showAjaxFlashMessage(data.message || 'Reunião excluída com sucesso.', 'success');
                return true;
            } catch (error) {
                console.error('Erro ao excluir reunião do projeto:', error);
                shared.showAjaxFlashMessage('Erro de comunicação ao excluir reunião.', 'danger');
                if (triggerButton) {
                    triggerButton.disabled = false;
                    triggerButton.innerHTML = originalButtonHtml;
                }
                return false;
            }
        }

        async function submitProjectMeetingForm(_event, api) {
            const form = api && typeof api.getForm === 'function' ? api.getForm() : null;
            if (!form) {
                return;
            }
            const editingMeetingId = api && typeof api.getEditId === 'function' ? api.getEditId() : null;

            const submitButton = form.querySelector('.cal-btn-save');
            const cancelButtons = Array.from(form.querySelectorAll('.cal-btn-cancel, [data-calendar-modal-close]'));
            const originalSubmitHtml = submitButton ? submitButton.innerHTML : '';

            if (submitButton) {
                submitButton.disabled = true;
                submitButton.innerHTML = '<i class="fas fa-spinner fa-spin" aria-hidden="true"></i>';
            }
            cancelButtons.forEach(button => {
                button.disabled = true;
            });

            try {
                const formData = new FormData(form);
                const response = await fetch(form.action || config.addMeetingUrl, {
                    method: 'POST',
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest',
                        'Accept': 'application/json',
                        'X-CSRFToken': config.csrfToken || '',
                    },
                    body: formData,
                });

                let data = null;
                try {
                    data = await response.json();
                } catch (error) {
                    data = null;
                }

                if (!response.ok || !data || !data.success || !data.etapa) {
                    shared.showAjaxFlashMessage(
                        (data && data.message) || (editingMeetingId ? 'Erro ao salvar reunião.' : 'Erro ao adicionar reunião.'),
                        'danger'
                    );
                    return;
                }

                if (editingMeetingId) {
                    shared.replaceEtapaRow(data.etapa);
                } else {
                    shared.appendEtapaRow(data.etapa);
                }
                closeMeetingPopover();
                api.closeModal();
                if (data.warning) {
                    shared.showAjaxFlashMessage(data.warning, 'warning');
                }
                shared.showAjaxFlashMessage(
                    data.message || (editingMeetingId ? 'Reunião atualizada com sucesso!' : 'Reunião adicionada ao projeto com sucesso!'),
                    'success'
                );
            } catch (error) {
                console.error('Erro ao salvar reunião do projeto:', error);
                shared.showAjaxFlashMessage(
                    editingMeetingId ? 'Erro de comunicação ao salvar reunião.' : 'Erro de comunicação ao adicionar reunião.',
                    'danger'
                );
            } finally {
                if (submitButton) {
                    submitButton.disabled = false;
                    submitButton.innerHTML = originalSubmitHtml;
                }
                cancelButtons.forEach(button => {
                    button.disabled = false;
                });
            }
        }

        shared.closeMeetingPopover = closeMeetingPopover;
        shared.openMeetingPopover = openMeetingPopover;
        shared.deleteProjectMeeting = deleteProjectMeeting;

        if (shared.canAddGoogleMeeting && typeof window.createCalendarEventModal === 'function') {
            projectMeetingModal = window.createCalendarEventModal({
                modalId: config.projectMeetingModalId || 'projectMeetingModal',
                createUrl: config.addMeetingUrl || `/project/${config.projectId}/meeting/add`,
                editUrlTemplate: config.editMeetingUrlTemplate || '/etapa/0/meeting/edit',
                createTitle: 'Nova reunião Google',
                editTitle: 'Editar reunião Google',
                onSubmit: submitProjectMeetingForm,
                onDelete: function (etapaId, api) {
                    deleteProjectMeeting(etapaId, { api: api });
                },
                onInvalid: function (message) {
                    shared.showAjaxFlashMessage(message, 'warning');
                },
            });
        }

        if (refs.btnOpenInlineMeetingAdd && projectMeetingModal) {
            refs.btnOpenInlineMeetingAdd.addEventListener('click', function (event) {
                event.preventDefault();
                if (typeof shared.closeInlineEtapaComposer === 'function') {
                    shared.closeInlineEtapaComposer(true);
                }
                projectMeetingModal.openCreateModal();
            });
        }

        document.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') {
                closeMeetingPopover();
            }
        });
    });
})();
