/**
 * Store do DRAWER de Tarefa (Fase 5b-2) — FACTORY com ESTADO CANÔNICO.
 *
 * Abre UMA tarefa (a partir do board Kanban, da lista ou de uma etapa) com
 * edição inline AUTOSAVE, comentários, anexos e ações de ciclo de vida. O drawer
 * é a fonte de verdade do DETALHE; o board (Fase 5b-1) continua sendo a fonte de
 * verdade do CARD. Para NÃO duplicar estado, toda mutação que afeta o card
 * (campos/status/finalizar/arquivar/desarquivar) é reconciliada na board store
 * via os callbacks `onCardChanged`/`onCardRemoved` injetados pelo consumidor —
 * o drawer nunca mantém uma cópia rival do card no board.
 *
 * AUTOSAVE: usa `createAutosave` (debounce ~520ms + saveToken + coalescing +
 * flush no fechar/blur). O servidor é AUTORITATIVO: 403 ao finalizar/editar
 * campo restrito vira erro no drawer (sem aplicar a mutação).
 *
 * Exemplo:
 *   const drawer = createTaskDrawerStore({
 *     onCardChanged: (card) => board.upsertCard(card),   // reconcilia no board
 *     onCardRemoved: (id) => board.removeCard(id)
 *   });
 *   await drawer.open(7, { mode: 'board' });
 *   drawer.editField({ descricao: 'novo texto' });        // autosave debounced
 *   await drawer.close();                                 // flush + reset
 */

import { writable, get as readStore, type Readable } from 'svelte/store';
import { ApiClientError } from '$lib/api/client';
import {
	getTaskDetail,
	saveFields,
	finalizarTask,
	arquivarTask,
	desarquivarTask,
	reativarTask,
	addComment,
	editComment,
	deleteComment,
	listAttachments,
	uploadAttachment,
	deleteAttachment
} from '$lib/api/taskDrawer';
import { createAutosave, type Autosave, type AutosavePhase } from '$lib/utils/autosave';
import { normalizeStatus } from '$lib/utils/taskStatus';
import type { BoardCard } from '$lib/types/board';
import type {
	TaskComment,
	TaskAttachment,
	TaskDetail,
	TaskDrawerPayload,
	TaskFieldEdits
} from '$lib/types/taskDrawer';

/** Origem de abertura do drawer (metadado de UX; não muda o contrato). */
export type DrawerMode = 'board' | 'list' | 'etapa';

/** Fase de carregamento do detalhe. */
export type DrawerStatus = 'closed' | 'loading' | 'ready' | 'error';

/** Estado canônico exposto pela store do drawer. */
export interface TaskDrawerState {
	status: DrawerStatus;
	mode: DrawerMode;
	/** ID da tarefa aberta (ou `null` quando fechado). */
	taskId: number | null;
	/** Detalhe completo (ou `null` enquanto carrega/fechado). */
	detail: TaskDetail | null;
	/** Fase do autosave de campos (para a UI mostrar "Salvando…/Salvo/Erro"). */
	autosave: AutosavePhase;
	/** Há uma ação de ciclo de vida (finalizar/arquivar/…) em andamento? */
	acting: boolean;
	/** Mensagem do último erro (carregamento/autosave/ação/comentário/anexo). */
	error: string | null;
}

/**
 * Reconciliadores injetados pelo consumidor para refletir a mutação no board
 * SEM duplicar estado (o drawer não conhece a implementação do board).
 */
export interface TaskDrawerReconcilers {
	/** Card atualizado (campos/status/desarquivar): faz upsert na coluna certa. */
	onCardChanged?: (card: BoardCard) => void;
	/** Card que saiu do board (finalizar/arquivar): remove da coluna. */
	onCardRemoved?: (taskId: number) => void;
}

/** Opções de `open`. */
export interface OpenDrawerOptions {
	mode?: DrawerMode;
	signal?: AbortSignal;
}

/** API pública da store do drawer. */
export interface TaskDrawerStore extends Readable<TaskDrawerState> {
	open(taskId: number, options?: OpenDrawerOptions): Promise<void>;
	close(): Promise<void>;
	editField(fields: TaskFieldEdits): void;
	flush(): Promise<void>;
	finalizar(): Promise<boolean>;
	arquivar(): Promise<boolean>;
	desarquivar(): Promise<boolean>;
	reativar(): Promise<boolean>;
	addComment(content: string): Promise<boolean>;
	editComment(commentId: number, content: string): Promise<boolean>;
	deleteComment(commentId: number): Promise<boolean>;
	refreshAttachments(): Promise<void>;
	uploadAttachment(file: File): Promise<boolean>;
	deleteAttachment(anexoId: number): Promise<boolean>;
}

const INITIAL: TaskDrawerState = {
	status: 'closed',
	mode: 'board',
	taskId: null,
	detail: null,
	autosave: 'idle',
	acting: false,
	error: null
};

/** Mensagem amigável de um erro de API/desconhecido. */
function errorMessage(err: unknown, fallback: string): string {
	if (err instanceof ApiClientError) return err.message;
	return fallback;
}

/** True quando o status normalizado indica que o card saiu do board ativo. */
function leftBoard(card: BoardCard): boolean {
	return card.is_archived || normalizeStatus(card.status) === 'finalizada';
}

/** Cria uma store de drawer isolada (uma por contexto/página). */
export function createTaskDrawerStore(
	reconcilers: TaskDrawerReconcilers = {}
): TaskDrawerStore {
	const store = writable<TaskDrawerState>({ ...INITIAL });

	/** Aplica o card no board: remove se saiu (finalizada/arquivada), senão upsert. */
	function reconcileBoard(card: BoardCard): void {
		if (leftBoard(card)) {
			reconcilers.onCardRemoved?.(card.id);
		} else {
			reconcilers.onCardChanged?.(card);
		}
	}

	/** Aplica o envelope `{task, detail}` no drawer e reconcilia o board. */
	function applyPayload(payload: TaskDrawerPayload): void {
		store.update((state) => ({
			...state,
			status: 'ready',
			taskId: payload.detail.id,
			detail: payload.detail,
			error: null
		}));
		reconcileBoard(payload.task);
	}

	// AUTOSAVE de campos: persiste o snapshot acumulado; guarda token/coalescing
	// ficam no createAutosave. `taskId` é lido no momento do persist (o drawer
	// não persiste após fechar — `editField` checa o id corrente).
	const autosave: Autosave<TaskFieldEdits> = createAutosave<TaskFieldEdits, TaskDrawerPayload>(
		(fields) => {
			const id = readStore(store).taskId;
			if (id === null) return Promise.reject(new Error('Drawer fechado.'));
			return saveFields(id, fields);
		},
		{
			onSaved: (payload) => applyPayload(payload),
			onError: (err) =>
				store.update((state) => ({
					...state,
					error: errorMessage(err, 'Não foi possível salvar a tarefa.')
				})),
			onPhaseChange: (phase) =>
				store.update((state) => ({ ...state, autosave: phase }))
		}
	);

	/** Snapshot acumulado dos campos editados (a última edição vence). */
	let pendingFields: TaskFieldEdits = {};

	async function open(taskId: number, options: OpenDrawerOptions = {}): Promise<void> {
		autosave.cancel();
		pendingFields = {};
		store.set({
			...INITIAL,
			status: 'loading',
			mode: options.mode ?? 'board',
			taskId
		});
		try {
			const payload = await getTaskDetail(taskId, options.signal);
			applyPayload(payload);
		} catch (err) {
			if (err instanceof DOMException && err.name === 'AbortError') return;
			store.update((state) => ({
				...state,
				status: 'error',
				error: errorMessage(err, 'Falha ao carregar a tarefa.')
			}));
		}
	}

	async function close(): Promise<void> {
		// Garante que nenhuma edição pendente seja perdida ANTES de fechar.
		await autosave.flush();
		autosave.cancel();
		pendingFields = {};
		store.set({ ...INITIAL });
	}

	function editField(fields: TaskFieldEdits): void {
		const state = readStore(store);
		if (state.taskId === null) return;
		pendingFields = { ...pendingFields, ...fields };
		autosave.schedule(pendingFields);
	}

	async function flush(): Promise<void> {
		await autosave.flush();
	}

	/** Executa uma ação de ciclo de vida, aplicando o payload e reconciliando. */
	async function runAction(
		action: (id: number) => Promise<TaskDrawerPayload>,
		fallback: string
	): Promise<boolean> {
		const id = readStore(store).taskId;
		if (id === null) return false;
		// Salva edições pendentes antes de mudar o ciclo de vida (não perder edição).
		await autosave.flush();
		store.update((state) => ({ ...state, acting: true, error: null }));
		try {
			const payload = await action(id);
			applyPayload(payload);
			return true;
		} catch (err) {
			store.update((state) => ({
				...state,
				error: errorMessage(err, fallback)
			}));
			return false;
		} finally {
			store.update((state) => ({ ...state, acting: false }));
		}
	}

	function finalizar(): Promise<boolean> {
		return runAction(finalizarTask, 'Não foi possível finalizar a tarefa.');
	}

	function arquivar(): Promise<boolean> {
		return runAction(arquivarTask, 'Não foi possível arquivar a tarefa.');
	}

	function desarquivar(): Promise<boolean> {
		return runAction(desarquivarTask, 'Não foi possível desarquivar a tarefa.');
	}

	function reativar(): Promise<boolean> {
		return runAction(reativarTask, 'Não foi possível reativar a tarefa.');
	}

	/** Substitui a lista de comentários do detalhe corrente (mesma tarefa). */
	function setComments(taskId: number, comentarios: TaskComment[]): void {
		store.update((state) => {
			if (state.detail === null || state.detail.id !== taskId) return state;
			return { ...state, detail: { ...state.detail, comentarios }, error: null };
		});
	}

	/** Substitui a lista de anexos do detalhe corrente (mesma tarefa). */
	function setAttachments(taskId: number, anexos: TaskAttachment[]): void {
		store.update((state) => {
			if (state.detail === null || state.detail.id !== taskId) return state;
			return { ...state, detail: { ...state.detail, anexos }, error: null };
		});
	}

	async function addCommentAction(content: string): Promise<boolean> {
		const id = readStore(store).taskId;
		if (id === null) return false;
		try {
			const result = await addComment(id, content);
			setComments(id, result.comentarios);
			return true;
		} catch (err) {
			store.update((state) => ({
				...state,
				error: errorMessage(err, 'Não foi possível adicionar o comentário.')
			}));
			return false;
		}
	}

	async function editCommentAction(commentId: number, content: string): Promise<boolean> {
		const id = readStore(store).taskId;
		if (id === null) return false;
		try {
			const result = await editComment(commentId, content);
			setComments(id, result.comentarios);
			return true;
		} catch (err) {
			store.update((state) => ({
				...state,
				error: errorMessage(err, 'Não foi possível editar o comentário.')
			}));
			return false;
		}
	}

	async function deleteCommentAction(commentId: number): Promise<boolean> {
		const id = readStore(store).taskId;
		if (id === null) return false;
		try {
			const result = await deleteComment(commentId);
			setComments(id, result.comentarios);
			return true;
		} catch (err) {
			store.update((state) => ({
				...state,
				error: errorMessage(err, 'Não foi possível excluir o comentário.')
			}));
			return false;
		}
	}

	async function refreshAttachments(): Promise<void> {
		const id = readStore(store).taskId;
		if (id === null) return;
		try {
			const result = await listAttachments(id);
			setAttachments(id, result.anexos);
		} catch (err) {
			store.update((state) => ({
				...state,
				error: errorMessage(err, 'Não foi possível listar os anexos.')
			}));
		}
	}

	async function uploadAttachmentAction(file: File): Promise<boolean> {
		const id = readStore(store).taskId;
		if (id === null) return false;
		try {
			const result = await uploadAttachment(id, file);
			setAttachments(id, result.anexos);
			return true;
		} catch (err) {
			store.update((state) => ({
				...state,
				error: errorMessage(err, 'Não foi possível enviar o anexo.')
			}));
			return false;
		}
	}

	async function deleteAttachmentAction(anexoId: number): Promise<boolean> {
		const id = readStore(store).taskId;
		if (id === null) return false;
		try {
			const result = await deleteAttachment(anexoId);
			setAttachments(id, result.anexos);
			return true;
		} catch (err) {
			store.update((state) => ({
				...state,
				error: errorMessage(err, 'Não foi possível excluir o anexo.')
			}));
			return false;
		}
	}

	return {
		subscribe: store.subscribe,
		open,
		close,
		editField,
		flush,
		finalizar,
		arquivar,
		desarquivar,
		reativar,
		addComment: addCommentAction,
		editComment: editCommentAction,
		deleteComment: deleteCommentAction,
		refreshAttachments,
		uploadAttachment: uploadAttachmentAction,
		deleteAttachment: deleteAttachmentAction
	};
}
