(function () {
    'use strict';

    const form = document.getElementById('templateForm');
    const list = document.querySelector('[data-stage-list]');
    const itemTemplate = document.getElementById('stage-item-template');
    const addButtons = document.querySelectorAll('[data-add-stage]');
    const clearButtons = document.querySelectorAll('[data-clear-all]');
    const counterCountEl = document.querySelector('[data-stage-count]');
    const counterDurationEl = document.querySelector('[data-stage-duration]');

    if (!form || !list || !itemTemplate) {
        return;
    }

    function getItems() {
        return Array.from(list.querySelectorAll('[data-stage-item]'));
    }

    function renumber() {
        getItems().forEach(function (item, idx) {
            const numberEl = item.querySelector('[data-stage-number]');
            if (numberEl) {
                numberEl.textContent = String(idx + 1);
            }
        });
    }

    function updateCounter() {
        const items = getItems();
        let total = 0;
        items.forEach(function (item) {
            const durInput = item.querySelector('.tpl-stage-duration-input');
            const raw = durInput ? parseInt(durInput.value, 10) : 0;
            if (Number.isFinite(raw) && raw > 0) {
                total += raw;
            }
        });
        if (counterCountEl) counterCountEl.textContent = String(items.length);
        if (counterDurationEl) counterDurationEl.textContent = String(total);
    }

    function refresh() {
        renumber();
        updateCounter();
    }

    let draggedItem = null;

    function createStageItem(options) {
        const opts = options || {};
        const fragment = itemTemplate.content.cloneNode(true);
        const item = fragment.querySelector('[data-stage-item]');
        if (!item) return null;
        if (opts.draft) {
            item.dataset.draftStage = '1';
        }
        if (opts.name) {
            const nameInput = item.querySelector('.tpl-stage-name-input');
            if (nameInput) nameInput.value = opts.name;
        }
        if (opts.duration) {
            const durInput = item.querySelector('.tpl-stage-duration-input');
            if (durInput) durInput.value = opts.duration;
        }
        return item;
    }

    function addStage(options) {
        const item = createStageItem(options);
        if (!item) return null;
        list.appendChild(item);
        refresh();
        const nameInput = item.querySelector('.tpl-stage-name-input');
        if (nameInput && (!options || options.focus !== false)) {
            window.requestAnimationFrame(function () {
                nameInput.focus();
                if (typeof nameInput.select === 'function') {
                    nameInput.select();
                }
            });
        }
        return item;
    }

    function removeStage(item) {
        if (!item || !list.contains(item)) return;
        item.classList.add('is-removing');
        window.setTimeout(function () {
            item.remove();
            refresh();
        }, 140);
    }

    function clearAll() {
        const items = getItems();
        if (items.length === 0) return;
        const ok = window.confirm('Remover todas as etapas deste modelo? Esta ação só é aplicada quando você salvar.');
        if (!ok) return;
        items.forEach(function (item) { item.remove(); });
        refresh();
    }

    addButtons.forEach(function (btn) {
        btn.addEventListener('click', function () {
            addStage({ draft: true });
        });
    });

    clearButtons.forEach(function (btn) {
        btn.addEventListener('click', clearAll);
    });

    list.addEventListener('click', function (event) {
        const removeBtn = event.target.closest('[data-remove-stage]');
        if (removeBtn) {
            event.preventDefault();
            removeStage(removeBtn.closest('[data-stage-item]'));
        }
    });

    list.addEventListener('input', function (event) {
        if (event.target.classList.contains('tpl-stage-duration-input')) {
            updateCounter();
        }
    });

    list.addEventListener('focusout', function (event) {
        const item = event.target.closest('[data-stage-item]');
        if (!item || item.dataset.draftStage !== '1') return;
        window.setTimeout(function () {
            if (!list.contains(item)) return;
            if (item.contains(document.activeElement)) return;
            const nameInput = item.querySelector('.tpl-stage-name-input');
            if (nameInput && !nameInput.value.trim()) {
                removeStage(item);
            }
        }, 0);
    });

    list.addEventListener('keydown', function (event) {
        if (event.key !== 'Enter') return;
        const nameInput = event.target.closest('.tpl-stage-name-input');
        if (!nameInput) return;
        const items = getItems();
        const currentItem = nameInput.closest('[data-stage-item]');
        if (!currentItem) return;
        if (items[items.length - 1] !== currentItem) return;
        event.preventDefault();
        addStage({ draft: true });
    });

    // --- Drag & drop (HTML5 vanilla) -------------------------------------
    let dropIndicator = null;

    function createDropIndicator() {
        if (!dropIndicator) {
            dropIndicator = document.createElement('div');
            dropIndicator.className = 'tpl-stage-drop-indicator';
            document.body.appendChild(dropIndicator);
        }
        return dropIndicator;
    }

    function getDropItems() {
        return getItems().filter(function (item) {
            return item !== draggedItem;
        });
    }

    function getInsertionSlot(clientY) {
        const items = getDropItems();
        if (items.length === 0) return null;

        let previousItem = null;
        for (let index = 0; index < items.length; index += 1) {
            const item = items[index];
            const rect = item.getBoundingClientRect();
            const midpoint = rect.top + rect.height / 2;

            if (clientY < midpoint) {
                return {
                    previousItem: previousItem,
                    referenceItem: item
                };
            }

            previousItem = item;
        }

        return {
            previousItem: previousItem,
            referenceItem: null
        };
    }

    function showDropIndicator(slot) {
        if (!slot || (!slot.referenceItem && !slot.previousItem)) return;

        const indicator = createDropIndicator();
        const listRect = list.getBoundingClientRect();
        const anchorRect = (slot.referenceItem || slot.previousItem).getBoundingClientRect();
        const top = slot.referenceItem ? anchorRect.top - 2 : anchorRect.bottom - 1;

        indicator.style.left = `${listRect.left}px`;
        indicator.style.width = `${listRect.width}px`;
        indicator.style.top = `${top}px`;
        indicator.classList.add('show');
    }

    function hideDropIndicator() {
        if (dropIndicator) {
            dropIndicator.classList.remove('show');
        }
    }

    list.addEventListener('dragstart', function (event) {
        const handle = event.target.closest('[data-drag-handle]');
        if (!handle) {
            event.preventDefault();
            return;
        }
        const item = handle.closest('[data-stage-item]');
        if (!item) {
            event.preventDefault();
            return;
        }
        draggedItem = item;
        event.dataTransfer.effectAllowed = 'move';
        try {
            event.dataTransfer.setData('text/plain', '');
        } catch (e) {
            // Safari can throw on empty payload — ignore.
        }
        window.setTimeout(function () {
            if (draggedItem) {
                draggedItem.classList.add('is-dragging');
            }
        }, 0);
    });

    list.addEventListener('dragend', function () {
        if (draggedItem) {
            draggedItem.classList.remove('is-dragging');
            draggedItem = null;
        }
        hideDropIndicator();
        refresh();
    });

    list.addEventListener('dragover', function (event) {
        if (!draggedItem) return;
        event.preventDefault();
        const slot = getInsertionSlot(event.clientY);
        if (!slot) {
            hideDropIndicator();
            return;
        }
        showDropIndicator(slot);
        event.dataTransfer.dropEffect = 'move';
    });

    list.addEventListener('dragleave', function (event) {
        if (!draggedItem) return;
        if (!list.contains(event.relatedTarget)) {
            hideDropIndicator();
        }
    });

    list.addEventListener('drop', function (event) {
        if (!draggedItem) return;
        event.preventDefault();
        const slot = getInsertionSlot(event.clientY);
        hideDropIndicator();
        if (!slot) return;
        if (slot.referenceItem) {
            list.insertBefore(draggedItem, slot.referenceItem);
        } else {
            list.appendChild(draggedItem);
        }
        refresh();
    });

    form.addEventListener('submit', function () {
        // Evita submit com valores inválidos vazios — o browser já cuida via `required`.
        // Mantemos só o refresh para garantir numeração correta visível até o reload.
        refresh();
    });

    // Bootstrap: se a lista está vazia (criação), oferece uma linha inicial em branco.
    if (getItems().length === 0) {
        addStage({ focus: false });
    }

    refresh();
})();
