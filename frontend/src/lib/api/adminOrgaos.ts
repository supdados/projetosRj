/**
 * Leitura da árvore de Órgãos do Admin + integração SIORG.
 *
 * A estrutura organizacional é espelho read-only do SIORG-RJ: as funções de
 * escrita (create/update/delete/move/reorder/toggle) foram removidas junto com
 * os endpoints. Restam a leitura da árvore (`GET /api/admin/orgaos`, envelope
 * `{ok, data}` via `client.ts`) e os endpoints SIORG, que respondem no formato
 * do contrato (`{"configurado": ...}` / `{"status": "sucesso", ...}` /
 * `{"error": "..."}` em 409/502) — por isso usam fetch próprio tolerante a
 * envelope, e não `client.request`.
 */

import { get } from './client';
import { createSwrCache } from './swrCache';
import type { OrgaoTreeData, SiorgStatusData, SiorgSyncResult } from '$lib/types/adminOrgaos';

const BASE = '/api/admin/orgaos';

// Ultima arvore boa (endpoint sem filtros). SWR: a tela reabre com o dado
// antigo e revalida em silencio (ver dashboard.ts).
const orgaoTreeCache = createSwrCache<OrgaoTreeData>();
const ORGAO_TREE_KEY = 'tree';

/** Ultima arvore carregada, ou null (sincrono, para o 1o render). */
export function peekOrgaoTree(): OrgaoTreeData | null {
	return orgaoTreeCache.peek(ORGAO_TREE_KEY);
}

/** Carrega a árvore completa de órgãos (visualização). */
export async function fetchOrgaoTree(signal?: AbortSignal): Promise<OrgaoTreeData> {
	const data = await get<OrgaoTreeData>(BASE, signal);
	orgaoTreeCache.store(ORGAO_TREE_KEY, data);
	return data;
}

/** Erro dos endpoints SIORG: preserva o HTTP status (409 lock, 502 indisponível). */
export class SiorgApiError extends Error {
	readonly status: number;

	constructor(message: string, status: number) {
		super(message);
		this.name = 'SiorgApiError';
		this.status = status;
	}
}

/** Token CSRF: meta injetada pelo Jinja ou re-busca em /api/csrf-token (dev). */
async function siorgCsrfToken(): Promise<string | null> {
	const meta = document.querySelector<HTMLMetaElement>('meta[name="csrf-token"]');
	const content = meta?.content?.trim() ?? '';
	if (content && content !== '%CSRF_TOKEN%') return content;
	try {
		const res = await fetch('/api/csrf-token', { credentials: 'include' });
		const body = (await res.json()) as { data?: { token?: string } };
		return body.data?.token ?? null;
	} catch {
		return null;
	}
}

/** Desembrulha `{ok, data}` se o backend envelopar; senão devolve o corpo cru. */
function unwrapSiorgBody(raw: unknown): Record<string, unknown> {
	if (raw === null || typeof raw !== 'object') return {};
	const body = raw as Record<string, unknown>;
	if (!('ok' in body)) return body;
	if (body.ok) return (body.data ?? {}) as Record<string, unknown>;
	const err = body.error as { message?: string } | undefined;
	return { error: err?.message ?? 'Falha na integração SIORG.' };
}

async function siorgRequest<T>(
	path: string,
	method: 'GET' | 'POST',
	signal?: AbortSignal
): Promise<T> {
	const headers: Record<string, string> = { Accept: 'application/json' };
	if (method === 'POST') {
		const token = await siorgCsrfToken();
		if (token) headers['X-CSRFToken'] = token;
	}
	const res = await fetch(path, { method, credentials: 'include', headers, signal });
	if (res.status === 401) {
		window.location.assign('/login');
		throw new SiorgApiError('Sessão expirada.', 401);
	}
	const body = unwrapSiorgBody(await res.json().catch(() => null));
	if (!res.ok || typeof body.error === 'string') {
		const message =
			typeof body.error === 'string'
				? body.error
				: `Falha na integração SIORG (HTTP ${res.status}).`;
		throw new SiorgApiError(message, res.status);
	}
	return body as T;
}

/** GET /api/admin/siorg/status — configuração + última sincronização. */
export function siorgStatus(signal?: AbortSignal): Promise<SiorgStatusData> {
	return siorgRequest<SiorgStatusData>('/api/admin/siorg/status', 'GET', signal);
}

/** POST /api/admin/siorg/sync — dispara o full-sync (409 lock, 502 SIORG fora). */
export function siorgSync(signal?: AbortSignal): Promise<SiorgSyncResult> {
	return siorgRequest<SiorgSyncResult>('/api/admin/siorg/sync', 'POST', signal);
}
