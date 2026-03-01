// === add-item-inline.js — IIFE de adição inline de tarefas ===
    // --- Adicionar tarefa inline (hub com múltiplos projetos) ---
    (function () {
        var listEl = document.querySelector('.task-items-list');
        if (!listEl) return;

        var addRows = Array.prototype.slice.call(
            listEl.querySelectorAll('.task-hub-add-row[data-project-value]')
        );
        if (!addRows.length) return;

        var addUrl = listEl.getAttribute('data-add-item-url');
        var sugestoesUrl = listEl.getAttribute('data-sugestoes-url');
        if (!addUrl) return;

        function escapeHtml(text) {
            var div = document.createElement('div');
            div.textContent = text == null ? '' : String(text);
            return div.innerHTML;
        }

        function normalizeProjectValue(value) {
            var normalized = String(value == null ? '' : value).trim();
            return normalized || '';
        }

        function buildProjectDetailUrl(projectValue) {
            var normalized = normalizeProjectValue(projectValue);
            if (!normalized || normalized === 'sem_projeto') return '';
            return '/project/' + encodeURIComponent(normalized);
        }

        function buildProjectContextMarkup(projectValue, projectTitulo) {
            var projectLabel = projectTitulo || 'Sem projeto';
            var projectUrl = buildProjectDetailUrl(projectValue);
            if (!projectUrl) {
                return '<span>' + escapeHtml(projectLabel) + '</span>';
            }
            return '<a href="' + projectUrl + '">' + escapeHtml(projectLabel) + '</a>';
        }

        function getAddRowByProject(projectValue) {
            var value = normalizeProjectValue(projectValue);
            if (!value) return null;
            return listEl.querySelector('.task-hub-add-row[data-project-value="' + value + '"]');
        }

        function updateGroupCount(groupEl) {
            if (!groupEl) return;
            var countEl = groupEl.querySelector('.task-hub-group-count');
            if (!countEl) return;
            var count = groupEl.querySelectorAll('.task-item-row[data-item-id]').length;
            countEl.textContent = count + (count === 1 ? ' tarefa' : ' tarefas');
        }

        function buildItemRowMarkup(item) {
            var prioridade = item.prioridade || '';
            var tipoPedido = item.tipo_pedido || '';
            var taskId = item.task_id || item.id || '';
            var taskTitulo = item.task_titulo || item.descricao || '';
            var projectTitulo = item.project_titulo || 'Sem projeto';
            var projectValue = item.project_value || (item.project_id ? String(item.project_id) : 'sem_projeto');
            var commentsCount = Number(item.comments_count || 0);
            var anexosCount = Number(item.anexos_count || 0);
            var legacyTipoOption = tipoPedido === 'implementacao'
                ? '<option value="implementacao" selected hidden>Implementação (legado)</option>'
                : '';

            var prioridadeOptions = '<option value="">—</option>' +
                '<option value="baixa"' + (prioridade === 'baixa' ? ' selected' : '') + '>Baixa</option>' +
                '<option value="media"' + (prioridade === 'media' ? ' selected' : '') + '>Média</option>' +
                '<option value="alta"' + (prioridade === 'alta' ? ' selected' : '') + '>Alta</option>' +
                '<option value="urgente"' + (prioridade === 'urgente' ? ' selected' : '') + '>Urgente</option>';
            var tipoOptions = '<option value="">—</option>' +
                legacyTipoOption +
                '<option value="bug"' + (tipoPedido === 'bug' ? ' selected' : '') + '>Bug</option>' +
                '<option value="melhoria"' + (tipoPedido === 'melhoria' ? ' selected' : '') + '>Melhoria</option>' +
                '<option value="duvida"' + (tipoPedido === 'duvida' ? ' selected' : '') + '>Dúvida</option>' +
                '<option value="outros"' + (tipoPedido === 'outros' ? ' selected' : '') + '>Outros</option>';

            var rowHtml =
                '<div class="task-item-row" ' +
                'data-item-id="' + item.id + '" ' +
                'data-item-status="' + item.status + '" ' +
                'data-comments-count="' + commentsCount + '" ' +
                'data-item-prioridade="' + escapeHtml(prioridade) + '" ' +
                'data-item-tipo="' + escapeHtml(tipoPedido) + '" ' +
                'data-anexos-count="' + anexosCount + '" ' +
                'data-task-id="' + escapeHtml(taskId) + '" ' +
                'data-task-titulo="' + escapeHtml(taskTitulo) + '" ' +
                'data-project-value="' + escapeHtml(projectValue) + '" ' +
                'data-project-titulo="' + escapeHtml(projectTitulo) + '">' +
                '<div class="task-item-bar status-' + item.status + '"></div>' +
                '<div class="task-item-main">' +
                '<div class="task-item-line">' +
                '<div class="task-item-desc-wrap">' +
                '<div class="task-item-desc-row">' +
                '<p class="task-item-desc" data-item-id="' + item.id + '">' + htmlEncode(item.descricao) + '</p>' +
                '<button type="button" class="task-item-desc-edit-btn" data-item-id="' + item.id + '" title="Editar descrição">' +
                '<i class="fas fa-pen" aria-hidden="true"></i><span class="visually-hidden">Editar</span></button>' +
                '</div>' +
                '</div>' +
                '<div class="task-item-meta">' +
                '<select class="task-item-prioridade-select prioridade-' + (prioridade || 'none') + '" data-item-id="' + item.id + '" title="Prioridade" onchange="updateItemPrioridade(' + item.id + ', this.value, this)">' + prioridadeOptions + '</select>' +
                '<select class="task-item-tipo-select" data-item-id="' + item.id + '" title="Tipo" onchange="updateItemTipo(' + item.id + ', this.value)">' + tipoOptions + '</select>' +
                '<select class="task-item-status status-' + item.status + '" onchange="updateItemStatus(' + item.id + ', this.value)" title="Status">' +
                '<option value="nao_iniciada"' + (item.status === 'nao_iniciada' ? ' selected' : '') + '>Não iniciada</option>' +
                '<option value="em_andamento"' + (item.status === 'em_andamento' ? ' selected' : '') + '>Em andamento</option>' +
                '<option value="para_validacao"' + (item.status === 'para_validacao' ? ' selected' : '') + '>Para validação</option>' +
                '<option value="para_ajustes"' + (item.status === 'para_ajustes' ? ' selected' : '') + '>Para ajustes</option>' +
                '<option value="finalizada"' + (item.status === 'finalizada' ? ' selected' : '') + '>Finalizada</option>' +
                '</select>' +
                '<span class="task-item-responsavel" data-item-id="' + item.id + '">' +
                (item.responsavel ? htmlEncode(item.responsavel) : '<em class="responsavel-placeholder">Responsável não informado</em>') +
                '</span>' +
                '<div class="task-item-actions">' +
                '<button type="button" class="task-item-comments-btn" aria-expanded="false" data-target="comments-body-' + item.id + '" onclick="toggleComments(this)" title="Comentários">' +
                '<i class="far fa-comment-alt" aria-hidden="true"></i><span class="task-item-comments-num">' + commentsCount + '</span></button>' +
                '<button type="button" class="task-item-anexos-btn" title="Anexos" data-item-id="' + item.id + '">' +
                '<i class="fas fa-paperclip" aria-hidden="true"></i><span class="task-item-anexos-num">' + anexosCount + '</span></button>' +
                '<button type="button" class="task-item-btn task-item-del" data-bs-toggle="modal" data-bs-target="#deleteItemModal-' + item.id + '" title="Excluir"><i class="fas fa-trash-alt" aria-hidden="true"></i></button>' +
                '</div></div></div>' +
                '<div id="comments-body-' + item.id + '" class="task-item-comments" hidden>' +
                '<div class="task-item-comments-inner">' +
                '<form class="task-comment-form" action="/tarefas/' + item.id + '/comentarios/add" method="POST" data-item-id="' + item.id + '">' +
                '<textarea name="content" rows="1" placeholder="Comentar... (Enter para enviar)" required></textarea>' +
                '<button type="submit" title="Enviar comentário"><i class="fas fa-paper-plane" aria-hidden="true"></i><span class="visually-hidden">Enviar</span></button>' +
                '</form></div></div></div></div>';

            var modalHtml =
                '<div class="modal fade task-detail-v2-modal" id="deleteItemModal-' + item.id + '" tabindex="-1" aria-hidden="true">' +
                '<div class="modal-dialog modal-dialog-centered"><div class="modal-content modal-clean">' +
                '<div class="modal-header-clean"><div><h5 class="modal-title-clean ds-type-section-title">Excluir Tarefa</h5><p class="modal-subtitle-clean ds-type-body-sm">Esta ação não pode ser desfeita</p></div>' +
                '<button type="button" class="btn-close-clean" data-bs-dismiss="modal">&times;</button></div>' +
                '<div class="modal-body-clean"><p>Confirma a exclusão desta tarefa?</p><p class="text-muted small">' + escapeHtml((item.descricao || '').substring(0, 100)) + ((item.descricao || '').length > 100 ? '...' : '') + '</p></div>' +
                '<div class="modal-footer-clean"><button type="button" class="btn-modal-clean btn-cancel-clean" data-bs-dismiss="modal">Cancelar</button>' +
                '<form action="/tarefas/' + item.id + '/delete" method="POST" class="inline-form">' +
                '<button type="submit" class="btn-modal-clean btn-confirm-delete">Excluir</button></form></div></div></div></div>';

            return { rowHtml: rowHtml, modalHtml: modalHtml };
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

        function insertNewItem(data, options) {
            var payload = data || {};
            var item = payload.item || {};
            var opts = options || {};
            var projectValue = normalizeProjectValue(item.project_value || item.project_id || opts.projectValue || '');
            var targetAddRow = opts.addRow || getAddRowByProject(projectValue);
            if (!targetAddRow || !targetAddRow.parentNode) return;

            var markup = buildItemRowMarkup(item);
            var wrap = document.createElement('div');
            wrap.innerHTML = markup.rowHtml + markup.modalHtml;
            targetAddRow.parentNode.insertBefore(wrap.firstChild, targetAddRow);
            targetAddRow.parentNode.insertBefore(wrap.firstChild, targetAddRow);

            updateGroupCount(targetAddRow.closest('.task-hub-group'));
            updateTaskItemsHeaderCount();
            updateTaskItemsTotalPill();
            if (window.taskItemsKanban && typeof window.taskItemsKanban.rebuildFromList === 'function') {
                window.taskItemsKanban.rebuildFromList();
            }
        }

        function focusInlineAdd(projectValue) {
            var addRow = getAddRowByProject(projectValue) || addRows[0];
            if (!addRow) return false;
            var placeholder = addRow.querySelector('[data-role="open-add-form"]');
            var formWrap = addRow.querySelector('[data-role="add-form"]');
            var desc = addRow.querySelector('[data-role="descricao"]');
            addRow.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            if (formWrap && formWrap.hasAttribute('hidden') && placeholder) {
                placeholder.click();
            }
            if (desc) desc.focus();
            return true;
        }

        addRows.forEach(function (addRow) {
            var projectValue = normalizeProjectValue(addRow.getAttribute('data-project-value'));
            var placeholder = addRow.querySelector('[data-role="open-add-form"]');
            var formWrap = addRow.querySelector('[data-role="add-form"]');
            var addDesc = addRow.querySelector('[data-role="descricao"]');
            var addPrioridade = addRow.querySelector('[data-role="prioridade"]');
            var addTipo = addRow.querySelector('[data-role="tipo_pedido"]');
            var addStatus = addRow.querySelector('[data-role="status"]');
            var addResponsavelTrigger = addRow.querySelector('[data-role="responsavel-trigger"]');
            var cancelBtn = addRow.querySelector('[data-role="cancel-add"]');
            var submitBtn = addRow.querySelector('[data-role="submit-add"]');
            if (!placeholder || !formWrap || !addDesc || !addStatus || !addResponsavelTrigger || !cancelBtn || !submitBtn) return;

            var responsavelNames = [];
            var isSubmitting = false;
            renderResponsavelPickerTrigger(addResponsavelTrigger, responsavelNames, 'Responsável');

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
            }

            function showForm() {
                placeholder.style.display = 'none';
                formWrap.removeAttribute('hidden');
                resetForm();
                setTimeout(function () { addDesc.focus(); }, 30);
            }

            function hideForm() {
                formWrap.setAttribute('hidden', '');
                placeholder.style.display = 'flex';
                responsavelPickerManager.closeIfAnchor(addResponsavelTrigger);
            }

            function submitForm(keepOpen) {
                if (isSubmitting) return;
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
                        insertNewItem(data, { addRow: addRow, projectValue: projectValue });
                        if (keepOpen) resetForm();
                        else hideForm();
                    })
                    .catch(function (error) {
                        alert((error && error.message) || 'Erro ao adicionar tarefa.');
                    })
                    .finally(function () {
                        isSubmitting = false;
                    });
            }

            placeholder.addEventListener('click', showForm);
            cancelBtn.addEventListener('click', hideForm);
            submitBtn.addEventListener('click', function () {
                submitForm(false);
            });
            addDesc.addEventListener('input', resizeTextarea);
            addDesc.addEventListener('keydown', function (e) {
                if (e.key === 'Escape') {
                    e.preventDefault();
                    hideForm();
                    return;
                }
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    submitForm(true);
                }
            });

            addResponsavelTrigger.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopPropagation();
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
                if (formWrap.hasAttribute('hidden')) return;
                if (isSubmitting) return;
                if (addRow.contains(event.target)) return;
                if (responsavelPickerManager.isEventInsidePopover(event.target)) return;
                if ((addDesc.value || '').trim()) {
                    submitForm(false);
                    return;
                }
                hideForm();
            });
        });

        window.taskItemsListBridge = {
            listEl: listEl,
            taskId: '',
            sugestoesUrl: sugestoesUrl,
            addItemUrl: addUrl,
            insertItemFromPayload: insertNewItem,
            requestAddItem: requestAddItem,
            focusInlineAdd: focusInlineAdd,
        };
    })();
