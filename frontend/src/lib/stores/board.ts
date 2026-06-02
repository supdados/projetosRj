/**
 * Store do Kanban de Tarefas (Fase 5b-1) — FACTORY com ESTADO CANÔNICO.
 *
 * A store Svelte é a ÚNICA fonte de verdade do board (colunas + cards). O DOM é
 * derivado dela — NUNCA o contrário (o JS legado fazia DOM-as-state via
 * `data-*`; aqui não). Mutações de DnD são OTIMISTAS: aplicamos na store, depois
 * confirmamos com o backend (autoritativo) e revertemos (rollback) se o servidor
 * recusar — ex.: 403 ao finalizar sem permissão.
 *
 * Projetada para 2 modos sem acoplar a UI:
 *   - 'board'  -> board completo (5 colunas), usado por /spa/tarefas (kanban).
 *   - 'drawer' -> futuro (5b-2): mesma store, carregada/operada para uma tarefa.
 * O modo é metadado da store; a UI escolhe como renderizar. Sem libs externas
 * de estado (apenas `writable` do Svelte).
 *
 * Exemplo:
 *   const board = createBoardStore();
 *   await board.load({ project: '42' });
 *   await board.moveCard(7, 'em_andamento', 'finalizada', 0);
 */

import { writable, get as readStore, type Readable } from 'svelte/store';
import { ApiClientError } from '$lib/api/client';
import { getBoard, reorderBoard, updateTaskStatus } from '$lib/api/board';
import {
	TASK_STATUS_ORDER,
	STATUS_LABELS,
	normalizeStatus,
	canItemMoveToStatus,
	type TaskStatus
} from '$lib/utils/taskStatus';
import type {
	BoardCard,
	BoardColumn,
	BoardData,
	BoardFilters,
	BoardQuery,
	BoardReorderColumn
} from '$lib/types/board';

/** Modo de operação da store (board completo vs. drawer-only futuro). */
export type BoardMode = 'board' | 'drawer';

/** Fase de carregamento do board. */
export type BoardStatus = 'idle' | 'loading' | 'ready' | 'error';

/** Estado canônico exposto pela store. */
export interface BoardState {
	mode: BoardMode;
	status: BoardStatus;
	columns: BoardColumn[];
	filters: BoardFilters | null;
	total: number;
	/** Mensagem do último erro (carregamento OU rollback de move/reorder). */
	error: string | null;
}

/** Opções da factory. */
export interface CreateBoardStoreOptions {
	/** Modo inicial (default `'board'`). */
	mode?: BoardMode;
}

/** API pública da store (a UI depende disto, não da implementação). */
export interface BoardStore extends Readable<BoardState> {
	load(filters?: BoardQuery, signal?: AbortSignal): Promise<void>;
	moveCard(
		cardId: number,
		fromStatus: TaskStatus,
		toStatus: TaskStatus,
		index: number
	): Promise<boolean>;
	reorder(status: TaskStatus, orderedIds: number[]): Promise<boolean>;
	reset(): void;
}

const FILTER_DEFAULTS: BoardFilters = {
	project: '',
	prioridade: '',
	tipo: '',
	status: '',
	responsavel: '',
	selected_orgao: null
};

/** Colunas vazias canônicas (5, na ordem de `TASK_STATUS_ORDER`). */
function emptyColumns(): BoardColumn[] {
	return TASK_STATUS_ORDER.map((status) => ({
		status,
		label: STATUS_LABELS[status],
		tasks: []
	}));
}

/** Estado inicial para um dado modo. */
function initialState(mode: BoardMode): BoardState {
	return {
		mode,
		status: 'idle',
		columns: emptyColumns(),
		filters: null,
		total: 0,
		error: null
	};
}

/**
 * Reconstrói as 5 colunas canônicas a partir de uma carga do backend,
 * garantindo ordem fixa e bucketização por `normalizeStatus` (status legado
 * desconhecido cai na primeira coluna — igual ao backend).
 */
function columnsFromData(data: BoardData): BoardColumn[] {
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
function findCard(
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
function cloneColumns(columns: BoardColumn[]): BoardColumn[] {
	return columns.map((column) => ({ ...column, tasks: [...column.tasks] }));
}

/** Move um card entre/dentro de colunas, retornando colunas NOVAS (imutável). */
function withCardMoved(
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
function withColumnReordered(
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
function columnIds(columns: BoardColumn[], status: TaskStatus): number[] {
	const column = columns.find((c) => c.status === status);
	return column ? column.tasks.map((task) => task.id) : [];
}

/** Mescla colunas afetadas (resposta de reordenar) sobre o snapshot atual. */
function withColumnsMerged(
	columns: BoardColumn[],
	affected: BoardColumn[]
): BoardColumn[] {
	const byStatus = new Map(affected.map((column) => [normalizeStatus(column.status), column]));
	return columns.map((column) => {
		const replacement = byStatus.get(column.status);
		return replacement
			? { status: column.status, label: column.label, tasks: [...replacement.tasks] }
			: column;
	});
}

/** Extrai mensagem amigável de um erro de API/desconhecido. */
function errorMessage(err: unknown, fallback: string): string {
	if (err instanceof ApiClientError) return err.message;
	return fallback;
}

/**
 * Cria uma store de board independente (estado canônico encapsulado).
 *
 * Cada chamada produz uma store isolada — adequado para "store por board"
 * (um board por contexto) sem estado global compartilhado.
 */
export function createBoardStore(options: CreateBoardStoreOptions = {}): BoardStore {
	const mode: BoardMode = options.mode ?? 'board';
	const store = writable<BoardState>(initialState(mode));

	async function load(filters: BoardQuery = {}, signal?: AbortSignal): Promise<void> {
		store.update((state) => ({ ...state, status: 'loading', error: null }));
		try {
			const data = await getBoard(filters, signal);
			store.update((state) => ({
				...state,
				status: 'ready',
				columns: columnsFromData(data),
				filters: { ...FILTER_DEFAULTS, ...data.filters },
				total: data.total,
				error: null
			}));
		} catch (err) {
			if (err instanceof DOMException && err.name === 'AbortError') return;
			store.update((state) => ({
				...state,
				status: 'error',
				error: errorMessage(err, 'Falha ao carregar o board.')
			}));
		}
	}

	/**
	 * Move um card entre colunas (muda status). Update OTIMISTA + confirmação no
	 * backend + ROLLBACK se recusado. Retorna `true` se o servidor confirmou.
	 *
	 * `canItemMoveToStatus` é só um curto-circuito de UX: se a regra de cliente
	 * já reprova (ex.: finalizar sem permissão), nem chamamos o backend e
	 * sinalizamos o erro. Caso contrário, o servidor decide.
	 */
	async function moveCard(
		cardId: number,
		fromStatus: TaskStatus,
		toStatus: TaskStatus,
		index: number
	): Promise<boolean> {
		const before = readStore(store).columns;
		const found = findCard(before, cardId);
		if (!found) return false;

		// Guard de UX: bloqueia drop inválido sem ir ao servidor.
		if (!canItemMoveToStatus(found.card, toStatus, fromStatus)) {
			store.update((state) => ({
				...state,
				error: 'Sem permissão para finalizar esta tarefa.'
			}));
			return false;
		}

		// 1) Otimista: aplica na store imediatamente.
		const optimistic = withCardMoved(before, cardId, toStatus, index);
		store.update((state) => ({ ...state, columns: optimistic, error: null }));

		// 2) Confirma no backend (autoritativo). Persistimos ordem + status numa
		//    chamada de reordenação, refletindo as colunas afetadas pelo move.
		const affected: BoardReorderColumn[] =
			fromStatus === toStatus
				? [{ status: toStatus, task_ids: columnIds(optimistic, toStatus) }]
				: [
						{ status: fromStatus, task_ids: columnIds(optimistic, fromStatus) },
						{ status: toStatus, task_ids: columnIds(optimistic, toStatus) }
					];

		try {
			const result = await reorderBoard({ columns: affected });
			store.update((state) => ({
				...state,
				columns: withColumnsMerged(state.columns, result.columns),
				error: null
			}));
			return true;
		} catch (err) {
			// 3) Rollback: o servidor recusou (ex.: 403 finalizar). Volta ao snapshot.
			store.update((state) => ({
				...state,
				columns: before,
				error: errorMessage(err, 'Não foi possível mover a tarefa.')
			}));
			return false;
		}
	}

	/**
	 * Reordena cards DENTRO de uma coluna (sem mudar status). Update OTIMISTA +
	 * confirmação + ROLLBACK. `orderedIds` é a nova ordem canônica da coluna.
	 */
	async function reorder(
		status: TaskStatus,
		orderedIds: number[]
	): Promise<boolean> {
		const before = readStore(store).columns;
		const optimistic = withColumnReordered(before, status, orderedIds);
		store.update((state) => ({ ...state, columns: optimistic, error: null }));

		try {
			const result = await reorderBoard({
				columns: [{ status, task_ids: columnIds(optimistic, status) }]
			});
			store.update((state) => ({
				...state,
				columns: withColumnsMerged(state.columns, result.columns),
				error: null
			}));
			return true;
		} catch (err) {
			store.update((state) => ({
				...state,
				columns: before,
				error: errorMessage(err, 'Não foi possível reordenar a coluna.')
			}));
			return false;
		}
	}

	function reset(): void {
		store.set(initialState(mode));
	}

	return { subscribe: store.subscribe, load, moveCard, reorder, reset };
}
