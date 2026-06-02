/**
 * Acesso tipado ao Hub de Tarefas em modo lista (GET /api/tarefas).
 *
 * Devolve a `TaskHubData` já desempacotada do envelope (`client.ts`),
 * respeitando o `orgao_scope` aplicado no servidor. Os filtros
 * (`?project`/`?prioridade`/`?tipo`/`?status`/`?responsavel`/`?orgao`/`?modo`)
 * espelham os do hub Jinja `/tarefas`.
 *
 * Exemplo:
 *   const data = await fetchTarefas({ modo: 'finalizadas' });
 */

import { get } from './client';
import type { TaskHubData, TaskHubQuery } from '$lib/types/tasks';

/** Monta a querystring a partir dos filtros, omitindo valores vazios/nulos. */
function buildQuery(query: TaskHubQuery): string {
	const params = new URLSearchParams();
	if (query.project) params.set('project', query.project);
	if (query.prioridade) params.set('prioridade', query.prioridade);
	if (query.tipo) params.set('tipo', query.tipo);
	if (query.status) params.set('status', query.status);
	if (query.responsavel) params.set('responsavel', query.responsavel);
	if (query.orgao !== undefined && query.orgao !== null && query.orgao !== '') {
		params.set('orgao', String(query.orgao));
	}
	if (query.modo) params.set('modo', query.modo);
	const qs = params.toString();
	return qs ? `?${qs}` : '';
}

/**
 * Busca o Hub de Tarefas (modo lista) do usuário autenticado.
 *
 * Um filtro de órgão fora do escopo do usuário faz o backend devolver
 * `fail(422,'validation')`, que `client.ts` converte em `ApiClientError`.
 */
export function fetchTarefas(
	query: TaskHubQuery = {},
	signal?: AbortSignal
): Promise<TaskHubData> {
	return get<TaskHubData>(`/api/tarefas${buildQuery(query)}`, signal);
}
