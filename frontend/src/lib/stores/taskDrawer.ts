/**
 * Store isolada do drawer: detalhe, autosave, comentários, anexos e ações.
 * O board recebe cards pelos reconciliadores, sem manter outra cópia do detalhe.
 *
 * Falha de autosave preserva o rascunho e termina flush/close/open com false.
 * A pessoa pode corrigir, usar retry() ou descartar explicitamente; uma troca
 * de tarefa nunca envia o rascunho anterior para o novo ID.
 */

import { writable, get as readStore } from 'svelte/store';
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
import { deleteTarefa, moverEtapa } from '$lib/api/tasks';
import { createAutosave, type Autosave } from '$lib/utils/autosave';
import { MSG_TAREFA_INACESSIVEL, accessErrorMessage } from '$lib/utils/accessErrorMessages';
import type { BoardCard } from '$lib/types/board';
import type {
	TaskComment,
	TaskAttachment,
	TaskDrawerPayload,
	TaskFieldEdits
} from '$lib/types/taskDrawer';

import type {
	OpenDrawerOptions, TaskDrawerReconcilers, TaskDrawerState, TaskDrawerStore
} from '$lib/types/taskDrawerStore';
export type {
	DrawerMode, DrawerStatus, OpenDrawerOptions, TaskDrawerReconcilers, TaskDrawerState, TaskDrawerStore
} from '$lib/types/taskDrawerStore';

interface DrawerContext {
	taskId: number;
	selection: number;
	intent: number;
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

/** O contrato do board inclui finalizadas e exclui somente arquivadas. */
function leftBoard(card: BoardCard): boolean {
	return card.is_archived;
}

/** Cria uma store de drawer isolada (uma por contexto/página). */
export function createTaskDrawerStore(
	reconcilers: TaskDrawerReconcilers = {}
): TaskDrawerStore {
	const store = writable<TaskDrawerState>({ ...INITIAL });
	let navigation = 0;
	let selection = 0;
	let loadingRequest: AbortController | null = null;

	function beginNavigation(): number {
		loadingRequest?.abort();
		loadingRequest = null;
		return ++navigation;
	}

	function captureContext(): DrawerContext | null {
		const { taskId } = readStore(store);
		return taskId === null ? null : { taskId, selection, intent: navigation };
	}

	function isCurrent(context: DrawerContext | null): boolean {
		return context !== null && context.selection === selection
			&& readStore(store).taskId === context.taskId;
	}

	function contextError(context: DrawerContext, error: unknown, fallback: string): void {
		if (!isCurrent(context)) return;
		store.update((state) => ({ ...state, error: errorMessage(error, fallback) }));
	}

	/** Aplica o card no board: arquivadas saem; demais ficam na coluna do status. */
	function reconcileBoard(card: BoardCard): void {
		if (leftBoard(card)) {
			reconcilers.onCardRemoved?.(card.id);
		} else {
			reconcilers.onCardChanged?.(card);
		}
	}

	/**
	 * Save externo (fora desta store): só substitui o `detail` se o drawer ainda
	 * está na MESMA tarefa (evita aplicar resposta atrasada de outra tarefa); o
	 * board é reconciliado sempre (o card mudou no servidor de todo jeito).
	 */
	function applyExternalPayload(payload: TaskDrawerPayload): void {
		applyPayload(payload, captureContext());
	}

	/** Aplica o envelope `{task, detail}` no drawer e reconcilia o board. */
	function applyPayload(payload: TaskDrawerPayload, context = captureContext()): void {
		if (isCurrent(context) && context?.taskId === payload.detail.id) {
			store.update((state) => ({
				...state, status: 'ready', detail: { ...payload.detail, ...pendingFields }, error: null
			}));
		}
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
			onSaved: (payload) => {
				pendingFields = {};
				applyPayload(payload);
			},
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

	/**
	 * Persiste edições pendentes da tarefa CORRENTE e zera o acumulador, antes de
	 * trocar ou fechar o drawer. O `flush` precede a troca de `taskId` no store
	 * (o `persistFn` mira a tarefa que estava aberta). Falha retorna false e
	 * preserva o rascunho para corrigir, tentar de novo ou descartar explicitamente.
	 */
	async function flushPending(intent: number): Promise<boolean> {
		if (!(await autosave.flush()) || intent !== navigation) return false;
		autosave.cancel();
		pendingFields = {};
		return true;
	}

	async function open(taskId: number, options: OpenDrawerOptions = {}): Promise<boolean> {
		if (options.signal?.aborted) return false;
		const intent = beginNavigation();
		if (!(await flushPending(intent))) return false;
		selection++;
		const context = { taskId, selection, intent };
		const controller = new AbortController();
		loadingRequest = controller;
		const abort = (): void => controller.abort();
		options.signal?.addEventListener('abort', abort, { once: true });
		if (options.signal?.aborted) abort();
		store.set({
			...INITIAL,
			status: 'loading',
			mode: options.mode ?? 'board',
			taskId
		});
		try {
			const payload = await getTaskDetail(taskId, controller.signal);
			if (intent !== navigation || !isCurrent(context) || controller.signal.aborted) return false;
			applyPayload(payload, context);
			return true;
		} catch (err) {
			if (intent !== navigation || !isCurrent(context) || controller.signal.aborted) return false;
			store.update((state) => ({
				...state,
				status: 'error',
				// 404 aqui e anti-enumeracao (nao existe OU sem acesso), S5 §6.3.
				error: accessErrorMessage(err, MSG_TAREFA_INACESSIVEL, 'Falha ao carregar a tarefa.')
			}));
			return false;
		} finally {
			options.signal?.removeEventListener('abort', abort);
			if (loadingRequest === controller) loadingRequest = null;
			if (intent === navigation && isCurrent(context) && controller.signal.aborted) discardAndClose();
		}
	}

	async function close(): Promise<boolean> {
		const intent = beginNavigation();
		if (!(await flushPending(intent))) return false;
		selection++;
		store.set({ ...INITIAL });
		return true;
	}

	function discardAndClose(): void {
		beginNavigation();
		selection++;
		autosave.cancel();
		pendingFields = {};
		store.set({ ...INITIAL });
	}

	function editField(fields: TaskFieldEdits): void {
		const state = readStore(store);
		if (state.taskId === null || state.status !== 'ready') return;
		pendingFields = { ...pendingFields, ...fields };
		store.update((current) => ({
			...current,
			detail: current.detail ? { ...current.detail, ...fields } : null,
			error: null
		}));
		autosave.schedule(pendingFields);
	}

	function flush(): Promise<boolean> {
		return autosave.flush();
	}

	/** Executa uma ação de ciclo de vida, aplicando o payload e reconciliando. */
	async function runAction(
		action: (id: number) => Promise<TaskDrawerPayload>,
		fallback: string
	): Promise<boolean> {
		const context = captureContext();
		if (!context) return false;
		// Salva edições pendentes antes de mudar o ciclo de vida (não perder edição).
		if (!(await autosave.flush()) || !isCurrent(context) || context.intent !== navigation) return false;
		store.update((state) => ({ ...state, acting: true, error: null }));
		try {
			const payload = await action(context.taskId);
			applyPayload(payload, context);
			return true;
		} catch (err) {
			contextError(context, err, fallback);
			return false;
		} finally {
			if (isCurrent(context)) store.update((state) => ({ ...state, acting: false }));
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

	/**
	 * Exclui a tarefa aberta. Diferente das ações de ciclo de vida (que aplicam um
	 * payload), a exclusão remove o card do board e fecha o drawer. Em 403 mantém
	 * o drawer aberto e mostra a mensagem do backend (paridade com `delete_task`).
	 */
	async function deleteTask(): Promise<boolean> {
		const context = captureContext();
		if (!context) return false;
		if (!(await autosave.flush()) || !isCurrent(context) || context.intent !== navigation) return false;
		store.update((state) => ({ ...state, acting: true, error: null }));
		try {
			await deleteTarefa(context.taskId);
			// Reconcilia o board (remove o card) e fecha o drawer.
			reconcilers.onCardRemoved?.(context.taskId);
			if (isCurrent(context) && context.intent === navigation) discardAndClose();
			return true;
		} catch (err) {
			contextError(context, err, 'Não foi possível excluir a tarefa.');
			return false;
		} finally {
			if (isCurrent(context)) store.update((state) => ({ ...state, acting: false }));
		}
	}

	/**
	 * Move a tarefa aberta para outra etapa. Após o servidor confirmar, recarrega
	 * o detalhe (que reconcilia o card no board via `applyPayload`). Devolve o
	 * `warning` opcional do backend (etapa concluída).
	 */
	async function moveEtapa(
		etapaId: number | 'sem_etapa' | null
	): Promise<{ ok: boolean; warning?: string }> {
		const context = captureContext();
		if (!context) return { ok: false };
		if (!(await autosave.flush()) || !isCurrent(context) || context.intent !== navigation) return { ok: false };
		store.update((state) => ({ ...state, acting: true, error: null }));
		try {
			const result = await moverEtapa(context.taskId, etapaId);
			const payload = await getTaskDetail(context.taskId);
			applyPayload(payload, context);
			return { ok: true, warning: result.warning };
		} catch (err) {
			contextError(context, err, 'Não foi possível mover a tarefa.');
			return { ok: false };
		} finally {
			if (isCurrent(context)) store.update((state) => ({ ...state, acting: false }));
		}
	}

	/** Substitui a lista de comentários do detalhe corrente (mesma tarefa). */
	function setComments(context: DrawerContext, comentarios: TaskComment[]): void {
		if (!isCurrent(context)) return;
		store.update((state) => {
			if (state.detail === null || state.detail.id !== context.taskId) return state;
			return { ...state, detail: { ...state.detail, comentarios }, error: null };
		});
	}

	/** Substitui a lista de anexos do detalhe corrente (mesma tarefa). */
	function setAttachments(context: DrawerContext, anexos: TaskAttachment[]): void {
		if (!isCurrent(context)) return;
		store.update((state) => {
			if (state.detail === null || state.detail.id !== context.taskId) return state;
			return { ...state, detail: { ...state.detail, anexos }, error: null };
		});
	}

	async function addCommentAction(content: string): Promise<boolean> {
		const context = captureContext();
		if (!context) return false;
		try {
			const result = await addComment(context.taskId, content);
			setComments(context, result.comentarios);
			return true;
		} catch (err) {
			contextError(context, err, 'Não foi possível adicionar o comentário.');
			return false;
		}
	}

	async function editCommentAction(commentId: number, content: string): Promise<boolean> {
		const context = captureContext();
		if (!context) return false;
		try {
			const result = await editComment(commentId, content);
			setComments(context, result.comentarios);
			return true;
		} catch (err) {
			contextError(context, err, 'Não foi possível editar o comentário.');
			return false;
		}
	}

	async function deleteCommentAction(commentId: number): Promise<boolean> {
		const context = captureContext();
		if (!context) return false;
		try {
			const result = await deleteComment(commentId);
			setComments(context, result.comentarios);
			return true;
		} catch (err) {
			contextError(context, err, 'Não foi possível excluir o comentário.');
			return false;
		}
	}

	async function refreshAttachments(): Promise<void> {
		const context = captureContext();
		if (!context) return;
		try {
			const result = await listAttachments(context.taskId);
			setAttachments(context, result.anexos);
		} catch (err) {
			contextError(context, err, 'Não foi possível listar os anexos.');
		}
	}

	async function uploadAttachmentAction(file: File): Promise<boolean> {
		const context = captureContext();
		if (!context) return false;
		try {
			const result = await uploadAttachment(context.taskId, file);
			setAttachments(context, result.anexos);
			return true;
		} catch (err) {
			contextError(context, err, 'Não foi possível enviar o anexo.');
			return false;
		}
	}

	async function deleteAttachmentAction(anexoId: number): Promise<boolean> {
		const context = captureContext();
		if (!context) return false;
		try {
			const result = await deleteAttachment(anexoId);
			setAttachments(context, result.anexos);
			return true;
		} catch (err) {
			contextError(context, err, 'Não foi possível excluir o anexo.');
			return false;
		}
	}

	return {
		subscribe: store.subscribe,
		open,
		close,
		discardAndClose,
		editField,
		flush,
		retry: autosave.retry,
		finalizar,
		arquivar,
		desarquivar,
		reativar,
		deleteTask,
		moveEtapa,
		applyExternalPayload,
		addComment: addCommentAction,
		editComment: editCommentAction,
		deleteComment: deleteCommentAction,
		refreshAttachments,
		uploadAttachment: uploadAttachmentAction,
		deleteAttachment: deleteAttachmentAction
	};
}
