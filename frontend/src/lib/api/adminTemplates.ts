/**
 * Acesso tipado ao CRUD de Modelos de Etapas (Admin) — `/api/admin/templates*`.
 *
 * Mutations usam `client.post` (que injeta `X-CSRFToken` e trata 401/CSRF);
 * NÃO editamos `client.ts`. A LISTAGEM precisa do bloco `meta` (paginação +
 * `order`/`q` reconciliados pelo backend), que `client.get` descarta ao
 * desempacotar o envelope. Por isso a leitura da lista usa um fetch local
 * (`fetchTemplateList`) que lê `data` + `meta` do envelope cru — encapsulado
 * neste módulo da tela, sem tocar no cliente compartilhado (evita corrida).
 * As demais leituras/escritas reusam `get`/`post`.
 *
 * Backend: routes/api/admin_templates.py (envelope ok/fail, api_admin_required).
 */

import { get, getWithMeta, post, put, del } from './client';
import { createSwrCache } from './swrCache';
import type {
	TemplateDetailResult,
	TemplateListMeta,
	TemplateListQuery,
	TemplateListResult,
	TemplateOrder,
	TemplatePayload,
	TemplateRow,
	TemplateDetail
} from '$lib/types/adminTemplates';

/** Monta a querystring da listagem, omitindo valores vazios/default. */
function buildListQuery(query: TemplateListQuery): string {
	const params = new URLSearchParams();
	if (query.q && query.q.trim()) params.set('q', query.q.trim());
	if (query.order) params.set('order', query.order);
	if (query.page && query.page > 1) params.set('page', String(query.page));
	const qs = params.toString();
	return qs ? `?${qs}` : '';
}

/** Envelope cru da listagem: `data` + `meta` (este último não vem em `client.get`). */
interface TemplateListEnvelope {
	templates: TemplateRow[];
	order_options: TemplateOrder[];
}

// Ultimo payload bom por chave de filtros (querystring de `buildListQuery`).
// SWR: a tela reabre com o dado antigo e revalida em silencio (dashboard.ts).
const templateListCache = createSwrCache<TemplateListResult>();

/** Ultima listagem carregada para os filtros, ou null (sincrono, 1o render). */
export function peekTemplateList(query: TemplateListQuery = {}): TemplateListResult | null {
	return templateListCache.peek(buildListQuery(query));
}

/**
 * Busca a lista de modelos + métricas + paginação.
 *
 * Usa `getWithMeta` do client (que preserva o `meta` do envelope — paginação e
 * `order`/`q` reconciliados pelo servidor — e trata 401/CSRF como `get`/`post`),
 * mantendo o retorno `{ templates, order_options, meta }` que a tela espera.
 */
export async function fetchTemplateList(
	query: TemplateListQuery = {},
	signal?: AbortSignal
): Promise<TemplateListResult> {
	const qs = buildListQuery(query);
	const { data, meta } = await getWithMeta<TemplateListEnvelope>(
		`/api/admin/templates${qs}`,
		signal
	);
	const listMeta: TemplateListMeta = (meta as TemplateListMeta | undefined) ?? {
		page: 1,
		per_page: data.templates.length,
		total: data.templates.length,
		total_pages: 1,
		order: (query.order ?? 'mais_usados') as TemplateOrder,
		q: query.q ?? ''
	};
	const result: TemplateListResult = {
		templates: data.templates,
		order_options: data.order_options,
		meta: listMeta
	};
	templateListCache.store(qs, result);
	return result;
}

/** Carrega um modelo com suas etapas (form de edição). */
export function fetchTemplateDetail(
	templateId: number,
	signal?: AbortSignal
): Promise<TemplateDetailResult> {
	return get<TemplateDetailResult>(`/api/admin/templates/${templateId}`, signal);
}

/** Cria um modelo de etapas. `fail(422)` vira `ApiClientError`. */
export async function createTemplate(payload: TemplatePayload): Promise<TemplateDetail> {
	const data = await post<{ template: TemplateDetail }>('/api/admin/templates', payload);
	return data.template;
}

/** Edita um modelo (substitui o conjunto de etapas por completo). */
export async function updateTemplate(
	templateId: number,
	payload: TemplatePayload
): Promise<TemplateDetail> {
	const data = await put<{ template: TemplateDetail }>(
		`/api/admin/templates/${templateId}`,
		payload
	);
	return data.template;
}

/** Duplica um modelo (sufixo "(cópia)"). Devolve o novo modelo. */
export async function duplicateTemplate(templateId: number): Promise<TemplateDetail> {
	const data = await post<{ template: TemplateDetail }>(
		`/api/admin/templates/${templateId}/duplicate`
	);
	return data.template;
}

/** Exclui um modelo (etapas/usos em cascata). Devolve o id removido. */
export async function deleteTemplate(templateId: number): Promise<number> {
	const data = await del<{ deleted_id: number }>(
		`/api/admin/templates/${templateId}`
	);
	return data.deleted_id;
}
