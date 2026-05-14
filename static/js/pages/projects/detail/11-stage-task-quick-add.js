(function () {
    'use strict';

    const overlay = document.getElementById('stageTaskQuickAdd');
    if (!overlay) {
        return;
    }
    const config = window.__PROJECT_DETAIL_CONFIG__ || {};
    const addTaskUrl = config.addTaskUrl;
    if (!addTaskUrl) {
        return;
    }

    const titleEl = overlay.querySelector('[data-stage-quick-add-title]');
    const errorEl = overlay.querySelector('[data-stage-quick-add-error]');
    const createdList = overlay.querySelector('[data-stage-quick-add-created]');
    const formHost = overlay.querySelector('[data-stage-quick-add-form-host]');

    const fields = {
        descricao: overlay.querySelector('[data-role="descricao"]'),
        prioridade: overlay.querySelector('[data-role="prioridade"]'),
        tipo_pedido: overlay.querySelector('[data-role="tipo_pedido"]'),
        status: overlay.querySelector('[data-role="status"]'),
        responsavel: overlay.querySelector('[data-role="responsavel"]'),
    };
    const responsavelTrigger = overlay.querySelector('[data-role="responsavel-trigger"]');
    const responsavelPlaceholder = responsavelTrigger
        ? responsavelTrigger.querySelector('.responsavel-picker-trigger-content')
        : null;
    const submitButton = overlay.querySelector('[data-role="submit-add"]');

    let currentEtapaId = null;
    let currentProjectId = null;

    function open(triggerButton) {
        const etapaId = triggerButton.dataset.etapaId;
        const etapaDescricao = triggerButton.dataset.etapaDescricao || 'Etapa';
        const projectId = triggerButton.dataset.projectId;
        if (!etapaId || !projectId) {
            return;
        }
        currentEtapaId = etapaId;
        currentProjectId = projectId;
        titleEl.textContent = etapaDescricao;
        resetFields();
        clearError();
        createdList.innerHTML = '';
        createdList.hidden = true;
        overlay.classList.remove('ds-hidden');
        overlay.setAttribute('aria-hidden', 'false');
        document.body.classList.add('stage-task-quick-add-open');
        window.requestAnimationFrame(() => {
            if (fields.descricao) {
                fields.descricao.focus();
            }
        });
    }

    function close() {
        overlay.classList.add('ds-hidden');
        overlay.setAttribute('aria-hidden', 'true');
        document.body.classList.remove('stage-task-quick-add-open');
        clearError();
        currentEtapaId = null;
        currentProjectId = null;
    }

    function resetFields() {
        if (fields.descricao) fields.descricao.value = '';
        if (fields.prioridade) fields.prioridade.value = '';
        if (fields.tipo_pedido) fields.tipo_pedido.value = '';
        if (fields.status) fields.status.value = 'nao_iniciada';
        if (fields.responsavel) fields.responsavel.value = '';
        if (responsavelPlaceholder) {
            responsavelPlaceholder.innerHTML =
                '<em class="responsavel-placeholder">Responsável</em>';
        }
    }

    function clearError() {
        errorEl.hidden = true;
        errorEl.textContent = '';
    }

    function showError(message) {
        errorEl.textContent = message;
        errorEl.hidden = false;
    }

    function updateBadge(etapaId, delta) {
        const badge = document.querySelector(`[data-stage-task-count="${etapaId}"]`);
        if (!badge) {
            return;
        }
        const current = parseInt(badge.textContent, 10) || 0;
        const next = Math.max(0, current + delta);
        badge.textContent = String(next);
        badge.classList.toggle('is-empty', next === 0);
    }

    function appendCreated(descricao) {
        const li = document.createElement('li');
        li.className = 'stage-task-quick-add__created-item';
        li.innerHTML = '<i class="fas fa-check"></i><span></span>';
        li.querySelector('span').textContent = descricao;
        createdList.appendChild(li);
        createdList.hidden = false;
    }

    function syncResponsavelFromTrigger() {
        // O responsavel-picker (compartilhado com o hub) atualiza o conteúdo
        // do trigger com os nomes selecionados. Como aqui não há picker real
        // (campo livre), usamos um input simples — mas mantemos o placeholder
        // visual do trigger sincronizado com o valor digitado.
        if (!fields.responsavel || !responsavelPlaceholder) {
            return;
        }
        const value = (fields.responsavel.value || '').trim();
        if (!value) {
            responsavelPlaceholder.innerHTML =
                '<em class="responsavel-placeholder">Responsável</em>';
            return;
        }
        responsavelPlaceholder.textContent = value;
    }

    async function submit() {
        clearError();
        const descricao = (fields.descricao.value || '').trim();
        if (!descricao) {
            showError('Descrição é obrigatória.');
            fields.descricao.focus();
            return;
        }
        const formData = new FormData();
        formData.append('descricao', descricao);
        formData.append('project', currentProjectId || '');
        formData.append('etapa', currentEtapaId || '');
        ['prioridade', 'tipo_pedido', 'status', 'responsavel'].forEach((name) => {
            const field = fields[name];
            if (field) {
                formData.append(name, field.value || '');
            }
        });
        submitButton.disabled = true;
        try {
            const response = await fetch(addTaskUrl, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json',
                },
            });
            const payload = await response.json().catch(() => ({}));
            if (!response.ok || !payload.success) {
                showError(payload.message || 'Não foi possível criar a tarefa.');
                return;
            }
            appendCreated(descricao);
            if (currentEtapaId) {
                updateBadge(currentEtapaId, 1);
            }
            resetFields();
            fields.descricao.focus();
        } catch (err) {
            showError('Erro de rede ao criar a tarefa.');
        } finally {
            submitButton.disabled = false;
        }
    }

    function handleKeydown(event) {
        if (event.key === 'Escape') {
            event.preventDefault();
            close();
            return;
        }
        if (event.key === 'Enter' && !event.shiftKey && event.target === fields.descricao) {
            event.preventDefault();
            submit();
        }
    }

    // Trigger global — abrir vindo de qualquer botão de etapa.
    document.addEventListener('click', (event) => {
        const trigger = event.target.closest('[data-stage-quick-add-trigger]');
        if (trigger) {
            event.preventDefault();
            open(trigger);
            return;
        }
        const dismiss = event.target.closest('[data-stage-quick-add-dismiss]');
        if (dismiss && overlay.contains(dismiss)) {
            event.preventDefault();
            close();
            return;
        }
    });

    // O botão de salvar não está dentro de um <form>, então é click-driven.
    if (submitButton) {
        submitButton.addEventListener('click', (event) => {
            event.preventDefault();
            submit();
        });
    }

    // Quando o usuário clica no trigger de responsável, abrimos um prompt nativo
    // simples (placeholder do picker complexo). Mantém a UX coerente sem puxar
    // o popover do hub, que depende de fetch/url próprios.
    if (responsavelTrigger) {
        responsavelTrigger.addEventListener('click', () => {
            const current = fields.responsavel ? fields.responsavel.value : '';
            const next = window.prompt('Responsável (separe múltiplos por vírgula):', current || '');
            if (next === null) {
                return;
            }
            if (fields.responsavel) {
                fields.responsavel.value = next.trim();
            }
            syncResponsavelFromTrigger();
        });
    }

    overlay.addEventListener('keydown', handleKeydown);
})();
