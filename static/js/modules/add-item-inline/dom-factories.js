// === dom-factories.js — Fábricas de markup para o hub de tarefas ===
(function (global) {
    var registry = global.AddItemInlineModules = global.AddItemInlineModules || {};

    registry.domFactories = function (ctx) {
        var escapeHtml = ctx.config.escapeHtml;

        function buildGroupHeaderMarkup(projectInfo) {
            var projectUrl = ctx.buildProjectDetailUrl(projectInfo.value);
            var titleMarkup = projectUrl
                ? '<a href="' + escapeHtml(projectUrl) + '" class="task-hub-group-title task-hub-group-title-link">' + escapeHtml(projectInfo.label) + '</a>'
                : '<h6 class="task-hub-group-title">' + escapeHtml(projectInfo.label) + '</h6>';
            var areaLabel = projectInfo.area || 'N\u00e3o informada';

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
                '<span class="task-item-col-desc">Descri\u00e7\u00e3o</span>',
                '<span class="task-item-col-prioridade">Prioridade</span>',
                '<span class="task-item-col-tipo">Tipo</span>',
                '<span class="task-item-col-status">Status</span>',
                '<span class="task-item-col-responsavel">Respons\u00e1vel</span>',
                '<span class="task-item-col-actions" title="A\u00e7\u00f5es">A\u00e7\u00f5es</span>',
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
                '<option value="media">M\u00e9dia</option>',
                '<option value="alta">Alta</option>',
                '<option value="urgente">Urgente</option>',
                '</select>',
                '<select class="task-item-add-tipo" data-role="tipo_pedido"' + disabledAttr + '>',
                '<option value="">Tipo</option>',
                '<option value="bug">Bug</option>',
                '<option value="melhoria">Melhoria</option>',
                '<option value="duvida">D\u00favida</option>',
                '<option value="outros">Outros</option>',
                '</select>',
                '<select class="task-item-add-status" data-role="status"' + disabledAttr + '>',
                '<option value="nao_iniciada" selected>N\u00e3o iniciada</option>',
                '<option value="em_andamento">Em andamento</option>',
                '<option value="para_validacao">Para valida\u00e7\u00e3o</option>',
                '<option value="para_ajustes">Para ajustes</option>',
                '<option value="finalizada">Finalizada</option>',
                '</select>',
                '<button type="button" class="responsavel-picker-trigger" data-role="responsavel-trigger" aria-haspopup="dialog" aria-expanded="false"' + disabledAttr + '>',
                '<span class="responsavel-picker-trigger-content">',
                '<em class="responsavel-placeholder">Respons\u00e1vel</em>',
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
            var pickerOptions = ctx.getProjectOptionsForPicker();
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
            var areaLabel = projectInfo.area || ctx.config.selectedArea || 'Selecione um projeto';
            var titleMarkup = opts.lockProject
                ? '<h6 class="task-hub-group-title task-hub-group-title-static" data-role="project-title-static">' + escapeHtml(projectInfo.label || ctx.config.selectedProjectLabel || 'Projeto') + '</h6><input type="hidden" data-role="project-value" value="' + escapeHtml(projectInfo.value) + '">'
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
            wrapper.insertAdjacentHTML('afterbegin', markup);
            return wrapper.firstElementChild;
        }

        function insertNodesBefore(referenceNode, markup) {
            var wrapper = document.createElement('div');
            wrapper.insertAdjacentHTML('afterbegin', markup);
            var inserted = [];
            while (wrapper.firstChild) {
                var node = wrapper.firstChild;
                inserted.push(node);
                referenceNode.parentNode.insertBefore(node, referenceNode);
            }
            return inserted;
        }

        function canDeleteTaskItem(item) {
            return item && item.can_delete !== false;
        }

        function canFinalizeTaskItem(item) {
            return item && item.can_finalize !== false;
        }

        function buildStatusOptionsMarkup(item) {
            var status = String(item && item.status || 'nao_iniciada');
            var options = [
                '<option value="nao_iniciada"' + (status === 'nao_iniciada' ? ' selected' : '') + '>N\u00e3o iniciada</option>',
                '<option value="em_andamento"' + (status === 'em_andamento' ? ' selected' : '') + '>Em andamento</option>',
                '<option value="para_validacao"' + (status === 'para_validacao' ? ' selected' : '') + '>Para valida\u00e7\u00e3o</option>',
                '<option value="para_ajustes"' + (status === 'para_ajustes' ? ' selected' : '') + '>Para ajustes</option>',
            ];

            if (canFinalizeTaskItem(item)) {
                options.push(
                    '<option value="finalizada"' + (status === 'finalizada' ? ' selected' : '') + '>Finalizada</option>'
                );
            } else if (status === 'finalizada') {
                options.push('<option value="finalizada" selected disabled>Finalizada</option>');
            }

            return options.join('');
        }

        function buildItemRowMarkup(item) {
            var prioridade = item.prioridade || '';
            var tipoPedido = item.tipo_pedido || '';
            var taskId = item.task_id || item.id || '';
            var taskTitulo = item.task_titulo || item.descricao || '';
            var projectInfo = ctx.getProjectInfo(item.project_value || item.project_id || '', item.project_titulo, item.project_area);
            var commentsCount = Number(item.comments_count || 0);
            var anexosCount = Number(item.anexos_count || 0);
            var canDelete = canDeleteTaskItem(item);
            var htmlEncode = window.htmlEncode;
            var legacyTipoOption = tipoPedido === 'implementacao'
                ? '<option value="implementacao" selected hidden>Implementa\u00e7\u00e3o (legado)</option>'
                : '';

            var prioridadeOptions = '<option value="">-</option>' +
                '<option value="baixa"' + (prioridade === 'baixa' ? ' selected' : '') + '>Baixa</option>' +
                '<option value="media"' + (prioridade === 'media' ? ' selected' : '') + '>M\u00e9dia</option>' +
                '<option value="alta"' + (prioridade === 'alta' ? ' selected' : '') + '>Alta</option>' +
                '<option value="urgente"' + (prioridade === 'urgente' ? ' selected' : '') + '>Urgente</option>';
            var tipoOptions = '<option value="">-</option>' +
                legacyTipoOption +
                '<option value="bug"' + (tipoPedido === 'bug' ? ' selected' : '') + '>Bug</option>' +
                '<option value="melhoria"' + (tipoPedido === 'melhoria' ? ' selected' : '') + '>Melhoria</option>' +
                '<option value="duvida"' + (tipoPedido === 'duvida' ? ' selected' : '') + '>D\u00favida</option>' +
                '<option value="outros"' + (tipoPedido === 'outros' ? ' selected' : '') + '>Outros</option>';

            var rowHtml = [
                '<div class="task-item-row" ',
                'data-item-id="' + item.id + '" ',
                'data-item-status="' + item.status + '" ',
                'data-can-delete="' + (canDelete ? '1' : '0') + '" ',
                'data-can-finalize="' + (canFinalizeTaskItem(item) ? '1' : '0') + '" ',
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
                '<button type="button" class="task-item-desc-edit-btn" data-item-id="' + item.id + '" title="Editar descri\u00e7\u00e3o">',
                '<i class="fas fa-pen" aria-hidden="true"></i><span class="visually-hidden">Editar</span></button>',
                '</div>',
                '</div>',
                '<div class="task-item-meta">',
                '<select class="task-item-prioridade-select prioridade-' + (prioridade || 'none') + '" data-item-id="' + item.id + '" title="Prioridade" data-action-change="updateItemPrioridade" data-action-args="' + item.id + '">' + prioridadeOptions + '</select>',
                '<select class="task-item-tipo-select" data-item-id="' + item.id + '" title="Tipo" data-action-change="updateItemTipo" data-action-args="' + item.id + '">' + tipoOptions + '</select>',
                '<select class="task-item-status status-' + item.status + '" data-action-change="updateItemStatus" data-action-args="' + item.id + '" title="Status">',
                buildStatusOptionsMarkup(item),
                '</select>',
                '<span class="task-item-responsavel" data-item-id="' + item.id + '">',
                (item.responsavel ? htmlEncode(item.responsavel) : '<em class="responsavel-placeholder">Respons\u00e1vel n\u00e3o informado</em>'),
                '</span>',
                '<div class="task-item-actions">',
                '<button type="button" class="task-item-comments-btn" aria-expanded="false" data-target="comments-body-' + item.id + '" data-action="toggleComments" title="Coment\u00e1rios">',
                '<i class="far fa-comment-alt" aria-hidden="true"></i><span class="task-item-comments-num">' + commentsCount + '</span></button>',
                '<button type="button" class="task-item-anexos-btn" title="Anexos" data-item-id="' + item.id + '">',
                '<i class="fas fa-paperclip" aria-hidden="true"></i><span class="task-item-anexos-num">' + anexosCount + '</span></button>',
                canDelete ? '<button type="button" class="task-item-btn task-item-del" data-bs-toggle="modal" data-bs-target="#deleteItemModal-' + item.id + '" title="Excluir"><i class="fas fa-trash-alt" aria-hidden="true"></i></button>' : '',
                '</div></div></div>',
                '<div id="comments-body-' + item.id + '" class="task-item-comments" hidden>',
                '<div class="task-item-comments-inner">',
                '<form class="task-comment-form" action="/tarefas/' + item.id + '/comentarios/add" method="POST" data-item-id="' + item.id + '">',
                '<textarea name="content" rows="1" placeholder="Comentar... (Enter para enviar)" required></textarea>',
                '<button type="submit" title="Enviar coment\u00e1rio"><i class="fas fa-paper-plane" aria-hidden="true"></i><span class="visually-hidden">Enviar</span></button>',
                '</form></div></div></div></div>',
            ].join('');

            if (!canDelete) {
                return { rowHtml: rowHtml, modalHtml: '' };
            }

            var modalHtml = [
                '<div class="modal fade task-detail-v2-modal" id="deleteItemModal-' + item.id + '" tabindex="-1" aria-hidden="true">',
                '<div class="modal-dialog modal-dialog-centered"><div class="modal-content modal-clean">',
                '<div class="modal-header-clean"><div><h5 class="modal-title-clean ds-type-section-title">Excluir Tarefa</h5><p class="modal-subtitle-clean ds-type-body-sm">Esta a\u00e7\u00e3o n\u00e3o pode ser desfeita</p></div>',
                '<button type="button" class="btn-close-clean" data-bs-dismiss="modal">&times;</button></div>',
                '<div class="modal-body-clean"><p>Confirma a exclus\u00e3o desta tarefa?</p><p class="text-muted small">' + escapeHtml((item.descricao || '').substring(0, 100)) + ((item.descricao || '').length > 100 ? '...' : '') + '</p></div>',
                '<div class="modal-footer-clean"><button type="button" class="btn-modal-clean btn-cancel-clean" data-bs-dismiss="modal">Cancelar</button>',
                '<form action="/tarefas/' + item.id + '/delete" method="POST" class="inline-form">',
                '<button type="submit" class="btn-modal-clean btn-confirm-delete">Excluir</button></form></div></div></div></div>',
            ].join('');

            return { rowHtml: rowHtml, modalHtml: modalHtml };
        }

        ctx.buildGroupHeaderMarkup = buildGroupHeaderMarkup;
        ctx.buildGroupColumnsMarkup = buildGroupColumnsMarkup;
        ctx.buildAddRowMarkup = buildAddRowMarkup;
        ctx.buildRegularGroupMarkup = buildRegularGroupMarkup;
        ctx.buildProjectPickerMarkup = buildProjectPickerMarkup;
        ctx.buildGlobalPlaceholderMarkup = buildGlobalPlaceholderMarkup;
        ctx.createElementFromMarkup = createElementFromMarkup;
        ctx.insertNodesBefore = insertNodesBefore;
        ctx.canDeleteTaskItem = canDeleteTaskItem;
        ctx.canFinalizeTaskItem = canFinalizeTaskItem;
        ctx.buildStatusOptionsMarkup = buildStatusOptionsMarkup;
        ctx.buildItemRowMarkup = buildItemRowMarkup;
    };
})(window);
