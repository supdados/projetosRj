// === inline-form-controller.js — Controle de formulário inline de tarefas ===
(function (global) {
    var registry = global.AddItemInlineModules = global.AddItemInlineModules || {};

    registry.inlineFormController = function (ctx) {
        var addUrl = ctx.config.addUrl;
        var sugestoesUrl = ctx.config.sugestoesUrl;

        function requestAddItem(payload) {
            return new Promise(function (resolve, reject) {
                var dataPayload = payload || {};
                var descricao = (dataPayload.descricao || '').trim();
                var projectValue = ctx.normalizeProjectValue(dataPayload.project);

                if (!projectValue) {
                    reject(new Error('Projeto \u00e9 obrigat\u00f3rio.'));
                    return;
                }
                if (!descricao) {
                    reject(new Error('Descri\u00e7\u00e3o \u00e9 obrigat\u00f3ria.'));
                    return;
                }

                var formData = new FormData();
                formData.append('project', projectValue);
                formData.append('descricao', descricao);
                formData.append('status', dataPayload.status || 'nao_iniciada');
                formData.append('responsavel', (dataPayload.responsavel || '').trim());
                formData.append('prioridade', (dataPayload.prioridade || '').trim());
                formData.append('tipo_pedido', (dataPayload.tipo_pedido || '').trim());

                var xhr = new XMLHttpRequest();
                xhr.open('POST', addUrl);
                xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
                xhr.setRequestHeader('Accept', 'application/json');
                xhr.onload = function () {
                    try {
                        var data = JSON.parse(xhr.responseText);
                        if (data.success && data.item) {
                            resolve(data);
                        } else {
                            reject(new Error((data && data.message) || 'Erro ao adicionar tarefa.'));
                        }
                    } catch (err) {
                        reject(new Error('Erro ao adicionar tarefa. Tente novamente.'));
                    }
                };
                xhr.onerror = function () {
                    reject(new Error('Erro de conex\u00e3o. Tente novamente.'));
                };
                xhr.send(formData);
            });
        }

        function initializeAddRow(addRow, options) {
            if (!addRow) return null;
            if (addRow._taskHubController) return addRow._taskHubController;

            var opts = options || {};
            var placeholder = addRow.querySelector('[data-role="open-add-form"]');
            var formWrap = addRow.querySelector('[data-role="add-form"]');
            var addDesc = addRow.querySelector('[data-role="descricao"]');
            var addPrioridade = addRow.querySelector('[data-role="prioridade"]');
            var addTipo = addRow.querySelector('[data-role="tipo_pedido"]');
            var addStatus = addRow.querySelector('[data-role="status"]');
            var addResponsavelTrigger = addRow.querySelector('[data-role="responsavel-trigger"]');
            var cancelBtn = addRow.querySelector('[data-role="cancel-add"]');
            var submitBtn = addRow.querySelector('[data-role="submit-add"]');
            if (!placeholder || !formWrap || !addDesc || !addStatus || !addResponsavelTrigger || !cancelBtn || !submitBtn) return null;

            var responsavelNames = [];
            var isSubmitting = false;

            renderResponsavelPickerTrigger(addResponsavelTrigger, responsavelNames, 'Respons\u00e1vel');

            function getProjectValue() {
                if (typeof opts.getProjectValue === 'function') {
                    return ctx.normalizeProjectValue(opts.getProjectValue());
                }
                return ctx.normalizeProjectValue(addRow.getAttribute('data-project-value'));
            }

            function resizeTextarea() {
                addDesc.style.height = 'auto';
                addDesc.style.height = Math.max(32, addDesc.scrollHeight) + 'px';
            }

            function resetForm() {
                addDesc.value = '';
                addStatus.value = 'nao_iniciada';
                if (addPrioridade) addPrioridade.value = '';
                if (addTipo) addTipo.value = '';
                responsavelNames = [];
                renderResponsavelPickerTrigger(addResponsavelTrigger, responsavelNames, 'Respons\u00e1vel');
                resizeTextarea();
                refreshProjectState();
            }

            function refreshProjectState() {
                var hasProject = !!getProjectValue();
                addDesc.disabled = !hasProject;
                addStatus.disabled = !hasProject;
                if (addPrioridade) addPrioridade.disabled = !hasProject;
                if (addTipo) addTipo.disabled = !hasProject;
                addResponsavelTrigger.disabled = !hasProject;
                submitBtn.disabled = !hasProject;
                addDesc.placeholder = hasProject ? 'Descreva a tarefa...' : 'Selecione o projeto primeiro';
                if (!hasProject) {
                    responsavelPickerManager.closeIfAnchor(addResponsavelTrigger);
                }
            }

            function showForm() {
                placeholder.style.display = 'none';
                formWrap.removeAttribute('hidden');
                resetForm();
                if (getProjectValue()) {
                    setTimeout(function () {
                        addDesc.focus();
                    }, 30);
                }
            }

            function hideForm() {
                formWrap.setAttribute('hidden', '');
                placeholder.style.display = 'flex';
                responsavelPickerManager.closeIfAnchor(addResponsavelTrigger);
            }

            function focusDescription() {
                if (formWrap.hasAttribute('hidden')) {
                    showForm();
                    return;
                }
                if (getProjectValue()) {
                    addDesc.focus();
                }
            }

            function submitForm(keepOpen) {
                if (isSubmitting) return;

                var projectValue = getProjectValue();
                if (!projectValue) {
                    if (typeof opts.focusProjectSelector === 'function') {
                        opts.focusProjectSelector();
                    }
                    return;
                }

                var descricao = (addDesc.value || '').trim();
                if (!descricao) {
                    addDesc.focus();
                    return;
                }

                isSubmitting = true;
                requestAddItem({
                    project: projectValue,
                    descricao: descricao,
                    status: addStatus.value || 'nao_iniciada',
                    responsavel: responsavelNames.join(', '),
                    prioridade: addPrioridade ? addPrioridade.value : '',
                    tipo_pedido: addTipo ? addTipo.value : '',
                })
                    .then(function (data) {
                        ctx.insertNewItem(data, {
                            addRow: addRow,
                            projectValue: projectValue,
                            sourceGroup: addRow.closest('.task-hub-group'),
                            focusInserted: !!opts.isGlobalPlaceholder,
                        });

                        if (keepOpen && !opts.isGlobalPlaceholder) {
                            resetForm();
                            return;
                        }
                        hideForm();
                    })
                    .catch(function (error) {
                        alert((error && error.message) || 'Erro ao adicionar tarefa.');
                    })
                    .finally(function () {
                        isSubmitting = false;
                    });
            }

            placeholder.addEventListener('click', showForm);
            cancelBtn.addEventListener('click', function () {
                if (typeof opts.onCancel === 'function') {
                    opts.onCancel();
                    return;
                }
                hideForm();
            });
            submitBtn.addEventListener('click', function () {
                submitForm(false);
            });
            addDesc.addEventListener('input', resizeTextarea);
            addDesc.addEventListener('keydown', function (event) {
                if (event.key === 'Escape') {
                    event.preventDefault();
                    if (typeof opts.onCancel === 'function') {
                        opts.onCancel();
                        return;
                    }
                    hideForm();
                    return;
                }
                if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    submitForm(!opts.isGlobalPlaceholder);
                }
            });

            addResponsavelTrigger.addEventListener('click', function (event) {
                event.preventDefault();
                event.stopPropagation();

                var projectValue = getProjectValue();
                if (!projectValue) {
                    if (typeof opts.focusProjectSelector === 'function') {
                        opts.focusProjectSelector();
                    }
                    alert('Selecione um projeto para escolher respons\u00e1veis.');
                    return;
                }

                responsavelPickerManager.open({
                    anchorEl: addResponsavelTrigger,
                    sugestoesUrl: sugestoesUrl,
                    projectValue: projectValue,
                    initialRawValue: responsavelNames.join(', '),
                    onApply: function (payload) {
                        responsavelNames = payload.names.slice();
                        renderResponsavelPickerTrigger(addResponsavelTrigger, responsavelNames, 'Respons\u00e1vel');
                        return true;
                    },
                });
            });

            document.addEventListener('mousedown', function (event) {
                if (!document.body.contains(addRow)) return;
                if (formWrap.hasAttribute('hidden')) return;
                if (isSubmitting) return;
                if (typeof opts.containsTarget === 'function' && opts.containsTarget(event.target)) return;
                if (addRow.contains(event.target)) return;
                if (responsavelPickerManager.isEventInsidePopover(event.target)) return;
                if ((addDesc.value || '').trim()) {
                    submitForm(false);
                    return;
                }
                if (typeof opts.onCancel === 'function') {
                    opts.onCancel();
                    return;
                }
                hideForm();
            });

            refreshProjectState();
            addRow._taskHubController = {
                open: showForm,
                close: hideForm,
                focus: focusDescription,
                focusDescription: function () {
                    if (formWrap.hasAttribute('hidden')) {
                        showForm();
                        return;
                    }
                    addDesc.focus();
                },
                refreshProjectState: refreshProjectState,
            };
            return addRow._taskHubController;
        }

        function focusGlobalCreateInList(options) {
            var groupEl = ctx.ensureGlobalPlaceholderGroup(options);
            if (!groupEl) return false;

            if (!ctx.config.selectedProject && options && options.projectValue) {
                ctx.setGlobalPlaceholderProject(groupEl, options.projectValue);
            }

            var addRow = groupEl.querySelector('.task-hub-add-row');
            if (addRow && addRow._taskHubController && typeof addRow._taskHubController.open === 'function') {
                addRow._taskHubController.open();
                return true;
            }
            return false;
        }

        function focusInlineAdd(projectValue) {
            var normalized = ctx.normalizeProjectValue(projectValue);
            var addRow = ctx.getAddRowByProject(normalized, { includePlaceholder: false });
            if (addRow && addRow._taskHubController && typeof addRow._taskHubController.focus === 'function') {
                addRow.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                addRow._taskHubController.focus();
                return true;
            }
            return focusGlobalCreateInList({ projectValue: normalized });
        }

        function bindCreateButton() {
            var createButton = ctx.refs.createButton;
            if (!createButton) return;

            createButton.addEventListener('click', function () {
                var kanban = window.taskItemsKanban;
                var currentView = kanban && typeof kanban.getCurrentView === 'function'
                    ? kanban.getCurrentView()
                    : 'list';

                if (currentView === 'kanban') {
                    if (kanban && typeof kanban.focusComposerForStatus === 'function' && kanban.focusComposerForStatus('nao_iniciada')) {
                        return;
                    }
                    if (kanban && typeof kanban.applyView === 'function') {
                        kanban.applyView('list');
                    }
                }

                focusGlobalCreateInList();
            });
        }

        ctx.requestAddItem = requestAddItem;
        ctx.initializeAddRow = initializeAddRow;
        ctx.focusGlobalCreateInList = focusGlobalCreateInList;
        ctx.focusInlineAdd = focusInlineAdd;
        ctx.bindCreateButton = bindCreateButton;
    };
})(window);
