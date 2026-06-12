/**
 * Acesso tipado ao endpoint "Projetos Pendentes" (GET /api/projetos-pendentes).
 *
 * Devolve a `PendingData` já desempacotada do envelope (`client.ts`),
 * respeitando o `orgao_scope` aplicado no servidor. Os filtros
 * (`?periodo`/`?responsavel`/`?orgao`/`?page`) espelham os da tela Jinja.
 *
 * Exemplo:
 *   const data = await fetchPendentes({ periodo: '7dias' });
 */

import { get } from './client';
import type { PendingData, PendingFilters } from '$lib/types/pendentes';

/** Monta a querystring a partir dos filtros, omitindo valores vazios/nulos. */
function buildQuery(filters: PendingFilters): string {
	const params = new URLSearchParams();
	if (filters.periodo) params.set('periodo', filters.periodo);
	if (filters.responsavel) params.set('responsavel', filters.responsavel);
	if (filters.prioridade) params.set('prioridade', filters.prioridade);
	if (filters.search && filters.search.trim()) params.set('q', filters.search.trim());
	if (filters.orgao !== undefined && filters.orgao !== null) {
		params.set('orgao', String(filters.orgao));
	}
	if (filters.page && filters.page > 1) params.set('page', String(filters.page));
	const query = params.toString();
	return query ? `?${query}` : '';
}

/**
 * Busca a listagem de "Projetos Pendentes" do usuário autenticado.
 *
 * Um filtro de órgão fora do escopo do usuário faz o backend devolver
 * `fail(422,'validation')`, que `client.ts` converte em `ApiClientError`.
 */
export function fetchPendentes(
	filters: PendingFilters = {},
	signal?: AbortSignal
): Promise<PendingData> {
	return get<PendingData>(`/api/projetos-pendentes${buildQuery(filters)}`, signal);
}
