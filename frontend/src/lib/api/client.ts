/**
 * Cliente HTTP da SPA contra a API JSON do Flask (mesma origem).
 *
 * Responsabilidades:
 *   - `credentials: 'include'` para enviar o cookie de sessao (SameSite=Lax).
 *   - Injeta `X-CSRFToken` em todo metodo nao-GET. Fonte primaria: a
 *     `<meta name="csrf-token">` injetada pelo Jinja (routes/spa.py). Em falha
 *     de CSRF, re-busca `GET /api/csrf-token` UMA vez e repete a requisicao.
 *   - Desempacota o envelope `{ok, data}`; em `{ok:false}` lanca
 *     `ApiClientError`.
 *   - Em 401 (`unauthenticated`), navega top-level para `/login` (NAO fetch),
 *     porque o callback Gov.br depende do cookie `govbr_refresh_token`
 *     (SameSite=Strict) que so flui em navegacao de primeiro nivel.
 *
 * NAO usa o monkeypatch de fetch do base.html (so existe no Jinja legado).
 */

import type { ApiResult, PageMeta } from '$lib/types/api';

/** Erro estruturado lancado quando o backend devolve `{ok:false}`. */
export class ApiClientError extends Error {
	readonly code: string;
	readonly status: number;

	constructor(code: string, message: string, status: number) {
		super(message);
		this.name = 'ApiClientError';
		this.code = code;
		this.status = status;
	}
}

/** Caminho de login do Flask (rota imutavel). Navegacao top-level. */
const LOGIN_PATH = '/login';

/** Prefixo da API no backend Flask (mesma origem, fora do base da SPA). */
const API_PREFIX = '';

/** Token CSRF em memoria; semeado da <meta> e atualizado em re-busca. */
let csrfToken: string | null = null;

/** Le o token CSRF da `<meta name="csrf-token">` (injetada pelo Jinja). */
function readCsrfMeta(): string | null {
	if (typeof document === 'undefined') return null;
	const meta = document.querySelector<HTMLMetaElement>('meta[name="csrf-token"]');
	const content = meta?.content?.trim() ?? '';
	// Em dev (vite) o placeholder literal permanece; trata-se como ausente.
	if (!content || content === '%CSRF_TOKEN%') return null;
	return content;
}

/** Token CSRF atual (memoria -> meta). */
function currentCsrfToken(): string | null {
	if (csrfToken) return csrfToken;
	csrfToken = readCsrfMeta();
	return csrfToken;
}

/** Re-busca o token CSRF via `GET /api/csrf-token` (rotacao em sessao longa). */
async function refreshCsrfToken(): Promise<string | null> {
	try {
		const res = await fetch(`${API_PREFIX}/api/csrf-token`, {
			method: 'GET',
			credentials: 'include',
			headers: { Accept: 'application/json' }
		});
		if (!res.ok) return null;
		const body = (await res.json()) as ApiResult<{ token: string }>;
		if (body.ok && body.data?.token) {
			csrfToken = body.data.token;
			return csrfToken;
		}
	} catch {
		// rede indisponivel — segue sem token novo
	}
	return null;
}

/** Redireciona para /login via navegacao top-level (nunca fetch). */
function redirectToLogin(): void {
	if (typeof window !== 'undefined') {
		window.location.assign(LOGIN_PATH);
	}
}

interface RequestConfig {
	method: string;
	body?: unknown;
	/** Corpo multipart pre-montado (UPLOAD). Mutuamente exclusivo com `body`. */
	formData?: FormData;
	signal?: AbortSignal;
}

const NON_GET = (method: string): boolean => method.toUpperCase() !== 'GET';

/** True quando o erro indica token CSRF invalido/ausente. */
function isCsrfFailure(status: number, code: string): boolean {
	// CSRFProtect responde 400; o backend marca code "validation"/"csrf".
	return status === 400 && (code === 'csrf' || code === 'validation');
}

/** Executa uma requisicao (sem logica de retry de CSRF). */
async function sendOnce<T>(path: string, config: RequestConfig): Promise<ApiResult<T>> {
	const headers: Record<string, string> = { Accept: 'application/json' };
	let payload: BodyInit | undefined;

	if (config.formData !== undefined) {
		// UPLOAD multipart: NUNCA seta Content-Type — o browser injeta o
		// boundary correto. Definir manualmente quebraria o parse no Flask.
		payload = config.formData;
	} else if (config.body !== undefined) {
		headers['Content-Type'] = 'application/json';
		payload = JSON.stringify(config.body);
	}
	if (NON_GET(config.method)) {
		const token = currentCsrfToken();
		if (token) headers['X-CSRFToken'] = token;
	}

	const res = await fetch(`${API_PREFIX}${path}`, {
		method: config.method,
		credentials: 'include',
		headers,
		body: payload,
		signal: config.signal
	});

	// Respostas sem corpo JSON (ex.: 204) — devolve envelope vazio.
	const text = await res.text();
	let parsed: ApiResult<T>;
	if (text) {
		parsed = JSON.parse(text) as ApiResult<T>;
	} else {
		parsed = { ok: true, data: undefined as unknown as T };
	}
	// Anexa o status HTTP para a camada superior decidir 401/CSRF.
	(parsed as ApiResult<T> & { __status: number }).__status = res.status;
	return parsed;
}

/** Nucleo: envia, trata 401 (login) e re-tenta UMA vez em falha de CSRF. */
async function request<T>(path: string, config: RequestConfig): Promise<T> {
	let parsed = (await sendOnce<T>(path, config)) as ApiResult<T> & { __status: number };
	const status = parsed.__status;

	if (!parsed.ok) {
		const { code, message } = parsed.error;

		if (status === 401 || code === 'unauthenticated') {
			redirectToLogin();
			throw new ApiClientError('unauthenticated', message, status);
		}

		// Falha de CSRF em mutacao: re-busca token e tenta de novo (uma vez).
		if (NON_GET(config.method) && isCsrfFailure(status, code)) {
			const fresh = await refreshCsrfToken();
			if (fresh) {
				parsed = (await sendOnce<T>(path, config)) as ApiResult<T> & {
					__status: number;
				};
				if (parsed.ok) return parsed.data;
				throw new ApiClientError(
					parsed.error.code,
					parsed.error.message,
					parsed.__status
				);
			}
		}

		throw new ApiClientError(code, message, status);
	}

	return parsed.data;
}

/**
 * Como `request<T>`, mas devolve `{ data, meta }` em vez de descartar a `meta`
 * do envelope. Reusa o MESMO pipeline (`sendOnce` + 401 -> /login + retry de
 * CSRF), so que preservando `meta` para chamadores que paginam (#9).
 */
async function requestWithMeta<T>(
	path: string,
	config: RequestConfig
): Promise<{ data: T; meta?: PageMeta }> {
	let parsed = (await sendOnce<T>(path, config)) as ApiResult<T> & {
		__status: number;
		meta?: PageMeta;
	};
	const status = parsed.__status;

	if (!parsed.ok) {
		const { code, message } = parsed.error;

		if (status === 401 || code === 'unauthenticated') {
			redirectToLogin();
			throw new ApiClientError('unauthenticated', message, status);
		}

		if (NON_GET(config.method) && isCsrfFailure(status, code)) {
			const fresh = await refreshCsrfToken();
			if (fresh) {
				parsed = (await sendOnce<T>(path, config)) as ApiResult<T> & {
					__status: number;
					meta?: PageMeta;
				};
				if (parsed.ok) return { data: parsed.data, meta: parsed.meta };
				throw new ApiClientError(
					parsed.error.code,
					parsed.error.message,
					parsed.__status
				);
			}
		}

		throw new ApiClientError(code, message, status);
	}

	return { data: parsed.data, meta: parsed.meta };
}

/** GET tipado: desempacota o envelope e devolve `data`. */
export function get<T>(path: string, signal?: AbortSignal): Promise<T> {
	return request<T>(path, { method: 'GET', signal });
}

/**
 * GET tipado que preserva a `meta` do envelope: devolve `{ data, meta }`.
 *
 * Mesmo pipeline de `get<T>` (cookie de sessao, 401 -> navegacao top-level para
 * /login, retry de CSRF herdado de `request`), mas sem descartar `meta`. Use em
 * listas paginadas que precisam de `page/page_size/total`.
 *
 * Exemplo:
 *   const { data, meta } = await getWithMeta<{ usuarios: User[] }>(
 *     '/api/admin/usuarios?page=2'
 *   );
 */
export function getWithMeta<T>(
	path: string,
	signal?: AbortSignal
): Promise<{ data: T; meta?: PageMeta }> {
	return requestWithMeta<T>(path, { method: 'GET', signal });
}

/** POST tipado: envia `body` como JSON, devolve `data`. */
export function post<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
	return request<T>(path, { method: 'POST', body, signal });
}

/**
 * PUT tipado (edição RESTful de recurso): envia `body` como JSON, devolve `data`.
 *
 * Mesmo pipeline de `post<T>` (cookie de sessão, `X-CSRFToken`, retry único de
 * CSRF, 401 -> navegação top-level para /login). Use em CRUD de recurso (ex.:
 * editar usuário/órgão/tipo/modelo em `PUT /api/admin/...`).
 */
export function put<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
	return request<T>(path, { method: 'PUT', body, signal });
}

/**
 * DELETE tipado (exclusão RESTful de recurso): devolve `data`.
 *
 * Nomeado `del` porque `delete` é palavra reservada em JS. Mesmo pipeline de
 * `post<T>`/`put<T>` (cookie de sessão, `X-CSRFToken`, retry único de CSRF, 401
 * -> /login). Aceita `body` opcional para simetria, normalmente omitido.
 */
export function del<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
	return request<T>(path, { method: 'DELETE', body, signal });
}

/**
 * POST multipart tipado (UPLOAD). Envia `formData` SEM `Content-Type` (o browser
 * monta o boundary), com `credentials:'include'` + `X-CSRFToken`. Desempacota o
 * envelope `{ok,data}`; em 401 navega top-level para /login; o 413 (limite de
 * 10MB, `MAX_CONTENT_LENGTH`) chega como `ApiClientError(code='validation',
 * status=413)` vindo do `api_payload_too_large` do backend.
 *
 * Exemplo:
 *   const fd = new FormData();
 *   fd.append('file', file);
 *   const { anexo } = await postForm(`/api/tarefas/${id}/anexos`, fd);
 */
export function postForm<T>(path: string, formData: FormData, signal?: AbortSignal): Promise<T> {
	return request<T>(path, { method: 'POST', formData, signal });
}

/**
 * Resultado cru de um POST multipart: o JSON parseado (qualquer forma) e o
 * status HTTP. Usado por `postFormRaw` para chamadores que NAO falam o envelope
 * canonico `{ok,data}` (ex.: rotas Jinja legadas que respondem `{ok,event}`).
 */
interface RawFormResult<T> {
	json: T | null;
	status: number;
}

/**
 * Envia UM POST multipart sem assumir envelope: devolve o JSON cru + status.
 *
 * NUNCA seta `Content-Type` (o browser monta o boundary). Injeta `X-CSRFToken`
 * da memoria/meta. Corpo vazio -> `json: null`.
 */
async function sendFormOnce<T>(
	path: string,
	formData: FormData,
	signal?: AbortSignal
): Promise<RawFormResult<T>> {
	const headers: Record<string, string> = { Accept: 'application/json' };
	const token = currentCsrfToken();
	if (token) headers['X-CSRFToken'] = token;

	const res = await fetch(`${API_PREFIX}${path}`, {
		method: 'POST',
		credentials: 'include',
		headers,
		body: formData,
		signal
	});

	const text = await res.text();
	let json: T | null = null;
	if (text) {
		try {
			json = JSON.parse(text) as T;
		} catch {
			json = null;
		}
	}
	return { json, status: res.status };
}

/**
 * POST multipart que devolve o JSON CRU (sem desempacotar `{ok,data}`), usando o
 * MESMO tratamento de CSRF e 401 do `client.ts` (#21).
 *
 * Diferente de `postForm` (que assume o envelope canonico), este poster serve
 * rotas que respondem outra forma — ex.: as rotas Jinja legadas de evento em
 * `calendars.ts`, que devolvem `{ "ok": true, "event": {...} }`. O chamador
 * interpreta o JSON; aqui so garantimos:
 *   - cookie de sessao (`credentials:'include'`);
 *   - `X-CSRFToken` da meta e, em falha de CSRF (HTTP 400), UM re-fetch via
 *     `GET /api/csrf-token` (`refreshCsrfToken`) + retry — igual a `request`;
 *   - 401 -> navegacao top-level para `/login` (lanca `ApiClientError`).
 *
 * Exemplo:
 *   const body = await postFormRaw<{ ok: boolean; event: CalendarEvent }>(
 *     '/calendarios/eventos', formData
 *   );
 */
export async function postFormRaw<T>(
	path: string,
	formData: FormData,
	signal?: AbortSignal
): Promise<T | null> {
	let result = await sendFormOnce<T>(path, formData, signal);

	if (result.status === 401) {
		redirectToLogin();
		throw new ApiClientError('unauthenticated', 'Sessao expirada.', 401);
	}

	// Falha de CSRF (HTTP 400): re-busca token e tenta de novo (uma vez). Sem
	// envelope canonico, decidimos pelo status — o backend marca CSRF como 400.
	if (result.status === 400) {
		const fresh = await refreshCsrfToken();
		if (fresh) {
			result = await sendFormOnce<T>(path, formData, signal);
			if (result.status === 401) {
				redirectToLogin();
				throw new ApiClientError('unauthenticated', 'Sessao expirada.', 401);
			}
		}
	}

	return result.json;
}

export const apiClient = { get, getWithMeta, post, put, del, postForm, postFormRaw };
