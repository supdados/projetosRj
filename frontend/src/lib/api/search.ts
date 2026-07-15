/**
 * Acesso tipado ao endpoint de Busca Global (GET /api/busca).
 *
 * Devolve a `GlobalSearchData` ja desempacotada do envelope (`client.ts`),
 * respeitando o `orgao_scope` aplicado no servidor. Termos com menos de 2
 * caracteres retornam (no servidor) o payload vazio canonico.
 *
 * ATENCAO: a tela `busca/+page.svelte` HOJE monta a querystring e chama
 * `get<GlobalSearchData>` diretamente de `$lib/api/client` (nao importa este
 * modulo) — por isso `buildSearchQuery` abaixo replica EXATAMENTE a mesma
 * ordem/regras de parametros (`q`, `page`, `per_page`, `types`, escopo de
 * orgao) usada la, para que um peek feito com os mesmos argumentos bata com a
 * chave que `fetchGlobalSearch` gravaria no cache. Ate a pagina migrar para
 * consumir este modulo, o cache aqui fica pronto porem NAO e alimentado pela
 * tela atual.
 *
 * Aceita um `AbortSignal` para cancelar a requisicao anterior em buscas com
 * debounce (evita resultados fora de ordem).
 */

import { get } from './client';
import { createSwrCache } from './swrCache';
import type { GlobalSearchData, SearchTypeKey } from '$lib/types/search';

/** Parametros do modo paginado da busca global (espelha o form da tela). */
export interface GlobalSearchParams {
	/** Termo de busca (ja trimado pelo chamador). */
	q: string;
	/** Pagina 1-based do modo paginado. */
	page?: number;
	/** Itens por pagina (contrato do backend: 40). */
	perPage?: number;
	/** Tipos selecionados; omitir/lista vazia = todos os tipos. */
	types?: readonly SearchTypeKey[];
	/** Querystring de escopo de orgao SEM o `?` (`orgaoScopeQuery`), ou ''. */
	orgaoQuery?: string;
}

const ALL_TYPES_COUNT = 4; // projects, stages, tasks, events (SearchTypeKey)

/**
 * Monta a querystring EXATAMENTE como `busca/+page.svelte::runSearch` monta a
 * sua: `q` + `page` + `per_page` sempre presentes, `types` só quando é um
 * subconjunto, escopo de orgao concatenado por último com `&`.
 */
export function buildSearchQuery(params: GlobalSearchParams): string {
	const { q, page = 1, perPage = 40, types, orgaoQuery = '' } = params;
	const search = new URLSearchParams({ q, page: String(page), per_page: String(perPage) });
	if (types && types.length > 0 && types.length < ALL_TYPES_COUNT) {
		search.set('types', types.join(','));
	}
	const base = search.toString();
	return orgaoQuery ? `${base}&${orgaoQuery}` : base;
}

// Ultimo payload bom por chave de busca (querystring de `buildSearchQuery`).
// SWR: a tela reabre com o dado antigo e revalida em silencio (dashboard.ts).
const globalSearchCache = createSwrCache<GlobalSearchData>();

/** Ultimo resultado carregado para os parametros, ou null (1o render). */
export function peekGlobalSearch(params: GlobalSearchParams): GlobalSearchData | null {
	return globalSearchCache.peek(buildSearchQuery(params));
}

/** Busca global paginada, respeitando o escopo de orgao do usuario. */
export async function fetchGlobalSearch(
	params: GlobalSearchParams,
	signal?: AbortSignal
): Promise<GlobalSearchData> {
	const qs = buildSearchQuery(params);
	const data = await get<GlobalSearchData>(`/api/busca?${qs}`, signal);
	globalSearchCache.store(qs, data);
	return data;
}
