import type { Readable } from 'svelte/store';
import type { AutosavePhase } from '$lib/utils/autosave';
import type { BoardCard } from './board';
import type { TaskDetail, TaskFieldEdits, TaskDrawerPayload } from './taskDrawer';

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
