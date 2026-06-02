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

import { get, post, ApiClientError } from './client';
import type { ApiResult } from '$lib/types/api';
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

/**
 * Busca a lista de modelos + métricas + paginação.
 *
 * Faz um fetch local para preservar o `meta` do envelope (paginação e
 * `order`/`q` reconciliados pelo servidor), que `client.get` descartaria.
 * Espelha `client.ts`: `credentials: 'include'`, GET sem CSRF, e em 401 deixa
 * a navegação top-level por conta do próximo `post`/`get` compartilhado — aqui
 * apenas lançamos `ApiClientError` para a tela tratar.
 *
 * @throws {ApiClientError} quando o backend devolve `{ok:false}`.
 */
export async function fetchTemplateList(
	query: TemplateListQuery = {},
	signal?: AbortSignal
): Promise<TemplateListResult> {
	const res = await fetch(`/api/admin/templates${buildListQuery(query)}`, {
		method: 'GET',
		credentials: 'include',
		headers: { Accept: 'application/json' },
		signal
	});
	const body = (await res.json()) as ApiResult<TemplateListEnvelope> & {
		meta?: TemplateListMeta;
	};
	if (!body.ok) {
		throw new ApiClientError(body.error.code, body.error.message, res.status);
	}
	const meta: TemplateListMeta = body.meta ?? {
		page: 1,
		per_page: body.data.templates.length,
		total: body.data.templates.length,
		total_pages: 1,
		order: (query.order ?? 'mais_usados') as TemplateOrder,
		q: query.q ?? ''
	};
	return {
		templates: body.data.templates,
		order_options: body.data.order_options,
		meta
	};
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
	const data = await post<{ template: TemplateDetail }>(
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
	const data = await post<{ deleted_id: number }>(
		`/api/admin/templates/${templateId}/delete`
	);
	return data.deleted_id;
}
