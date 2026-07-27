/**
 * Acesso tipado ao Kanban de Tarefas (Fase 5b-1).
 *
 * Endpoints no envelope canônico (`api_login_required`, `orgao_scope`):
 *   - `GET  /api/tarefas/board`            -> colunas + cards (read-only + DnD).
 *   - `POST /api/tarefas/<id>/status`      -> muda o status de UMA tarefa.
 *   - `POST /api/tarefas/board/reordenar`  -> persiste ordem (e status) das colunas.
 *
 * Tudo desempacotado do envelope por `client.ts`; mutações via `post`
 * (que injeta `X-CSRFToken`). O servidor é AUTORITATIVO: as mutações podem
 * recusar — a store reverte em qualquer erro. Contrato S5: 403 `forbidden`
 * quando o usuário vê a tarefa mas não pode a ação; 404 `not_found` quando a
 * tarefa não existe OU ele não tem acesso (indistinguíveis por design).
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
 * 404 `not_found` (não existe OU sem acesso), 422 (status inválido). Devolve o
 * card atualizado.
 */
export function updateTaskStatus(
	taskId: number,
	status: TaskStatus,
	signal?: AbortSignal
): Promise<TaskStatusResult> {
	return post<TaskStatusResult>(`/api/tarefas/${taskId}/status`, { status }, signal);
}

/**
 * Persiste a nova ordem das colunas afetadas. Só o `moved_task_id` (quando
 * enviado) pode mudar de status; ids com status divergente no servidor
 * (mudança concorrente) são ignorados e não voltam na resposta — o backend
 * reescreve `Task.ordem` e devolve as colunas afetadas para reconciliação.
 */
export function reorderBoard(
	payload: BoardReorderPayload,
	signal?: AbortSignal
): Promise<BoardReorderResult> {
	return post<BoardReorderResult>('/api/tarefas/board/reordenar', payload, signal);
}
