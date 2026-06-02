/**
 * Acesso tipado ao endpoint de Busca Global (GET /api/busca).
 *
 * Devolve a `GlobalSearchData` ja desempacotada do envelope (`client.ts`),
 * respeitando o `orgao_scope` aplicado no servidor. Termos com menos de 2
 * caracteres retornam (no servidor) o payload vazio canonico — aqui apenas
 * encaminhamos o termo via querystring.
 *
 * Aceita um `AbortSignal` para cancelar a requisicao anterior em buscas com
 * debounce (evita resultados fora de ordem).
 */

import { get } from './client';
import type { GlobalSearchData } from '$lib/types/search';

/** Busca global por `term`, respeitando o escopo de orgao do usuario. */
export function fetchGlobalSearch(
	term: string,
	signal?: AbortSignal
): Promise<GlobalSearchData> {
	const query = new URLSearchParams({ q: term }).toString();
	return get<GlobalSearchData>(`/api/busca?${query}`, signal);
}
