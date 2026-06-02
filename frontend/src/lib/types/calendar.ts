/**
 * Tipos da tela de Calendario.
 *
 * Espelham o que o backend serializa:
 *   - Hub: `GET /api/calendarios` -> `serialize_calendar_event` +
 *     `_serialize_connection` (routes/api/calendars.py, serializers.py).
 *   - CRUD de evento (rotas legadas com `Accept: application/json`):
 *     `_event_json` (routes/calendars/helpers.py) -> `{ ok, event }`.
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
 * `sync_error` so chega pelo hub (`serialize_calendar_event`); as rotas
 * legadas de CRUD (`_event_json`) NAO o incluem — por isso e opcional.
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
