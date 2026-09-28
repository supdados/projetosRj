/**
 * Store isolada do drawer: detalhe, autosave, comentários, anexos e ações.
 * O board recebe cards pelos reconciliadores, sem manter outra cópia do detalhe.
 *
 * Falha de autosave preserva o rascunho e termina flush/close/open com false.
 * A pessoa pode corrigir, usar retry() ou descartar explicitamente; uma troca
 * de tarefa nunca envia o rascunho anterior para o novo ID.
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
import { deleteTarefa, moverEtapa } from '$lib/api/tasks';
import { createAutosave, type Autosave, type AutosavePhase } from '$lib/utils/autosave';
import { MSG_TAREFA_INACESSIVEL, accessErrorMessage } from '$lib/utils/accessErrorMessages';
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
	/** Card arquivado: remove da coluna. Finalizadas não arquivadas permanecem. */
	onCardRemoved?: (taskId: number) => void;
}

/** Opções de `open`. */
export interface OpenDrawerOptions {
	mode?: DrawerMode;
	signal?: AbortSignal;
}

/** API pública da store do drawer. */
export interface TaskDrawerStore extends Readable<TaskDrawerState> {
	open(taskId: number, options?: OpenDrawerOptions): Promise<boolean>;
	close(): Promise<boolean>;
	/** Saída explícita quando a pessoa decide descartar uma edição não salva. */
	discardAndClose(): void;
	editField(fields: TaskFieldEdits): void;
	flush(): Promise<boolean>;
	retry(): Promise<boolean>;
	finalizar(): Promise<boolean>;
	arquivar(): Promise<boolean>;
	desarquivar(): Promise<boolean>;
	reativar(): Promise<boolean>;
	/**
	 * Exclui a tarefa aberta (botão lixeira do drawer). Server-autoritativo
	 * (403 só autor/admin). Em sucesso remove o card do board (`onCardRemoved`)
	 * e FECHA o drawer; em erro mantém aberto e expõe a mensagem.
	 */
	deleteTask(): Promise<boolean>;
	/**
	 * Move a tarefa aberta para outra etapa (`etapaId` ou `"sem_etapa"`). Recarrega
	 * o detalhe (reconciliando o card no board). Devolve um `warning` opcional
	 * quando a etapa de destino está concluída (paridade com o legado).
	 */
	moveEtapa(etapaId: number | 'sem_etapa' | null): Promise<{ ok: boolean; warning?: string }>;
	/**
	 * Aplica um envelope `{task, detail}` vindo de um save EXTERNO à store (ex.:
	 * o AssigneePicker persiste responsáveis direto na API): atualiza o detalhe
	 * aberto (se for a mesma tarefa) e reconcilia o card no board.
	 */
	applyExternalPayload(payload: TaskDrawerPayload): void;
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

/** O contrato do board inclui finalizadas e exclui somente arquivadas. */
function leftBoard(card: BoardCard): boolean {
	return card.is_archived;
}

/** Cria uma store de drawer isolada (uma por contexto/página). */
export function createTaskDrawerStore(
	reconcilers: TaskDrawerReconcilers = {}
): TaskDrawerStore {
	const store = writable<TaskDrawerState>({ ...INITIAL });

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
		store.update((state) => {
			if (state.status === 'closed' || state.taskId !== payload.detail.id) return state;
			return { ...state, detail: payload.detail };
		});
		reconcileBoard(payload.task);
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
	async function flushPending(): Promise<boolean> {
		if (!(await autosave.flush())) return false;
		autosave.cancel();
		pendingFields = {};
		return true;
	}

	async function open(taskId: number, options: OpenDrawerOptions = {}): Promise<boolean> {
		if (!(await flushPending())) return false;
		store.set({
			...INITIAL,
			status: 'loading',
			mode: options.mode ?? 'board',
			taskId
		});
		try {
			const payload = await getTaskDetail(taskId, options.signal);
			applyPayload(payload);
			return true;
		} catch (err) {
			if (err instanceof DOMException && err.name === 'AbortError') return false;
			store.update((state) => ({
				...state,
				status: 'error',
				// 404 aqui e anti-enumeracao (nao existe OU sem acesso), S5 §6.3.
				error: accessErrorMessage(err, MSG_TAREFA_INACESSIVEL, 'Falha ao carregar a tarefa.')
			}));
			return false;
		}
	}

	async function close(): Promise<boolean> {
		if (!(await flushPending())) return false;
		store.set({ ...INITIAL });
		return true;
	}

	function discardAndClose(): void {
		autosave.cancel();
		pendingFields = {};
		store.set({ ...INITIAL });
	}

	function editField(fields: TaskFieldEdits): void {
		const state = readStore(store);
		if (state.taskId === null) return;
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
		const id = readStore(store).taskId;
		if (id === null) return false;
		// Salva edições pendentes antes de mudar o ciclo de vida (não perder edição).
		if (!(await autosave.flush())) return false;
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

	/**
	 * Exclui a tarefa aberta. Diferente das ações de ciclo de vida (que aplicam um
	 * payload), a exclusão remove o card do board e fecha o drawer. Em 403 mantém
	 * o drawer aberto e mostra a mensagem do backend (paridade com `delete_task`).
	 */
	async function deleteTask(): Promise<boolean> {
		const id = readStore(store).taskId;
		if (id === null) return false;
		if (!(await autosave.flush())) return false;
		store.update((state) => ({ ...state, acting: true, error: null }));
		try {
			await deleteTarefa(id);
			// Reconcilia o board (remove o card) e fecha o drawer.
			reconcilers.onCardRemoved?.(id);
			autosave.cancel();
			pendingFields = {};
			store.set({ ...INITIAL });
			return true;
		} catch (err) {
			store.update((state) => ({
				...state,
				acting: false,
				error: errorMessage(err, 'Não foi possível excluir a tarefa.')
			}));
			return false;
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
		const id = readStore(store).taskId;
		if (id === null) return { ok: false };
		if (!(await autosave.flush())) return { ok: false };
		store.update((state) => ({ ...state, acting: true, error: null }));
		try {
			const result = await moverEtapa(id, etapaId);
			await open(id, { mode: readStore(store).mode });
			return { ok: true, warning: result.warning };
		} catch (err) {
			store.update((state) => ({
				...state,
				error: errorMessage(err, 'Não foi possível mover a tarefa.')
			}));
			return { ok: false };
		} finally {
			store.update((state) => ({ ...state, acting: false }));
		}
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
