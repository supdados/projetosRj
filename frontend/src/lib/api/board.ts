/**
 * Acesso tipado ao Kanban de Tarefas (Fase 5b-1).
 *
 * Endpoints NOVOS, aditivos (envelope canônico, `api_login_required`,
 * `orgao_scope`), que coexistem com as rotas Jinja/JSON legadas:
 *   - `GET  /api/tarefas/board`            -> colunas + cards (read-only + DnD).
 *   - `POST /api/tarefas/<id>/status`      -> muda o status de UMA tarefa.
 *   - `POST /api/tarefas/board/reordenar`  -> persiste ordem (e status) das colunas.
 *
 * Tudo desempacotado do envelope por `client.ts`; mutações via `post`
 * (que injeta `X-CSRFToken`). O servidor é AUTORITATIVO: as mutações podem
 * recusar (403 `forbidden` ao finalizar sem permissão) — a store reverte.
 */

import { get, post } from './client';
import type {
	BoardData,
	BoardQuery,
	BoardReorderPayload,
	BoardReorderResult,
	TaskStatusResult
} from '$lib/types/board';
import type { TaskStatus } from '$lib/utils/taskStatus';

/** Monta a querystring dos filtros, omitindo valores vazios/nulos. */
function buildQuery(query: BoardQuery): string {
	const params = new URLSearchParams();
	if (query.project) params.set('project', query.project);
	if (query.prioridade) params.set('prioridade', query.prioridade);
	if (query.tipo) params.set('tipo', query.tipo);
	if (query.status) params.set('status', query.status);
	if (query.responsavel) params.set('responsavel', query.responsavel);
	if (query.orgao !== undefined && query.orgao !== null && query.orgao !== '') {
		params.set('orgao', String(query.orgao));
	}
	const qs = params.toString();
	return qs ? `?${qs}` : '';
}

/**
 * Busca o board (5 colunas por status, só tarefas ativas) do usuário.
 *
 * Um filtro de órgão fora do escopo faz o backend devolver
 * `fail(422,'validation')`, convertido em `ApiClientError` por `client.ts`.
 */
export function getBoard(
	filters: BoardQuery = {},
	signal?: AbortSignal
): Promise<BoardData> {
	return get<BoardData>(`/api/tarefas/board${buildQuery(filters)}`, signal);
}

/**
 * Muda o status de UMA tarefa (drop entre colunas). Autoritativo no servidor:
 * 403 `forbidden` (`FINALIZE_DENIED_MESSAGE`) ao finalizar sem permissão,
 * 404 (inexistente), 422 (status inválido). Devolve o card atualizado.
 */
export function updateTaskStatus(
	taskId: number,
	status: TaskStatus,
	signal?: AbortSignal
): Promise<TaskStatusResult> {
	return post<TaskStatusResult>(`/api/tarefas/${taskId}/status`, { status }, signal);
}

/**
 * Persiste a nova ordem (e eventuais mudanças de status) das colunas afetadas.
 * O estado canônico vem da store; o backend valida transições e reescreve
 * `Task.ordem`, devolvendo as colunas afetadas para reconciliação.
 */
export function reorderBoard(
	payload: BoardReorderPayload,
	signal?: AbortSignal
): Promise<BoardReorderResult> {
	return post<BoardReorderResult>('/api/tarefas/board/reordenar', payload, signal);
}
