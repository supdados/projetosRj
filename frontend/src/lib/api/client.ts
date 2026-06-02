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

import type { ApiResult } from '$lib/types/api';

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

	if (config.body !== undefined) {
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

/** GET tipado: desempacota o envelope e devolve `data`. */
export function get<T>(path: string, signal?: AbortSignal): Promise<T> {
	return request<T>(path, { method: 'GET', signal });
}

/** POST tipado: envia `body` como JSON, devolve `data`. */
export function post<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
	return request<T>(path, { method: 'POST', body, signal });
}

export const apiClient = { get, post };
