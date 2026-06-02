/**
 * Acesso tipado a tela de Calendario.
 *
 * Dois grupos de endpoints, ambos na mesma origem do Flask:
 *
 *  1. Hub + acoes de conexao (envelope canonico `{ok,data}`, via `client.ts`):
 *       - `GET  /api/calendarios`                  -> CalendarHub.
 *       - `POST /api/calendarios/google/disconnect` -> { disconnected }.
 *       - `POST /api/calendarios/google/sync`        -> resumo do sync.
 *       - `POST /api/calendarios/google/watch/renew` -> { expires_at_display }.
 *
 *  2. CRUD de evento (REUSO das rotas Jinja legadas — NAO ha endpoint /api):
 *       - `POST /calendarios/eventos`                  (criar)
 *       - `POST /calendarios/eventos/<id>/editar`      (editar)
 *       - `POST /calendarios/eventos/<id>/gerar-meet`  (gerar Meet)
 *       - `POST /calendarios/eventos/<id>/excluir`     (excluir)
 *     Essas rotas esperam `request.form` (multipart) e, com
 *     `Accept: application/json`, respondem `{ "ok": true, "event": {...} }`
 *     (NAO o envelope canonico `{ok,data}`). Por isso usam o poster dedicado
 *     `postLegacyEventForm` abaixo, e nao `client.postForm`.
 */

import { get, post } from './client';
import { ApiClientError } from './client';
import type { ApiResult } from '$lib/types/api';
import type {
	CalendarEvent,
	CalendarEventInput,
	CalendarHub
} from '$lib/types/calendar';

/** Resumo devolvido por `POST /api/calendarios/google/sync`. */
export interface CalendarSyncSummary {
	upserted: number;
	deleted: number;
	ignored: number;
	full_sync: boolean;
}

/** Resultado de `POST /api/calendarios/google/disconnect`. */
export interface CalendarDisconnectResult {
	disconnected: boolean;
}

/** Resultado de `POST /api/calendarios/google/watch/renew`. */
export interface CalendarWatchRenewResult {
	expires_at_display: string | null;
}

/** Busca o hub do calendario (eventos + estado da conexao Google). */
export function getCalendarHub(signal?: AbortSignal): Promise<CalendarHub> {
	return get<CalendarHub>('/api/calendarios', signal);
}

/** Desconecta a conta Google Calendar do usuario. */
export function disconnectGoogle(
	signal?: AbortSignal
): Promise<CalendarDisconnectResult> {
	return post<CalendarDisconnectResult>(
		'/api/calendarios/google/disconnect',
		undefined,
		signal
	);
}

/** Dispara uma sincronizacao manual com o Google Calendar. */
export function syncNow(signal?: AbortSignal): Promise<CalendarSyncSummary> {
	return post<CalendarSyncSummary>('/api/calendarios/google/sync', undefined, signal);
}

/** Renova o canal de watch (push notifications) do Google Calendar. */
export function renewWatch(
	signal?: AbortSignal
): Promise<CalendarWatchRenewResult> {
	return post<CalendarWatchRenewResult>(
		'/api/calendarios/google/watch/renew',
		undefined,
		signal
	);
}

// ---------------------------------------------------------------------------
// CRUD de evento via rotas legadas (multipart/form-data + Accept JSON).
// ---------------------------------------------------------------------------

/** Caminho de login do Flask (rota imutavel). Navegacao top-level. */
const LOGIN_PATH = '/login';

/** Le o token CSRF da `<meta name="csrf-token">` injetada pelo Jinja. */
function readCsrfToken(): string | null {
	if (typeof document === 'undefined') return null;
	const meta = document.querySelector<HTMLMetaElement>('meta[name="csrf-token"]');
	const content = meta?.content?.trim() ?? '';
	if (!content || content === '%CSRF_TOKEN%') return null;
	return content;
}

/**
 * Monta o `FormData` a partir do input do formulario.
 *
 * Espelha `parse_event_form` (services/calendar_core.py): campos `title`,
 * `description`, `location`, `starts_at`, `ends_at`, e os checkboxes `all_day`
 * / `create_conference` (o backend usa `bool(form.get(...))`, logo so importa
 * a presenca da chave — so anexamos quando `true`).
 */
function buildEventFormData(input: CalendarEventInput): FormData {
	const form = new FormData();
	form.set('title', input.title);
	form.set('description', input.description);
	form.set('location', input.location);
	form.set('starts_at', input.starts_at);
	form.set('ends_at', input.ends_at);
	if (input.is_all_day) form.set('all_day', 'on');
	if (input.create_conference) form.set('create_conference', 'on');
	return form;
}

/** Resposta crua das rotas legadas de evento: `{ ok, event }` (nao `{ok,data}`). */
interface LegacyEventResponse {
	ok: boolean;
	event?: CalendarEvent;
	error?: { code?: string; message?: string };
	message?: string;
}

/**
 * POST multipart para uma rota legada de evento, desempacotando `{ok,event}`.
 *
 * Mantem as mesmas convencoes de `client.ts` (cookie de sessao via
 * `credentials:'include'`, `X-CSRFToken` da meta, 401 -> navegacao top-level
 * para `/login`), mas le a chave `event` em vez do envelope `{ok,data}`,
 * porque essas rotas Jinja respondem `{ "ok": true, "event": _event_json }`.
 * Em falha estruturada lanca `ApiClientError`.
 */
async function postLegacyEventForm(
	path: string,
	form: FormData,
	signal?: AbortSignal
): Promise<CalendarEvent> {
	const headers: Record<string, string> = { Accept: 'application/json' };
	const token = readCsrfToken();
	if (token) headers['X-CSRFToken'] = token;

	const res = await fetch(path, {
		method: 'POST',
		credentials: 'include',
		headers,
		body: form,
		signal
	});

	if (res.status === 401) {
		if (typeof window !== 'undefined') window.location.assign(LOGIN_PATH);
		throw new ApiClientError('unauthenticated', 'Sessao expirada.', 401);
	}

	const text = await res.text();
	let parsed: LegacyEventResponse | ApiResult<unknown> | null = null;
	if (text) {
		try {
			parsed = JSON.parse(text) as LegacyEventResponse | ApiResult<unknown>;
		} catch {
			parsed = null;
		}
	}

	const legacy = (parsed ?? {}) as LegacyEventResponse;
	if (res.ok && legacy.ok && legacy.event) {
		return legacy.event;
	}

	const code = legacy.error?.code ?? 'server';
	const message =
		legacy.error?.message ??
		legacy.message ??
		'Nao foi possivel concluir a operacao do evento.';
	throw new ApiClientError(code, message, res.status);
}

/** Cria um evento (rota legada `POST /calendarios/eventos`). */
export function createEvent(
	input: CalendarEventInput,
	signal?: AbortSignal
): Promise<CalendarEvent> {
	return postLegacyEventForm(
		'/calendarios/eventos',
		buildEventFormData(input),
		signal
	);
}

/** Edita um evento (rota legada `POST /calendarios/eventos/<id>/editar`). */
export function updateEvent(
	id: number,
	input: CalendarEventInput,
	signal?: AbortSignal
): Promise<CalendarEvent> {
	return postLegacyEventForm(
		`/calendarios/eventos/${id}/editar`,
		buildEventFormData(input),
		signal
	);
}

/**
 * Gera o link do Google Meet de um evento
 * (rota legada `POST /calendarios/eventos/<id>/gerar-meet`).
 */
export function generateMeet(
	id: number,
	signal?: AbortSignal
): Promise<CalendarEvent> {
	return postLegacyEventForm(
		`/calendarios/eventos/${id}/gerar-meet`,
		new FormData(),
		signal
	);
}

/**
 * Exclui um evento (rota legada `POST /calendarios/eventos/<id>/excluir`).
 *
 * A rota responde `{ "ok": true, "event": _event_json }` mesmo apos a remocao
 * (o objeto `event` ainda esta carregado na sessao); o chamador normalmente
 * ignora o retorno e recarrega o hub.
 */
export function deleteEvent(
	id: number,
	signal?: AbortSignal
): Promise<CalendarEvent> {
	return postLegacyEventForm(
		`/calendarios/eventos/${id}/excluir`,
		new FormData(),
		signal
	);
}
