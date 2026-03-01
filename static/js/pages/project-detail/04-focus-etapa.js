    document.addEventListener('DOMContentLoaded', function () {
        const focusEtapaId = new URLSearchParams(window.location.search).get('focus_etapa');
        if (!focusEtapaId) {
            return;
        }

        const target = document.querySelector(`#etapas-tbody tr[data-etapa-id="${focusEtapaId}"]`);
        if (!target) {
            return;
        }

        setTimeout(function () {
            target.scrollIntoView({ behavior: 'smooth', block: 'center' });
            target.classList.add('search-focus-highlight');
            setTimeout(function () {
                target.classList.remove('search-focus-highlight');
            }, 2300);
        }, 180);
    });
