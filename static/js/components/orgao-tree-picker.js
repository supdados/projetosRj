(function () {
    'use strict';

    function initTreePicker(root) {
        const filterInput = root.querySelector('[data-orgao-tree-filter]');
        const body = root.querySelector('[data-orgao-tree-body]');
        const emptyMsg = root.querySelector('[data-orgao-tree-empty]');
        if (!body) return;

        const nodes = Array.from(body.querySelectorAll('.orgao-tree-node'));
        const allChildren = Array.from(body.querySelectorAll('.orgao-tree-children'));

        function collapseAllExceptSelectedPath() {
            allChildren.forEach(ul => ul.classList.add('is-collapsed'));
            body.querySelectorAll('.orgao-tree-toggle').forEach(btn => btn.classList.remove('is-expanded'));

            const selected = body.querySelector('.orgao-tree-row.is-selected, .orgao-tree-row.is-user-orgao');
            if (!selected) {
                const firstUl = body.querySelector('.orgao-tree-list > .orgao-tree-node > .orgao-tree-children');
                if (firstUl) {
                    firstUl.classList.remove('is-collapsed');
                    const toggle = firstUl.parentElement.querySelector(':scope > .orgao-tree-row > .orgao-tree-toggle');
                    if (toggle) toggle.classList.add('is-expanded');
                }
                return;
            }
            let current = selected.parentElement;
            while (current && current !== body) {
                if (current.classList && current.classList.contains('orgao-tree-children')) {
                    current.classList.remove('is-collapsed');
                    const parentNode = current.parentElement;
                    const toggle = parentNode.querySelector(':scope > .orgao-tree-row > .orgao-tree-toggle');
                    if (toggle) toggle.classList.add('is-expanded');
                }
                current = current.parentElement;
            }
        }

        body.addEventListener('click', function (event) {
            const toggle = event.target.closest('[data-orgao-tree-toggle]');
            if (!toggle) return;
            event.preventDefault();
            event.stopPropagation();
            const node = toggle.closest('.orgao-tree-node');
            const childrenUl = node.querySelector(':scope > .orgao-tree-children');
            if (!childrenUl) return;
            childrenUl.classList.toggle('is-collapsed');
            toggle.classList.toggle('is-expanded');
        });

        function applyFilter(query) {
            const q = (query || '').trim().toLowerCase();
            if (!q) {
                nodes.forEach(n => n.classList.remove('is-filtered-out'));
                allChildren.forEach(ul => {});
                if (emptyMsg) emptyMsg.hidden = true;
                collapseAllExceptSelectedPath();
                return;
            }
            const matches = new Set();
            nodes.forEach(node => {
                const sigla = node.dataset.orgaoNodeSigla || '';
                const nome = node.dataset.orgaoNodeNome || '';
                if (sigla.includes(q) || nome.includes(q)) {
                    matches.add(node);
                    let ancestor = node.parentElement;
                    while (ancestor && ancestor !== body) {
                        if (ancestor.classList && ancestor.classList.contains('orgao-tree-node')) {
                            matches.add(ancestor);
                        }
                        ancestor = ancestor.parentElement;
                    }
                }
            });

            nodes.forEach(node => {
                if (matches.has(node)) {
                    node.classList.remove('is-filtered-out');
                } else {
                    node.classList.add('is-filtered-out');
                }
            });
            allChildren.forEach(ul => ul.classList.remove('is-collapsed'));
            body.querySelectorAll('.orgao-tree-toggle').forEach(btn => btn.classList.add('is-expanded'));

            if (emptyMsg) emptyMsg.hidden = matches.size > 0;
        }

        if (filterInput) {
            filterInput.addEventListener('input', function () {
                applyFilter(filterInput.value);
            });
            filterInput.addEventListener('click', function (e) {
                e.stopPropagation();
            });
        }

        const trigger = root.querySelector('.orgao-tree-trigger');
        if (trigger) {
            trigger.addEventListener('shown.bs.dropdown', function () {});
            trigger.addEventListener('hidden.bs.dropdown', function () {
                if (filterInput) filterInput.value = '';
                applyFilter('');
            });
        }

        collapseAllExceptSelectedPath();
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('.orgao-tree-control').forEach(initTreePicker);
    });
})();
