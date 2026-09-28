/**
 * Store do Kanban de Tarefas (Fase 5b-1) — FACTORY com ESTADO CANÔNICO.
 *
 * A store Svelte é a ÚNICA fonte de verdade do board (colunas + cards). O DOM é
 * derivado dela — NUNCA o contrário. Mutações de DnD são OTIMISTAS: aplicamos na
 * store ao iniciar cada escrita, confirmamos com o backend e revertemos se
 * recusada. Escritas aguardam a anterior para preservar a ordem das ações.
 *
 * Projetada para 2 modos sem acoplar a UI:
 *   - 'board'  -> board completo (5 colunas), usado por /tarefas (kanban).
 *   - 'drawer' -> mesma store carregada/operada para uma única tarefa.
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
import { getBoard, reorderBoard } from '$lib/api/board';
import {
	TASK_STATUS_ORDER,
	STATUS_LABELS,
	normalizeStatus,
	canItemMoveToStatus,
	type TaskStatus
} from '$lib/utils/taskStatus';
import {
	columnsFromData, findCard, cloneColumns, withCardMoved,
	withColumnReordered, columnIds, withColumnsMerged, totalCards
} from './boardColumns';
import { createSerialMutationQueue } from '$lib/utils/serialMutationQueue';
import { sortByPriority } from '$lib/utils/taskPriority';
import type {
	BoardCard,
	BoardColumn,
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
	 * card para a dropzone do status escolhido). Arquivadas não entram no board.
	 */
	addCard(card: BoardCard, status: TaskStatus): void;
	/** Remove um card do board (ex.: tarefa arquivada pelo drawer). */
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
	const writes = createSerialMutationQueue();
	let generation = 0;
	let externalRevision = 0;
	let activeQuery: BoardQuery | null = null;

	async function load(filters: BoardQuery = {}, signal?: AbortSignal): Promise<void> {
		const context = ++generation;
		activeQuery = { ...filters };
		store.update((state) => ({ ...state, status: 'loading', error: null }));
		try {
			const data = await getBoard(filters, signal);
			if (context !== generation || signal?.aborted) return;
			store.update((state) => ({
				...state,
				status: 'ready',
				columns: columnsFromData(data),
				filters: { ...FILTER_DEFAULTS, ...data.filters },
				total: data.total,
				error: null
			}));
		} catch (err) {
			if (context !== generation || signal?.aborted) return;
			if (err instanceof DOMException && err.name === 'AbortError') return;
			store.update((state) => ({
				...state,
				status: 'error',
				error: errorMessage(err, 'Falha ao carregar o board.')
			}));
		}
	}

	/** Revalida após alterações concorrentes; uma leitura velha não apaga novas edições. */
	async function revalidate(context: number): Promise<void> {
		if (activeQuery === null || context !== generation) return;
		const revision = externalRevision;
		try {
			const fresh = await getBoard(activeQuery);
			if (context !== generation || revision !== externalRevision) return;
			const columns = columnsFromData(fresh);
			store.update((state) => ({ ...state, columns, total: totalCards(columns) }));
		} catch (err) {
			if (context === generation) {
				store.update((state) => ({ ...state, error: errorMessage(err, 'Falha ao atualizar o board.') }));
			}
		}
	}

	async function confirmColumns(
		context: number, revision: number, submitted: BoardColumn[], affected: BoardColumn[]
	): Promise<void> {
		if (context !== generation) return;
		store.update((state) => {
			const columns = withColumnsMerged(state.columns, affected, submitted);
			return { ...state, columns, total: totalCards(columns) };
		});
		const returned = new Set(affected.flatMap((column) => column.tasks.map((card) => card.id)));
		const statuses = new Set(affected.map((column) => column.status));
		const omitted = submitted.some((column) =>
			statuses.has(column.status) && column.tasks.some((card) => !returned.has(card.id))
		);
		if (externalRevision !== revision || omitted) await revalidate(context);
	}

	/**
	 * Move um card entre colunas (muda status). Update OTIMISTA + confirmação no
	 * backend + ROLLBACK se recusado. Retorna `true` se o servidor confirmou.
	 *
	 * `canItemMoveToStatus` é só um curto-circuito de UX: se a regra de cliente
	 * já reprova (ex.: finalizar sem permissão), nem chamamos o backend e
	 * sinalizamos o erro. Caso contrário, o servidor decide.
	 */
	function moveCard(
		cardId: number,
		_fromStatus: TaskStatus,
		toStatus: TaskStatus,
		index: number
	): Promise<boolean> {
		const context = generation;
		store.update((state) => ({ ...state, error: null }));
		return writes.run(() => performMove(cardId, toStatus, index, context));
	}

	async function performMove(
		cardId: number, toStatus: TaskStatus, index: number, context: number
	): Promise<boolean> {
		if (context !== generation) return false;
		const revision = externalRevision;
		const before = readStore(store).columns;
		const found = findCard(before, cardId);
		if (!found) return false;
		// A origem pode mudar enquanto a ação aguarda na fila.
		const fromStatus = found.status;
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
		store.update((state) => ({ ...state, columns: optimistic }));

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
			await confirmColumns(context, revision, optimistic, result.columns);
			return true;
		} catch (err) {
			if (context !== generation) return false;
			// 3) Rollback pela operação INVERSA sobre o estado ATUAL — restaurar o
			//    snapshot `before` apagaria moves concorrentes já confirmados (bug 2.11).
			store.update((state) => ({
				...state,
				columns: findCard(state.columns, cardId)?.card === findCard(optimistic, cardId)?.card
					? withCardMoved(state.columns, cardId, found.status, originIndex)
					: state.columns,
				error: errorMessage(err, 'Não foi possível mover a tarefa.')
			}));
			if (externalRevision !== revision) await revalidate(context);
			return false;
		}
	}

	/**
	 * Reordena cards DENTRO de uma coluna (sem mudar status). Update OTIMISTA +
	 * confirmação + ROLLBACK. `orderedIds` é a nova ordem canônica da coluna.
	 */
	function reorder(
		status: TaskStatus,
		orderedIds: number[]
	): Promise<boolean> {
		const context = generation;
		store.update((state) => ({ ...state, error: null }));
		return writes.run(() => performReorder(status, [...orderedIds], context));
	}

	async function performReorder(
		status: TaskStatus, orderedIds: number[], context: number
	): Promise<boolean> {
		if (context !== generation) return false;
		const revision = externalRevision;
		const before = readStore(store).columns;
		const optimistic = withColumnReordered(before, status, orderedIds);
		store.update((state) => ({ ...state, columns: optimistic }));

		try {
			const result = await reorderBoard({
				columns: [{ status, task_ids: columnIds(optimistic, status) }]
			});
			await confirmColumns(context, revision, optimistic, result.columns);
			return true;
		} catch (err) {
			if (context !== generation) return false;
			// Rollback só da coluna afetada, sobre o estado ATUAL: reaplica a ordem
			// anterior aos ids ainda presentes; cards que chegaram em voo vão ao fim.
			const previousIds = columnIds(before, status);
			store.update((state) => ({
				...state,
				columns: withColumnReordered(state.columns, status, previousIds),
				error: errorMessage(err, 'Não foi possível reordenar a coluna.')
			}));
			if (externalRevision !== revision) await revalidate(context);
			return false;
		}
	}

	/**
	 * Insere ou atualiza um card (reconciliação vinda do drawer da Fase 5b-2).
	 * Se o card já existe na coluna do seu status atual, é substituído NO LUGAR:
	 * editar prioridade não reordena a coluna — o salto para a posição ordenada
	 * tirava o card da viewport e lia-se como "a tarefa sumiu" (bug 2026-08-02);
	 * a ordem por prioridade volta no próximo load. Card novo ou que mudou de
	 * coluna entra ordenado na coluna do status (autoritativo do servidor).
	 */
	function upsertCard(card: BoardCard): void {
		externalRevision++;
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
				if (priorIndexInTarget !== -1) {
					target.tasks.splice(Math.min(priorIndexInTarget, target.tasks.length), 0, card);
				} else {
					target.tasks.unshift(card);
					target.tasks = sortByPriority(target.tasks);
				}
			}
			return { ...state, columns: next, total: totalCards(next) };
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
		externalRevision++;
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
			return { ...state, columns: next, total: totalCards(next) };
		});
	}

	/** Remove um card que saiu do board (exclusão ou arquivamento). */
	function removeCard(taskId: number): void {
		externalRevision++;
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
		generation++;
		activeQuery = null;
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
