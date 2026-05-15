(function () {
    'use strict';

    function getFormRoot(contentHost) {
        return contentHost ? contentHost.querySelector('[data-stage-quick-add-form-host]') : null;
    }

    function getField(contentHost, name) {
        const root = getFormRoot(contentHost);
        return root ? root.querySelector(`[data-role="${name}"]`) : null;
    }

    function getPlaceholder(contentHost) {
        const root = getFormRoot(contentHost);
        return root ? root.querySelector('[data-role="open-add-form"]') : null;
    }

    function getFormWrap(contentHost) {
        const root = getFormRoot(contentHost);
        return root ? root.querySelector('[data-role="add-form"]') : null;
    }

    function getResponsavelTrigger(contentHost) {
        const root = getFormRoot(contentHost);
        return root ? root.querySelector('[data-role="responsavel-trigger"]') : null;
    }

    function resizeTextarea(contentHost) {
        const descricao = getField(contentHost, 'descricao');
        if (!descricao) {
            return;
        }
        descricao.style.height = 'auto';
        descricao.style.height = `${Math.max(32, descricao.scrollHeight)}px`;
    }

    function renderResponsavel(contentHost, responsavelNames) {
        const trigger = getResponsavelTrigger(contentHost);
        if (typeof renderResponsavelPickerTrigger === 'function') {
            renderResponsavelPickerTrigger(trigger, responsavelNames, 'Responsável');
            return;
        }
        const contentEl = trigger ? trigger.querySelector('.responsavel-picker-trigger-content') : null;
        if (!contentEl) {
            return;
        }
        if (!responsavelNames.length) {
            contentEl.innerHTML = '<em class="responsavel-placeholder">Responsável</em>';
            return;
        }
        contentEl.textContent = responsavelNames.join(', ');
    }

    function showForm(contentHost, responsavelNames) {
        const placeholder = getPlaceholder(contentHost);
        const formWrap = getFormWrap(contentHost);
        if (placeholder) {
            placeholder.hidden = true;
            placeholder.style.display = 'none';
        }
        if (formWrap) {
            formWrap.hidden = false;
            formWrap.removeAttribute('hidden');
        }
        renderResponsavel(contentHost, responsavelNames);
        const descricao = getField(contentHost, 'descricao');
        if (descricao) {
            descricao.focus({ preventScroll: true });
            resizeTextarea(contentHost);
        }
    }

    function hideForm(contentHost, closeResponsavelPicker) {
        const placeholder = getPlaceholder(contentHost);
        const formWrap = getFormWrap(contentHost);
        if (formWrap) {
            formWrap.hidden = true;
            formWrap.setAttribute('hidden', '');
        }
        if (placeholder) {
            placeholder.hidden = false;
            placeholder.style.display = 'flex';
        }
        if (typeof closeResponsavelPicker === 'function') {
            closeResponsavelPicker();
        }
    }

    function resetFields(contentHost, responsavelNames) {
        const descricao = getField(contentHost, 'descricao');
        const prioridade = getField(contentHost, 'prioridade');
        const tipo = getField(contentHost, 'tipo_pedido');
        const status = getField(contentHost, 'status');
        const responsavel = getField(contentHost, 'responsavel');
        if (descricao) descricao.value = '';
        if (prioridade) prioridade.value = '';
        if (tipo) tipo.value = '';
        if (status) status.value = 'nao_iniciada';
        if (responsavel) responsavel.value = '';
        responsavelNames.length = 0;
        renderResponsavel(contentHost, responsavelNames);
        resizeTextarea(contentHost);
    }

    function highlightCreatedRow(contentHost, taskId, options) {
        const opts = options || {};
        if (!taskId || !contentHost) {
            return;
        }
        const newRow = contentHost.querySelector(`.task-item-row[data-item-id="${String(taskId)}"]`);
        if (!newRow) {
            return;
        }
        newRow.classList.add('is-just-created');
        window.setTimeout(() => {
            newRow.classList.remove('is-just-created');
        }, 2000);
        if (opts.scroll !== false && typeof newRow.scrollIntoView === 'function') {
            newRow.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'smooth' });
        }
    }

    function updateStageBadge(etapaId, delta) {
        if (!etapaId) {
            return;
        }
        const badge = document.querySelector(`[data-stage-task-count="${String(etapaId)}"]`);
        if (!badge) {
            return;
        }
        const current = parseInt(badge.textContent || '0', 10) || 0;
        const next = Math.max(0, current + delta);
        badge.textContent = String(next);
        badge.classList.toggle('is-empty', next === 0);
    }

    window.stageTaskQuickAddRows = {
        getField,
        getFormRoot,
        getResponsavelTrigger,
        hideForm,
        highlightCreatedRow,
        renderResponsavel,
        resetFields,
        resizeTextarea,
        showForm,
        updateStageBadge,
    };
})();
