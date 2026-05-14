(function () {
    'use strict';

    const config = window.TASK_HUB_CONFIG || {};
    if (config.archivedMode) {
        // Modo arquivado é somente leitura.
        return;
    }
    const urlTemplate = config.moveTaskEtapaUrlTemplate;
    if (!urlTemplate) {
        return;
    }

    const board = document.getElementById('taskItemsListView')
        || document.querySelector('.task-items-list-view')
        || document.body;

    let dragState = null;

    function getRow(target) {
        if (!target) {
            return null;
        }
        return target.closest('.task-item-row');
    }

    function getStageZone(target) {
        if (!target) {
            return null;
        }
        return target.closest('[data-stage-drop-zone]');
    }

    function buildMoveUrl(taskId) {
        return urlTemplate.replace(/\/0\/mover-etapa$/, `/${taskId}/mover-etapa`);
    }

    function clearDropTargets() {
        document
            .querySelectorAll('.is-drop-target, .task-item-row.is-drop-target-top, .task-item-row.is-drop-target-bottom')
            .forEach((el) => {
                el.classList.remove(
                    'is-drop-target',
                    'is-drop-target-top',
                    'is-drop-target-bottom'
                );
            });
    }

    function markRowDragging(row, active) {
        if (!row) {
            return;
        }
        row.classList.toggle('is-dragging', active);
    }

    function sameProject(row, projectId) {
        if (!row) {
            return false;
        }
        return (row.dataset.projectId || '') === String(projectId);
    }

    function performMove(taskId, etapaValue) {
        return fetch(buildMoveUrl(taskId), {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
                Accept: 'application/json',
            },
            body: JSON.stringify({ etapa_id: etapaValue }),
        }).then(async (response) => {
            const payload = await response.json().catch(() => ({}));
            if (!response.ok || !payload.success) {
                throw new Error(payload.message || 'Falha ao mover tarefa.');
            }
            return payload;
        });
    }

    function moveRowInDom(row, targetStageHeader) {
        // Insere o row imediatamente após o header de etapa (vira primeiro item).
        const parent = targetStageHeader.parentNode;
        if (!parent) {
            return;
        }
        parent.insertBefore(row, targetStageHeader.nextSibling);
    }

    function updateRowDataset(row, targetStageHeader) {
        row.dataset.stageValue = targetStageHeader.dataset.stageValue || 'sem_etapa';
        row.dataset.stageId = targetStageHeader.dataset.stageId || '';
        const isLegacy = (targetStageHeader.dataset.stageValue || 'sem_etapa') === 'sem_etapa';
        row.dataset.stageLegacy = isLegacy ? '1' : '0';
    }

    board.addEventListener('dragstart', (event) => {
        const row = getRow(event.target);
        if (!row) {
            return;
        }
        // Só inicia DnD se o drag vem do próprio row (não de form/select).
        const interactive = event.target.closest('input, textarea, select, button, a');
        if (interactive && interactive !== row) {
            return;
        }
        dragState = {
            taskId: row.dataset.itemId,
            projectId: row.dataset.projectId,
            originStageValue: row.dataset.stageValue,
            row,
        };
        event.dataTransfer.effectAllowed = 'move';
        try {
            event.dataTransfer.setData('text/plain', String(dragState.taskId));
        } catch (_err) {
            // Firefox exige setData mas pode falhar em alguns contextos.
        }
        markRowDragging(row, true);
    });

    board.addEventListener('dragend', () => {
        if (dragState) {
            markRowDragging(dragState.row, false);
        }
        clearDropTargets();
        dragState = null;
    });

    board.addEventListener('dragover', (event) => {
        if (!dragState) {
            return;
        }
        const zone = getStageZone(event.target);
        if (!zone) {
            return;
        }
        if (!sameProject(dragState.row, zone.dataset.projectId)) {
            return;
        }
        event.preventDefault();
        event.dataTransfer.dropEffect = 'move';
        clearDropTargets();
        zone.classList.add('is-drop-target');
    });

    board.addEventListener('drop', (event) => {
        if (!dragState) {
            return;
        }
        const zone = getStageZone(event.target);
        if (!zone) {
            return;
        }
        if (!sameProject(dragState.row, zone.dataset.projectId)) {
            return;
        }
        event.preventDefault();
        const targetStageValue = zone.dataset.stageValue || 'sem_etapa';
        const targetStageId = zone.dataset.stageId || '';
        const originStageValue = dragState.originStageValue || 'sem_etapa';
        if (targetStageValue === originStageValue) {
            clearDropTargets();
            return;
        }
        const { taskId, row } = dragState;
        const payloadEtapa = targetStageValue === 'sem_etapa' ? 'sem_etapa' : targetStageId;
        performMove(taskId, payloadEtapa)
            .then(() => {
                moveRowInDom(row, zone);
                updateRowDataset(row, zone);
            })
            .catch((err) => {
                window.alert(err.message || 'Não foi possível mover a tarefa.');
            })
            .finally(() => {
                clearDropTargets();
            });
        dragState = null;
    });

    // Habilita draggable nas rows que ainda não têm o atributo.
    function decorate() {
        document.querySelectorAll('.task-item-row').forEach((row) => {
            if (!row.hasAttribute('draggable')) {
                row.setAttribute('draggable', 'true');
            }
        });
    }
    decorate();

    // Reaplica após renders dinâmicos do hub (add inline cria novas rows).
    const observer = new MutationObserver(decorate);
    observer.observe(board, { childList: true, subtree: true });
})();
