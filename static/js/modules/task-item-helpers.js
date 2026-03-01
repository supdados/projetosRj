// === task-item-helpers.js — Funções utilitárias globais (htmlEncode, getTaskItem*, setTaskItem*, etc.) ===
    // Utilidade global de escape HTML (usada fora de IIFEs)
    function htmlEncode(s) {
        var d = document.createElement('div');
        d.textContent = String(s == null ? '' : s);
        return d.innerHTML;
    }

    function getTaskItemRowById(itemId) {
        return document.querySelector('.task-item-row[data-item-id="' + itemId + '"]');
    }

    function getTaskItemProjectValue(itemId) {
        var row = getTaskItemRowById(itemId);
        if (!row) return '';
        return String(row.getAttribute('data-project-value') || '').trim();
    }

    function setTaskItemRowStatus(row, status) {
        if (!row) return;
        row.setAttribute('data-item-status', status);

        var bar = row.querySelector('.task-item-bar');
        if (bar) {
            bar.classList.remove('status-nao_iniciada', 'status-em_andamento', 'status-para_validacao', 'status-para_ajustes', 'status-finalizada');
            bar.classList.add('status-' + status);
        }

        var statusSelect = row.querySelector('.task-item-status');
        if (statusSelect) {
            statusSelect.value = status;
            statusSelect.classList.remove('status-nao_iniciada', 'status-em_andamento', 'status-para_validacao', 'status-para_ajustes', 'status-finalizada');
            statusSelect.classList.add('status-' + status);
        }
    }

    function syncTaskItemRowMetadata(row) {
        if (!row) return;
        var statusSelect = row.querySelector('.task-item-status');
        if (statusSelect && statusSelect.value) {
            row.setAttribute('data-item-status', statusSelect.value);
        }
        var commentsNum = row.querySelector('.task-item-comments-num');
        if (commentsNum) {
            row.setAttribute('data-comments-count', String(parseInt(commentsNum.textContent || '0', 10) || 0));
        }
        var anexosNum = row.querySelector('.task-item-anexos-num');
        if (anexosNum) {
            row.setAttribute('data-anexos-count', String(parseInt(anexosNum.textContent || '0', 10) || 0));
        }
    }

    function updateTaskItemsHeaderCount() {
        var countEl = document.querySelector('.items-header-clean .header-count');
        if (!countEl) return;
        var itemCount = document.querySelectorAll('.task-item-row[data-item-id]').length;
        countEl.textContent = itemCount + (itemCount === 1 ? ' tarefa' : ' tarefas');
    }

    function updateTaskItemsTotalPill() {
        var totalPill = document.querySelector('.tasks-header .tasks-total-pill');
        if (!totalPill) return;
        var itemCount = document.querySelectorAll('.task-item-row[data-item-id]').length;
        totalPill.textContent = itemCount + ' tarefa' + (itemCount === 1 ? '' : 's');
    }

    function updateTaskHubArchiveCounter(delta) {
        if (!delta) return;
        var countEl = document.querySelector('.tasks-header .tasks-archive-count');
        if (!countEl) return;
        var current = parseInt(countEl.textContent || '0', 10);
        if (!Number.isFinite(current)) current = 0;
        var next = current + delta;
        countEl.textContent = String(next < 0 ? 0 : next);
    }

    function ensureTaskHubEmptyState(root) {
        var pageRoot = root || document.getElementById('taskHubPage');
        if (!pageRoot) return;
        var listItems = document.querySelectorAll('.task-item-row[data-item-id]');
        if (listItems.length) return;
        if (pageRoot.querySelector('.tasks-empty-state')) return;

        var itemsSection = pageRoot.querySelector('.task-detail-v2-items.task-hub-items');
        if (itemsSection && itemsSection.parentNode) {
            itemsSection.parentNode.removeChild(itemsSection);
        }

        var emptyState = document.createElement('section');
        emptyState.className = 'tasks-empty-state';
        emptyState.innerHTML =
            '<h2 class="tasks-empty-title">' + escapeTaskItemHtml(pageRoot.getAttribute('data-empty-title') || 'Nenhuma tarefa encontrada') + '</h2>' +
            '<p class="tasks-empty-text">' + escapeTaskItemHtml(pageRoot.getAttribute('data-empty-text') || 'Ajuste os filtros para visualizar tarefas ativas.') + '</p>';
        pageRoot.appendChild(emptyState);
    }

    function removeTaskItemFromDom(itemId) {
        if (!itemId) return false;
        var removed = false;
        var row = getTaskItemRowById(itemId);
        var groupEl = row ? row.closest('.task-hub-group') : null;
        if (row && row.parentNode) {
            row.parentNode.removeChild(row);
            removed = true;
        }

        var modal = document.getElementById('deleteItemModal-' + itemId);
        if (modal && modal.parentNode) {
            modal.parentNode.removeChild(modal);
        }

        if (groupEl) {
            var remaining = groupEl.querySelectorAll('.task-item-row[data-item-id]').length;
            var groupCountEl = groupEl.querySelector('.task-hub-group-count');
            if (groupCountEl) {
                groupCountEl.textContent = remaining + (remaining === 1 ? ' tarefa' : ' tarefas');
            }
            if (remaining === 0 && groupEl.parentNode) {
                groupEl.parentNode.removeChild(groupEl);
            }
        }

        updateTaskItemsHeaderCount();
        updateTaskItemsTotalPill();
        return removed;
    }

    function escapeTaskItemHtml(text) {
        var div = document.createElement('div');
        div.textContent = text == null ? '' : String(text);
        return div.innerHTML;
    }

    function getTaskItemStatus(row) {
        if (!row) return 'nao_iniciada';
        var status = row.getAttribute('data-item-status') || '';
        if (status) return status;
        var statusSelect = row.querySelector('.task-item-status');
        return statusSelect && statusSelect.value ? statusSelect.value : 'nao_iniciada';
    }

    function getTaskItemDescricao(row) {
        if (!row) return '';
        var descEl = row.querySelector('.task-item-desc');
        return descEl ? (descEl.textContent || '').trim() : '';
    }

    function getTaskItemResponsavel(row) {
        if (!row) return '';
        var responsavelEl = row.querySelector('.task-item-responsavel');
        if (!responsavelEl) return '';
        if (responsavelEl.querySelector('.responsavel-placeholder')) return '';
        var value = (responsavelEl.textContent || '').trim();
        return value === '\u00a0' ? '' : value;
    }

    function getTaskItemCommentsCount(row) {
        if (!row) return 0;
        var count = parseInt(row.getAttribute('data-comments-count') || '0', 10);
        if (!Number.isFinite(count) || count < 0) count = 0;
        return count;
    }

    function setTaskItemCommentsCount(row, count) {
        if (!row) return;
        var safeCount = parseInt(count, 10);
        if (!Number.isFinite(safeCount) || safeCount < 0) safeCount = 0;
        var numEl = row.querySelector('.task-item-comments-num');
        if (numEl) numEl.textContent = String(safeCount);
        row.setAttribute('data-comments-count', String(safeCount));
    }

    function getTaskItemPrioridade(row) {
        if (!row) return '';
        return row.getAttribute('data-item-prioridade') || '';
    }

    function getTaskItemTipoPedido(row) {
        if (!row) return '';
        return row.getAttribute('data-item-tipo') || '';
    }

    function getTaskItemAnexosCount(row) {
        if (!row) return 0;
        var count = parseInt(row.getAttribute('data-anexos-count') || '0', 10);
        if (!Number.isFinite(count) || count < 0) count = 0;
        return count;
    }

    function setTaskItemAnexosCount(row, count) {
        if (!row) return;
        var safeCount = parseInt(count, 10);
        if (!Number.isFinite(safeCount) || safeCount < 0) safeCount = 0;
        var numEl = row.querySelector('.task-item-anexos-num');
        if (numEl) numEl.textContent = String(safeCount);
        row.setAttribute('data-anexos-count', String(safeCount));
    }

    var PRIORIDADE_LABELS = { baixa: 'Baixa', media: 'Média', alta: 'Alta', urgente: 'Urgente' };
    var TIPO_LABELS = { implementacao: 'Implementação', bug: 'Bug', melhoria: 'Melhoria', duvida: 'Dúvida', outros: 'Outros' };

    function setTaskItemChips(row, prioridade, tipo) {
        if (!row) return;
        row.setAttribute('data-item-prioridade', prioridade || '');
        row.setAttribute('data-item-tipo', tipo || '');

        var prioSel = row.querySelector('.task-item-prioridade-select');
        if (prioSel) {
            prioSel.value = prioridade || '';
            _applyPrioridadeClass(prioSel, prioridade || '');
        }

        var tipoSel = row.querySelector('.task-item-tipo-select');
        if (tipoSel) {
            tipoSel.value = tipo || '';
        }
    }

    function _applyPrioridadeClass(sel, prioridade) {
        sel.classList.remove('prioridade-baixa', 'prioridade-media', 'prioridade-alta', 'prioridade-urgente', 'prioridade-none');
        sel.classList.add(prioridade ? 'prioridade-' + prioridade : 'prioridade-none');
    }

    function getTaskItemCommentsInner(row) {
        if (!row) return null;
        return row.querySelector('.task-item-comments-inner');
    }

    function findTaskCommentElementById(commentId) {
        if (!commentId) return null;
        return document.getElementById('comment-' + commentId);
    }

    function extractTaskCommentData(commentEl) {
        if (!commentEl) return null;
        var idAttr = commentEl.id || '';
        var id = parseInt(idAttr.replace('comment-', ''), 10);
        if (!Number.isFinite(id)) return null;
        var toneIndex = null;
        if (commentEl.classList) {
            for (var i = 0; i < commentEl.classList.length; i++) {
                var cls = commentEl.classList[i];
                if (cls.indexOf('task-comment-author-') === 0) {
                    var parsedTone = parseInt(cls.replace('task-comment-author-', ''), 10);
                    if (Number.isFinite(parsedTone)) {
                        toneIndex = Math.abs(parsedTone) % 5;
                    }
                    break;
                }
            }
        }

        var authorEl = commentEl.querySelector('.task-comment-user');
        var timeEl = commentEl.querySelector('.task-comment-time');
        var textEl = commentEl.querySelector('.task-comment-text');
        var editBtn = commentEl.querySelector('.btn-edit-comment[data-comment-id]');
        var hasDelete = !!commentEl.querySelector('form[action*="/tarefas/comentarios/"][action$="/delete"]');

        return {
            id: id,
            author_name: authorEl ? (authorEl.textContent || '').trim() : '',
            created_at: timeEl ? (timeEl.textContent || '').trim() : '',
            content: textEl ? (textEl.textContent || '').trim() : '',
            is_own: !!editBtn && hasDelete,
            user_id: null,
            tone_index: toneIndex,
            updated_at: null,
        };
    }

    function buildTaskCommentMarkup(comment) {
        var item = comment || {};
        var commentId = item.id;
        var authorClass = 'task-comment-author-' + ((item.user_id != null ? item.user_id : commentId || 0) % 5);
        var createdAt = item.updated_at
            ? (item.updated_at + ' (edit.)')
            : (item.created_at || '');

        var html = '<div class="task-comment ' + authorClass + '" id="comment-' + commentId + '">' +
            '<div class="task-comment-head">' +
            '<span class="task-comment-user">' + escapeTaskItemHtml(item.author_name || '') + '</span>' +
            '<span class="task-comment-time">' + escapeTaskItemHtml(createdAt) + '</span>';

        if (item.is_own) {
            html += '<span class="task-comment-acts">' +
                '<button type="button" class="task-comment-btn btn-edit-comment" data-comment-id="' + commentId +
                '" data-comment-content="' + escapeTaskItemHtml(item.content || '') + '" title="Editar">Editar</button>' +
                '<form action="/tarefas/comentarios/' + commentId + '/delete" method="POST" class="d-inline" onsubmit="return confirm(\'Excluir comentário?\');">' +
                '<button type="submit" class="task-comment-btn task-comment-btn-del" title="Excluir">Excluir</button>' +
                '</form></span>';
        }

        html += '</div><p class="task-comment-text">' + escapeTaskItemHtml(item.content || '') + '</p></div>';
        return html;
    }

    function appendCommentToTaskItemRow(row, comment) {
        if (!row || !comment || !comment.id) return null;
        var wrap = getTaskItemCommentsInner(row);
        if (!wrap) return null;
        var form = wrap.querySelector('.task-comment-form');
        if (!form) return null;

        var temp = document.createElement('div');
        temp.innerHTML = buildTaskCommentMarkup(comment);
        var commentEl = temp.firstChild;
        if (!commentEl) return null;
        wrap.insertBefore(commentEl, form);
        setTaskItemCommentsCount(row, getTaskItemCommentsCount(row) + 1);
        syncTaskItemRowMetadata(row);
        return commentEl;
    }

    function updateTaskCommentInRow(commentId, content, updatedAt) {
        var commentEl = findTaskCommentElementById(commentId);
        if (!commentEl) return;
        var textEl = commentEl.querySelector('.task-comment-text');
        if (textEl) textEl.textContent = content;
        var timeEl = commentEl.querySelector('.task-comment-time');
        if (timeEl && updatedAt) {
            timeEl.textContent = updatedAt + ' (edit.)';
        }
        var editBtn = commentEl.querySelector('.btn-edit-comment[data-comment-id]');
        if (editBtn) editBtn.setAttribute('data-comment-content', content);
    }

    function deleteTaskCommentFromRow(commentId) {
        var commentEl = findTaskCommentElementById(commentId);
        if (!commentEl) return null;
        var row = commentEl.closest('.task-item-row');
        if (commentEl.parentNode) commentEl.parentNode.removeChild(commentEl);
        if (row) {
            setTaskItemCommentsCount(row, Math.max(0, getTaskItemCommentsCount(row) - 1));
            syncTaskItemRowMetadata(row);
        }
        return row;
    }

    function collectTaskItemCommentsFromRow(row) {
        var wrap = getTaskItemCommentsInner(row);
        if (!wrap) return [];
        return Array.prototype.map.call(
            wrap.querySelectorAll('.task-comment[id^="comment-"]'),
            function (commentEl) { return extractTaskCommentData(commentEl); }
        ).filter(function (item) { return !!item; });
    }

    function updateTaskItemRowFromPayload(item) {
        if (!item || !item.id) return null;
        var row = getTaskItemRowById(item.id);
        if (!row) return null;

        if (typeof item.descricao === 'string') {
            var descEl = row.querySelector('.task-item-desc');
            if (descEl) descEl.textContent = item.descricao;
        }

        if (typeof item.status === 'string') {
            setTaskItemRowStatus(row, item.status);
        }

        if (typeof item.responsavel === 'string') {
            var respEl = row.querySelector('.task-item-responsavel');
            if (respEl) {
                setResponsavelCellText(respEl, item.responsavel);
            }
        }

        if (typeof item.comments_count === 'number') {
            setTaskItemCommentsCount(row, item.comments_count);
        }

        if (typeof item.anexos_count === 'number') {
            setTaskItemAnexosCount(row, item.anexos_count);
        }

        if (typeof item.prioridade === 'string' || typeof item.tipo_pedido === 'string') {
            var newPrioridade = typeof item.prioridade === 'string' ? item.prioridade : getTaskItemPrioridade(row);
            var newTipo = typeof item.tipo_pedido === 'string' ? item.tipo_pedido : getTaskItemTipoPedido(row);
            setTaskItemChips(row, newPrioridade, newTipo);
        }

        syncTaskItemRowMetadata(row);
        return row;
    }

    function persistTaskItemDetails(itemId, payload) {
        var row = getTaskItemRowById(itemId);
        var safePayload = payload || {};
        var hasOwn = Object.prototype.hasOwnProperty;

        var descricaoValue = hasOwn.call(safePayload, 'descricao')
            ? (safePayload.descricao || '')
            : (row ? getTaskItemDescricao(row) : '');
        var statusValue = hasOwn.call(safePayload, 'status')
            ? (safePayload.status || 'nao_iniciada')
            : (row ? getTaskItemStatus(row) : 'nao_iniciada');
        var responsavelValue = hasOwn.call(safePayload, 'responsavel')
            ? (safePayload.responsavel || '')
            : (row ? getTaskItemResponsavel(row) : '');
        var prioridadeValue = hasOwn.call(safePayload, 'prioridade')
            ? (safePayload.prioridade || '')
            : (row ? getTaskItemPrioridade(row) : '');
        var tipoPedidoValue = hasOwn.call(safePayload, 'tipo_pedido')
            ? (safePayload.tipo_pedido || '')
            : (row ? getTaskItemTipoPedido(row) : '');

        var formData = new FormData();
        formData.append('descricao', descricaoValue);
        formData.append('status', statusValue);
        formData.append('responsavel', responsavelValue);
        formData.append('prioridade', prioridadeValue);
        formData.append('tipo_pedido', tipoPedidoValue);

        return fetch('/tarefas/' + itemId + '/edit', {
            method: 'POST',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'Accept': 'application/json',
            },
            body: formData,
        })
            .then(function (response) {
                return response.json().catch(function () { return {}; }).then(function (data) {
                    if (!response.ok || !data.success) {
                        throw new Error((data && data.message) || 'Erro ao salvar tarefa.');
                    }
                    return data;
                });
            });
    }

    function focusTaskItemRow(itemId, options) {
        var opts = options || {};
        var targetRow = getTaskItemRowById(itemId);
        if (!targetRow) return false;

        var scrollDelay = typeof opts.scrollDelay === 'number' ? opts.scrollDelay : 180;
        var shouldHighlight = opts.highlight !== false;

        setTimeout(function () {
            targetRow.scrollIntoView({ behavior: 'smooth', block: 'center' });
            if (!shouldHighlight) return;
            targetRow.classList.add('search-focus-highlight');
            setTimeout(function () {
                targetRow.classList.remove('search-focus-highlight');
            }, 2300);
        }, scrollDelay);
        return true;
    }
