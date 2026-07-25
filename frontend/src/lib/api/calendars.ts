/**
 * Acesso tipado a tela de Calendario.
 *
 * Dois grupos de endpoints, ambos no envelope canonico `{ok,data}` (via
 * `client.ts`), na mesma origem do Flask:
 *
 *  1. Hub + acoes de conexao:
 *       - `GET  /api/calendarios`                  -> CalendarHub.
 *       - `POST /api/calendarios/google/disconnect` -> { disconnected }.
 *       - `POST /api/calendarios/google/sync`        -> resumo do sync.
 *       - `POST /api/calendarios/google/watch/renew` -> { expires_at_display }.
 *
 *  2. CRUD de evento (endpoints /api dedicados — issue #20, envelope `{ok,data}`):
 *       - `POST /api/calendarios/eventos`                 (criar)
 *       - `POST /api/calendarios/eventos/<id>/editar`     (editar)
 *       - `POST /api/calendarios/eventos/<id>/gerar-meet` (gerar Meet)
 *       - `POST /api/calendarios/eventos/<id>/excluir`    (excluir)
 *     Recebem JSON no corpo e respondem `{ok, data}`. A FALHA DE SYNC com o
 *     Google NAO e erro HTTP (o evento persiste): criar/editar devolvem
 *     `sync_outcome`/`sync_message` (espelhando o flash legado) para a SPA
 *     exibir o aviso equivalente; excluir devolve `remote_warning` opcional.
 */

import { get, post } from './client';
import { createSwrCache } from './swrCache';
import type {
	CalendarEvent,
	CalendarEventInput,
	CalendarEventMutationResult,
	CalendarEventDeleteResult,
	CalendarHub,
	CalendarMember
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

// Ultimo hub bom (sem filtros/escopo — endpoint nao aceita querystring). SWR:
// a tela reabre com o dado antigo e revalida em silencio (ver dashboard.ts).
const calendarHubCache = createSwrCache<CalendarHub>();
const CALENDAR_HUB_KEY = 'hub';

/** Ultimo hub carregado, ou null (sincrono, para o 1o render). */
export function peekCalendarHub(): CalendarHub | null {
	return calendarHubCache.peek(CALENDAR_HUB_KEY);
}

/** Busca o hub do calendario (eventos + estado da conexao Google). */
export async function getCalendarHub(signal?: AbortSignal): Promise<CalendarHub> {
	const data = await get<CalendarHub>('/api/calendarios', signal);
	calendarHubCache.store(CALENDAR_HUB_KEY, data);
	return data;
}

/** Busca os membros do Time visiveis no calendario do usuario logado. */
export function fetchCalendarMembers(
	signal?: AbortSignal
): Promise<{ members: CalendarMember[] }> {
	return get<{ members: CalendarMember[] }>('/api/calendarios/membros', signal);
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

// CRUD de evento via endpoints /api dedicados (envelope `{ok,data}`, issue #20).
// O corpo e enviado como JSON (`client.post`); o backend (routes/api/
// calendars_events.py) adapta para `parse_event_form` internamente.

/**
 * Cria um evento (`POST /api/calendarios/eventos`).
 *
 * A falha de sync com o Google NAO e erro HTTP: o evento persiste e o resultado
 * traz `sync_outcome`/`sync_message` (espelhando o flash legado) para a pagina
 * exibir o aviso equivalente. Erros estruturados (422 validacao / 500) viram
 * `ApiClientError` lancado por `client.post`.
 */
export function createEvent(
	input: CalendarEventInput,
	signal?: AbortSignal
): Promise<CalendarEventMutationResult> {
	return post<CalendarEventMutationResult>('/api/calendarios/eventos', input, signal);
}

/**
 * Edita um evento (`POST /api/calendarios/eventos/<id>/editar`).
 *
 * Mesmo contrato de `createEvent` (`{event, sync_outcome, sync_message}`).
 * Reuniao vinculada sem permissao -> 403 (`ApiClientError`).
 */
export function updateEvent(
	id: number,
	input: CalendarEventInput,
	signal?: AbortSignal
): Promise<CalendarEventMutationResult> {
	return post<CalendarEventMutationResult>(
		`/api/calendarios/eventos/${id}/editar`,
		input,
		signal
	);
}

/**
 * Gera o link do Google Meet de um evento
 * (`POST /api/calendarios/eventos/<id>/gerar-meet`).
 *
 * Devolve o evento ja com `meet_link` preenchido. Sem conexao Google -> 409;
 * falha de geracao -> 502 (ambos `ApiClientError`).
 */
export function generateMeet(
	id: number,
	signal?: AbortSignal
): Promise<{ event: CalendarEvent }> {
	return post<{ event: CalendarEvent }>(
		`/api/calendarios/eventos/${id}/gerar-meet`,
		undefined,
		signal
	);
}

/**
 * Exclui um evento (`POST /api/calendarios/eventos/<id>/excluir`).
 *
 * Devolve `{deleted}` e, quando o evento simples foi removido localmente mas
 * falhou no Google, `remote_warning` (a pagina exibe como aviso). Reuniao
 * vinculada com falha remota ABORTA no backend (502 -> `ApiClientError`),
 * nao exclui.
 */
export function deleteEvent(
	id: number,
	signal?: AbortSignal
): Promise<CalendarEventDeleteResult> {
	return post<CalendarEventDeleteResult>(
		`/api/calendarios/eventos/${id}/excluir`,
		undefined,
		signal
	);
}
