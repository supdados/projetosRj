(function () {
    'use strict';

    function setOverlayInert(overlay, isInert) {
        if (isInert) {
            overlay.setAttribute('inert', '');
        } else {
            overlay.removeAttribute('inert');
        }
    }

    function getFocusableElements(overlay) {
        return Array.from(
            overlay.querySelectorAll(
                'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
            )
        ).filter((el) => !el.hasAttribute('hidden') && el.offsetParent !== null);
    }

    function focusInitialControl(overlay, contentHost, rows) {
        const descricao = rows.getField(contentHost, 'descricao');
        if (descricao) {
            descricao.focus();
            return;
        }
        const formRoot = rows.getFormRoot(contentHost);
        const addButton = formRoot ? formRoot.querySelector('[data-role="open-add-form"]') : null;
        if (addButton) {
            addButton.focus();
            return;
        }
        const closeButton = overlay.querySelector('[data-stage-quick-add-dismiss]');
        if (closeButton) {
            closeButton.focus();
        }
    }

    function trapFocus(overlay, event) {
        if (overlay.classList.contains('is-closed') || event.key !== 'Tab') {
            return;
        }
        const focusables = getFocusableElements(overlay);
        if (!focusables.length) {
            event.preventDefault();
            return;
        }
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        const active = document.activeElement;
        if (event.shiftKey) {
            if (active === first || !overlay.contains(active)) {
                event.preventDefault();
                last.focus();
            }
            return;
        }
        if (active === last) {
            event.preventDefault();
            first.focus();
        }
    }

    function hasUnsavedDraft(contentHost, rows, responsavelNames) {
        const descricao = rows.getField(contentHost, 'descricao');
        const prioridade = rows.getField(contentHost, 'prioridade');
        const tipo = rows.getField(contentHost, 'tipo_pedido');
        const status = rows.getField(contentHost, 'status');
        const responsavel = rows.getField(contentHost, 'responsavel');
        return Boolean(
            (descricao && descricao.value.trim()) ||
            (prioridade && prioridade.value) ||
            (tipo && tipo.value) ||
            (status && status.value && status.value !== 'nao_iniciada') ||
            (responsavel && responsavel.value.trim()) ||
            responsavelNames.length
        );
    }

    window.stageTaskQuickAddLifecycle = {
        focusInitialControl,
        hasUnsavedDraft,
        setOverlayInert,
        trapFocus,
    };
})();
