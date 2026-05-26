(function (global) {
    var registry = global.TaskItemsKanbanModules = global.TaskItemsKanbanModules || {};

    registry.composer = function registerComposer(ctx) {
        var refs = ctx.refs;
        var state = ctx.state;
        var etapaCacheByProject = {};

        // Busca (e cacheia) as etapas de um projeto via endpoint AJAX. O template
        // injeta `projectEtapasUrlTemplate` com `project_id=0`; trocamos pelo id real.
        ctx.fetchEtapasForProject = function fetchEtapasForProject(projectValue) {
            if (etapaCacheByProject[projectValue]) {
                return Promise.resolve(etapaCacheByProject[projectValue]);
            }
            var template = (window.TASK_HUB_CONFIG && window.TASK_HUB_CONFIG.projectEtapasUrlTemplate) || '';
            if (!template) return Promise.resolve([]);
            var url = template.replace(/\/0\/etapas(\?|$)/, '/' + encodeURIComponent(projectValue) + '/etapas$1');

            return fetch(url, {
                headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' },
                credentials: 'same-origin',
            })
                .then(function (response) { return response.json(); })
                .then(function (data) {
                    var etapas = (data && data.success && Array.isArray(data.etapas)) ? data.etapas : [];
                    etapaCacheByProject[projectValue] = etapas;
                    return etapas;
                });
        };

        function bindKanbanComposers() {
            state.composerControllers = {};
            var composers = refs.kanbanView.querySelectorAll('.task-items-kanban-composer[data-status]');
            var selectedProjectFromFilter = (
                window.TASK_HUB_CONFIG &&
                String(window.TASK_HUB_CONFIG.selectedProject || '').trim()
            ) || '';
            var selectedOrgaoFromFilter = (
                window.TASK_HUB_CONFIG &&
                String(window.TASK_HUB_CONFIG.selectedOrgao || '').trim()
            ) || '';

            function ensureComposerVisible(composerEl, focusEl, attempt) {
                if (!composerEl || typeof composerEl.getBoundingClientRect !== 'function') return;
                requestAnimationFrame(function () {
                    var tries = Number.isFinite(attempt) ? attempt : 0;
                    var verticalTarget = focusEl && !focusEl.hasAttribute('hidden') ? focusEl : composerEl;
                    var rect = verticalTarget.getBoundingClientRect();
                    var viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
                    var viewportWidth = window.innerWidth || document.documentElement.clientWidth || 0;
                    if (!viewportHeight) return;
                    var topLimit = 90;
                    var bottomLimit = viewportHeight - 22;
                    var deltaY = 0;
                    if (rect.top < topLimit) {
                        deltaY = rect.top - topLimit;
                    } else if (rect.bottom > bottomLimit) {
                        deltaY = rect.bottom - bottomLimit;
                    }
                    if (Math.abs(deltaY) > 1) {
                        window.scrollTo({
                            top: Math.max(0, (window.scrollY || window.pageYOffset || 0) + deltaY),
                            behavior: 'smooth'
                        });
                        if (tries < 2) {
                            setTimeout(function () {
                                ensureComposerVisible(composerEl, focusEl, tries + 1);
                            }, 220);
                        }
                    }

                    var needsInlineAdjust = viewportWidth && (rect.left < 12 || rect.right > (viewportWidth - 12));
                    if (needsInlineAdjust && typeof composerEl.scrollIntoView === 'function') {
                        composerEl.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
                    }
                    var isBaseVisible = rect.bottom <= bottomLimit;
                    if (!isBaseVisible && tries < 2) {
                        setTimeout(function () {
                            ensureComposerVisible(composerEl, focusEl, tries + 1);
                        }, 180);
                    }
                });
            }

            composers.forEach(function (composer) {
                var status = ctx.normalizeStatus(composer.getAttribute('data-status') || 'nao_iniciada');
                var addBtn = composer.querySelector('.task-items-kanban-add-btn[data-status]');
                var form = composer.querySelector('.task-items-kanban-add-form[data-status]');
                var desc = form ? form.querySelector('.task-items-kanban-add-desc') : null;
                var ownerTrigger = form ? form.querySelector('.task-items-kanban-add-owner[data-role="responsavel-trigger"]') : null;
                var cancelBtn = form ? form.querySelector('.task-items-kanban-add-cancel') : null;
                if (!addBtn || !form || !desc || !ownerTrigger || !cancelBtn) return;

                var selectedNames = [];
                var isSaving = false;
                var prioSelect = form.querySelector('.task-items-kanban-add-prioridade');
                var tipoSelect = form.querySelector('.task-items-kanban-add-tipo');
                var projectInput = form.querySelector('.task-items-kanban-add-project-input[data-role="project-input"]');
                var projectValueInput = form.querySelector('.task-items-kanban-add-project-value[data-role="project-value"]');
                var projectDropdown = form.querySelector('.task-hub-kanban-project-dropdown[data-role="project-dropdown"]');
                var etapaWrap = form.querySelector('[data-role="etapa-wrap"]');
                var etapaSelect = form.querySelector('[data-role="etapa-select"]');
                var etapaLoadedFor = null;
                renderResponsavelPickerTrigger(ownerTrigger, selectedNames, 'Responsável');

                function getComposerProjectValue() {
                    if (selectedProjectFromFilter) return selectedProjectFromFilter;
                    if (projectValueInput) return (projectValueInput.value || '').trim();
                    return '';
                }

                function getComposerEtapaValue() {
                    if (!etapaSelect || !etapaWrap || etapaWrap.hasAttribute('hidden')) return '';
                    return (etapaSelect.value || '').trim();
                }

                function clearEtapaOptions() {
                    while (etapaSelect.firstChild) {
                        etapaSelect.removeChild(etapaSelect.firstChild);
                    }
                    var semEtapa = document.createElement('option');
                    semEtapa.value = 'sem_etapa';
                    semEtapa.textContent = 'Sem etapa';
                    etapaSelect.appendChild(semEtapa);
                    etapaSelect.value = 'sem_etapa';
                }

                function resetEtapaPicker() {
                    etapaLoadedFor = null;
                    if (!etapaSelect || !etapaWrap) return;
                    clearEtapaOptions();
                    etapaWrap.setAttribute('hidden', '');
                }

                // Busca as etapas do projeto selecionado e popula o campo "Etapa".
                // O resultado é cacheado por projeto (ctx.etapaCacheByProject) para
                // evitar refetch entre as colunas do kanban (uma por status). Etapas
                // concluídas entram desabilitadas — o backend recusa tarefa nelas.
                function loadEtapasForProject(projectValue) {
                    if (!etapaSelect || !etapaWrap) return;
                    var normalized = (projectValue || '').trim();
                    if (!normalized || normalized === 'sem_projeto') {
                        resetEtapaPicker();
                        return;
                    }
                    if (etapaLoadedFor === normalized) return;

                    // Esconde/zera imediatamente as etapas do projeto anterior. Enquanto o
                    // fetch do novo projeto não resolve, o campo fica oculto e
                    // getComposerEtapaValue() retorna '' — evita submeter uma etapa do
                    // projeto antigo (que o backend recusaria: "Etapa não pertence...").
                    resetEtapaPicker();

                    ctx.fetchEtapasForProject(normalized)
                        .then(function (etapas) {
                            if (getComposerProjectValue() !== normalized) return;
                            clearEtapaOptions();
                            etapas.forEach(function (etapa) {
                                var option = document.createElement('option');
                                option.value = etapa.value;
                                option.textContent = etapa.done
                                    ? etapa.label + ' (concluída)'
                                    : etapa.label;
                                if (etapa.done) option.disabled = true;
                                etapaSelect.appendChild(option);
                            });
                            etapaWrap.removeAttribute('hidden');
                            etapaLoadedFor = normalized;
                        })
                        .catch(function () {
                            resetEtapaPicker();
                        });
                }

                function setupComposerProjectPicker() {
                    if (!projectInput || !projectValueInput || !projectDropdown) return;
                    var options = Array.prototype.slice.call(projectDropdown.querySelectorAll('.project-search-option[data-value]'));
                    var emptyState = projectDropdown.querySelector('[data-empty-state="1"]');

                    function filterOptions() {
                        var q = (projectInput.value || '').trim().toLowerCase();
                        var visibleCount = 0;
                        options.forEach(function (opt) {
                            var label = (opt.getAttribute('data-label') || opt.textContent || '').toLowerCase();
                            var isVisible = !q || label.indexOf(q) !== -1;
                            opt.classList.toggle('hidden-by-filter', !isVisible);
                            if (isVisible) visibleCount += 1;
                        });
                        if (emptyState) {
                            emptyState.hidden = visibleCount > 0;
                        }
                    }

                    function showDrop() {
                        filterOptions();
                        projectDropdown.removeAttribute('hidden');
                        projectInput.setAttribute('aria-expanded', 'true');
                    }

                    function hideDrop() {
                        projectDropdown.setAttribute('hidden', '');
                        projectInput.setAttribute('aria-expanded', 'false');
                    }

                    function selectOption(optionEl) {
                        var value = (optionEl.getAttribute('data-value') || '').trim();
                        var label = optionEl.getAttribute('data-label') || optionEl.textContent || '';
                        projectValueInput.value = value;
                        projectInput.value = label;
                        hideDrop();
                        loadEtapasForProject(value);
                    }

                    projectInput.addEventListener('focus', showDrop);
                    projectInput.addEventListener('input', showDrop);
                    projectInput.addEventListener('keydown', function (event) {
                        if (event.key === 'Escape') {
                            hideDrop();
                            return;
                        }

                        var visibleOptions = options.filter(function (opt) {
                            return !opt.classList.contains('hidden-by-filter');
                        });
                        if (!visibleOptions.length) return;

                        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                            event.preventDefault();
                            var active = projectDropdown.querySelector('.project-search-option.active');
                            var idx = visibleOptions.indexOf(active);
                            if (event.key === 'ArrowDown') {
                                idx = idx < 0 ? 0 : Math.min(idx + 1, visibleOptions.length - 1);
                            } else {
                                idx = idx < 0 ? visibleOptions.length - 1 : Math.max(idx - 1, 0);
                            }
                            visibleOptions.forEach(function (opt, i) {
                                opt.classList.toggle('active', i === idx);
                            });
                            visibleOptions[idx].scrollIntoView({ block: 'nearest' });
                        } else if (event.key === 'Enter') {
                            var current = projectDropdown.querySelector('.project-search-option.active');
                            if (current && !current.classList.contains('hidden-by-filter')) {
                                event.preventDefault();
                                selectOption(current);
                            }
                        }
                    });

                    options.forEach(function (opt) {
                        opt.addEventListener('click', function () {
                            selectOption(opt);
                        });
                    });

                    document.addEventListener('mousedown', function (event) {
                        if (!composer.contains(event.target)) hideDrop();
                    });
                }

                setupComposerProjectPicker();

                function openComposer() {
                    if (state.isDeleting || state.isPersisting) return;
                    Object.keys(state.composerControllers).forEach(function (key) {
                        if (key === status || !state.composerControllers[key]) return;
                        state.composerControllers[key].close(true);
                    });
                    addBtn.setAttribute('hidden', '');
                    form.removeAttribute('hidden');
                    // Projeto travado (filtro/rota de projeto): carrega etapas na abertura,
                    // já que não há dropdown de projeto para disparar o carregamento.
                    if (selectedProjectFromFilter) {
                        loadEtapasForProject(selectedProjectFromFilter);
                    }
                    ensureComposerVisible(composer, form, 0);
                    setTimeout(function () {
                        desc.focus();
                        ensureComposerVisible(composer, form, 0);
                    }, 30);
                    setTimeout(function () {
                        ensureComposerVisible(composer, form, 0);
                    }, 180);
                }

                function closeComposer(resetValues) {
                    form.setAttribute('hidden', '');
                    addBtn.removeAttribute('hidden');
                    responsavelPickerManager.closeIfAnchor(ownerTrigger);
                    if (resetValues) {
                        desc.value = '';
                        if (prioSelect) prioSelect.value = '';
                        if (tipoSelect) tipoSelect.value = '';
                        if (!selectedProjectFromFilter && projectInput && projectValueInput) {
                            projectInput.value = '';
                            projectValueInput.value = '';
                            resetEtapaPicker();
                        } else if (etapaSelect) {
                            etapaSelect.value = 'sem_etapa';
                        }
                        selectedNames = [];
                        renderResponsavelPickerTrigger(ownerTrigger, selectedNames, 'Responsável');
                    }
                }

                function isComposerOpen() {
                    return !form.hasAttribute('hidden');
                }

                function hasComposerValue() {
                    if ((desc.value || '').trim()) return true;
                    if (selectedNames.length) return true;
                    if (prioSelect && (prioSelect.value || '').trim()) return true;
                    if (tipoSelect && (tipoSelect.value || '').trim()) return true;
                    // Projeto + etapa escolhidos mantêm o composer aberto ao clicar fora.
                    // Sem descrição, trySubmitComposerOutside() não envia — só preserva a
                    // seleção em vez de fechar e perder projeto/etapa.
                    var etapaValue = getComposerEtapaValue();
                    if (getComposerProjectValue() && etapaValue && etapaValue !== 'sem_etapa') return true;
                    return false;
                }

                function submitComposer(event) {
                    if (event && typeof event.preventDefault === 'function') {
                        event.preventDefault();
                    }
                    if (isSaving || state.isDeleting || state.isPersisting) return;
                    if (!window.taskItemsListBridge || typeof window.taskItemsListBridge.requestAddItem !== 'function') {
                        alert('Fluxo de adição indisponível.');
                        return;
                    }

                    var descricao = (desc.value || '').trim();
                    if (!descricao) {
                        desc.focus();
                        return;
                    }
                    var composerProject = getComposerProjectValue();
                    if (!composerProject) {
                        if (projectInput) {
                            projectInput.focus();
                        }
                        alert('Selecione um projeto para criar a tarefa.');
                        return;
                    }

                    isSaving = true;
                    composer.classList.add('is-saving');
                    window.taskItemsListBridge.requestAddItem({
                        project: composerProject,
                        etapa: getComposerEtapaValue(),
                        descricao: descricao,
                        status: status,
                        responsavel: selectedNames.join(', '),
                        prioridade: prioSelect ? prioSelect.value : '',
                        tipo_pedido: tipoSelect ? tipoSelect.value : '',
                    })
                        .then(function (data) {
                            window.taskItemsListBridge.insertItemFromPayload(data, { projectValue: composerProject });
                            closeComposer(true);
                            if (state.currentView === 'kanban') {
                                ctx.renderKanbanFromList();
                                var newItemId = data && data.item && String(data.item.id);
                                if (newItemId) {
                                    var newCard = refs.board.querySelector('.task-items-kanban-card[data-item-id="' + newItemId + '"]');
                                    var targetDropzone = ctx.getDropzone(status);
                                    if (newCard && targetDropzone) {
                                        targetDropzone.appendChild(newCard);
                                    }
                                }
                            }
                        })
                        .catch(function (error) {
                            alert((error && error.message) || 'Erro ao adicionar tarefa.');
                        })
                        .finally(function () {
                            isSaving = false;
                            composer.classList.remove('is-saving');
                        });
                }

                function trySubmitComposerOutside() {
                    if (isSaving || state.isDeleting || state.isPersisting) return false;
                    var descricao = (desc.value || '').trim();
                    if (!descricao) return false;
                    submitComposer();
                    return true;
                }

                addBtn.addEventListener('click', function () {
                    openComposer();
                });
                cancelBtn.addEventListener('click', function () {
                    closeComposer(true);
                });
                form.addEventListener('submit', submitComposer);
                desc.addEventListener('keydown', function (event) {
                    if (event.key === 'Escape') {
                        event.preventDefault();
                        closeComposer(true);
                        return;
                    }
                    if (event.key === 'Enter' && !event.shiftKey) {
                        event.preventDefault();
                        submitComposer(event);
                    }
                });
                ownerTrigger.addEventListener('click', function (event) {
                    event.preventDefault();
                    event.stopPropagation();
                    if (isSaving || state.isDeleting || state.isPersisting) return;
                    var composerProject = getComposerProjectValue();
                    if (!composerProject && !selectedOrgaoFromFilter) {
                        if (projectInput) projectInput.focus();
                        alert('Selecione um projeto para escolher responsáveis.');
                        return;
                    }
                    responsavelPickerManager.open({
                        anchorEl: ownerTrigger,
                        taskId: ctx.taskId,
                        sugestoesUrl: refs.listEl.getAttribute('data-sugestoes-url') || '',
                        projectValue: composerProject,
                        orgaoValue: !composerProject ? selectedOrgaoFromFilter : '',
                        initialRawValue: selectedNames.join(', '),
                        onApply: function (payload) {
                            selectedNames = payload.names.slice();
                            renderResponsavelPickerTrigger(ownerTrigger, selectedNames, 'Responsável');
                            return true;
                        },
                    });
                });

                state.composerControllers[status] = {
                    open: openComposer,
                    close: closeComposer,
                    isOpen: isComposerOpen,
                    hasValue: hasComposerValue,
                    trySubmitOutside: trySubmitComposerOutside,
                    containsTarget: function (target) {
                        return !!(target && composer.contains(target));
                    },
                    focus: function () {
                        openComposer();
                        setTimeout(function () { desc.focus(); }, 20);
                    },
                };
            });

            document.addEventListener('mousedown', function (event) {
                if (state.currentView !== 'kanban') return;
                if (responsavelPickerManager.isEventInsidePopover(event.target)) return;
                Object.keys(state.composerControllers).forEach(function (key) {
                    var controller = state.composerControllers[key];
                    if (!controller || typeof controller.isOpen !== 'function' || !controller.isOpen()) return;
                    if (typeof controller.containsTarget === 'function' && controller.containsTarget(event.target)) return;
                    if (typeof controller.hasValue === 'function' && controller.hasValue()) {
                        if (typeof controller.trySubmitOutside === 'function' && controller.trySubmitOutside()) return;
                        return;
                    }
                    controller.close(true);
                });
            });
        }

        function focusComposerForStatus(status) {
            if (state.currentView !== 'kanban') return false;
            var normalized = ctx.normalizeStatus(status || 'nao_iniciada');
            var controller = state.composerControllers[normalized];
            if (!controller || typeof controller.focus !== 'function') return false;
            var column = refs.kanbanView.querySelector('.task-items-kanban-column[data-status="' + normalized + '"]');
            if (column && typeof column.scrollIntoView === 'function') {
                column.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
            }
            controller.focus();
            return true;
        }

        ctx.bindKanbanComposers = bindKanbanComposers;
        ctx.focusComposerForStatus = focusComposerForStatus;
    };
})(window);
