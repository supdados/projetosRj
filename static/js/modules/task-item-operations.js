// === task-item-operations.js — Funções de operações AJAX (updateItemStatus, updateItemPrioridade, etc.) ===
    // Atualizar status da tarefa via AJAX (sem recarregar a página)
    function updateItemStatus(itemId, status, options) {
        var opts = options || {};
        var showAlert = opts.showAlert !== false;

        return fetch('/tarefas/' + itemId + '/update_status', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ status: status })
        })
            .then(function (response) { return response.json(); })
            .then(function (data) {
                if (!data.success) {
                    throw new Error(data.message || 'Erro ao atualizar status.');
                }

                var row = getTaskItemRowById(itemId);
                if (row) {
                    setTaskItemRowStatus(row, status);
                    syncTaskItemRowMetadata(row);
                }

                if (!opts.skipKanbanSync && window.taskItemsKanban && typeof window.taskItemsKanban.syncItemFromRow === 'function') {
                    window.taskItemsKanban.syncItemFromRow(String(itemId));
                }

                return data;
            })
            .catch(function (error) {
                console.error('Erro:', error);
                if (showAlert) {
                    alert(error && error.message ? error.message : 'Erro ao atualizar status');
                }
                throw error;
            });
    }

    function updateItemPrioridade(itemId, prioridade, selectEl) {
        var prev = selectEl ? selectEl.getAttribute('data-prev-value') || '' : '';
        if (selectEl) selectEl.setAttribute('data-prev-value', prioridade);

        return fetch('/tarefas/' + itemId + '/update_prioridade', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prioridade: prioridade || null })
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.success) throw new Error(data.message || 'Erro ao atualizar prioridade.');
                var row = getTaskItemRowById(itemId);
                if (row) {
                    row.setAttribute('data-item-prioridade', prioridade || '');
                    if (selectEl) _applyPrioridadeClass(selectEl, prioridade);
                    syncTaskItemRowMetadata(row);
                }
                if (window.taskItemsKanban && typeof window.taskItemsKanban.syncItemFromRow === 'function') {
                    window.taskItemsKanban.syncItemFromRow(String(itemId));
                }
                return data;
            })
            .catch(function (error) {
                console.error('Erro:', error);
                if (selectEl) {
                    selectEl.value = prev;
                    _applyPrioridadeClass(selectEl, prev);
                }
                alert(error && error.message ? error.message : 'Erro ao atualizar prioridade');
            });
    }

    function updateItemTipo(itemId, tipo) {
        return fetch('/tarefas/' + itemId + '/update_tipo', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tipo_pedido: tipo || null })
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.success) throw new Error(data.message || 'Erro ao atualizar tipo.');
                var row = getTaskItemRowById(itemId);
                if (row) {
                    row.setAttribute('data-item-tipo', tipo || '');
                    syncTaskItemRowMetadata(row);
                }
                if (window.taskItemsKanban && typeof window.taskItemsKanban.syncItemFromRow === 'function') {
                    window.taskItemsKanban.syncItemFromRow(String(itemId));
                }
                return data;
            })
            .catch(function (error) {
                console.error('Erro:', error);
                alert(error && error.message ? error.message : 'Erro ao atualizar tipo');
            });
    }
