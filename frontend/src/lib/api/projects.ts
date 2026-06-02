/**
 * Acesso tipado ao endpoint "Lista de Projetos" (GET /api/projetos).
 *
 * Devolve a `ProjectsListData` já desempacotada do envelope (`client.ts`),
 * respeitando o `orgao_scope` aplicado no servidor. Os query params
 * (`?status`/`?prioridade`/`?special_project`/`?abep_indicator`/`?q`/`?orgao`/
 * `?page`...) espelham os filtros da tela Jinja; `?q` é o alias JSON de
 * `?search`. Um filtro de órgão fora do escopo do usuário faz o backend
 * devolver `fail(422,'validation')`, que `client.ts` converte em
 * `ApiClientError`.
 *
 * Aceita um `AbortSignal` para cancelar a requisição anterior (busca textual
 * com debounce / troca rápida de filtros), evitando respostas fora de ordem.
 *
 * Exemplo:
 *   const data = await fetchProjects({ status: 'Vigente', q: 'painel' });
 */

import { get } from './client';
import type { ProjectsListData, ProjectsListQuery } from '$lib/types/projects';

/** Monta a querystring a partir dos filtros, omitindo valores vazios/nulos. */
function buildQuery(query: ProjectsListQuery): string {
	const params = new URLSearchParams();
	if (query.status) params.set('status', query.status);
	if (query.prioridade) params.set('prioridade', query.prioridade);
	if (query.atraso) params.set('atraso', query.atraso);
	if (query.special_project) params.set('special_project', query.special_project);
	if (query.delivery_type) params.set('delivery_type', query.delivery_type);
	if (query.abep_indicator) params.set('abep_indicator', query.abep_indicator);
	if (query.objetivo) params.set('objetivo', query.objetivo);
	if (query.q) params.set('q', query.q);
	if (query.orgao !== undefined && query.orgao !== null) {
		params.set('orgao', String(query.orgao));
	}
	if (query.page && query.page > 1) params.set('page', String(query.page));
	const qs = params.toString();
	return qs ? `?${qs}` : '';
}

/**
 * Busca a "Lista de Projetos" do usuário autenticado, respeitando o escopo de
 * órgão server-side. Sem `status` explícito o backend assume "Vigente".
 */
export function fetchProjects(
	query: ProjectsListQuery = {},
	signal?: AbortSignal
): Promise<ProjectsListData> {
	return get<ProjectsListData>(`/api/projetos${buildQuery(query)}`, signal);
}
