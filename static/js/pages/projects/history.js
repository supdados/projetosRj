document.addEventListener('DOMContentLoaded', function() {
    const list = document.getElementById('historyEntriesList');
    if (!list) {
        return;
    }

    const searchInput = document.getElementById('historySearch');
    const typeFilter = document.getElementById('historyTypeFilter');
    const periodFilter = document.getElementById('historyPeriodFilter');
    const noResults = document.getElementById('historyNoResults');

    const counterTotal = document.getElementById('counterTotal');
    const counterProject = document.getElementById('counterProject');
    const counterStage = document.getElementById('counterStage');
    const counterSystem = document.getElementById('counterSystem');

    const entries = Array.from(list.querySelectorAll('.history-entry'));

    function setCounter(node, value) {
        if (node) {
            node.textContent = String(value);
        }
    }

    function parseEntryDate(entry) {
        const value = entry.getAttribute('data-timestamp');
        if (!value) {
            return null;
        }
        const parsed = new Date(value);
        if (Number.isNaN(parsed.getTime())) {
            return null;
        }
        return parsed;
    }

    function inPeriod(entryDate, periodValue) {
        if (!entryDate || periodValue === 'all') {
            return true;
        }
        const now = new Date();
        let days = 0;
        if (periodValue === '7d') {
            days = 7;
        } else if (periodValue === '30d') {
            days = 30;
        } else if (periodValue === '90d') {
            days = 90;
        } else {
            return true;
        }
        const threshold = new Date(now.getTime() - (days * 24 * 60 * 60 * 1000));
        return entryDate >= threshold;
    }

    function entryTextBlob(entry) {
        return [
            entry.getAttribute('data-description') || '',
            entry.getAttribute('data-user') || '',
            entry.getAttribute('data-old') || '',
            entry.getAttribute('data-new') || ''
        ].join(' ');
    }

    function applyFilters() {
        const searchTerm = (searchInput ? searchInput.value : '').trim().toLowerCase();
        const selectedType = typeFilter ? typeFilter.value : 'all';
        const selectedPeriod = periodFilter ? periodFilter.value : 'all';

        let visibleCount = 0;
        let projectCount = 0;
        let stageCount = 0;
        let systemCount = 0;

        entries.forEach(function(entry) {
            const category = entry.getAttribute('data-category') || 'system';
            const textBlob = entryTextBlob(entry);
            const entryDate = parseEntryDate(entry);

            const typeOk = selectedType === 'all' || category === selectedType;
            const searchOk = !searchTerm || textBlob.includes(searchTerm);
            const periodOk = inPeriod(entryDate, selectedPeriod);
            const visible = typeOk && searchOk && periodOk;

            entry.style.display = visible ? '' : 'none';

            if (visible) {
                visibleCount += 1;
                if (category === 'project') {
                    projectCount += 1;
                } else if (category === 'stage') {
                    stageCount += 1;
                } else {
                    systemCount += 1;
                }
            }
        });

        setCounter(counterTotal, visibleCount);
        setCounter(counterProject, projectCount);
        setCounter(counterStage, stageCount);
        setCounter(counterSystem, systemCount);

        if (noResults) {
            noResults.style.display = visibleCount === 0 ? 'block' : 'none';
        }
    }

    if (searchInput) {
        searchInput.addEventListener('input', applyFilters);
    }
    if (typeFilter) {
        typeFilter.addEventListener('change', applyFilters);
    }
    if (periodFilter) {
        periodFilter.addEventListener('change', applyFilters);
    }

    applyFilters();
});
