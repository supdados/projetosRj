/**
 * Tipos do DRAWER de Tarefa (Fase 5b-2).
 *
 * Espelham os serializers reais do backend (`routes/api/serializers.py`):
 *   - `serialize_task_detail` -> `TaskDetail` (card + contexto + comentários +
 *     anexos + permissions autoritativos).
 *   - `_serialize_task_comment` -> `TaskComment`.
 *   - `_serialize_task_anexo`   -> `TaskAttachment` (SEM `stored_filename`).
 *   - `serialize_task_card`     -> `BoardCard` (reusado de `$lib/types/board`).
 *
 * O `detalhe`/`campos`/`finalizar`/`arquivar`/`desarquivar`/`reativar` devolvem
 * o envelope `{task, detail}`: `task` é o card canônico que a board store
 * reconcilia (Fase 5b-1); `detail` é o payload completo do drawer.
 */

import type { BoardCard } from '$lib/types/board';

/** Bloco autoritativo de permissões do drawer (derivado server-side). */
export interface TaskDrawerPermissions {
	can_edit: boolean;
	can_finalize: boolean;
	can_delete: boolean;
}

/** Contexto mínimo da etapa vinculada (cabeçalho do drawer). */
export interface TaskDrawerEtapa {
	id: number;
	descricao: string;
	done: boolean;
}

/** Contexto mínimo do projeto vinculado (cabeçalho do drawer). */
export interface TaskDrawerProject {
	id: number;
	titulo: string;
}

/** Comentário de tarefa (= `_serialize_task_comment`). */
/**
 * Menção resolvida no servidor (`services/comment_mentions`): `start`/`length`
 * são deslocamentos em caracteres do próprio `content`, incluindo o `@`.
 */
export interface CommentMention {
	user_id: number;
	name: string;
	/** Deslocamentos em unidades UTF-16 (mesma unidade de `String.slice`). */
	start: number;
	length: number;
	/** `true` quando mais de uma pessoa responde pelo mesmo nome. */
	ambiguous?: boolean;
}

export interface TaskComment {
	id: number;
	content: string;
	user_id: number | null;
	author_name: string;
	created_at: string | null; // ISO 8601
	updated_at: string | null; // ISO 8601
	/** `null` = comentário anterior ao recurso (render cai na heurística). */
	mentions: CommentMention[] | null;
	is_own: boolean;
	can_edit: boolean;
	can_delete: boolean;
}

/** Anexo de tarefa (= `_serialize_task_anexo`; nunca expõe o caminho físico). */
export interface TaskAttachment {
	id: number;
	filename: string;
	content_type: string;
	is_image: boolean;
	uploaded_by: string;
	created_at: string | null; // ISO 8601
	/** URL de download binário (mesma origin, cookie de sessão). */
	url: string | null;
}

/**
 * Payload completo do drawer (= `serialize_task_detail`). Estende o card com o
 * contexto de etapa/projeto, listas de comentários/anexos e `permissions`
 * autoritativos.
 */
export interface TaskDetail extends BoardCard {
	etapa: TaskDrawerEtapa | null;
	project: TaskDrawerProject | null;
	comentarios: TaskComment[];
	anexos: TaskAttachment[];
	permissions: TaskDrawerPermissions & BoardCard['permissions'];
}

/** Envelope `{task, detail}` devolvido por detalhe/campos/lifecycle actions. */
export interface TaskDrawerPayload {
	task: BoardCard;
	detail: TaskDetail;
}

/** Campos editáveis pelo AUTOSAVE inline (`POST /api/tarefas/<id>/campos`). */
export interface TaskFieldEdits {
	descricao?: string;
	prioridade?: string | null;
	tipo_pedido?: string | null;
	responsavel?: string | null;
}

/** Uma sugestão de responsável (`GET .../sugestoes-responsavel`). */
export interface ResponsavelSuggestion {
	id: number;
	name: string;
}

/** Resposta de add/edit comentário: comentário afetado + lista atualizada. */
export interface CommentMutationResult {
	comment: TaskComment;
	comentarios: TaskComment[];
}

/** Resposta de excluir comentário: id removido + lista atualizada. */
export interface CommentDeleteResult {
	comment_id: number;
	comentarios: TaskComment[];
}

/** Resposta de listar anexos. */
export interface AttachmentListResult {
	anexos: TaskAttachment[];
	count: number;
}

/** Resposta de upload de anexo: anexo criado + lista atualizada. */
export interface AttachmentUploadResult {
	anexo: TaskAttachment;
	anexos: TaskAttachment[];
	count: number;
}

/** Resposta de excluir anexo: id removido + lista atualizada. */
export interface AttachmentDeleteResult {
	anexo_id: number;
	anexos: TaskAttachment[];
	count: number;
}
