/**
 * Acesso tipado ao DRAWER de Tarefa (Fase 5b-2).
 *
 * Endpoints NOVOS, aditivos (envelope canônico, `api_login_required`), do drawer
 * que abre UMA tarefa:
 *   - `GET  /api/tarefas/<id>/detalhe`               -> payload completo.
 *   - `POST /api/tarefas/<id>/campos`                -> AUTOSAVE inline.
 *   - `POST /api/tarefas/<id>/{finalizar,arquivar,desarquivar,reativar}`.
 *   - `GET  /api/tarefas/<id>/sugestoes-responsavel` -> picker de responsável.
 *   - `POST /api/tarefas/<id>/comentarios`, `POST /api/comentarios/<id>`,
 *     `POST /api/comentarios/<id>/delete`            -> comentários.
 *   - `GET/POST /api/tarefas/<id>/anexos`, `POST /api/anexos/<id>/delete`,
 *     `GET /api/anexos/<id>`                         -> anexos (upload multipart;
 *     download binário via URL, mesma origin).
 *
 * Mutações via `post` (JSON, injeta X-CSRFToken) e o UPLOAD via `postForm`
 * (multipart, SEM Content-Type). O servidor é AUTORITATIVO e todo erro sobe como
 * `ApiClientError` (o drawer faz rollback). Contrato S5, válido para TODAS as
 * funções abaixo:
 *   - 404 `not_found`: a tarefa não existe OU o usuário não tem acesso ao
 *     projeto dela — mesmo corpo nos dois casos, indistinguíveis por design
 *     ("não existe ou você não tem acesso").
 *   - 403 `forbidden`: ele vê a tarefa mas não pode ESTA ação (ex.: finalizar
 *     sem `can_finalize`, editar campo restrito sem ser autor/admin).
 */

import { get, post, postForm } from './client';
import type {
	AttachmentDeleteResult,
	AttachmentListResult,
	AttachmentUploadResult,
	CommentDeleteResult,
	CommentMutationResult,
	ResponsavelSuggestion,
	TaskDrawerPayload,
	TaskFieldEdits
} from '$lib/types/taskDrawer';

/** Busca o payload completo do drawer de uma tarefa (read-only). */
export function getTaskDetail(taskId: number, signal?: AbortSignal): Promise<TaskDrawerPayload> {
	return get<TaskDrawerPayload>(`/api/tarefas/${taskId}/detalhe`, signal);
}

/**
 * AUTOSAVE inline de campos (descricao/prioridade/tipo_pedido/responsavel). O
 * `status` NÃO passa por aqui — continua em `POST /api/tarefas/<id>/status`
 * (Fase 5b-1). Campos restritos sem permissão => 403 (vê a tarefa mas não pode);
 * valores inválidos => 422.
 */
export function saveFields(
	taskId: number,
	fields: TaskFieldEdits,
	signal?: AbortSignal
): Promise<TaskDrawerPayload> {
	return post<TaskDrawerPayload>(`/api/tarefas/${taskId}/campos`, fields, signal);
}

/** Finaliza a tarefa (respeita `can_finalize`; 403 = vê mas não pode finalizar). */
export function finalizarTask(taskId: number, signal?: AbortSignal): Promise<TaskDrawerPayload> {
	return post<TaskDrawerPayload>(`/api/tarefas/${taskId}/finalizar`, undefined, signal);
}

/** Arquiva a tarefa (board remove o card). */
export function arquivarTask(taskId: number, signal?: AbortSignal): Promise<TaskDrawerPayload> {
	return post<TaskDrawerPayload>(`/api/tarefas/${taskId}/arquivar`, undefined, signal);
}

/** Desarquiva a tarefa (reseta status para "nao_iniciada"). */
export function desarquivarTask(taskId: number, signal?: AbortSignal): Promise<TaskDrawerPayload> {
	return post<TaskDrawerPayload>(`/api/tarefas/${taskId}/desarquivar`, undefined, signal);
}

/** Reativa a tarefa (alias de desarquivar). */
export function reativarTask(taskId: number, signal?: AbortSignal): Promise<TaskDrawerPayload> {
	return post<TaskDrawerPayload>(`/api/tarefas/${taskId}/reativar`, undefined, signal);
}

/** Sugestões de responsável para o picker (`?q=` filtra por nome). */
export function suggestResponsavel(
	taskId: number,
	query = '',
	signal?: AbortSignal
): Promise<{ users: ResponsavelSuggestion[] }> {
	const qs = query.trim() ? `?q=${encodeURIComponent(query.trim())}` : '';
	return get<{ users: ResponsavelSuggestion[] }>(
		`/api/tarefas/${taskId}/sugestoes-responsavel${qs}`,
		signal
	);
}

/** Adiciona um comentário à tarefa. */
export function addComment(
	taskId: number,
	content: string,
	signal?: AbortSignal
): Promise<CommentMutationResult> {
	return post<CommentMutationResult>(`/api/tarefas/${taskId}/comentarios`, { content }, signal);
}

/** Edita um comentário (somente o autor). */
export function editComment(
	commentId: number,
	content: string,
	signal?: AbortSignal
): Promise<CommentMutationResult> {
	return post<CommentMutationResult>(`/api/comentarios/${commentId}`, { content }, signal);
}

/** Exclui um comentário (somente o autor). */
export function deleteComment(
	commentId: number,
	signal?: AbortSignal
): Promise<CommentDeleteResult> {
	return post<CommentDeleteResult>(`/api/comentarios/${commentId}/delete`, undefined, signal);
}

/** Lista os anexos de uma tarefa. */
export function listAttachments(
	taskId: number,
	signal?: AbortSignal
): Promise<AttachmentListResult> {
	return get<AttachmentListResult>(`/api/tarefas/${taskId}/anexos`, signal);
}

/**
 * UPLOAD de um anexo (multipart). A chave do arquivo é `"file"` (contrato do
 * backend). Usa `postForm` (NÃO seta Content-Type). Limite de 10MB => 413
 * (`ApiClientError` code `validation`).
 */
export function uploadAttachment(
	taskId: number,
	file: File,
	signal?: AbortSignal
): Promise<AttachmentUploadResult> {
	const formData = new FormData();
	formData.append('file', file);
	return postForm<AttachmentUploadResult>(`/api/tarefas/${taskId}/anexos`, formData, signal);
}

/** Exclui um anexo (autor/admin). */
export function deleteAttachment(
	anexoId: number,
	signal?: AbortSignal
): Promise<AttachmentDeleteResult> {
	return post<AttachmentDeleteResult>(`/api/anexos/${anexoId}/delete`, undefined, signal);
}

/**
 * URL de download binário de um anexo (mesma origin, cookie de sessão). O drawer
 * abre via `<a href download>` / nova aba — NÃO é fetch (resposta octet-stream).
 * Prefere a `url` já vinda no payload do anexo; este helper é o fallback.
 */
export function attachmentDownloadUrl(anexoId: number): string {
	return `/api/anexos/${anexoId}`;
}
