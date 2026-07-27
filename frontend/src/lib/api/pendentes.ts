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
import { createSwrCache } from './swrCache';
import type { PendingData, PendingFilters } from '$lib/types/pendentes';

// Ultimo payload bom por chave de filtros (querystring de `buildQuery`). SWR:
// a tela reabre com o dado antigo e revalida em silencio (ver dashboard.ts).
const pendentesCache = createSwrCache<PendingData>();

/** Ultima listagem carregada para os filtros, ou null (sincrono, 1o render). */
export function peekPendentes(filters: PendingFilters = {}): PendingData | null {
	return pendentesCache.peek(buildQuery(filters));
}

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
 * `fail(422,'validation')`, que `client.ts` converte em `ApiClientError`. Não há
 * 403/404 de autorização: projeto fora do rank não entra na listagem.
 */
export async function fetchPendentes(
	filters: PendingFilters = {},
	signal?: AbortSignal
): Promise<PendingData> {
	const qs = buildQuery(filters);
	const data = await get<PendingData>(`/api/projetos-pendentes${qs}`, signal);
	pendentesCache.store(qs, data);
	return data;
}
