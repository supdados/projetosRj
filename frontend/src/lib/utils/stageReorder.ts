/**
 * Reordenação de etapas (teclado E drag-and-drop) com semântica ÚNICA de
 * pinagem absoluta: as reuniões Google ficam pinadas em suas posições e a etapa
 * movida anda entre as etapas arrastáveis PULANDO as linhas de reunião —
 * mesma regra aplicada pelo backend de reorder (bug 2.17 da auditoria).
 */
export interface ReorderableStage {
	id: number;
	is_google_meeting?: boolean;
}

/**
 * Move a etapa em ``index`` por ``delta`` (-1 = acima, +1 = abaixo) dentro do
 * subconjunto arrastável, mantendo as reuniões nas suas posições absolutas.
 *
 * Retorna a nova ordem COMPLETA de ids (reuniões incluídas) ou ``null`` quando o
 * movimento é inválido — alvo é reunião, fora da lista, ou já no limite.
 *
 * @example
 * // [E1, M, E2, E3] com E3 (index 3) subindo → [E1, M, E3, E2]
 * moveStageSkippingMeetings(stages, 3, -1);
 */
export function moveStageSkippingMeetings(
	stages: ReorderableStage[],
	index: number,
	delta: number
): number[] | null {
	const stage = stages[index];
	if (!stage || stage.is_google_meeting) return null;

	const draggablePositions = stages
		.map((s, i) => (s.is_google_meeting ? -1 : i))
		.filter((i) => i >= 0);
	const draggableIndex = draggablePositions.indexOf(index);
	const target = draggableIndex + delta;
	if (target < 0 || target >= draggablePositions.length) return null;

	const draggableIds = draggablePositions.map((i) => stages[i].id);
	const [moved] = draggableIds.splice(draggableIndex, 1);
	draggableIds.splice(target, 0, moved);

	let cursor = 0;
	return stages.map((s) => (s.is_google_meeting ? s.id : draggableIds[cursor++]));
}

/**
 * Calcula a nova ordem ao SOLTAR ``draggedId`` sobre ``targetId`` (drop do
 * drag-and-drop): o movimento acontece no subconjunto arrastável e as reuniões
 * permanecem pinadas nas posições absolutas — mesma semântica do teclado e do
 * backend (o drop cruzando uma reunião não a desloca).
 *
 * Retorna a nova ordem COMPLETA de ids ou ``null`` quando o drop é inválido —
 * ids ausentes, alvo igual à origem ou reunião envolvida.
 *
 * @example
 * // [E1, M, E2] com E1 solto abaixo de E2 → [E2, M, E1]
 * dropStagePinningMeetings(stages, e1.id, e2.id, 'bottom');
 */
export function dropStagePinningMeetings(
	stages: ReorderableStage[],
	draggedId: number,
	targetId: number,
	position: 'top' | 'bottom'
): number[] | null {
	if (draggedId === targetId) return null;
	const draggableIds = stages.filter((s) => !s.is_google_meeting).map((s) => s.id);
	const fromIdx = draggableIds.indexOf(draggedId);
	if (fromIdx === -1) return null;
	draggableIds.splice(fromIdx, 1);
	const targetIdx = draggableIds.indexOf(targetId);
	if (targetIdx === -1) return null;
	draggableIds.splice(position === 'top' ? targetIdx : targetIdx + 1, 0, draggedId);
	let cursor = 0;
	return stages.map((s) => (s.is_google_meeting ? s.id : draggableIds[cursor++]));
}
