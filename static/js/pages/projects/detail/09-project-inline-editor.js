(function () {
    const page = window.ProjectDetailPage;
    if (!page || typeof page.registerInit !== 'function') {
        return;
    }

    page.registerInit('projectInlineEditor', function initProjectInlineEditor(currentPage) {
        const refs = currentPage.refs;
        const shared = currentPage.shared;
        const config = currentPage.config;

        let editDataCache = null;

        async function loadEditData() {
            if (editDataCache) {
                return editDataCache;
            }

            try {
                const response = await fetch(`/project/${config.projectId}/edit_data`);
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

        function createAreaSelect(currentValue) {
            const select = document.createElement('select');
            select.className = 'form-select form-select-sm';
            select.dataset.field = 'area_responsavel';
            select.dataset.originalValue = currentValue;

            const areas = shared.availableAreas;
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

        async function createOrgaoSelect(currentValue) {
            const data = await loadEditData();
            const orgaos = (data && data.available_orgaos) || [];

            const select = document.createElement('select');
            select.className = 'form-select form-select-sm';
            select.dataset.field = 'orgao_id';
            select.dataset.originalValue = currentValue || '';

            const placeholder = document.createElement('option');
            placeholder.value = '';
            placeholder.textContent = orgaos.length ? 'Selecione um órgão' : 'Nenhum órgão disponível';
            select.appendChild(placeholder);

            const currentId = currentValue ? String(currentValue) : '';
            orgaos.forEach(orgao => {
                const option = document.createElement('option');
                option.value = String(orgao.id);
                option.textContent = orgao.nome && orgao.nome !== orgao.sigla
                    ? `${orgao.sigla} — ${orgao.nome}`
                    : orgao.sigla;
                if (option.value === currentId) {
                    option.selected = true;
                }
                select.appendChild(option);
            });

            return select;
        }

        async function createObjetivoSelect(currentValue) {
            const data = await loadEditData();
            if (!data) {
                return null;
            }

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

            select.addEventListener('change', function () {
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
            if (!data) {
                return;
            }

            const resultadoEl = document.querySelector('[data-field="resultado_esperado_id"]');
            if (!resultadoEl || !resultadoEl.tagName || resultadoEl.tagName !== 'SELECT') {
                return;
            }

            const resultadoSelect = resultadoEl;
            resultadoSelect.innerHTML = '<option value="">Selecione um resultado esperado</option>';

            if (objetivoId && data.resultados_por_objetivo[objetivoId]) {
                data.resultados_por_objetivo[objetivoId].forEach(res => {
                    const option = document.createElement('option');
                    option.value = res.id;
                    option.textContent = res.descricao;
                    resultadoSelect.appendChild(option);
                });
            }

            if (!preserveValue) {
                updateIndicadoresContainer(null);
            }
        }

        async function createResultadoSelect(currentValue, objetivoId) {
            const data = await loadEditData();
            if (!data) {
                return null;
            }

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

            select.addEventListener('change', function () {
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
            if (!data) {
                return;
            }

            const indicadoresEl = document.querySelector('[data-field="indicadores_ids"]');
            if (!indicadoresEl) {
                return;
            }

            let selectedIds = [];
            if (preserveSelection) {
                try {
                    selectedIds = JSON.parse(indicadoresEl.dataset.originalValue || '[]');
                } catch (error) {
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
            if (!data) {
                return null;
            }

            const container = document.createElement('div');
            container.dataset.field = 'indicadores_ids';
            container.dataset.originalValue = JSON.stringify(currentValue);

            if (resultadoId && data.indicadores_por_resultado[resultadoId]) {
                let selectedIds = currentValue;
                if (typeof selectedIds === 'string') {
                    try {
                        selectedIds = JSON.parse(selectedIds);
                    } catch (error) {
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
                    { value: 'Suspenso', label: 'Suspenso' },
                ];
            } else if (field === 'prioridade') {
                options = [
                    { value: 'urgente', label: 'Urgente' },
                    { value: 'alta', label: 'Alta' },
                    { value: 'media', label: 'Média' },
                    { value: 'baixa', label: 'Baixa' },
                ];
            } else if (field === 'special_project') {
                options = [
                    { value: '', label: 'Nenhum' },
                    { value: 'ABEP', label: 'ABEP' },
                    { value: 'TCE', label: 'TCE' },
                ];
            } else if (field === 'delivery_type') {
                options = [
                    { value: '', label: 'Não informado' },
                    { value: 'Sistema', label: 'Sistema' },
                    { value: 'Painel', label: 'Painel' },
                    { value: 'Norma', label: 'Norma' },
                    { value: 'Instrumento de parceria', label: 'Instrumento de parceria' },
                    { value: 'Fluxo Processual', label: 'Fluxo Processual' },
                    { value: 'Outro', label: 'Outro' },
                ];
            }

            options.forEach(opt => {
                const option = document.createElement('option');
                option.value = opt.value;
                option.textContent = opt.label;
                if (opt.value === currentValue || opt.label === currentValue) {
                    option.selected = true;
                }
                select.appendChild(option);
            });

            return select;
        }

        function saveProjectInline() {
            const formData = {};

            document.querySelectorAll('[data-field]:not([data-etapa-id])').forEach(el => {
                const field = el.dataset.field;
                if (field === 'indicadores_ids') {
                    const checkboxes = el.querySelectorAll('.indicador-checkbox:checked');
                    formData[field] = Array.from(checkboxes).map(cb => parseInt(cb.value, 10));
                } else if (el.value !== undefined) {
                    formData[field] = el.value || null;
                }
            });

            refs.saveButton.disabled = true;
            refs.cancelButton.disabled = true;
            refs.saveButton.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Salvando...';

            fetch(`/project/${config.projectId}/update_inline`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                },
                body: JSON.stringify(formData),
            })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        shared.showAjaxFlashMessage(data.message || 'Projeto atualizado com sucesso!', 'success');
                        setTimeout(function () {
                            window.location.reload();
                        }, 1000);
                    } else {
                        shared.showAjaxFlashMessage(data.message || 'Erro ao atualizar projeto.', 'danger');
                        refs.saveButton.disabled = false;
                        refs.cancelButton.disabled = false;
                        refs.saveButton.innerHTML = '<i class="fas fa-save me-1"></i>Salvar';
                    }
                })
                .catch(error => {
                    console.error('Erro:', error);
                    shared.showAjaxFlashMessage('Erro de comunicação com o servidor.', 'danger');
                    refs.saveButton.disabled = false;
                    refs.cancelButton.disabled = false;
                    refs.saveButton.innerHTML = '<i class="fas fa-save me-1"></i>Salvar';
                });
        }

        function exitEditMode() {
            window.location.reload();
        }

        async function enterEditMode() {
            if (refs.projectCompactHeader) {
                refs.projectCompactHeader.classList.add('is-hidden-by-edit');
                if (typeof shared.setCompactHeaderVisible === 'function') {
                    shared.setCompactHeaderVisible(false);
                }
            }

            refs.editButton.style.display = 'none';
            if (refs.historyButton) {
                refs.historyButton.style.display = 'none';
            }
            if (refs.concludeButton) {
                refs.concludeButton.style.display = 'none';
            }
            if (refs.saveButton) {
                refs.saveButton.classList.remove('ds-hidden');
                refs.saveButton.style.display = 'inline-block';
            }
            if (refs.cancelButton) {
                refs.cancelButton.classList.remove('ds-hidden');
                refs.cancelButton.style.display = 'inline-block';
            }

            const backButton = document.querySelector('.btn-back-to-list');
            if (backButton) {
                backButton.style.display = 'none';
            }

            await loadEditData();

            const objetivoOriginal = document.querySelector('[data-field="objetivo_id"]')
                ? document.querySelector('[data-field="objetivo_id"]').dataset.value
                : '';
            const resultadoOriginal = document.querySelector('[data-field="resultado_esperado_id"]')
                ? document.querySelector('[data-field="resultado_esperado_id"]').dataset.value
                : '';

            const projectFields = document.querySelectorAll('[data-field]:not([data-etapa-id])');
            for (const el of projectFields) {
                const field = el.dataset.field;
                const currentValue = el.dataset.value || '';

                if (field === 'area_responsavel' && !shared.canEditAreaResponsavel) {
                    continue;
                }

                let input;
                if (field === 'orgao_id') {
                    input = await createOrgaoSelect(currentValue);
                } else if (field === 'objetivo_id') {
                    input = await createObjetivoSelect(currentValue);
                } else if (field === 'resultado_esperado_id') {
                    input = await createResultadoSelect(currentValue, objetivoOriginal);
                } else if (field === 'indicadores_ids') {
                    let ids = [];
                    try {
                        ids = JSON.parse(currentValue || '[]');
                    } catch (error) {
                        ids = [];
                    }
                    input = await createIndicadoresContainer(ids, resultadoOriginal);
                } else if (field === 'status' || field === 'prioridade' || field === 'special_project' || field === 'delivery_type') {
                    input = createSelectForField(field, currentValue);
                } else if (field === 'abep_indicator') {
                    input = shared.createAbepIndicatorCombobox(currentValue);
                } else if (field === 'area_responsavel') {
                    input = createAreaSelect(currentValue);
                } else if (field === 'observacao') {
                    input = document.createElement('textarea');
                    input.className = 'form-control form-control-sm';
                    input.rows = 3;
                    input.value = currentValue === 'Nenhuma observação registrada.' ? '' : (currentValue || '');
                    input.placeholder = 'Nenhuma observação registrada.';
                } else if (field === 'short_description') {
                    input = document.createElement('textarea');
                    input.className = 'form-control form-control-sm project-inline-input project-inline-input-description';
                    input.rows = 2;
                    input.value = currentValue || '';
                    input.placeholder = 'Adicione uma descrição...';
                } else if (field === 'titulo') {
                    input = document.createElement('input');
                    input.type = 'text';
                    input.className = 'form-control form-control-sm project-inline-input project-inline-input-title';
                    input.value = currentValue;
                    input.placeholder = 'Nome do projeto';
                } else {
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

        shared.createAreaSelect = createAreaSelect;
        shared.createSelectForField = createSelectForField;
        shared.saveProjectInline = saveProjectInline;
        shared.exitProjectEditMode = exitEditMode;

        if (refs.editButton) {
            refs.editButton.addEventListener('click', function (event) {
                event.preventDefault();
                enterEditMode();
            });
        }

        if (refs.saveButton) {
            refs.saveButton.addEventListener('click', function (event) {
                event.preventDefault();
                saveProjectInline();
            });
        }

        if (refs.cancelButton) {
            refs.cancelButton.addEventListener('click', function (event) {
                event.preventDefault();
                exitEditMode();
            });
        }

        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.get('edit') === 'true' && refs.editButton) {
            setTimeout(function () {
                enterEditMode();
                window.history.replaceState({}, document.title, window.location.pathname);
            }, 100);
        }
    });
})();
