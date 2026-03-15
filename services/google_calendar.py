import json
import os
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


GOOGLE_OAUTH_AUTH_URI = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_OAUTH_TOKEN_URI = 'https://oauth2.googleapis.com/token'
GOOGLE_OAUTH_USERINFO_URI = 'https://openidconnect.googleapis.com/v1/userinfo'
GOOGLE_CALENDAR_SCOPE_EVENTS = 'https://www.googleapis.com/auth/calendar.events'
GOOGLE_CALENDAR_API_BASE = 'https://www.googleapis.com/calendar/v3'


class GoogleCalendarError(RuntimeError):
    """Erro de integração com Google OAuth/Calendar API."""

    def __init__(self, message, *, status_code=None, response_body=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


@dataclass(frozen=True)
class GoogleCalendarSettings:
    client_id: str
    client_secret: str
    auth_uri: str
    token_uri: str
    redirect_uri: str
    available_redirect_uris: tuple
    scope: str
    timeout_seconds: int


def _as_bool(value):
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def _normalize_timeout(raw_value):
    try:
        timeout = int(raw_value)
    except (TypeError, ValueError):
        return 10
    return timeout if timeout > 0 else 10


def _decode_bytes(raw_body):
    if raw_body is None:
        return ''
    if isinstance(raw_body, bytes):
        return raw_body.decode('utf-8', errors='replace')
    return str(raw_body)


def _resolve_client_secret_path(config):
    configured = str(config.get('GOOGLE_CALENDAR_CLIENT_SECRET_FILE', 'config/client_secret.json')).strip()
    if not configured:
        configured = 'config/client_secret.json'
    if os.path.isabs(configured):
        return configured
    return os.path.abspath(configured)


def load_google_oauth_client(config):
    path = _resolve_client_secret_path(config)
    if not os.path.exists(path):
        raise GoogleCalendarError(
            f"Arquivo de credenciais Google não encontrado: {path}"
        )

    try:
        with open(path, 'r', encoding='utf-8') as fp:
            payload = json.load(fp)
    except OSError as exc:
        raise GoogleCalendarError(f'Falha ao ler credenciais Google: {exc}') from exc
    except json.JSONDecodeError as exc:
        raise GoogleCalendarError('Arquivo de credenciais Google inválido (JSON).') from exc

    client = payload.get('web') or payload.get('installed')
    if not isinstance(client, dict):
        raise GoogleCalendarError('Credencial Google inválida: esperado bloco "web" ou "installed".')

    return client


def get_google_client_redirect_uris(config):
    client = load_google_oauth_client(config)
    redirect_uris = client.get('redirect_uris') or []
    if not isinstance(redirect_uris, list):
        return []
    return [str(uri).strip() for uri in redirect_uris if str(uri).strip()]


def is_google_calendar_enabled(config):
    if str(config.get('GOOGLE_CALENDAR_ENABLED', 'true')).strip().lower() in {'0', 'false', 'no', 'off'}:
        return False

    try:
        client = load_google_oauth_client(config)
    except GoogleCalendarError:
        return False

    return bool(str(client.get('client_id', '')).strip() and str(client.get('client_secret', '')).strip())


def get_google_calendar_settings(config, *, redirect_uri=None):
    if not is_google_calendar_enabled(config):
        raise GoogleCalendarError('Integração Google Calendar não está habilitada ou configurada.')

    client = load_google_oauth_client(config)
    redirect_uris = tuple(get_google_client_redirect_uris(config))

    configured_redirect_uri = str(config.get('GOOGLE_CALENDAR_REDIRECT_URI', '')).strip()
    resolved_redirect_uri = str(redirect_uri or configured_redirect_uri or (redirect_uris[0] if redirect_uris else '')).strip()
    if not resolved_redirect_uri:
        raise GoogleCalendarError('Nenhuma redirect_uri disponível para OAuth do Google Calendar.')

    auth_uri = str(client.get('auth_uri', '')).strip() or GOOGLE_OAUTH_AUTH_URI
    token_uri = str(client.get('token_uri', '')).strip() or GOOGLE_OAUTH_TOKEN_URI
    scope = str(config.get('GOOGLE_CALENDAR_SCOPE', GOOGLE_CALENDAR_SCOPE_EVENTS)).strip() or GOOGLE_CALENDAR_SCOPE_EVENTS

    return GoogleCalendarSettings(
        client_id=str(client.get('client_id', '')).strip(),
        client_secret=str(client.get('client_secret', '')).strip(),
        auth_uri=auth_uri,
        token_uri=token_uri,
        redirect_uri=resolved_redirect_uri,
        available_redirect_uris=redirect_uris,
        scope=scope,
        timeout_seconds=_normalize_timeout(config.get('GOOGLE_CALENDAR_TIMEOUT_SECONDS', 10)),
    )


def _http_json_request(*, method, url, timeout_seconds, headers=None, form_data=None, json_data=None):
    request_headers = dict(headers or {})
    payload = None

    if form_data is not None and json_data is not None:
        raise GoogleCalendarError('Não é permitido enviar form_data e json_data na mesma requisição.')

    if form_data is not None:
        payload = urlencode(form_data).encode('utf-8')
        request_headers.setdefault('Content-Type', 'application/x-www-form-urlencoded')
    elif json_data is not None:
        payload = json.dumps(json_data).encode('utf-8')
        request_headers.setdefault('Content-Type', 'application/json')

    req = Request(url, data=payload, headers=request_headers, method=method)
    try:
        with urlopen(req, timeout=timeout_seconds) as response:
            raw_body = response.read()
            body = _decode_bytes(raw_body)
            if not body:
                return {}
    except HTTPError as exc:
        body = _decode_bytes(exc.read())
        raise GoogleCalendarError(
            f'Erro HTTP {exc.code} em {url}: {body[:300]}',
            status_code=exc.code,
            response_body=body,
        ) from exc
    except URLError as exc:
        raise GoogleCalendarError(f'Falha de conectividade com Google APIs: {exc}') from exc
    except Exception as exc:
        raise GoogleCalendarError(f'Falha inesperada na chamada para Google APIs: {exc}') from exc

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise GoogleCalendarError('Resposta da API Google não está em JSON válido.') from exc

    if not isinstance(parsed, dict):
        raise GoogleCalendarError('Resposta da API Google veio em formato inesperado.')
    return parsed


def build_google_authorization_url(config, *, state, redirect_uri=None):
    settings = get_google_calendar_settings(config, redirect_uri=redirect_uri)
    params = {
        'client_id': settings.client_id,
        'redirect_uri': settings.redirect_uri,
        'response_type': 'code',
        'scope': settings.scope,
        'state': state,
        'access_type': 'offline',
        'include_granted_scopes': 'true',
        'prompt': 'consent',
    }
    return f'{settings.auth_uri}?{urlencode(params)}'


def exchange_google_code_for_tokens(config, *, code, redirect_uri=None):
    settings = get_google_calendar_settings(config, redirect_uri=redirect_uri)
    payload = _http_json_request(
        method='POST',
        url=settings.token_uri,
        timeout_seconds=settings.timeout_seconds,
        form_data={
            'grant_type': 'authorization_code',
            'code': code,
            'client_id': settings.client_id,
            'client_secret': settings.client_secret,
            'redirect_uri': settings.redirect_uri,
        },
    )
    if 'access_token' not in payload:
        raise GoogleCalendarError('Resposta de token OAuth sem access_token.')
    return payload


def refresh_google_access_token(config, *, refresh_token, redirect_uri=None):
    settings = get_google_calendar_settings(config, redirect_uri=redirect_uri)
    payload = _http_json_request(
        method='POST',
        url=settings.token_uri,
        timeout_seconds=settings.timeout_seconds,
        form_data={
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'client_id': settings.client_id,
            'client_secret': settings.client_secret,
        },
    )
    if 'access_token' not in payload:
        raise GoogleCalendarError('Resposta de refresh sem access_token.')
    return payload


def get_google_userinfo(config, *, access_token):
    settings = get_google_calendar_settings(config)
    payload = _http_json_request(
        method='GET',
        url=GOOGLE_OAUTH_USERINFO_URI,
        timeout_seconds=settings.timeout_seconds,
        headers=_authorized_headers(access_token),
    )
    if 'sub' not in payload:
        raise GoogleCalendarError('Resposta do userinfo sem identificador da conta Google.')
    return payload


def _authorized_headers(access_token):
    return {
        'Authorization': f'Bearer {access_token}',
        'Accept': 'application/json',
    }


def create_google_calendar_event(config, *, access_token, calendar_id, event_payload, conference_data_version=0):
    settings = get_google_calendar_settings(config)
    encoded_calendar = quote(str(calendar_id), safe='')
    url = f'{GOOGLE_CALENDAR_API_BASE}/calendars/{encoded_calendar}/events'
    if conference_data_version:
        url += f'?conferenceDataVersion={int(conference_data_version)}'
    return _http_json_request(
        method='POST',
        url=url,
        timeout_seconds=settings.timeout_seconds,
        headers=_authorized_headers(access_token),
        json_data=event_payload,
    )


def update_google_calendar_event(config, *, access_token, calendar_id, event_id, event_payload, conference_data_version=0):
    settings = get_google_calendar_settings(config)
    encoded_calendar = quote(str(calendar_id), safe='')
    encoded_event = quote(str(event_id), safe='')
    url = f'{GOOGLE_CALENDAR_API_BASE}/calendars/{encoded_calendar}/events/{encoded_event}'
    if conference_data_version:
        url += f'?conferenceDataVersion={int(conference_data_version)}'
    return _http_json_request(
        method='PUT',
        url=url,
        timeout_seconds=settings.timeout_seconds,
        headers=_authorized_headers(access_token),
        json_data=event_payload,
    )


def delete_google_calendar_event(config, *, access_token, calendar_id, event_id):
    settings = get_google_calendar_settings(config)
    encoded_calendar = quote(str(calendar_id), safe='')
    encoded_event = quote(str(event_id), safe='')
    url = f'{GOOGLE_CALENDAR_API_BASE}/calendars/{encoded_calendar}/events/{encoded_event}'
    try:
        _http_json_request(
            method='DELETE',
            url=url,
            timeout_seconds=settings.timeout_seconds,
            headers=_authorized_headers(access_token),
        )
    except GoogleCalendarError as exc:
        if exc.status_code == 404:
            return False
        raise
    return True


def list_google_calendar_events(config, *, access_token, calendar_id, params=None):
    settings = get_google_calendar_settings(config)
    encoded_calendar = quote(str(calendar_id), safe='')
    query = ''
    if params:
        query = '?' + urlencode(params)
    url = f'{GOOGLE_CALENDAR_API_BASE}/calendars/{encoded_calendar}/events{query}'
    return _http_json_request(
        method='GET',
        url=url,
        timeout_seconds=settings.timeout_seconds,
        headers=_authorized_headers(access_token),
    )


def create_google_calendar_watch(
    config,
    *,
    access_token,
    calendar_id,
    channel_id,
    webhook_address,
    channel_token=None,
    ttl_seconds=604800,
):
    settings = get_google_calendar_settings(config)
    encoded_calendar = quote(str(calendar_id), safe='')
    url = f'{GOOGLE_CALENDAR_API_BASE}/calendars/{encoded_calendar}/events/watch'
    payload = {
        'id': channel_id,
        'type': 'web_hook',
        'address': webhook_address,
        'params': {'ttl': str(max(60, int(ttl_seconds)))},
    }
    if channel_token:
        payload['token'] = channel_token

    return _http_json_request(
        method='POST',
        url=url,
        timeout_seconds=settings.timeout_seconds,
        headers=_authorized_headers(access_token),
        json_data=payload,
    )


def stop_google_calendar_watch(config, *, access_token, channel_id, resource_id):
    settings = get_google_calendar_settings(config)
    url = f'{GOOGLE_CALENDAR_API_BASE}/channels/stop'
    return _http_json_request(
        method='POST',
        url=url,
        timeout_seconds=settings.timeout_seconds,
        headers=_authorized_headers(access_token),
        json_data={
            'id': channel_id,
            'resourceId': resource_id,
        },
    )
