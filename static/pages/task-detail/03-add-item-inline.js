    // --- Adicionar item inline (sem modal) ---
    (function () {
        var listEl = document.querySelector('.task-items-list');
        var addRow = document.getElementById('addItemRow');
        var placeholder = document.getElementById('addItemPlaceholder');
        var formWrap = document.getElementById('addItemFormWrap');
        var addDesc = document.getElementById('addItemDesc');
        var addPrioridade = document.getElementById('addItemPrioridade');
        var addTipo = document.getElementById('addItemTipo');
        var addStatus = document.getElementById('addItemStatus');
        var addResponsavelTrigger = document.getElementById('addItemResponsavelTrigger');
        var emptyState = document.getElementById('emptyStateItems');
        var btnFocusAddItem = document.getElementById('btnFocusAddItem');

        if (!listEl || !addRow || !placeholder || !formWrap) return;
        if (!addDesc || !addStatus || !addResponsavelTrigger) return;

        var addUrl = listEl.getAttribute('data-add-item-url');
        var sugestoesUrl = listEl.getAttribute('data-sugestoes-url');
        var taskId = listEl.getAttribute('data-task-id');
        if (!addUrl) return;

        var addResponsavelNames = [];
        var addItemSubmitting = false;
        renderResponsavelPickerTrigger(addResponsavelTrigger, addResponsavelNames, 'Responsável');

        function resizeAddDesc() {
            if (!addDesc) return;
            addDesc.style.height = 'auto';
            addDesc.style.height = Math.max(32, addDesc.scrollHeight) + 'px';
        }

        function resetAddFormForNextItem() {
            if (addDesc) {
                addDesc.value = '';
                resizeAddDesc();
            }
            if (addPrioridade) addPrioridade.value = '';
            if (addTipo) addTipo.value = '';
            addResponsavelNames = [];
            renderResponsavelPickerTrigger(addResponsavelTrigger, addResponsavelNames, 'Responsável');
            responsavelPickerManager.closeIfAnchor(addResponsavelTrigger);
            setTimeout(function () {
                if (addDesc && !formWrap.hasAttribute('hidden')) addDesc.focus();
            }, 0);
        }

        function isAddFormEmpty() {
            var descEmpty = !addDesc || !(addDesc.value || '').trim();
            var respEmpty = !addResponsavelNames.length;
            return descEmpty && respEmpty;
        }

        function showAddForm() {
            placeholder.style.display = 'none';
            formWrap.removeAttribute('hidden');
            addDesc.value = '';
            resizeAddDesc();
            if (addPrioridade) addPrioridade.value = '';
            if (addTipo) addTipo.value = '';
            addStatus.value = 'programado';
            addResponsavelNames = [];
            renderResponsavelPickerTrigger(addResponsavelTrigger, addResponsavelNames, 'Responsável');
            setTimeout(function () { addDesc.focus(); }, 50);
        }

        function hideAddForm() {
            formWrap.setAttribute('hidden', '');
            placeholder.style.display = 'flex';
            responsavelPickerManager.closeIfAnchor(addResponsavelTrigger);
        }

        function escapeHtml(text) {
            var div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function insertNewItem(data) {
            var item = data.item;
            var prioridade = item.prioridade || '';
            var tipoPedido = item.tipo_pedido || '';
            var legacyTipoOption = tipoPedido === 'implementacao'
                ? '<option value="implementacao" selected hidden>Implementação (legado)</option>'
                : '';

            var pOptions = '<option value="">—</option>' +
                '<option value="baixa"' + (prioridade === 'baixa' ? ' selected' : '') + '>Baixa</option>' +
                '<option value="media"' + (prioridade === 'media' ? ' selected' : '') + '>Média</option>' +
                '<option value="alta"' + (prioridade === 'alta' ? ' selected' : '') + '>Alta</option>' +
                '<option value="urgente"' + (prioridade === 'urgente' ? ' selected' : '') + '>Urgente</option>';
            var tOptions = '<option value="">—</option>' +
                legacyTipoOption +
                '<option value="bug"' + (tipoPedido === 'bug' ? ' selected' : '') + '>Bug</option>' +
                '<option value="melhoria"' + (tipoPedido === 'melhoria' ? ' selected' : '') + '>Melhoria</option>' +
                '<option value="duvida"' + (tipoPedido === 'duvida' ? ' selected' : '') + '>Dúvida</option>' +
                '<option value="outros"' + (tipoPedido === 'outros' ? ' selected' : '') + '>Outros</option>';

            var rowHtml = '<div class="task-item-row" data-item-id="' + item.id + '" data-item-status="' + item.status + '" data-comments-count="0" data-item-prioridade="' + (prioridade || '') + '" data-item-tipo="' + (tipoPedido || '') + '" data-anexos-count="0">' +
                '<div class="task-item-bar status-' + item.status + '"></div>' +
                '<div class="task-item-main">' +
                '<div class="task-item-line">' +
                '<div class="task-item-desc-wrap">' +
                '<div class="task-item-desc-row">' +
                '<p class="task-item-desc" data-item-id="' + item.id + '">' + htmlEncode(item.descricao) + '</p>' +
                '<button type="button" class="task-item-desc-edit-btn" data-item-id="' + item.id + '" title="Editar descrição"><i class="fas fa-pen" aria-hidden="true"></i><span class="visually-hidden">Editar</span></button>' +
                '</div>' +
                '</div>' +
                '<div class="task-item-meta">' +
                '<select class="task-item-prioridade-select prioridade-' + (prioridade || 'none') + '" data-item-id="' + item.id + '" title="Prioridade" onchange="updateItemPrioridade(' + item.id + ', this.value, this)">' + pOptions + '</select>' +
                '<select class="task-item-tipo-select" data-item-id="' + item.id + '" title="Tipo" onchange="updateItemTipo(' + item.id + ', this.value)">' + tOptions + '</select>' +
                '<select class="task-item-status status-' + item.status + '" onchange="updateItemStatus(' + item.id + ', this.value)" title="Status">' +
                '<option value="programado"' + (item.status === 'programado' ? ' selected' : '') + '>Programado</option>' +
                '<option value="em_andamento"' + (item.status === 'em_andamento' ? ' selected' : '') + '>Em andamento</option>' +
                '<option value="validacao"' + (item.status === 'validacao' ? ' selected' : '') + '>Validação</option>' +
                '<option value="finalizado"' + (item.status === 'finalizado' ? ' selected' : '') + '>Finalizado</option>' +
                '</select>' +
                '<span class="task-item-responsavel" data-item-id="' + item.id + '">' + (item.responsavel ? htmlEncode(item.responsavel) : '<em class="responsavel-placeholder">Responsável não informado</em>') + '</span>' +
                '<div class="task-item-actions">' +
                '<button type="button" class="task-item-comments-btn" aria-expanded="false" data-target="comments-body-' + item.id + '" onclick="toggleComments(this)" title="Comentários">' +
                '<i class="far fa-comment-alt" aria-hidden="true"></i><span class="task-item-comments-num">0</span></button>' +
                '<button type="button" class="task-item-anexos-btn" title="Anexos" data-item-id="' + item.id + '">' +
                '<i class="fas fa-paperclip" aria-hidden="true"></i><span class="task-item-anexos-num">0</span></button>' +
                '<button type="button" class="task-item-btn task-item-del" data-bs-toggle="modal" data-bs-target="#deleteItemModal-' + item.id + '" title="Excluir"><i class="fas fa-trash-alt" aria-hidden="true"></i></button>' +
                '</div></div></div>' +
                '<div id="comments-body-' + item.id + '" class="task-item-comments" hidden>' +
                '<div class="task-item-comments-inner">' +
                '<form class="task-comment-form" action="/tarefas/itens/' + item.id + '/comentarios/add" method="POST" data-item-id="' + item.id + '">' +
                '<textarea name="content" rows="1" placeholder="Comentar... (Enter para enviar)" required></textarea>' +
                '<button type="submit" title="Enviar comentário"><i class="fas fa-paper-plane" aria-hidden="true"></i><span class="visually-hidden">Enviar</span></button></form></div></div></div></div>';
            var modalHtml = '<div class="modal fade task-detail-v2-modal" id="deleteItemModal-' + item.id + '" tabindex="-1" aria-hidden="true">' +
                '<div class="modal-dialog modal-dialog-centered">' +
                '<div class="modal-content modal-clean">' +
                '<div class="modal-header-clean">' +
                '<div><h5 class="modal-title-clean ds-type-section-title">Excluir Item</h5><p class="modal-subtitle-clean ds-type-body-sm">Esta ação não pode ser desfeita</p></div>' +
                '<button type="button" class="btn-close-clean" data-bs-dismiss="modal">&times;</button></div>' +
                '<div class="modal-body-clean"><p>Confirma a exclusão deste item?</p><p class="text-muted small">' + escapeHtml(item.descricao.substring(0, 100)) + (item.descricao.length > 100 ? '...' : '') + '</p></div>' +
                '<div class="modal-footer-clean">' +
                '<button type="button" class="btn-modal-clean btn-cancel-clean" data-bs-dismiss="modal">Cancelar</button>' +
                '<form action="/tarefas/itens/' + item.id + '/delete" method="POST" class="inline-form">' +
                '<button type="submit" class="btn-modal-clean btn-confirm-delete">Excluir</button></form></div></div></div></div>';
            var wrap = document.createElement('div');
            wrap.innerHTML = rowHtml + modalHtml;
            addRow.parentNode.insertBefore(wrap.firstChild, addRow);
            addRow.parentNode.insertBefore(wrap.firstChild, addRow);
            if (emptyState && emptyState.contains(addRow)) {
                var newRow = emptyState.querySelector('.task-item-row[data-item-id="' + item.id + '"]');
                var newModal = document.getElementById('deleteItemModal-' + item.id);
                if (newRow) listEl.appendChild(newRow);
                if (newModal) listEl.appendChild(newModal);
                listEl.appendChild(addRow);
                if (emptyState.parentNode) emptyState.parentNode.removeChild(emptyState);
            } else if (emptyState) {
                emptyState.style.display = 'none';
            }
            updateTaskItemsHeaderCount();
            if (window.taskItemsKanban && typeof window.taskItemsKanban.rebuildFromList === 'function') {
                window.taskItemsKanban.rebuildFromList();
            }
        }

        function requestAddItem(payload) {
            return new Promise(function (resolve, reject) {
                var dataPayload = payload || {};
                var descricao = (dataPayload.descricao || '').trim();
                if (!descricao) {
                    reject(new Error('Descrição é obrigatória.'));
                    return;
                }

                var formData = new FormData();
                formData.append('descricao', descricao);
                formData.append('status', dataPayload.status || 'programado');
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
                            reject(new Error((data && data.message) || 'Erro ao adicionar item.'));
                        }
                    } catch (err) {
                        reject(new Error('Erro ao adicionar item. Tente novamente.'));
                    }
                };
                xhr.onerror = function () {
                    reject(new Error('Erro de conexão. Tente novamente.'));
                };
                xhr.send(formData);
            });
        }

        function submitAddItem(options) {
            if (addItemSubmitting) return;
            var opts = options || {};
            var keepComposerOpen = opts.keepComposerOpen === true;
            var desc = (addDesc && addDesc.value) ? addDesc.value.trim() : '';
            if (!desc) { addDesc.focus(); return; }

            addItemSubmitting = true;
            requestAddItem({
                descricao: desc,
                status: addStatus ? addStatus.value : 'programado',
                responsavel: addResponsavelNames.join(', '),
                prioridade: addPrioridade ? addPrioridade.value : '',
                tipo_pedido: addTipo ? addTipo.value : '',
            })
                .then(function (data) {
                    insertNewItem(data);
                    if (keepComposerOpen) {
                        resetAddFormForNextItem();
                    } else {
                        hideAddForm();
                    }
                })
                .catch(function (error) {
                    alert((error && error.message) || 'Erro ao adicionar item.');
                })
                .finally(function () {
                    addItemSubmitting = false;
                });
        }

        placeholder.addEventListener('click', showAddForm);

        addDesc.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') hideAddForm();
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                submitAddItem({ keepComposerOpen: true });
            }
        });
        addDesc.addEventListener('input', resizeAddDesc);

        if (addStatus) {
            addStatus.addEventListener('keydown', function (e) {
                if (e.key === 'Escape') hideAddForm();
            });
        }

        addResponsavelTrigger.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            responsavelPickerManager.open({
                anchorEl: addResponsavelTrigger,
                taskId: taskId,
                sugestoesUrl: sugestoesUrl,
                initialRawValue: addResponsavelNames.join(', '),
                onApply: function (payload) {
                    addResponsavelNames = payload.names.slice();
                    renderResponsavelPickerTrigger(addResponsavelTrigger, addResponsavelNames, 'Responsável');
                    return true;
                },
            });
        });

        if (btnFocusAddItem) {
            btnFocusAddItem.addEventListener('click', function () {
                if (window.taskItemsKanban && typeof window.taskItemsKanban.getCurrentView === 'function' &&
                    window.taskItemsKanban.getCurrentView() === 'kanban' &&
                    typeof window.taskItemsKanban.focusComposerForStatus === 'function') {
                    if (window.taskItemsKanban.focusComposerForStatus('programado')) {
                        return;
                    }
                }
                addRow.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                if (formWrap.hasAttribute('hidden')) placeholder.click();
            });
        }

        document.addEventListener('mousedown', function (e) {
            if (formWrap.hasAttribute('hidden')) return;
            if (addItemSubmitting) return;
            if (addRow.contains(e.target)) return;
            if (responsavelPickerManager.isEventInsidePopover(e.target)) return;
            if ((addDesc && (addDesc.value || '').trim())) {
                submitAddItem({ keepComposerOpen: false });
                return;
            }
            if (isAddFormEmpty()) hideAddForm();
        });

        window.taskItemsListBridge = {
            listEl: listEl,
            taskId: taskId,
            sugestoesUrl: sugestoesUrl,
            addItemUrl: addUrl,
            insertItemFromPayload: insertNewItem,
            requestAddItem: requestAddItem,
            focusInlineAdd: function () {
                addRow.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                if (formWrap.hasAttribute('hidden')) showAddForm();
                if (addDesc) addDesc.focus();
            },
        };
    })();

    // Utilidade global de escape HTML (usada fora de IIFEs)
