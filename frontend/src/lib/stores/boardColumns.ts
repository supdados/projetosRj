import { TASK_STATUS_ORDER, STATUS_LABELS, normalizeStatus, type TaskStatus } from '$lib/utils/taskStatus';
import type { BoardCard, BoardColumn, BoardData } from '$lib/types/board';

/**
 * Reconstrói as 5 colunas canônicas a partir de uma carga do backend,
 * garantindo ordem fixa e bucketização por `normalizeStatus` (status legado
 * desconhecido cai na primeira coluna — igual ao backend).
 */
export function columnsFromData(data: BoardData): BoardColumn[] {
	const byStatus = new Map<TaskStatus, BoardCard[]>(
		TASK_STATUS_ORDER.map((status) => [status, []])
	);
	for (const column of data.columns) {
		for (const card of column.tasks) {
			byStatus.get(normalizeStatus(card.status))!.push(card);
		}
	}
	return TASK_STATUS_ORDER.map((status) => ({
		status,
		label: STATUS_LABELS[status],
		tasks: byStatus.get(status)!
	}));
}

/** Localiza um card e sua coluna no snapshot atual. */
export function findCard(
	columns: BoardColumn[],
	cardId: number
): { card: BoardCard; status: TaskStatus } | null {
	for (const column of columns) {
		const card = column.tasks.find((task) => task.id === cardId);
		if (card) return { card, status: column.status };
	}
	return null;
}

/** Cópia rasa por coluna (clona a lista `tasks`; cards são imutáveis aqui). */
export function cloneColumns(columns: BoardColumn[]): BoardColumn[] {
	return columns.map((column) => ({ ...column, tasks: [...column.tasks] }));
}

/** Move um card entre/dentro de colunas, retornando colunas NOVAS (imutável). */
export function withCardMoved(
	columns: BoardColumn[],
	cardId: number,
	toStatus: TaskStatus,
	index: number,
	overrideStatus = true
): BoardColumn[] {
	const next = cloneColumns(columns);
	let moved: BoardCard | null = null;
	for (const column of next) {
		const at = column.tasks.findIndex((task) => task.id === cardId);
		if (at !== -1) {
			moved = column.tasks[at];
			column.tasks.splice(at, 1);
			break;
		}
	}
	if (!moved) return columns;
	const target = next.find((column) => column.status === toStatus);
	if (!target) return columns;
	const card = overrideStatus && moved.status !== toStatus
		? { ...moved, status: toStatus }
		: moved;
	const clamped = Math.max(0, Math.min(index, target.tasks.length));
	target.tasks.splice(clamped, 0, card);
	return next;
}

/** Reaplica a ordem `orderedIds` numa coluna (cards desconhecidos ignorados). */
export function withColumnReordered(
	columns: BoardColumn[],
	status: TaskStatus,
	orderedIds: number[]
): BoardColumn[] {
	const next = cloneColumns(columns);
	const column = next.find((c) => c.status === status);
	if (!column) return columns;
	const byId = new Map(column.tasks.map((task) => [task.id, task]));
	const reordered: BoardCard[] = [];
	for (const id of orderedIds) {
		const card = byId.get(id);
		if (card) {
			reordered.push(card);
			byId.delete(id);
		}
	}
	// Mantém quaisquer cards remanescentes (defensivo) ao final.
	for (const card of byId.values()) reordered.push(card);
	column.tasks = reordered;
	return next;
}

/** IDs ordenados de uma coluna no snapshot. */
export function columnIds(columns: BoardColumn[], status: TaskStatus): number[] {
	const column = columns.find((c) => c.status === status);
	return column ? column.tasks.map((task) => task.id) : [];
}

/** Resposta parcial só substitui cartões que não mudaram desde o envio. */
export function withColumnsMerged(
	columns: BoardColumn[],
	affected: BoardColumn[],
	submitted: BoardColumn[]
): BoardColumn[] {
	const byStatus = new Map(affected.map((column) => [normalizeStatus(column.status), column]));
	const sentCards = new Map(
		submitted.flatMap((column) => column.tasks.map((card) => [card.id, card] as const))
	);
	return columns.map((column) => {
		const replacement = byStatus.get(column.status);
		if (!replacement) return column;
		const unchanged = new Set(
			column.tasks.filter((card) => sentCards.get(card.id) === card).map((card) => card.id)
		);
		const confirmed = replacement.tasks.filter((card) => unchanged.has(card.id));
		const confirmedIds = new Set(confirmed.map((card) => card.id));
		let position = 0;
		// Novos/editados permanecem no lugar; removidos nunca são reinseridos.
		return {
			...column,
			tasks: column.tasks.map((card) => confirmedIds.has(card.id) ? confirmed[position++] : card)
		};
	});
}

/** O total acompanha os cartões presentes, inclusive após reconciliações parciais. */
export function totalCards(columns: BoardColumn[]): number {
	return columns.reduce((total, column) => total + column.tasks.length, 0);
}
