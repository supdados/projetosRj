"""Helpers PUROS de datas/serialização de etapas (sem dependência de rotas).

Extraído de ``routes/etapas/helpers.py`` (item de débito técnico #11) para
quebrar o acoplamento serviço -> rota: serviços como ``etapas_cascade`` e
``etapas_mutation`` precisavam destas funções, mas importá-las de uma rota criava
um ciclo (``services -> routes.etapas -> crud -> services.etapas_cascade``).
Agora moram num módulo de serviço neutro; ``routes/etapas/helpers.py`` mantém
re-exports finos para o código legado que ainda importa de lá.

As funções de cálculo de dias úteis (``_add_business_days``,
``_normalize_to_business_day``, ``_business_days_between``) são PURAS. As de
ordem/serialização (``_next_etapa_order``, ``_serialize_etapa_payload``) tocam o
ORM mas não dependem de ``flask`` request/blueprint.
"""

import datetime

from models import Etapa, db
from services.calendar_core import format_input_datetime
from services.project_meetings import (
    can_manage_project_meeting,
    is_google_meeting_stage,
    meeting_time_display,
    meeting_time_summary,
)


def _is_business_day(date_value):
    return date_value.weekday() < 5


def _normalize_to_business_day(date_value, *, forward=True):
    if date_value is None:
        return None

    normalized = date_value
    step = 1 if forward else -1
    while not _is_business_day(normalized):
        normalized += datetime.timedelta(days=step)
    return normalized


def _add_business_days(date_value, business_days):
    if date_value is None:
        return None

    try:
        business_days_int = int(business_days)
    except (TypeError, ValueError):
        business_days_int = 0

    if business_days_int == 0:
        return _normalize_to_business_day(date_value, forward=True)

    current_date = date_value
    step = 1 if business_days_int > 0 else -1
    remaining_days = abs(business_days_int)
    while remaining_days > 0 and current_date.weekday() >= 5:
        current_date += datetime.timedelta(days=step)
        if _is_business_day(current_date):
            remaining_days -= 1

    full_weeks, remaining_days = divmod(remaining_days, 5)
    if full_weeks:
        current_date += datetime.timedelta(days=full_weeks * 7 * step)

    while remaining_days > 0:
        current_date += datetime.timedelta(days=step)
        if _is_business_day(current_date):
            remaining_days -= 1
    return current_date


def _business_days_between(start_date, end_date):
    if not start_date or not end_date or start_date == end_date:
        return 0

    step = 1 if end_date > start_date else -1
    current_date = start_date
    business_days = 0

    while current_date != end_date:
        current_date += datetime.timedelta(days=step)
        if _is_business_day(current_date):
            business_days += step
    return business_days


def _next_etapa_order(project_id):
    ultima_etapa = (
        db.session.query(Etapa)
        .filter(Etapa.project_id == project_id)
        .order_by(Etapa.ordem.desc())
        .first()
    )
    return (ultima_etapa.ordem + 1) if ultima_etapa else 0


def _serialize_etapa_payload(etapa, *, connection=None):
    payload = {
        "id": etapa.id,
        "descricao": etapa.descricao,
        "comentarios": etapa.comentarios or "",
        "responsavel": etapa.responsavel or "",
        "data_inicio": (
            etapa.data_inicio.strftime("%Y-%m-%d") if etapa.data_inicio else ""
        ),
        "data_inicio_display": (
            etapa.data_inicio.strftime("%d/%m/%Y") if etapa.data_inicio else "Sem data"
        ),
        "data_fim": etapa.data_fim.strftime("%Y-%m-%d") if etapa.data_fim else "",
        "data_fim_display": (
            etapa.data_fim.strftime("%d/%m/%Y") if etapa.data_fim else "Sem data"
        ),
        "iniciada": bool(etapa.iniciada),
        "done": bool(etapa.done),
        "ordem": int(etapa.ordem or 0),
        "entry_type": etapa.entry_type or "manual",
    }

    if is_google_meeting_stage(etapa) and etapa.meeting is not None:
        can_manage = can_manage_project_meeting(connection, etapa.meeting)
        payload["meeting"] = {
            "time_summary": meeting_time_summary(etapa.meeting),
            "title": etapa.descricao,
            "description": etapa.meeting.description or "",
            "starts_at": format_input_datetime(etapa.meeting.starts_at),
            "ends_at": format_input_datetime(etapa.meeting.ends_at),
            "start_time_display": meeting_time_display(etapa.meeting, boundary="start"),
            "end_time_display": meeting_time_display(etapa.meeting, boundary="end"),
            "is_all_day": bool(etapa.meeting.is_all_day),
            "sync_status": etapa.meeting.sync_status,
            "sync_error": etapa.meeting.sync_error or "",
            "location": etapa.meeting.location or "",
            "meet_link": etapa.meeting.meet_link or "",
            "owner_email": etapa.meeting.google_owner_email or "",
            "can_manage": can_manage,
            "can_edit": can_manage and etapa.meeting.sync_status != "error",
            "can_edit_dates": can_manage and etapa.meeting.sync_status != "error",
        }
    return payload
