// === add-item-inline.js — IIFE de adicao inline de tarefas ===
// --- Adicionar tarefa inline (hub com multiplos projetos) ---
(function () {
    var listEl = document.querySelector('.task-items-list');
    if (!listEl) return;

    var listView = document.getElementById('taskItemsListView');
    var createButton = document.getElementById('taskHubCreateButton');
    var addUrl = listEl.getAttribute('data-add-item-url');
    var sugestoesUrl = listEl.getAttribute('data-sugestoes-url');
    if (!addUrl) return;

    var config = window.TASK_HUB_CONFIG || {};
    var selectedArea = String(config.selectedArea || '').trim();
    var selectedProject = normalizeProjectValue(config.selectedProject || '');
    var selectedProjectLabel = String(config.selectedProjectLabel || '').trim();
    var projectOptions = Array.isArray(config.projectOptions)
        ? config.projectOptions.map(normalizeProjectOption).filter(function (option) { return !!option; })
        : [];

    function escapeHtml(text) {
        var div = document.createElement('div');
        div.textContent = text == null ? '' : String(text);
        return div.innerHTML;
    }

    function normalizeProjectValue(value) {
        var normalized = String(value == null ? '' : value).trim();
        return normalized || '';
    }

    function normalizeProjectOption(option) {
        if (!option || typeof option !== 'object') return null;
        var value = normalizeProjectValue(option.value);
        if (!value) return null;
        return {
            value: value,
            label: String(option.label || '').trim() || 'Projeto',
            area: String(option.area || '').trim(),
        };
    }

    function getProjectOptionByValue(projectValue) {
        var normalized = normalizeProjectValue(projectValue);
        if (!normalized) return null;
        for (var i = 0; i < projectOptions.length; i += 1) {
            if (projectOptions[i].value === normalized) {
                return projectOptions[i];
            }
        }
        return null;
    }

    function getProjectOptionsForPicker() {
        if (!selectedArea) {
            return projectOptions.slice();
        }

        var selectedAreaKey = selectedArea.toLowerCase();
        return projectOptions.filter(function (option) {
            var optionArea = String(option && option.area || '').trim().toLowerCase();
            return !!optionArea && optionArea === selectedAreaKey;
        });
    }

    function getProjectInfo(projectValue, fallbackLabel, fallbackArea) {
        var normalized = normalizeProjectValue(projectValue);
        var option = getProjectOptionByValue(normalized);
        return {
            value: normalized,
            label: option ? option.label : (fallbackLabel || (normalized === 'sem_projeto' ? 'Sem projeto' : 'Projeto')),
            area: option ? option.area : String(fallbackArea || '').trim(),
        };
    }

    function buildProjectDetailUrl(projectValue) {
        var normalized = normalizeProjectValue(projectValue);
        if (!normalized || normalized === 'sem_projeto') return '';
        return '/project/' + encodeURIComponent(normalized);
    }

    function getEmptyState() {
        return listView ? listView.querySelector('[data-role="task-hub-empty-state"]') : null;
    }

    function syncListScaffoldVisibility() {
        var hasGroups = !!listEl.querySelector('.task-hub-group');
        listEl.hidden = !hasGroups;

        var emptyState = getEmptyState();
        if (emptyState) {
            emptyState.hidden = hasGroups;
        }
    }

    function getGlobalPlaceholderGroup() {
        return listEl.querySelector('.task-hub-group[data-global-placeholder="1"]');
    }

    function getGroupByProject(projectValue, options) {
        var normalized = normalizeProjectValue(projectValue);
        if (!normalized) return null;

        var opts = options || {};
        var groups = Array.prototype.slice.call(listEl.querySelectorAll('.task-hub-group[data-project-value]'));
        for (var i = 0; i < groups.length; i += 1) {
            var groupEl = groups[i];
            if (opts.excludeGroup && groupEl === opts.excludeGroup) continue;
            if (!opts.includePlaceholder && groupEl.getAttribute('data-global-placeholder') === '1') continue;
            if (normalizeProjectValue(groupEl.getAttribute('data-project-value')) === normalized) {
                return groupEl;
            }
        }
        return null;
    }

    function getAddRowByProject(projectValue, options) {
        var groupEl = getGroupByProject(projectValue, options);
        if (!groupEl) return null;
        return groupEl.querySelector('.task-hub-add-row[data-project-value]');
    }

    function updateGroupCount(groupEl) {
        if (!groupEl) return;
        var countEl = groupEl.querySelector('.task-hub-group-count');
        if (!countEl) return;
        var count = groupEl.querySelectorAll('.task-item-row[data-item-id]').length;
        countEl.textContent = count + (count === 1 ? ' tarefa' : ' tarefas');
    }

    function buildGroupHeaderMarkup(projectInfo) {
        var projectUrl = buildProjectDetailUrl(projectInfo.value);
        var titleMarkup = projectUrl
            ? '<a href="' + escapeHtml(projectUrl) + '" class="task-hub-group-title task-hub-group-title-link">' + escapeHtml(projectInfo.label) + '</a>'
            : '<h6 class="task-hub-group-title">' + escapeHtml(projectInfo.label) + '</h6>';
        var areaLabel = projectInfo.area || 'Não informada';

        return [
            '<div class="task-hub-group-title-wrap">',
            '<div class="task-hub-group-heading">',
            titleMarkup,
            '<p class="task-hub-group-meta">Area: <strong>' + escapeHtml(areaLabel) + '</strong></p>',
            '</div>',
            '</div>',
            '<span class="task-hub-group-count">0 tarefas</span>',
        ].join('');
    }

    function buildGroupColumnsMarkup() {
        return [
            '<div class="task-item-header-row task-hub-group-columns">',
            '<div class="task-item-bar task-item-bar-header"></div>',
            '<div class="task-item-main">',
            '<div class="task-item-line task-item-header">',
            '<span class="task-item-col-desc">Descrição</span>',
            '<span class="task-item-col-prioridade">Prioridade</span>',
            '<span class="task-item-col-tipo">Tipo</span>',
            '<span class="task-item-col-status">Status</span>',
            '<span class="task-item-col-responsavel">Responsável</span>',
            '<span class="task-item-col-actions" title="Ações">Ações</span>',
            '</div>',
            '</div>',
            '</div>',
        ].join('');
    }

    function buildAddRowMarkup(projectValue, options) {
        var opts = options || {};
        var isOpen = !!opts.open;
        var disabledAttr = opts.projectReady ? '' : ' disabled';
        var placeholderStyle = isOpen ? ' style="display:none;"' : '';
        var formHidden = isOpen ? '' : ' hidden';

        return [
            '<div class="task-item-add-row task-hub-add-row' + (opts.isGlobal ? ' task-hub-global-add-row' : '') + '" data-project-value="' + escapeHtml(projectValue) + '"' + (opts.isGlobal ? ' data-global-add="1"' : '') + '>',
            '<div class="task-item-add-placeholder" data-role="open-add-form"' + placeholderStyle + '>',
            '<span class="task-item-add-dashes"><i class="fas fa-plus" aria-hidden="true"></i></span>',
            '<span class="task-item-add-label">Adicionar nova tarefa</span>',
            '</div>',
            '<div class="task-item-add-form" data-role="add-form"' + formHidden + '>',
            '<div class="task-item-add-bar"></div>',
            '<div class="task-item-add-main">',
            '<div class="task-item-add-line">',
            '<textarea class="task-item-add-desc" data-role="descricao" rows="1" placeholder="' + (opts.projectReady ? 'Descreva a tarefa...' : 'Selecione o projeto primeiro') + '"' + disabledAttr + '></textarea>',
            '<select class="task-item-add-prioridade" data-role="prioridade"' + disabledAttr + '>',
            '<option value="">Prioridade</option>',
            '<option value="baixa">Baixa</option>',
            '<option value="media">Média</option>',
            '<option value="alta">Alta</option>',
            '<option value="urgente">Urgente</option>',
            '</select>',
            '<select class="task-item-add-tipo" data-role="tipo_pedido"' + disabledAttr + '>',
            '<option value="">Tipo</option>',
            '<option value="bug">Bug</option>',
            '<option value="melhoria">Melhoria</option>',
            '<option value="duvida">Dúvida</option>',
            '<option value="outros">Outros</option>',
            '</select>',
            '<select class="task-item-add-status" data-role="status"' + disabledAttr + '>',
            '<option value="nao_iniciada" selected>Não iniciada</option>',
            '<option value="em_andamento">Em andamento</option>',
            '<option value="para_validacao">Para validação</option>',
            '<option value="para_ajustes">Para ajustes</option>',
            '<option value="finalizada">Finalizada</option>',
            '</select>',
            '<button type="button" class="responsavel-picker-trigger" data-role="responsavel-trigger" aria-haspopup="dialog" aria-expanded="false"' + disabledAttr + '>',
            '<span class="responsavel-picker-trigger-content">',
            '<em class="responsavel-placeholder">Responsável</em>',
            '</span>',
            '<i class="fas fa-chevron-down" aria-hidden="true"></i>',
            '</button>',
            '<div class="task-item-add-actions">',
            '<button type="button" class="task-item-btn task-hub-add-cancel" data-role="cancel-add" title="Cancelar">',
            '<i class="fas fa-xmark" aria-hidden="true"></i>',
            '</button>',
            '<button type="button" class="task-item-btn task-item-btn-confirm task-hub-add-submit" data-role="submit-add" title="Salvar"' + disabledAttr + '>',
            '<i class="fas fa-check" aria-hidden="true"></i>',
            '</button>',
            '</div>',
            '</div>',
            '</div>',
            '</div>',
            '</div>',
        ].join('');
    }

    function buildRegularGroupMarkup(projectInfo) {
        return [
            '<section class="task-hub-group" data-project-value="' + escapeHtml(projectInfo.value) + '" data-project-id="' + escapeHtml(projectInfo.value === 'sem_projeto' ? '' : projectInfo.value) + '">',
            '<header class="task-hub-group-header">',
            buildGroupHeaderMarkup(projectInfo),
            '</header>',
            buildGroupColumnsMarkup(),
            buildAddRowMarkup(projectInfo.value, { projectReady: true }),
            '</section>',
        ].join('');
    }

    function buildProjectPickerMarkup(projectInfo) {
        var pickerOptions = getProjectOptionsForPicker();
        var optionsMarkup = pickerOptions.map(function (option) {
            return '<div class="project-search-option" data-value="' + escapeHtml(option.value) + '" data-label="' + escapeHtml(option.label) + '">' + escapeHtml(option.label) + '</div>';
        }).join('');

        return [
            '<div class="project-search-wrap task-hub-group-project-wrap">',
            '<input type="text" class="task-items-kanban-add-project-input task-hub-group-project-input project-search-input" data-role="project-input" placeholder="Selecione o projeto" autocomplete="off" aria-haspopup="listbox" aria-expanded="false" value="' + escapeHtml(projectInfo.label && projectInfo.value ? projectInfo.label : '') + '">',
            '<span class="task-hub-kanban-project-caret" aria-hidden="true"><i class="fas fa-chevron-down" aria-hidden="true"></i></span>',
            '<input type="hidden" data-role="project-value" value="' + escapeHtml(projectInfo.value) + '">',
            '<div class="project-search-dropdown task-hub-group-project-dropdown" data-role="project-dropdown" role="listbox" hidden>',
            optionsMarkup,
            '<div class="project-search-option project-search-empty" data-empty-state="1" hidden>Nenhum projeto encontrado</div>',
            '</div>',
            '</div>',
        ].join('');
    }

    function buildGlobalPlaceholderMarkup(projectInfo, options) {
        var opts = options || {};
        var areaLabel = projectInfo.area || selectedArea || 'Selecione um projeto';
        var titleMarkup = opts.lockProject
            ? '<h6 class="task-hub-group-title task-hub-group-title-static" data-role="project-title-static">' + escapeHtml(projectInfo.label || selectedProjectLabel || 'Projeto') + '</h6><input type="hidden" data-role="project-value" value="' + escapeHtml(projectInfo.value) + '">'
            : buildProjectPickerMarkup(projectInfo);

        return [
            '<section class="task-hub-group task-hub-group-global-placeholder" data-global-placeholder="1" data-project-value="' + escapeHtml(projectInfo.value) + '" data-project-id="' + escapeHtml(projectInfo.value === 'sem_projeto' ? '' : projectInfo.value) + '">',
            '<header class="task-hub-group-header">',
            '<div class="task-hub-group-title-wrap">',
            '<div class="task-hub-group-heading task-hub-group-heading-composer">',
            titleMarkup,
            '<p class="task-hub-group-meta">Area: <strong data-role="project-area">' + escapeHtml(areaLabel) + '</strong></p>',
            '</div>',
            '</div>',
            '<span class="task-hub-group-count">0 tarefas</span>',
            '</header>',
            buildGroupColumnsMarkup(),
            buildAddRowMarkup(projectInfo.value, { projectReady: !!projectInfo.value, open: true, isGlobal: true }),
            '</section>',
        ].join('');
    }

    function createElementFromMarkup(markup) {
        var wrapper = document.createElement('div');
        wrapper.innerHTML = markup;
        return wrapper.firstElementChild;
    }

    function requestAddItem(payload) {
        return new Promise(function (resolve, reject) {
            var dataPayload = payload || {};
            var descricao = (dataPayload.descricao || '').trim();
            var projectValue = normalizeProjectValue(dataPayload.project);

            if (!projectValue) {
                reject(new Error('Projeto é obrigatório.'));
                return;
            }
            if (!descricao) {
                reject(new Error('Descrição é obrigatória.'));
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
                reject(new Error('Erro de conexão. Tente novamente.'));
            };
            xhr.send(formData);
        });
    }

    function buildItemRowMarkup(item) {
        var prioridade = item.prioridade || '';
        var tipoPedido = item.tipo_pedido || '';
        var taskId = item.task_id || item.id || '';
        var taskTitulo = item.task_titulo || item.descricao || '';
        var projectInfo = getProjectInfo(item.project_value || item.project_id || '', item.project_titulo, item.project_area);
        var commentsCount = Number(item.comments_count || 0);
        var anexosCount = Number(item.anexos_count || 0);
        var legacyTipoOption = tipoPedido === 'implementacao'
            ? '<option value="implementacao" selected hidden>Implementação (legado)</option>'
            : '';

        var prioridadeOptions = '<option value="">-</option>' +
            '<option value="baixa"' + (prioridade === 'baixa' ? ' selected' : '') + '>Baixa</option>' +
            '<option value="media"' + (prioridade === 'media' ? ' selected' : '') + '>Média</option>' +
            '<option value="alta"' + (prioridade === 'alta' ? ' selected' : '') + '>Alta</option>' +
            '<option value="urgente"' + (prioridade === 'urgente' ? ' selected' : '') + '>Urgente</option>';
        var tipoOptions = '<option value="">-</option>' +
            legacyTipoOption +
            '<option value="bug"' + (tipoPedido === 'bug' ? ' selected' : '') + '>Bug</option>' +
            '<option value="melhoria"' + (tipoPedido === 'melhoria' ? ' selected' : '') + '>Melhoria</option>' +
            '<option value="duvida"' + (tipoPedido === 'duvida' ? ' selected' : '') + '>Dúvida</option>' +
            '<option value="outros"' + (tipoPedido === 'outros' ? ' selected' : '') + '>Outros</option>';

        var rowHtml = [
            '<div class="task-item-row" ',
            'data-item-id="' + item.id + '" ',
            'data-item-status="' + item.status + '" ',
            'data-comments-count="' + commentsCount + '" ',
            'data-item-prioridade="' + escapeHtml(prioridade) + '" ',
            'data-item-tipo="' + escapeHtml(tipoPedido) + '" ',
            'data-anexos-count="' + anexosCount + '" ',
            'data-task-id="' + escapeHtml(taskId) + '" ',
            'data-task-titulo="' + escapeHtml(taskTitulo) + '" ',
            'data-project-value="' + escapeHtml(projectInfo.value) + '" ',
            'data-project-titulo="' + escapeHtml(projectInfo.label) + '">',
            '<div class="task-item-bar status-' + item.status + '"></div>',
            '<div class="task-item-main">',
            '<div class="task-item-line">',
            '<div class="task-item-desc-wrap">',
            '<div class="task-item-desc-row">',
            '<p class="task-item-desc" data-item-id="' + item.id + '">' + htmlEncode(item.descricao) + '</p>',
            '<button type="button" class="task-item-desc-edit-btn" data-item-id="' + item.id + '" title="Editar descrição">',
            '<i class="fas fa-pen" aria-hidden="true"></i><span class="visually-hidden">Editar</span></button>',
            '</div>',
            '</div>',
            '<div class="task-item-meta">',
            '<select class="task-item-prioridade-select prioridade-' + (prioridade || 'none') + '" data-item-id="' + item.id + '" title="Prioridade" onchange="updateItemPrioridade(' + item.id + ', this.value, this)">' + prioridadeOptions + '</select>',
            '<select class="task-item-tipo-select" data-item-id="' + item.id + '" title="Tipo" onchange="updateItemTipo(' + item.id + ', this.value)">' + tipoOptions + '</select>',
            '<select class="task-item-status status-' + item.status + '" onchange="updateItemStatus(' + item.id + ', this.value)" title="Status">',
            '<option value="nao_iniciada"' + (item.status === 'nao_iniciada' ? ' selected' : '') + '>Não iniciada</option>',
            '<option value="em_andamento"' + (item.status === 'em_andamento' ? ' selected' : '') + '>Em andamento</option>',
            '<option value="para_validacao"' + (item.status === 'para_validacao' ? ' selected' : '') + '>Para validação</option>',
            '<option value="para_ajustes"' + (item.status === 'para_ajustes' ? ' selected' : '') + '>Para ajustes</option>',
            '<option value="finalizada"' + (item.status === 'finalizada' ? ' selected' : '') + '>Finalizada</option>',
            '</select>',
            '<span class="task-item-responsavel" data-item-id="' + item.id + '">',
            (item.responsavel ? htmlEncode(item.responsavel) : '<em class="responsavel-placeholder">Responsável não informado</em>'),
            '</span>',
            '<div class="task-item-actions">',
            '<button type="button" class="task-item-comments-btn" aria-expanded="false" data-target="comments-body-' + item.id + '" onclick="toggleComments(this)" title="Comentários">',
            '<i class="far fa-comment-alt" aria-hidden="true"></i><span class="task-item-comments-num">' + commentsCount + '</span></button>',
            '<button type="button" class="task-item-anexos-btn" title="Anexos" data-item-id="' + item.id + '">',
            '<i class="fas fa-paperclip" aria-hidden="true"></i><span class="task-item-anexos-num">' + anexosCount + '</span></button>',
            '<button type="button" class="task-item-btn task-item-del" data-bs-toggle="modal" data-bs-target="#deleteItemModal-' + item.id + '" title="Excluir"><i class="fas fa-trash-alt" aria-hidden="true"></i></button>',
            '</div></div></div>',
            '<div id="comments-body-' + item.id + '" class="task-item-comments" hidden>',
            '<div class="task-item-comments-inner">',
            '<form class="task-comment-form" action="/tarefas/' + item.id + '/comentarios/add" method="POST" data-item-id="' + item.id + '">',
            '<textarea name="content" rows="1" placeholder="Comentar... (Enter para enviar)" required></textarea>',
            '<button type="submit" title="Enviar comentário"><i class="fas fa-paper-plane" aria-hidden="true"></i><span class="visually-hidden">Enviar</span></button>',
            '</form></div></div></div></div>',
        ].join('');

        var modalHtml = [
            '<div class="modal fade task-detail-v2-modal" id="deleteItemModal-' + item.id + '" tabindex="-1" aria-hidden="true">',
            '<div class="modal-dialog modal-dialog-centered"><div class="modal-content modal-clean">',
            '<div class="modal-header-clean"><div><h5 class="modal-title-clean ds-type-section-title">Excluir Tarefa</h5><p class="modal-subtitle-clean ds-type-body-sm">Esta ação não pode ser desfeita</p></div>',
            '<button type="button" class="btn-close-clean" data-bs-dismiss="modal">&times;</button></div>',
            '<div class="modal-body-clean"><p>Confirma a exclusão desta tarefa?</p><p class="text-muted small">' + escapeHtml((item.descricao || '').substring(0, 100)) + ((item.descricao || '').length > 100 ? '...' : '') + '</p></div>',
            '<div class="modal-footer-clean"><button type="button" class="btn-modal-clean btn-cancel-clean" data-bs-dismiss="modal">Cancelar</button>',
            '<form action="/tarefas/' + item.id + '/delete" method="POST" class="inline-form">',
            '<button type="submit" class="btn-modal-clean btn-confirm-delete">Excluir</button></form></div></div></div></div>',
        ].join('');

        return { rowHtml: rowHtml, modalHtml: modalHtml };
    }

    function insertNodesBefore(referenceNode, markup) {
        var wrapper = document.createElement('div');
        wrapper.innerHTML = markup;
        var inserted = [];
        while (wrapper.firstChild) {
            var node = wrapper.firstChild;
            inserted.push(node);
            referenceNode.parentNode.insertBefore(node, referenceNode);
        }
        return inserted;
    }

    function getSortedInsertBefore(projectInfo) {
        var groups = Array.prototype.slice.call(listEl.querySelectorAll('.task-hub-group:not([data-global-placeholder="1"])'));
        if (!groups.length) return null;

        var isOrphan = projectInfo.value === 'sem_projeto';
        var targetTitle = String(projectInfo.label || '').toLowerCase();

        for (var i = 0; i < groups.length; i += 1) {
            var current = groups[i];
            var currentProjectValue = normalizeProjectValue(current.getAttribute('data-project-value'));
            var currentTitleEl = current.querySelector('.task-hub-group-title, .task-hub-group-title-link');
            var currentTitle = currentTitleEl ? (currentTitleEl.textContent || '').trim() : '';
            var currentNormalizedTitle = String(currentTitle || '').toLowerCase();

            if (isOrphan) {
                continue;
            }
            if (currentProjectValue === 'sem_projeto') {
                return current;
            }
            if (currentNormalizedTitle > targetTitle) {
                return current;
            }
        }
        return null;
    }

    function createRegularGroup(projectInfo) {
        var groupEl = createElementFromMarkup(buildRegularGroupMarkup(projectInfo));
        var beforeNode = getSortedInsertBefore(projectInfo);
        if (beforeNode) {
            listEl.insertBefore(groupEl, beforeNode);
        } else {
            listEl.appendChild(groupEl);
        }

        initializeAddRow(groupEl.querySelector('.task-hub-add-row[data-project-value]'), {
            getProjectValue: function () {
                return normalizeProjectValue(groupEl.getAttribute('data-project-value'));
            },
        });
        syncListScaffoldVisibility();
        return groupEl;
    }

    function convertGlobalPlaceholderGroupToRegular(groupEl, projectInfo) {
        if (!groupEl) return null;

        groupEl.removeAttribute('data-global-placeholder');
        groupEl.classList.remove('task-hub-group-global-placeholder');
        groupEl.setAttribute('data-project-value', projectInfo.value);
        groupEl.setAttribute('data-project-id', projectInfo.value === 'sem_projeto' ? '' : projectInfo.value);

        var header = groupEl.querySelector('.task-hub-group-header');
        if (header) {
            header.innerHTML = buildGroupHeaderMarkup(projectInfo);
        }

        var addRow = groupEl.querySelector('.task-hub-add-row[data-project-value]');
        if (addRow) {
            addRow.setAttribute('data-project-value', projectInfo.value);
            addRow.removeAttribute('data-global-add');
        }

        updateGroupCount(groupEl);
        return groupEl;
    }

    function removeGlobalPlaceholderGroup(groupEl) {
        var targetGroup = groupEl || getGlobalPlaceholderGroup();
        if (targetGroup && targetGroup.parentNode) {
            targetGroup.parentNode.removeChild(targetGroup);
        }
        syncListScaffoldVisibility();
    }

    function setGlobalPlaceholderProject(groupEl, projectValue, projectLabel, projectArea) {
        if (!groupEl) return;

        var projectInfo = getProjectInfo(projectValue, projectLabel, projectArea);
        groupEl.setAttribute('data-project-value', projectInfo.value);
        groupEl.setAttribute('data-project-id', projectInfo.value === 'sem_projeto' ? '' : projectInfo.value);

        var hiddenValue = groupEl.querySelector('input[data-role="project-value"]');
        if (hiddenValue) {
            hiddenValue.value = projectInfo.value;
        }

        var input = groupEl.querySelector('input[data-role="project-input"]');
        if (input) {
            input.value = projectInfo.value ? projectInfo.label : '';
        }

        var areaEl = groupEl.querySelector('[data-role="project-area"]');
        if (areaEl) {
            areaEl.textContent = projectInfo.area || selectedArea || 'Selecione um projeto';
        }

        var addRow = groupEl.querySelector('.task-hub-add-row');
        if (addRow) {
            addRow.setAttribute('data-project-value', projectInfo.value);
            if (addRow._taskHubController && typeof addRow._taskHubController.refreshProjectState === 'function') {
                addRow._taskHubController.refreshProjectState();
            }
        }
    }

    function setupGlobalPlaceholderProjectPicker(groupEl) {
        var wrap = groupEl.querySelector('.task-hub-group-project-wrap');
        var input = groupEl.querySelector('input[data-role="project-input"]');
        var hiddenValue = groupEl.querySelector('input[data-role="project-value"]');
        var dropdown = groupEl.querySelector('[data-role="project-dropdown"]');
        if (!wrap || !input || !hiddenValue || !dropdown) return;

        var options = Array.prototype.slice.call(dropdown.querySelectorAll('.project-search-option[data-value]'));
        var emptyState = dropdown.querySelector('[data-empty-state="1"]');

        function filterOptions() {
            var query = (input.value || '').trim().toLowerCase();
            var visibleCount = 0;
            options.forEach(function (optionEl) {
                var label = (optionEl.getAttribute('data-label') || optionEl.textContent || '').toLowerCase();
                var isVisible = !query || label.indexOf(query) !== -1;
                optionEl.classList.toggle('hidden-by-filter', !isVisible);
                if (isVisible) visibleCount += 1;
            });
            if (emptyState) {
                emptyState.hidden = visibleCount > 0;
            }
        }

        function showDropdown() {
            filterOptions();
            dropdown.removeAttribute('hidden');
            input.setAttribute('aria-expanded', 'true');
        }

        function hideDropdown() {
            dropdown.setAttribute('hidden', '');
            input.setAttribute('aria-expanded', 'false');
        }

        function selectOption(optionEl) {
            var value = normalizeProjectValue(optionEl.getAttribute('data-value'));
            var label = optionEl.getAttribute('data-label') || optionEl.textContent || '';
            var info = getProjectInfo(value, label);
            setGlobalPlaceholderProject(groupEl, info.value, info.label, info.area);
            hideDropdown();

            var addRow = groupEl.querySelector('.task-hub-add-row');
            if (addRow && addRow._taskHubController && typeof addRow._taskHubController.focusDescription === 'function') {
                addRow._taskHubController.focusDescription();
            }
        }

        input.addEventListener('click', showDropdown);
        input.addEventListener('input', function () {
            if (!(input.value || '').trim()) {
                hiddenValue.value = '';
                setGlobalPlaceholderProject(groupEl, '', '', selectedArea);
            }
            showDropdown();
        });
        input.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') {
                hideDropdown();
                return;
            }

            var visibleOptions = options.filter(function (optionEl) {
                return !optionEl.classList.contains('hidden-by-filter');
            });
            if (!visibleOptions.length) return;

            if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                event.preventDefault();
                var active = dropdown.querySelector('.project-search-option.active');
                var index = visibleOptions.indexOf(active);
                if (event.key === 'ArrowDown') {
                    index = index < 0 ? 0 : Math.min(index + 1, visibleOptions.length - 1);
                } else {
                    index = index < 0 ? visibleOptions.length - 1 : Math.max(index - 1, 0);
                }
                visibleOptions.forEach(function (optionEl, position) {
                    optionEl.classList.toggle('active', position === index);
                });
                visibleOptions[index].scrollIntoView({ block: 'nearest' });
                return;
            }

            if (event.key === 'Enter') {
                event.preventDefault();
                var current = dropdown.querySelector('.project-search-option.active');
                if (current && !current.classList.contains('hidden-by-filter')) {
                    selectOption(current);
                }
            }
        });

        options.forEach(function (optionEl) {
            optionEl.addEventListener('click', function () {
                selectOption(optionEl);
            });
        });

        document.addEventListener('mousedown', function (event) {
            if (!document.body.contains(groupEl)) return;
            if (!wrap.contains(event.target)) {
                hideDropdown();
            }
        });
    }

    function ensureGlobalPlaceholderGroup(options) {
        var opts = options || {};
        var existing = getGlobalPlaceholderGroup();
        var preferredValue = selectedProject || normalizeProjectValue(opts.projectValue);
        if (existing) {
            if (!selectedProject && preferredValue) {
                setGlobalPlaceholderProject(existing, preferredValue);
            }
            return existing;
        }

        if (!preferredValue && !getProjectOptionsForPicker().length) {
            alert('Nenhum projeto disponível para criar tarefas neste escopo.');
            return null;
        }

        var projectInfo = getProjectInfo(preferredValue, selectedProjectLabel, selectedArea);
        var groupEl = createElementFromMarkup(buildGlobalPlaceholderMarkup(projectInfo, { lockProject: !!selectedProject }));
        listEl.insertBefore(groupEl, listEl.firstChild);

        var addRow = groupEl.querySelector('.task-hub-add-row[data-project-value]');
        initializeAddRow(addRow, {
            isGlobalPlaceholder: true,
            getProjectValue: function () {
                return normalizeProjectValue(groupEl.getAttribute('data-project-value'));
            },
            containsTarget: function (target) {
                return !!(target && groupEl.contains(target));
            },
            focusProjectSelector: function () {
                var input = groupEl.querySelector('input[data-role="project-input"]');
                if (input) {
                    input.focus();
                }
            },
            onCancel: function () {
                removeGlobalPlaceholderGroup(groupEl);
            },
        });

        if (!selectedProject) {
            setupGlobalPlaceholderProjectPicker(groupEl);
        }

        syncListScaffoldVisibility();
        return groupEl;
    }

    function resolveTargetGroupForItem(item, options) {
        var opts = options || {};
        var projectInfo = getProjectInfo(item.project_value || item.project_id || opts.projectValue || '', item.project_titulo, item.project_area);
        var sourceGroup = opts.sourceGroup || null;
        var existingGroup = getGroupByProject(projectInfo.value, {
            includePlaceholder: false,
            excludeGroup: sourceGroup,
        });

        if (sourceGroup && sourceGroup.getAttribute('data-global-placeholder') === '1') {
            var sourceProjectValue = normalizeProjectValue(sourceGroup.getAttribute('data-project-value'));
            if (sourceProjectValue === projectInfo.value) {
                if (existingGroup) {
                    removeGlobalPlaceholderGroup(sourceGroup);
                    return existingGroup;
                }
                return convertGlobalPlaceholderGroupToRegular(sourceGroup, projectInfo);
            }
        }

        if (sourceGroup) {
            var sourceProjectValue = normalizeProjectValue(sourceGroup.getAttribute('data-project-value'));
            if (sourceProjectValue === projectInfo.value) {
                return sourceGroup;
            }
        }

        if (existingGroup) {
            return existingGroup;
        }
        return createRegularGroup(projectInfo);
    }

    function insertNewItem(data, options) {
        var payload = data || {};
        var opts = options || {};
        var item = payload.item || {};
        if (!item || !item.id) return null;

        var targetGroup = resolveTargetGroupForItem(item, opts);
        if (!targetGroup) return null;

        var targetAddRow = targetGroup.querySelector('.task-hub-add-row[data-project-value]');
        if (!targetAddRow || !targetAddRow.parentNode) return null;

        var markup = buildItemRowMarkup(item);
        insertNodesBefore(targetAddRow, markup.rowHtml + markup.modalHtml);

        updateGroupCount(targetGroup);
        syncListScaffoldVisibility();
        updateTaskItemsHeaderCount();
        updateTaskItemsTotalPill();
        if (window.taskItemsKanban && typeof window.taskItemsKanban.rebuildFromList === 'function') {
            window.taskItemsKanban.rebuildFromList();
        }
        if (opts.focusInserted !== false) {
            focusTaskItemRow(String(item.id), { scrollDelay: 100 });
        }
        return getTaskItemRowById(item.id);
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

        renderResponsavelPickerTrigger(addResponsavelTrigger, responsavelNames, 'Responsável');

        function getProjectValue() {
            if (typeof opts.getProjectValue === 'function') {
                return normalizeProjectValue(opts.getProjectValue());
            }
            return normalizeProjectValue(addRow.getAttribute('data-project-value'));
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
            renderResponsavelPickerTrigger(addResponsavelTrigger, responsavelNames, 'Responsável');
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
                    insertNewItem(data, {
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
                alert('Selecione um projeto para escolher responsáveis.');
                return;
            }

            responsavelPickerManager.open({
                anchorEl: addResponsavelTrigger,
                sugestoesUrl: sugestoesUrl,
                projectValue: projectValue,
                initialRawValue: responsavelNames.join(', '),
                onApply: function (payload) {
                    responsavelNames = payload.names.slice();
                    renderResponsavelPickerTrigger(addResponsavelTrigger, responsavelNames, 'Responsável');
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
        var groupEl = ensureGlobalPlaceholderGroup(options);
        if (!groupEl) return false;

        if (!selectedProject && options && options.projectValue) {
            setGlobalPlaceholderProject(groupEl, options.projectValue);
        }

        var addRow = groupEl.querySelector('.task-hub-add-row');
        if (addRow && addRow._taskHubController && typeof addRow._taskHubController.open === 'function') {
            addRow._taskHubController.open();
            return true;
        }
        return false;
    }

    function focusInlineAdd(projectValue) {
        var normalized = normalizeProjectValue(projectValue);
        var addRow = getAddRowByProject(normalized, { includePlaceholder: false });
        if (addRow && addRow._taskHubController && typeof addRow._taskHubController.focus === 'function') {
            addRow.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            addRow._taskHubController.focus();
            return true;
        }
        return focusGlobalCreateInList({ projectValue: normalized });
    }

    function bindCreateButton() {
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

    Array.prototype.slice.call(listEl.querySelectorAll('.task-hub-add-row[data-project-value]')).forEach(function (addRow) {
        initializeAddRow(addRow, {
            getProjectValue: function () {
                return normalizeProjectValue(addRow.getAttribute('data-project-value'));
            },
        });
    });

    syncListScaffoldVisibility();
    bindCreateButton();

    window.taskItemsListBridge = {
        listEl: listEl,
        taskId: '',
        sugestoesUrl: sugestoesUrl,
        addItemUrl: addUrl,
        insertItemFromPayload: insertNewItem,
        requestAddItem: requestAddItem,
        focusInlineAdd: focusInlineAdd,
        focusGlobalCreateInList: focusGlobalCreateInList,
    };
})();
