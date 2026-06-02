"""Endpoints JSON do calendário (Fase 6 — Google Calendar) para a SPA.

Anexa ao ``main_bp`` ÚNICO (``routes/blueprint.py``); NÃO cria blueprint novo.

Cobre o hub de calendário (``GET /api/calendarios``) e as ações de conexão com o
Google que, no fluxo Jinja, eram redirect-only (``routes/calendars/sync.py``).
Como aquelas rotas não respondem JSON, criamos endpoints ``/api`` novos que
chamam EXATAMENTE os mesmos helpers de ``routes/calendars/helpers.py``
(``_sync_events_from_google``, ``_stop_watch_channel``, ``_auto_disconnect``,
``_renew_watch_channel``), porém respondendo no envelope canônico. NÃO
importamos nem alteramos ``routes/calendars/sync.py``.

O CRUD de evento NÃO é reimplementado aqui: o frontend reusa as rotas legadas
``POST /calendarios/eventos[/...]`` enviando ``Accept: application/json`` (elas
já devolvem ``{ok: true, event: ...}``).

NUNCA serializa ``access_token``/``refresh_token``/``sync_token``/
``watch_channel_token``/``password_hash``.
"""

from __future__ import annotations

import datetime
from typing import Any

from flask import Response, current_app, g

from models import CalendarEvent, db
from services.google_calendar import is_google_calendar_enabled

from ..blueprint import main_bp
from ..calendars.helpers import (
    _EXPIRED_TOKEN_CODES,
    _auto_disconnect,
    _connection_for_current_user,
    _describe_calendar_issue,
    _format_human_datetime,
    _renew_watch_channel,
    _stop_watch_channel,
    _sync_events_from_google,
)
from .envelope import fail, ok
from .negotiation import api_login_required
from .serializers import serialize_calendar_event

# Janela (em horas) para sinalizar que o canal de watch está perto de vencer.
_WATCH_EXPIRY_WARN_HOURS = 48


def _serialize_connection(connection: Any) -> dict[str, Any] | None:
    """Serializa a conexão Google SEM tokens, com displays prontos.

    Expõe apenas campos seguros (``provider``, ``calendar_id``,
    ``google_account_email``, expiração de token/watch e ``last_sync_at``).
    NUNCA inclui ``access_token``/``refresh_token``/``sync_token``/
    ``watch_channel_token``.

    Args:
        connection: ``UserCalendarConnection`` ou ``None``.

    Returns:
        ``dict`` com o estado da conexão, ou ``None`` se não houver conexão.
    """
    if connection is None:
        return None

    watch_expiration = connection.watch_expiration
    watch_expiring_soon = False
    if watch_expiration is not None:
        threshold = datetime.datetime.utcnow() + datetime.timedelta(
            hours=_WATCH_EXPIRY_WARN_HOURS
        )
        watch_expiring_soon = watch_expiration <= threshold

    return {
        "connected": True,
        "provider": connection.provider,
        "calendar_id": connection.calendar_id,
        "google_account_email": connection.google_account_email,
        "token_expires_at_display": _format_human_datetime(
            connection.token_expires_at
        ),
        "watch_expiration_display": _format_human_datetime(watch_expiration),
        "watch_expiring_soon": watch_expiring_soon,
        "last_sync_at_display": _format_human_datetime(connection.last_sync_at),
    }


@main_bp.route("/api/calendarios", methods=["GET"])
@api_login_required
def api_calendars_hub() -> Response | tuple[Response, int]:
    """Hub do calendário: eventos do usuário + estado da conexão Google.

    Reaproveita os mesmos helpers do fluxo Jinja
    (``_connection_for_current_user``, ``_format_human_datetime``,
    ``is_google_calendar_enabled``). Não dispara sync automático — apenas lê o
    estado atual. NUNCA expõe tokens.

    Returns:
        Envelope ``{"ok": true, "data": {...}}`` com ``events``, ``connection``
        (ou ``None``), ``google_calendar_enabled`` e ``last_sync_display``.
    """
    events = (
        CalendarEvent.query.filter_by(user_id=g.user.id)
        .order_by(CalendarEvent.starts_at.asc(), CalendarEvent.id.asc())
        .all()
    )
    connection = _connection_for_current_user()
    last_sync_display = (
        _format_human_datetime(connection.last_sync_at)
        if connection is not None
        else None
    )

    return ok(
        {
            "events": [serialize_calendar_event(event) for event in events],
            "connection": _serialize_connection(connection),
            "google_calendar_enabled": bool(
                is_google_calendar_enabled(current_app.config)
            ),
            "last_sync_display": last_sync_display,
        }
    )


def _disconnect_for_expired_token(connection: Any) -> None:
    """Remove a conexão quando o token expirou/revogou (igual ao legado).

    Tenta ``_auto_disconnect`` + commit; em falha, faz rollback silencioso —
    o erro estruturado já será reportado ao cliente.
    """
    try:
        _auto_disconnect(connection)
        db.session.commit()
    except Exception:
        db.session.rollback()


@main_bp.route("/api/calendarios/google/disconnect", methods=["POST"])
@api_login_required
def api_disconnect_google_calendar() -> Response | tuple[Response, int]:
    """Desconecta a conta Google, reusando ``_stop_watch_channel`` + delete.

    Espelha ``routes/calendars/sync.py::disconnect_google_calendar``, porém no
    envelope JSON.

    Returns:
        ``ok({"disconnected": true})`` no sucesso; ``fail`` em erro/ausência.
    """
    connection = _connection_for_current_user()
    if connection is None:
        return fail(
            "Nenhuma conexão Google Calendar para desconectar.",
            status=404,
            code="not_found",
        )

    try:
        _stop_watch_channel(connection, suppress_errors=True)
        db.session.delete(connection)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return fail(
            f"Falha ao desconectar Google Calendar: {exc}",
            status=502,
            code="server",
        )

    return ok({"disconnected": True})


@main_bp.route("/api/calendarios/google/sync", methods=["POST"])
@api_login_required
def api_sync_google_calendar_now() -> Response | tuple[Response, int]:
    """Sincroniza eventos com o Google, reusando ``_sync_events_from_google``.

    Espelha ``routes/calendars/sync.py::sync_google_calendar_now``, porém no
    envelope JSON. Trata token expirado igual ao legado: ``_describe_calendar_issue``
    + ``_EXPIRED_TOKEN_CODES`` -> ``_auto_disconnect`` e erro estruturado.

    Returns:
        ``ok({"upserted", "deleted", "ignored", "full_sync"})`` no sucesso;
        ``fail`` (com ``code="unauthenticated"`` quando o token expirou) no erro.
    """
    connection = _connection_for_current_user()
    if connection is None:
        return fail(
            "Conecte sua conta Google antes de sincronizar.",
            status=409,
            code="validation",
        )

    try:
        summary = _sync_events_from_google(connection)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        desc = _describe_calendar_issue(exc)
        if desc in _EXPIRED_TOKEN_CODES:
            _disconnect_for_expired_token(connection)
            return fail(
                "Sua conexão com o Google Calendar expirou e foi removida. "
                "Conecte novamente para retomar a sincronização.",
                status=401,
                code="unauthenticated",
            )
        return fail(
            f"Erro ao sincronizar com Google Calendar: {exc}",
            status=502,
            code="server",
        )

    return ok(
        {
            "upserted": summary["upserted"],
            "deleted": summary["deleted"],
            "ignored": summary["ignored"],
            "full_sync": summary.get("full_sync", False),
        }
    )


@main_bp.route("/api/calendarios/google/watch/renew", methods=["POST"])
@api_login_required
def api_renew_google_calendar_watch() -> Response | tuple[Response, int]:
    """Renova o canal de watch, reusando ``_renew_watch_channel``.

    Espelha ``routes/calendars/sync.py::renew_google_calendar_watch``, porém no
    envelope JSON. Trata token expirado igual ao legado.

    Returns:
        ``ok({"expires_at_display"})`` no sucesso; ``fail`` no erro.
    """
    connection = _connection_for_current_user()
    if connection is None:
        return fail(
            "Conecte sua conta Google antes de renovar watch.",
            status=409,
            code="validation",
        )

    try:
        watch_summary = _renew_watch_channel(connection)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        desc = _describe_calendar_issue(exc)
        if desc in _EXPIRED_TOKEN_CODES:
            _disconnect_for_expired_token(connection)
            return fail(
                "Sua conexão com o Google Calendar expirou e foi removida. "
                "Conecte novamente para retomar a sincronização.",
                status=401,
                code="unauthenticated",
            )
        return fail(
            f"Erro ao renovar watch do Google Calendar: {desc}",
            status=502,
            code="server",
        )

    return ok(
        {
            "expires_at_display": _format_human_datetime(
                watch_summary.get("expires_at")
            ),
        }
    )
