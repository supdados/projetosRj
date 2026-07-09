/**
 * Tipos da carga de Busca Global (GET /api/busca).
 *
 * Espelha o payload de `build_global_search_results` (routes/search.py:168) e o
 * payload vazio `_empty_global_search_payload` (mesmo formato com listas/contadores
 * zerados). O envelope `{ok, data}` e desempacotado por `client.ts`; os tipos
 * abaixo descrevem apenas `data`.
 *
 * Cada item ja chega serializado e JSON-safe (strings/urls). O campo `url` e um
 * caminho ABSOLUTO da app Flask (url_for em rotas Jinja) — usado como href direto,
 * sem prefixo de `base` da SPA.
 */

/** Discriminante de tipo de resultado (espelha o campo `type` do backend). */
export type SearchResultType = 'project' | 'stage' | 'task' | 'event';

/**
 * Item unico de resultado. `match_field`/`match_label`/`match_excerpt` indicam
 * onde o termo bateu (ex.: comentario de etapa) — vazios quando o match foi no
 * proprio titulo.
 */
export interface SearchResultItem {
	type: SearchResultType;
	type_label: string;
	title: string;
	display_title?: string;
	subtitle: string;
	meta: string;
	url: string;
	match_field: string;
	match_label: string;
	match_excerpt: string;
}

/** Contadores por tipo (+ `total`). */
export interface SearchCounts {
	projects: number;
	stages: number;
	tasks: number;
	events: number;
	total: number;
}

/** Indicador de "ha mais resultados" por tipo (+ `any` agregado). */
export interface SearchHasMore {
	projects: boolean;
	stages: boolean;
	tasks: boolean;
	events: boolean;
	any: boolean;
}

/** Chave plural de tipo usada em results/types= (espelha SEARCH_TYPE_KEYS). */
export type SearchTypeKey = keyof SearchResultsByType;

/** Paginação do modo paginado de /api/busca (?page=). */
export interface SearchPagination {
	page: number;
	per_page: number;
	total_pages: number;
	total: number;
}

/** Contagem total por tipo para termo+escopo, independente da seleção. */
export interface SearchTypeCounts {
	projects: number;
	stages: number;
	tasks: number;
	events: number;
}

/** Metadados da busca (limite por tipo aplicado no servidor). */
export interface SearchMeta {
	limit_per_type: number | null;
	has_more: SearchHasMore;
	/** Presentes só no modo paginado (?page=). */
	pagination?: SearchPagination;
	type_counts?: SearchTypeCounts;
	selected_types?: SearchTypeKey[];
}

/** Resultados agrupados por tipo. */
export interface SearchResultsByType {
	projects: SearchResultItem[];
	stages: SearchResultItem[];
	tasks: SearchResultItem[];
	events: SearchResultItem[];
}

/** Carga completa devolvida em `data` por GET /api/busca. */
export interface GlobalSearchData {
	query: string;
	meta: SearchMeta;
	counts: SearchCounts;
	results: SearchResultsByType;
}
