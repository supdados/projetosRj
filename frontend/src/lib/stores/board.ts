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
import { sortByPriority } from '$lib/utils/taskPriority';
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
	/** Insere/atualiza um card vindo de outra fonte (ex.: drawer da Fase 5b-2). */
	upsertCard(card: BoardCard): void;
	/**
	 * Insere um card NOVO (composer) na coluna do `status` informado, no topo
	 * (paridade com `insertItemFromPayload` do composer legado, que move o novo
	 * card para a dropzone do status escolhido). Cards finalizados/arquivados não
	 * entram no board ativo (no-op).
	 */
	addCard(card: BoardCard, status: TaskStatus): void;
	/** Remove um card do board (ex.: tarefa finalizada/arquivada pelo drawer). */
	removeCard(taskId: number): void;
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
		const originIndex = columnIds(before, found.status).indexOf(cardId);

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
			// `moved_task_id` diz ao backend qual card pode transicionar de status
			// (ids stale de mudança concorrente são ignorados lá — bug 2.10).
			const result = await reorderBoard({ columns: affected, moved_task_id: cardId });
			store.update((state) => ({
				...state,
				columns: withColumnsMerged(state.columns, result.columns),
				error: null
			}));
			return true;
		} catch (err) {
			// 3) Rollback pela operação INVERSA sobre o estado ATUAL — restaurar o
			//    snapshot `before` apagaria moves concorrentes já confirmados (bug 2.11).
			store.update((state) => ({
				...state,
				columns: findCard(state.columns, cardId)
					? withCardMoved(state.columns, cardId, found.status, originIndex)
					: state.columns,
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
			// Rollback só da coluna afetada, sobre o estado ATUAL: reaplica a ordem
			// anterior aos ids ainda presentes; cards que chegaram em voo vão ao fim.
			const previousIds = columnIds(before, status);
			store.update((state) => ({
				...state,
				columns: withColumnReordered(state.columns, status, previousIds),
				error: errorMessage(err, 'Não foi possível reordenar a coluna.')
			}));
			return false;
		}
	}

	/**
	 * Insere ou atualiza um card (reconciliação vinda do drawer da Fase 5b-2).
	 * Se o card já existe na coluna do seu status atual, é substituído no lugar
	 * (preserva posição); se mudou de coluna ou é novo, entra no topo da coluna
	 * correta. O status do card determina a coluna (autoritativo do servidor).
	 * Em seguida a coluna alvo é reordenada por prioridade (paridade com o
	 * backend) — editar a prioridade reposiciona o card sem precisar de reload.
	 */
	function upsertCard(card: BoardCard): void {
		store.update((state) => {
			const targetStatus = normalizeStatus(card.status);
			const next = cloneColumns(state.columns);
			let priorIndexInTarget = -1;
			for (const column of next) {
				const at = column.tasks.findIndex((task) => task.id === card.id);
				if (at !== -1) {
					if (column.status === targetStatus) priorIndexInTarget = at;
					column.tasks.splice(at, 1);
				}
			}
			const target = next.find((column) => column.status === targetStatus);
			if (target) {
				const idx = priorIndexInTarget === -1
					? 0
					: Math.min(priorIndexInTarget, target.tasks.length);
				target.tasks.splice(idx, 0, card);
				target.tasks = sortByPriority(target.tasks);
			}
			return { ...state, columns: next };
		});
	}

	/**
	 * Insere um card recém-criado na coluna `status` (composer). O card já vem
	 * com `status` do servidor; usamos o `status` explícito como coluna alvo (a
	 * coluna onde o composer foi acionado). Entra no topo e a coluna é reordenada
	 * por prioridade (paridade com o backend), para um card de baixa prioridade
	 * não ficar no topo até o reload. Se já existir um card com o mesmo id
	 * (defensivo), faz upsert para não duplicar.
	 */
	function addCard(card: BoardCard, status: TaskStatus): void {
		// Card arquivado não pertence ao board ativo (paridade: só tarefas ativas).
		if (card.is_archived) return;
		const targetStatus = normalizeStatus(status);
		store.update((state) => {
			const next = cloneColumns(state.columns);
			for (const column of next) {
				const at = column.tasks.findIndex((task) => task.id === card.id);
				if (at !== -1) column.tasks.splice(at, 1);
			}
			const target = next.find((column) => column.status === targetStatus);
			if (target) {
				target.tasks.unshift(card);
				target.tasks = sortByPriority(target.tasks);
			}
			return { ...state, columns: next, total: state.total + 1 };
		});
	}

	/** Remove um card do board (tarefa saiu do board ativo: finalizada/arquivada). */
	function removeCard(taskId: number): void {
		store.update((state) => {
			const next = cloneColumns(state.columns);
			let removed = false;
			for (const column of next) {
				const at = column.tasks.findIndex((task) => task.id === taskId);
				if (at !== -1) {
					column.tasks.splice(at, 1);
					removed = true;
					break;
				}
			}
			if (!removed) return { ...state, columns: next };
			return { ...state, columns: next, total: Math.max(0, state.total - 1) };
		});
	}

	function reset(): void {
		store.set(initialState(mode));
	}

	return {
		subscribe: store.subscribe,
		load,
		moveCard,
		reorder,
		upsertCard,
		addCard,
		removeCard,
		reset
	};
}
