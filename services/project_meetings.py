import datetime

from services.calendar_core import format_human_datetime, to_local_datetime
from services.calendar_sync import sync_local_event_to_google
from models import CalendarEvent, Etapa, ProjectStageMeeting, db

MEETING_ENTRY_TYPE = "google_meeting"


def _shift_weekend_meeting_payload(payload):
    """Se o início da reunião cair num sábado/domingo, empurra `starts_at`/
    `ends_at` (UTC-naive) pro próximo dia útil, preservando duração e horário
    local BR — mesma regra de `etapas_dates._normalize_to_business_day` usada
    na edição manual da data da etapa, agora também no caminho de reunião
    Google (que gravava a data direto, sem essa checagem).

    Returns:
        ``(payload_ajustado, (data_antiga, data_nova) | None)``.
    """
    # Import tardio evita ciclo project_meetings <-> etapas_dates.
    from services.etapas_dates import _normalize_to_business_day

    start_local = to_local_datetime(payload["starts_at"])
    old_date = start_local.date()
    if old_date.weekday() < 5:
        return payload, None

    new_date = _normalize_to_business_day(old_date, forward=True)
    day_delta = datetime.timedelta(days=(new_date - old_date).days)

    shifted = dict(payload)
    shifted["starts_at"] = payload["starts_at"] + day_delta
    shifted["ends_at"] = payload["ends_at"] + day_delta
    return shifted, (old_date, new_date)


def _weekend_shift_message(weekend_shift):
    if not weekend_shift:
        return None
    old_date, new_date = weekend_shift
    return (
        f"A data da reunião caiu num fim de semana ({old_date.strftime('%d/%m/%Y')}) "
        f"e foi movida automaticamente para o próximo dia útil "
        f"({new_date.strftime('%d/%m/%Y')})."
    )


def shift_weekend_calendar_event(event) -> "tuple[datetime.date, datetime.date] | None":
    """Aplica a regra de fim de semana num ``CalendarEvent`` já preenchido —
    caminho inbound (webhook/sync Google→app), que não passa pelo payload de
    formulário coberto por ``_shift_weekend_meeting_payload``.

    Returns:
        ``(data_antiga, data_nova)`` quando houve shift, senão ``None``.
    """
    payload = {"starts_at": event.starts_at, "ends_at": event.ends_at}
    shifted, weekend_shift = _shift_weekend_meeting_payload(payload)
    if weekend_shift is None:
        return None
    event.starts_at = shifted["starts_at"]
    event.ends_at = shifted["ends_at"]
    return weekend_shift


def is_google_meeting_stage(etapa):
    return bool(etapa and etapa.entry_type == MEETING_ENTRY_TYPE)


def can_manage_project_meeting(connection, meeting):
    if not connection or not meeting:
        return False
    account_id = (connection.google_account_id or "").strip()
    if not account_id:
        return False
    return account_id == (meeting.google_owner_account_id or "").strip()


def local_meeting_dates(meeting):
    start_local = to_local_datetime(meeting.starts_at) if meeting else None
    end_local = to_local_datetime(meeting.ends_at) if meeting else None
    return start_local, end_local


def meeting_time_summary(meeting):
    start_local, end_local = local_meeting_dates(meeting)
    if not start_local or not end_local:
        return "Sem horário"
    if meeting.is_all_day:
        return "Dia inteiro"
    if start_local.date() == end_local.date():
        return f'{start_local.strftime("%H:%M")} - {end_local.strftime("%H:%M")}'
    return f"{format_human_datetime(meeting.starts_at)} - {format_human_datetime(meeting.ends_at)}"


def meeting_time_display(meeting, *, boundary="start"):
    start_local, end_local = local_meeting_dates(meeting)
    local_value = start_local if boundary != "end" else end_local
    if not local_value:
        return ""
    if meeting.is_all_day:
        return "Dia inteiro"
    return local_value.strftime("%H:%M")


def sync_etapa_from_meeting(etapa, meeting, *, title=None):
    if not etapa or not meeting:
        return etapa

    start_local, end_local = local_meeting_dates(meeting)
    if title is not None:
        etapa.descricao = title
    etapa.data_inicio = start_local.date() if start_local else None
    etapa.data_fim = end_local.date() if end_local else None
    etapa.responsavel = meeting.google_owner_email or etapa.responsavel
    etapa.iniciada = False
    etapa.done = False
    etapa.entry_type = MEETING_ENTRY_TYPE
    return etapa


def update_meeting_from_calendar_event(meeting, event):
    if not meeting or not event:
        return meeting

    meeting.calendar_event_id = event.id
    meeting.google_event_id = event.google_event_id
    meeting.google_calendar_id = event.google_calendar_id
    meeting.starts_at = event.starts_at
    meeting.ends_at = event.ends_at
    meeting.is_all_day = bool(event.is_all_day)
    meeting.timezone = event.timezone or meeting.timezone
    meeting.description = event.description
    meeting.location = event.location
    meeting.meet_link = event.meet_link
    meeting.sync_status = event.sync_status
    meeting.sync_error = event.sync_error
    return meeting


def find_project_meeting_for_calendar_event(event, connection=None):
    if event is None:
        return None

    direct = ProjectStageMeeting.query.filter_by(calendar_event_id=event.id).first()
    if direct is not None:
        return direct

    google_event_id = (event.google_event_id or "").strip()
    if not google_event_id:
        return None

    query = ProjectStageMeeting.query.filter_by(google_event_id=google_event_id)
    if event.google_calendar_id:
        query = query.filter(
            ProjectStageMeeting.google_calendar_id == event.google_calendar_id
        )
    if connection is not None and connection.google_account_id:
        query = query.filter(
            ProjectStageMeeting.google_owner_account_id == connection.google_account_id
        )
    return query.first()


def mark_project_meeting_sync_error(meeting, *, message):
    if not meeting:
        return
    meeting.sync_status = "error"
    meeting.sync_error = message
    if meeting.etapa is not None:
        meeting.etapa.iniciada = False
        meeting.etapa.done = False


def sync_local_calendar_event_mirrors(meeting, *, title):
    if not meeting or not meeting.google_event_id:
        return

    mirror_events = CalendarEvent.query.filter(
        CalendarEvent.google_event_id == meeting.google_event_id,
        CalendarEvent.google_calendar_id == meeting.google_calendar_id,
    ).all()
    for event in mirror_events:
        event.title = title
        event.description = meeting.description
        event.location = meeting.location
        event.starts_at = meeting.starts_at
        event.ends_at = meeting.ends_at
        event.is_all_day = meeting.is_all_day
        event.timezone = meeting.timezone
        event.meet_link = meeting.meet_link
        event.sync_status = meeting.sync_status
        event.sync_error = meeting.sync_error


def delete_local_calendar_event_mirrors(meeting):
    if not meeting or not meeting.google_event_id:
        return

    mirror_events = CalendarEvent.query.filter(
        CalendarEvent.google_event_id == meeting.google_event_id,
        CalendarEvent.google_calendar_id == meeting.google_calendar_id,
    ).all()
    for event in mirror_events:
        db.session.delete(event)


def create_stage_meeting(app_config, project, connection, payload, *, actor_user_id):
    """Cria a etapa-reunião Google do projeto, reusando a MESMA lógica de
    ``add_project_meeting`` (cria ``CalendarEvent`` + ``Etapa`` + sync Google +
    ``ProjectStageMeeting`` espelhado). SEM commit/flash — o chamador decide.

    Args:
        app_config: ``current_app.config`` (passado para o sync Google).
        project: ``Project`` alvo.
        connection: ``UserCalendarConnection`` ativa.
        payload: dict de ``parse_event_form`` (title/description/.../create_conference).
        actor_user_id: ID do usuário criador.

    Returns:
        ``(etapa, sync_warning, weekend_shift_message)`` — ``sync_warning`` é
        ``None`` quando o sync com o Google foi bem-sucedido, ou a mensagem de
        erro quando falhou (o evento persiste local com ``sync_status='error'``,
        igual ao legado). ``weekend_shift_message`` é ``None`` exceto quando a
        data escolhida caiu num fim de semana e foi movida automaticamente.
    """
    # Import tardio evita ciclo project_meetings <-> etapas_dates (etapas_dates
    # reexporta símbolos deste módulo).
    from services.etapas_dates import _next_etapa_order

    payload, weekend_shift = _shift_weekend_meeting_payload(payload)

    event = CalendarEvent(
        user_id=actor_user_id,
        title=payload["title"],
        description=payload["description"],
        location=payload["location"],
        starts_at=payload["starts_at"],
        ends_at=payload["ends_at"],
        is_all_day=payload["is_all_day"],
        timezone="America/Sao_Paulo",
        source="app",
    )
    etapa = Etapa(
        descricao=payload["title"],
        project_id=project.id,
        ordem=_next_etapa_order(project.id),
        entry_type=MEETING_ENTRY_TYPE,
    )
    db.session.add_all([event, etapa])
    db.session.flush()

    sync_warning = None
    try:
        sync_local_event_to_google(
            app_config,
            event,
            connection,
            create_conference=payload["create_conference"],
        )
    except Exception as exc:
        event.sync_status = "error"
        event.sync_error = str(exc)
        sync_warning = str(exc)

    meeting = ProjectStageMeeting(
        etapa_id=etapa.id,
        project_id=project.id,
        calendar_event_id=event.id,
        creator_user_id=actor_user_id,
        google_owner_account_id=connection.google_account_id,
        google_owner_email=connection.google_account_email,
        google_event_id=event.google_event_id,
        google_calendar_id=event.google_calendar_id
        or connection.calendar_id
        or "primary",
        starts_at=event.starts_at,
        ends_at=event.ends_at,
        is_all_day=bool(event.is_all_day),
        timezone=event.timezone or "America/Sao_Paulo",
        description=event.description,
        location=event.location,
        meet_link=event.meet_link,
        sync_status=event.sync_status,
        sync_error=event.sync_error,
    )
    db.session.add(meeting)
    update_meeting_from_calendar_event(meeting, event)
    sync_etapa_from_meeting(etapa, meeting, title=event.title)
    sync_local_calendar_event_mirrors(meeting, title=event.title)
    return etapa, sync_warning, _weekend_shift_message(weekend_shift)


def update_stage_meeting(app_config, etapa, connection, payload):
    """Atualiza a etapa-reunião Google, reusando a MESMA lógica de
    ``edit_project_meeting`` (cria o ``CalendarEvent`` se ausente, aplica campos,
    sync Google, espelha meeting/etapa). SEM commit/flash.

    Args:
        app_config: ``current_app.config``.
        etapa: ``Etapa`` que é uma reunião Google editável.
        connection: ``UserCalendarConnection`` da mesma conta dona da reunião.
        payload: dict de ``parse_event_form``.

    Returns:
        ``(etapa, sync_warning, weekend_shift_message)`` — mesma semântica de
        ``create_stage_meeting``.
    """
    payload, weekend_shift = _shift_weekend_meeting_payload(payload)

    meeting = etapa.meeting
    event = meeting.calendar_event
    if event is None:
        event = CalendarEvent(
            user_id=meeting.creator_user_id,
            title=etapa.descricao,
            description=meeting.description,
            location=meeting.location,
            starts_at=meeting.starts_at,
            ends_at=meeting.ends_at,
            is_all_day=meeting.is_all_day,
            timezone=meeting.timezone or "America/Sao_Paulo",
            source="app",
            google_calendar_id=meeting.google_calendar_id,
            google_event_id=meeting.google_event_id,
            meet_link=meeting.meet_link,
            sync_status=meeting.sync_status,
            sync_error=meeting.sync_error,
        )
        db.session.add(event)
        db.session.flush()
        meeting.calendar_event_id = event.id

    event.title = payload["title"]
    event.description = payload["description"]
    event.location = payload["location"]
    event.starts_at = payload["starts_at"]
    event.ends_at = payload["ends_at"]
    event.is_all_day = payload["is_all_day"]
    event.timezone = meeting.timezone or event.timezone or "America/Sao_Paulo"
    event.source = "app"

    sync_warning = None
    try:
        sync_local_event_to_google(
            app_config,
            event,
            connection,
            create_conference=payload["create_conference"],
        )
    except Exception as exc:
        event.sync_status = "error"
        event.sync_error = str(exc)
        sync_warning = str(exc)

    update_meeting_from_calendar_event(meeting, event)
    sync_etapa_from_meeting(etapa, meeting, title=event.title)
    sync_local_calendar_event_mirrors(meeting, title=event.title)
    return etapa, sync_warning, _weekend_shift_message(weekend_shift)


def find_project_meeting_by_google_event(
    *, google_event_id, google_calendar_id=None, google_owner_account_id=None
):
    if not google_event_id:
        return None

    query = ProjectStageMeeting.query.filter_by(google_event_id=google_event_id)
    if google_calendar_id:
        query = query.filter(
            ProjectStageMeeting.google_calendar_id == google_calendar_id
        )
    if google_owner_account_id:
        query = query.filter(
            ProjectStageMeeting.google_owner_account_id == google_owner_account_id
        )
    return query.first()
