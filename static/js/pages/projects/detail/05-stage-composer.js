(function () {
    const page = window.ProjectDetailPage;
    if (!page || typeof page.registerInit !== 'function') {
        return;
    }

    page.registerInit('stageComposer', function initStageComposer(currentPage) {
        const refs = currentPage.refs;
        const shared = currentPage.shared;
        const state = currentPage.state;

        const inlineAddForm = refs.inlineAddForm;
        const inlineAddFormRow = refs.inlineAddFormRow;
        const inlineAddEntryRow = refs.inlineAddEntryRow;
        const inlineAddEntryBtn = refs.inlineAddEntryBtn;
        const inlineDescricaoInput = refs.inlineDescricaoInput;
        const inlineDateInputs = refs.inlineDateInputs;
        const inlineIniciadaCheckbox = refs.inlineIniciadaCheckbox;
        const inlineDoneCheckbox = refs.inlineDoneCheckbox;
        const inlineIniciadaToggle = refs.inlineIniciadaToggle;
        const inlineDoneToggle = refs.inlineDoneToggle;
        const inlineAddSubmitBtn = refs.inlineAddSubmitBtn;
        const inlineAddCancelBtn = refs.inlineAddCancelBtn;
        const btnOpenInlineEtapaAdd = refs.btnOpenInlineEtapaAdd;
        const reactivateProjectModal = refs.reactivateProjectModal;
        const reactivateProjectConfirmBtn = refs.reactivateProjectConfirmBtn;
        const reactivateProjectCancelBtn = refs.reactivateProjectCancelBtn;

        let inlineComposerSaving = false;
        let inlineDatePickerOpening = false;
        let reactivateProjectModalResolver = null;

        function updateInlineIniciadaButton(button, iniciada) {
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
            button.classList.add(iniciada ? 'etapa-status-toggle-started' : 'etapa-status-toggle-idle');
            button.dataset.state = iniciada ? 'started' : 'idle';
            if (iniciada) {
                button.innerHTML = '<i class="fas fa-stop-circle"></i><span>Iniciada</span>';
            } else {
                button.innerHTML = '<i class="fas fa-play-circle"></i><span>Iniciar</span>';
            }
        }

        function updateInlineDoneButton(button, done, iniciada) {
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
            if (done) {
                button.classList.add('etapa-status-toggle-done');
                button.dataset.state = 'done';
                button.innerHTML = '<i class="fas fa-check-circle"></i><span>Concluída</span>';
                button.title = 'Marcar como pendente';
            } else {
                button.classList.add(iniciada ? 'etapa-status-toggle-ready' : 'etapa-status-toggle-blocked');
                button.dataset.state = iniciada ? 'ready' : 'blocked';
                button.innerHTML = '<i class="fas fa-check-circle"></i><span>Concluir</span>';
                button.title = iniciada ? 'Marcar como concluída' : 'Marcar como concluída (necessário iniciar primeiro)';
            }
            button.disabled = !iniciada && !done;
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

        function syncInlineStatusControls() {
            const isIniciada = Boolean(inlineIniciadaCheckbox && inlineIniciadaCheckbox.checked);
            const isDone = Boolean(inlineDoneCheckbox && inlineDoneCheckbox.checked);

            if (inlineIniciadaToggle) {
                updateInlineIniciadaButton(inlineIniciadaToggle, isIniciada);
            }
            if (inlineDoneToggle) {
                updateInlineDoneButton(inlineDoneToggle, isDone, isIniciada);
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

        function openInlineEtapaComposer(source) {
            if (!shared.canEditEtapas || !inlineAddFormRow || !inlineAddForm) {
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
            shared.syncInlineOrderPreview();
            resizeInlineDescricaoTextarea();
            inlineAddFormRow.classList.remove('ds-hidden');
            if (inlineAddEntryRow) {
                inlineAddEntryRow.classList.add('ds-hidden');
            }
            requestAnimationFrame(() => {
                shared.ensureInlineComposerVisible();
                if (inlineDescricaoInput) {
                    inlineDescricaoInput.focus();
                }
            });
            inlineAddFormRow.dataset.openedFrom = source === 'entry' ? 'entry' : 'button';
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
            delete inlineAddFormRow.dataset.openedFrom;
        }

        async function submitInlineEtapaForm(options = {}) {
            if (!inlineAddForm || inlineComposerSaving) {
                return;
            }
            const keepComposerOpen = Boolean(options.keepComposerOpen);

            const descricao = (inlineDescricaoInput ? inlineDescricaoInput.value : '').trim();
            if (!descricao) {
                shared.showAjaxFlashMessage('A descrição da etapa é obrigatória.', 'warning');
                if (inlineDescricaoInput) {
                    inlineDescricaoInput.focus();
                }
                return;
            }

            const shouldReactivateProject = state.currentProjectStatus === 'Finalizado';
            if (shouldReactivateProject && !options.reactivateProject) {
                const confirmed = await promptReactivateProjectConfirmation();
                if (!confirmed) {
                    closeInlineEtapaComposer(true);
                    shared.showAjaxFlashMessage('A etapa não foi salva e o projeto permaneceu finalizado.', 'info');
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
                        'X-CSRFToken': currentPage.config.csrfToken || '',
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
                    if (response.status === 409 && data && data.confirmation_required) {
                        shared.showAjaxFlashMessage(data.message || 'Confirmação necessária para reativar o projeto.', 'warning');
                        return;
                    }
                    shared.showAjaxFlashMessage((data && data.message) || 'Erro ao adicionar etapa.', 'danger');
                    return;
                }

                if (data.project_status) {
                    shared.updateProjectStatusDisplay(data.project_status);
                }

                if (data.project_reactivated && typeof shared.ensureConcludeProjectButton === 'function') {
                    shared.ensureConcludeProjectButton();
                }

                shared.appendEtapaRow(data.etapa);
                if (data.warning) {
                    shared.showAjaxFlashMessage(data.warning, 'warning');
                }
                shared.showAjaxFlashMessage(data.message || 'Etapa adicionada com sucesso!', 'success');
                if (keepComposerOpen) {
                    inlineAddForm.reset();
                    resetInlineComposerDateValues();
                    syncInlineStatusControls();
                    resizeInlineDescricaoTextarea();
                    requestAnimationFrame(() => {
                        shared.ensureInlineComposerVisible();
                        if (inlineDescricaoInput) {
                            inlineDescricaoInput.focus();
                        }
                    });
                } else {
                    closeInlineEtapaComposer(true);
                }
            } catch (error) {
                console.error('Erro ao adicionar etapa inline:', error);
                shared.showAjaxFlashMessage('Erro de comunicação ao adicionar etapa.', 'danger');
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

        shared.openInlineEtapaComposer = openInlineEtapaComposer;
        shared.closeInlineEtapaComposer = closeInlineEtapaComposer;
        shared.submitInlineEtapaForm = submitInlineEtapaForm;
        shared.isInlineComposerOpen = isInlineComposerOpen;

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
                const currentDescricao = (inlineDescricaoInput ? inlineDescricaoInput.value : '').trim();
                if (!currentDescricao) {
                    if (inlineDescricaoInput) {
                        inlineDescricaoInput.focus();
                    }
                    return;
                }
                submitInlineEtapaForm({ keepComposerOpen: true });
            });
        }

        inlineDateInputs.forEach(input => {
            if (window.CalDatetimePicker) {
                CalDatetimePicker.initDatePicker(input);
            }
            input.addEventListener('input', function () {
                syncInlineDateEmptyState(input);
            });
            input.addEventListener('change', function () {
                syncInlineDateEmptyState(input);
            });
            if (!window.CalDatetimePicker) {
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
            }
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
                target && (
                    target.closest('#etapaInlineAddFormRow') ||
                    target.closest('#etapaInlineAddEntryRow') ||
                    target.closest('#btnOpenInlineEtapaAdd')
                )
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
    });
})();
