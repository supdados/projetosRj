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
        const HEADER_CHIP_EDIT_LABELS = {
            status: 'Status',
            prioridade: 'Prioridade',
            delivery_type: 'Tipo',
            special_project: 'Categoria',
        };

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
                // Apenas a sigla — coerente com o modo de visualização.
                // Nome completo fica disponível no `title` para tooltip.
                option.textContent = orgao.sigla;
                if (orgao.nome && orgao.nome !== orgao.sigla) {
                    option.title = orgao.nome;
                }
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

        function prepareHeaderChipEditor(input, sourceEl, field) {
            if (!input || !sourceEl || !sourceEl.closest('.project-header-chips')) {
                return null;
            }

            const rect = sourceEl.getBoundingClientRect();
            const width = Math.max(1, Math.ceil(rect.width || 0));
            const height = Math.max(1, Math.ceil(rect.height || 0));
            const safeField = String(field || 'field').replace(/[^a-z0-9_-]+/gi, '-').toLowerCase();
            const labelText = HEADER_CHIP_EDIT_LABELS[field] || field;

            const wrapper = document.createElement('span');
            wrapper.className = `project-header-chip-edit-wrap project-header-chip-edit-wrap--${safeField}`;
            wrapper.dataset.minWidth = String(width);
            wrapper.style.setProperty('--ph-editor-width', `${width}px`);
            wrapper.style.setProperty('--ph-editor-height', `${height}px`);

            const label = document.createElement('span');
            label.className = 'project-header-chip-edit-label';
            label.textContent = labelText;

            input.classList.add('project-header-chip-editor', `project-header-chip-editor--${safeField}`);
            input.setAttribute('aria-label', sourceEl.getAttribute('aria-label') || sourceEl.textContent.trim());

            wrapper.appendChild(label);
            wrapper.appendChild(input);
            resizeHeaderChipSelect(input);
            input.addEventListener('change', function () {
                resizeHeaderChipSelect(input);
            });
            return wrapper;
        }

        function getSelectedOptionText(select) {
            if (!select || select.tagName !== 'SELECT') {
                return '';
            }
            const selected = select.options[select.selectedIndex];
            return selected ? selected.textContent.trim() : '';
        }

        function resizeHeaderChipSelect(select) {
            if (!select || !select.classList.contains('project-header-chip-editor')) {
                return;
            }

            const wrapper = select.closest('.project-header-chip-edit-wrap');
            if (!wrapper) {
                return;
            }

            const minWidth = Number(wrapper.dataset.minWidth || '0') || 0;
            const selectedLabel = getSelectedOptionText(select);
            const estimatedWidth = Math.ceil((selectedLabel.length * 7.4) + 42);
            const width = Math.max(minWidth, estimatedWidth);

            wrapper.style.setProperty('--ph-editor-width', `${width}px`);
        }

        function resizeProjectHeaderTextEditor(input) {
            if (!input) {
                return;
            }

            const isDescription = (
                input.classList.contains('project-header-text-editor--short-description')
                || input.classList.contains('project-header-text-editor--short_description')
            );
            const maxWidth = Number(input.dataset.visualMaxWidth || input.dataset.visualWidth || '0') || 0;
            const measuredWidth = measureProjectHeaderTextWidth(input);
            const minWidth = isDescription ? 72 : 180;
            const nextWidth = maxWidth
                ? Math.min(maxWidth, Math.max(minWidth, measuredWidth))
                : Math.max(minWidth, measuredWidth);
            input.style.setProperty('--ph-text-editor-width', `${nextWidth}px`);
            input.style.setProperty('--ph-text-editor-max-width', maxWidth ? `${maxWidth}px` : '100%');
            if (input.tagName === 'TEXTAREA') {
                const style = window.getComputedStyle(input);
                const verticalPadding = parseFloat(style.paddingTop || '0') + parseFloat(style.paddingBottom || '0');
                const lineHeight = parseFloat(style.lineHeight || '0') || (parseFloat(style.fontSize || '0') * 1.2) || 18;
                input.style.height = 'auto';
                const contentHeight = input.scrollHeight - verticalPadding;
                input.style.height = `${Math.max(contentHeight, lineHeight)}px`;
            }
        }

        function measureProjectHeaderTextWidth(input) {
            const style = window.getComputedStyle(input);
            const canvas = measureProjectHeaderTextWidth.canvas || document.createElement('canvas');
            measureProjectHeaderTextWidth.canvas = canvas;
            const context = canvas.getContext('2d');
            if (!context) {
                return Number(input.dataset.visualMaxWidth || input.dataset.visualWidth || '220') || 220;
            }
            context.font = [
                style.fontStyle,
                style.fontVariant,
                style.fontWeight,
                style.fontSize,
                style.fontFamily,
            ].filter(Boolean).join(' ');

            const rawText = input.value || input.getAttribute('placeholder') || '';
            const lines = rawText.split(/\r?\n/);
            const longestWidth = lines.reduce((max, line) => {
                const text = line || ' ';
                return Math.max(max, context.measureText(text).width);
            }, 0);
            return Math.ceil(longestWidth + 24);
        }

        function prepareProjectHeaderTextEditor(input, sourceEl, field) {
            if (!input || !sourceEl || !sourceEl.closest('.project-header')) {
                return;
            }

            const safeField = String(field || 'field').replace(/[^a-z0-9]+/gi, '-').toLowerCase();
            const sourceWidth = Math.ceil(sourceEl.getBoundingClientRect().width || 0);
            const sourceContainer = sourceEl.closest('.project-header-main-content');
            const maxWidth = Math.ceil(
                (sourceContainer ? sourceContainer.getBoundingClientRect().width : 0) || sourceWidth || 0
            );
            const sourceStyle = window.getComputedStyle(sourceEl);
            if (sourceWidth) {
                input.dataset.visualWidth = String(sourceWidth);
            }
            if (maxWidth) {
                input.dataset.visualMaxWidth = String(maxWidth);
            }
            input.style.setProperty('--ph-text-editor-font-family', sourceStyle.fontFamily);
            input.style.setProperty('--ph-text-editor-font-size', sourceStyle.fontSize);
            input.style.setProperty('--ph-text-editor-font-weight', sourceStyle.fontWeight);
            input.style.setProperty('--ph-text-editor-line-height', sourceStyle.lineHeight);
            input.style.setProperty('--ph-text-editor-letter-spacing', sourceStyle.letterSpacing);
            input.classList.add('project-header-text-editor', `project-header-text-editor--${safeField}`);
            resizeProjectHeaderTextEditor(input);
            input.addEventListener('input', function () {
                resizeProjectHeaderTextEditor(input);
            });
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
                    input.className = 'form-control form-control-sm project-observacao-editor';
                    input.rows = 3;
                    input.value = currentValue === 'Nenhuma observação registrada.' ? '' : (currentValue || '');
                    input.placeholder = 'Nenhuma observação registrada.';
                } else if (field === 'short_description') {
                    input = document.createElement('textarea');
                    input.className = 'form-control form-control-sm project-inline-input project-inline-input-description';
                    input.rows = 1;
                    input.value = currentValue || '';
                    input.placeholder = 'Descrição';
                } else if (field === 'titulo') {
                    input = document.createElement('textarea');
                    input.className = 'form-control form-control-sm project-inline-input project-inline-input-title';
                    input.rows = 1;
                    input.value = currentValue;
                    input.placeholder = 'Nome do projeto';
                } else {
                    input = document.createElement('input');
                    input.type = 'text';
                    input.className = field === 'github_link' || field === 'documentation_link'
                        ? 'form-control form-control-sm project-additional-link-editor'
                        : 'form-control form-control-sm';
                    input.value = currentValue || '';
                    if (!currentValue || String(currentValue).trim() === '') {
                        input.placeholder = 'Não informado';
                    }
                }

                if (input) {
                    input.dataset.field = field;
                    input.dataset.originalValue = currentValue;
                    prepareProjectHeaderTextEditor(input, el, field);
                    const replacement = prepareHeaderChipEditor(input, el, field) || input;
                    el.replaceWith(replacement);
                    if (input.classList.contains('project-header-text-editor')) {
                        resizeProjectHeaderTextEditor(input);
                    }
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
