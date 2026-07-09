"""Lógica de negócio para criação, edição e exclusão de etapas."""

import datetime

from flask import current_app

from models import Etapa, Task, db
from routes.shared import log_project_action
from services.etapas_dates import (
    _add_business_days,
    _business_days_between,
    _next_etapa_order,
    _normalize_to_business_day,
    _serialize_etapa_payload,
)
from services.calendar_core import to_local_datetime
from services.calendar_sync import delete_remote_event, sync_local_event_to_google
from services.task_status import FINALIZED_TASK_STATUSES
from services.project_meetings import (
    can_manage_project_meeting,
    delete_local_calendar_event_mirrors,
    sync_etapa_from_meeting,
    sync_local_calendar_event_mirrors,
    update_meeting_from_calendar_event,
)

# ── Bloqueio por tarefas abertas ─────────────────────────────────────────────


def count_open_tasks_in_etapa(etapa_id: int) -> int:
    """Quantas tarefas da etapa ainda estão abertas (não arquivadas, não finalizadas)."""
    return Task.query.filter(
        Task.etapa_id == etapa_id,
        Task.is_archived.is_(False),
        ~Task.status.in_(FINALIZED_TASK_STATUSES),
    ).count()


def _clear_tasks_from_etapa(etapa) -> None:
    Task.query.filter(Task.etapa_id == etapa.id).update(
        {Task.etapa_id: None}, synchronize_session=False
    )


# ── Criação ──────────────────────────────────────────────────────────────────


def create_etapa_record(
    project,
    *,
    descricao,
    data_inicio,
    data_fim,
    responsavel,
    comentarios,
    iniciada,
    done,
):
    """Cria uma Etapa, reativa o projeto se necessário.

    Não faz commit — a rota é responsável pela transação.
    Retorna ``(etapa, project_was_reactivated)``.
    """
    nova_ordem = _next_etapa_order(project.id)
    etapa = Etapa(
        descricao=descricao,
        data_inicio=data_inicio,
        data_fim=data_fim,
        responsavel=responsavel,
        iniciada=iniciada,
        done=done,
        comentarios=comentarios,
        project_id=project.id,
        ordem=nova_ordem,
    )
    db.session.add(etapa)

    project_was_reactivated = False
    if project.status == "Finalizado":
        project.status = "Vigente"
        project_was_reactivated = True
        log_project_action(
            project_id=project.id,
            action_type="reactivate",
            description=f'Reativou o projeto ao adicionar a etapa "{descricao}"',
        )

    log_project_action(
        project_id=project.id,
        action_type="add_etapa",
        description=f'Adicionou a etapa "{descricao}"',
    )
    return etapa, project_was_reactivated


# ── Exclusão ─────────────────────────────────────────────────────────────────


def delete_meeting_etapa(etapa, connection):
    """Exclui uma etapa de reunião Google (evento remoto + mirrors locais).

    Não faz commit.
    Retorna ``remote_warning`` (str) se houver problema com o evento remoto,
    ``None`` em caso de sucesso.
    """
    meeting = etapa.meeting
    remote_warning = None

    if meeting.google_event_id and meeting.sync_status != "error":
        try:
            delete_remote_event(
                current_app.config,
                connection,
                google_event_id=meeting.google_event_id,
                google_calendar_id=meeting.google_calendar_id,
            )
        except Exception as exc:
            remote_warning = str(exc)

    if remote_warning:
        return remote_warning

    log_project_action(
        project_id=etapa.project_id,
        action_type="delete_google_meeting",
        description=f'Excluiu a reunião "{etapa.descricao}"',
    )
    delete_local_calendar_event_mirrors(meeting)
    _clear_tasks_from_etapa(etapa)
    db.session.delete(etapa)
    return None


def delete_regular_etapa(etapa):
    """Exclui uma etapa normal (não-reunião). Não faz commit."""
    log_project_action(
        project_id=etapa.project_id,
        action_type="delete_etapa",
        description=f'Excluiu a etapa "{etapa.descricao}"',
    )
    _clear_tasks_from_etapa(etapa)
    db.session.delete(etapa)


# ── Edição inline — reunião Google ───────────────────────────────────────────


def update_meeting_dates(etapa, field, new_date, connection):
    """Atualiza data de início ou fim de uma reunião Google e sincroniza.

    ``new_date`` deve ser um ``datetime.date`` (obrigatório).
    Não faz commit.
    Retorna ``response_data`` dict para jsonify.
    """
    meeting = etapa.meeting
    start_local = to_local_datetime(meeting.starts_at)
    end_local = to_local_datetime(meeting.ends_at)

    if start_local is None or end_local is None:
        raise ValueError("A reunião não possui horário válido para ajuste.")

    if field == "data_inicio":
        duration = meeting.ends_at - meeting.starts_at
        new_start_local = datetime.datetime.combine(new_date, start_local.timetz())
        new_start_utc = new_start_local.astimezone(datetime.timezone.utc).replace(
            tzinfo=None
        )
        new_end_utc = new_start_utc + duration
        old_value_str = start_local.strftime("%d/%m/%Y")
        new_value_str = new_start_local.strftime("%d/%m/%Y")
        meeting.starts_at = new_start_utc
        meeting.ends_at = new_end_utc
    else:
        new_end_local = datetime.datetime.combine(new_date, end_local.timetz())
        new_end_utc = new_end_local.astimezone(datetime.timezone.utc).replace(
            tzinfo=None
        )
        if new_end_utc <= meeting.starts_at:
            raise ValueError("A data final precisa ser posterior ao início da reunião.")
        old_value_str = end_local.strftime("%d/%m/%Y")
        new_value_str = new_end_local.strftime("%d/%m/%Y")
        meeting.ends_at = new_end_utc

    event = meeting.calendar_event
    if event is not None:
        event.starts_at = meeting.starts_at
        event.ends_at = meeting.ends_at
        event.is_all_day = meeting.is_all_day
        event.timezone = meeting.timezone
        try:
            sync_local_event_to_google(
                current_app.config,
                event,
                connection,
                create_conference=False,
            )
        except Exception as exc:
            event.sync_status = "error"
            event.sync_error = str(exc)
        update_meeting_from_calendar_event(meeting, event)

    sync_etapa_from_meeting(etapa, meeting, title=etapa.descricao)
    sync_local_calendar_event_mirrors(meeting, title=etapa.descricao)

    log_project_action(
        project_id=etapa.project_id,
        action_type="reschedule_google_meeting",
        description=f'Reagendou a reunião "{etapa.descricao}"',
        old_value=old_value_str,
        new_value=new_value_str,
    )

    response_data = {
        "success": True,
        "isMeeting": True,
        "message": "Data da reunião atualizada com sucesso.",
    }
    if field == "data_inicio" and etapa.data_inicio:
        response_data["newValue"] = etapa.data_inicio.strftime("%Y-%m-%d")
        response_data["displayValue"] = etapa.data_inicio.strftime("%d/%m/%Y")
    else:
        response_data["newValue"] = (
            etapa.data_fim.strftime("%Y-%m-%d") if etapa.data_fim else ""
        )
        response_data["displayValue"] = (
            etapa.data_fim.strftime("%d/%m/%Y") if etapa.data_fim else "Sem data"
        )

    if field == "data_inicio" and etapa.data_fim:
        response_data["updatedEndDate"] = etapa.data_fim.strftime("%Y-%m-%d")
        response_data["updatedEndDateDisplay"] = etapa.data_fim.strftime("%d/%m/%Y")

    return response_data


# ── Edição inline — campo regular ────────────────────────────────────────────

_FIELD_DISPLAY_NAMES = {
    "descricao": "descrição",
    "data_inicio": "data de início",
    "data_fim": "data de fim",
    "responsavel": "responsável",
}


def _parse_and_normalize_date(value: str | None) -> "datetime.date | None":
    if not value:
        return None
    raw = datetime.datetime.strptime(value, "%Y-%m-%d").date()
    return _normalize_to_business_day(raw, forward=True)


def _date_iso(d: "datetime.date | None") -> str:
    return d.strftime("%Y-%m-%d") if d else ""


def _date_br(d: "datetime.date | None", empty: str = "Sem data") -> str:
    return d.strftime("%d/%m/%Y") if d else empty


def _log_etapa_field_change(
    etapa, field_display: str, old_str: str, new_str: str
) -> None:
    log_project_action(
        project_id=etapa.project_id,
        action_type="edit_etapa_inline",
        description=f'Alterou {field_display} da etapa "{etapa.descricao}"',
        old_value=old_str,
        new_value=new_str,
    )


def _update_data_inicio(etapa, value: str | None, out: dict) -> None:
    old_date = etapa.data_inicio
    new_date = _parse_and_normalize_date(value)
    _log_etapa_field_change(
        etapa,
        _FIELD_DISPLAY_NAMES["data_inicio"],
        _date_br(old_date, "vazio"),
        _date_br(new_date, "vazio"),
    )
    etapa.data_inicio = new_date
    out["newValue"] = _date_iso(new_date)
    out["displayValue"] = _date_br(new_date)

    if old_date and new_date:
        days_diff = _business_days_between(old_date, new_date)
        out["daysDiff"] = days_diff
        if etapa.data_fim:
            etapa.data_fim = _normalize_to_business_day(
                _add_business_days(etapa.data_fim, days_diff), forward=True
            )
            out["updatedEndDate"] = _date_iso(etapa.data_fim)
            out["updatedEndDateDisplay"] = _date_br(etapa.data_fim)


def _update_data_fim(etapa, value: str | None, out: dict) -> None:
    old_date = etapa.data_fim
    new_date = _parse_and_normalize_date(value)
    _log_etapa_field_change(
        etapa,
        _FIELD_DISPLAY_NAMES["data_fim"],
        _date_br(old_date, "vazio"),
        _date_br(new_date, "vazio"),
    )
    etapa.data_fim = new_date
    out["newValue"] = _date_iso(new_date)
    out["displayValue"] = _date_br(new_date)


def _update_descricao(etapa, value: str | None, out: dict) -> None:
    old_value = etapa.descricao
    log_project_action(
        project_id=etapa.project_id,
        action_type="edit_etapa_inline",
        description=f'Alterou {_FIELD_DISPLAY_NAMES["descricao"]} da etapa',
        old_value=old_value or "vazio",
        new_value=value or "vazio",
    )
    etapa.descricao = value
    out["newValue"] = value
    out["displayValue"] = value if value else "-"


def _update_responsavel(etapa, value: str | None, out: dict) -> None:
    old_value = etapa.responsavel
    _log_etapa_field_change(
        etapa,
        _FIELD_DISPLAY_NAMES["responsavel"],
        old_value or "vazio",
        value or "vazio",
    )
    etapa.responsavel = value
    out["newValue"] = value
    out["displayValue"] = value if value else "Sem responsável"


_FIELD_UPDATERS = {
    "data_inicio": _update_data_inicio,
    "data_fim": _update_data_fim,
    "descricao": _update_descricao,
    "responsavel": _update_responsavel,
}


def update_regular_field(etapa, field: str, value: str | None) -> dict:
    """Atualiza um campo de uma etapa regular (não-reunião).

    Não faz commit.
    Retorna ``response_data`` dict para jsonify.
    """
    response_data: dict = {"success": True}
    updater = _FIELD_UPDATERS.get(field)
    if updater:
        updater(etapa, value, response_data)
    return response_data


# ── Comentário ───────────────────────────────────────────────────────────────


def save_etapa_comentario(etapa, comentario):
    """Atualiza comentário de uma etapa. Não faz commit.

    Retorna ``message`` string.
    """
    old_comentario = etapa.comentarios or "vazio"
    new_comentario = comentario if comentario else "vazio"

    etapa.comentarios = comentario if comentario else None

    if comentario and old_comentario == "vazio":
        action_description = "Adicionou comentário"
    elif not comentario and old_comentario != "vazio":
        action_description = "Removeu comentário"
    else:
        action_description = "Editou comentário"

    log_project_action(
        project_id=etapa.project_id,
        action_type="edit_etapa_comentario",
        description=f'{action_description} da etapa "{etapa.descricao}"',
        old_value=old_comentario,
        new_value=new_comentario,
    )

    return (
        "Comentário salvo com sucesso!"
        if comentario
        else "Comentário removido com sucesso!"
    )
