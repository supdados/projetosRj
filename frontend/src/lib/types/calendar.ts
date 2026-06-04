/**
 * Tipos da tela de Calendario.
 *
 * Espelham o que o backend serializa:
 *   - Hub: `GET /api/calendarios` -> `serialize_calendar_event` +
 *     `_serialize_connection` (routes/api/calendars.py, serializers.py).
 *   - CRUD de evento (endpoints /api dedicados, issue #20, envelope `{ok,data}`):
 *     `routes/api/calendars_events.py` -> `{event, sync_outcome, sync_message}`
 *     (criar/editar), `{event}` (gerar-meet), `{deleted, remote_warning?}` (excluir).
 *
 * NUNCA expoem tokens (access_token/refresh_token/sync_token/
 * watch_channel_token) nem password_hash — o backend ja os omite.
 */

/**
 * Status de sincronizacao de um evento. Valores reais escritos pelo backend
 * (services/*, routes/calendars/*, models/calendar.py default="pending"):
 *   - "pending": salvo localmente, ainda nao enviado ao Google.
 *   - "ok": sincronizado com sucesso.
 *   - "error": falha de sync (ver `sync_error`).
 */
export type SyncStatus = 'pending' | 'ok' | 'error';

/** Origem do evento (models/calendar.py). */
export type CalendarEventSource = 'app' | 'google';

/**
 * Evento do calendario, ja serializado pelo backend.
 *
 * `starts_at`/`ends_at` vem em formato de input (`format_input_datetime`),
 * proprios para `<input type="datetime-local">`; os `_display` sao legiveis.
 * `sync_error` vem de `serialize_calendar_event` (hub e CRUD /api).
 */
export interface CalendarEvent {
	id: number;
	title: string;
	description: string;
	location: string;
	starts_at: string;
	ends_at: string;
	starts_at_display: string;
	ends_at_display: string;
	is_all_day: boolean;
	source: CalendarEventSource;
	sync_status: SyncStatus;
	sync_error?: string;
	meet_link: string;
}

/**
 * Estado da conexao Google Calendar (SEM tokens), com displays prontos.
 * Espelha `_serialize_connection` (routes/api/calendars.py). `connected` e
 * sempre `true` quando o objeto existe; ausencia de conexao = `null` no hub.
 */
export interface CalendarConnection {
	connected: true;
	provider: string;
	calendar_id: string;
	google_account_email: string | null;
	token_expires_at_display: string | null;
	watch_expiration_display: string | null;
	/** `true` quando o watch expira em menos de 48h. */
	watch_expiring_soon: boolean;
	last_sync_at_display: string | null;
}

/**
 * Carga do hub do calendario (`GET /api/calendarios`).
 * `connection` e `null` quando o usuario nao tem conta Google conectada.
 */
export interface CalendarHub {
	events: CalendarEvent[];
	connection: CalendarConnection | null;
	google_calendar_enabled: boolean;
	last_sync_display: string | null;
}

/**
 * Campos do formulario de criacao/edicao de evento.
 *
 * Enviados como `multipart/form-data` para as rotas legadas (request.form,
 * via `parse_event_form`): `title`, `description`, `location`, `starts_at`,
 * `ends_at`, `all_day`, `create_conference`. `is_all_day`/`create_conference`
 * sao booleanos no cliente; o cliente os converte para os campos de form.
 */
export interface CalendarEventInput {
	title: string;
	description: string;
	location: string;
	starts_at: string;
	ends_at: string;
	is_all_day: boolean;
	create_conference: boolean;
}

/**
 * Desfecho do sync com o Google ao criar/editar um evento. Espelha os flashes
 * legados (routes/calendars/events.py) — a falha de sync NAO e erro HTTP:
 *   - `synced`     : evento salvo E sincronizado com o Google Calendar.
 *   - `local_only` : sem conexao Google; salvo apenas localmente.
 *   - `sync_error` : evento persiste, mas o envio ao Google falhou.
 */
export type CalendarSyncOutcome = 'synced' | 'local_only' | 'sync_error';

/**
 * Resultado de criar/editar evento (`POST /api/calendarios/eventos[/<id>/editar]`).
 * `sync_message` e o texto PT pronto para exibir como toast/aviso, equivalente
 * ao flash do fluxo Jinja.
 */
export interface CalendarEventMutationResult {
	event: CalendarEvent;
	sync_outcome: CalendarSyncOutcome;
	sync_message: string;
}

/**
 * Resultado de excluir evento (`POST /api/calendarios/eventos/<id>/excluir`).
 * `remote_warning` so vem quando o evento simples foi removido localmente, mas
 * falhou no Google Calendar (equivalente ao flash warning legado).
 */
export interface CalendarEventDeleteResult {
	deleted: boolean;
	remote_warning?: string;
}

/**
 * Membro do Time exibido na secao lateral do calendario.
 * Espelha o item de `GET /api/calendarios/membros` -> `data.members`.
 */
export interface CalendarMember {
	id: number;
	name: string;
	initials: string;
}
