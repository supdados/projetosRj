from services.calendar_core import format_human_datetime, to_local_datetime
from models import CalendarEvent, ProjectStageMeeting, db


MEETING_ENTRY_TYPE = 'google_meeting'


def is_google_meeting_stage(etapa):
    return bool(etapa and etapa.entry_type == MEETING_ENTRY_TYPE)


def can_manage_project_meeting(connection, meeting):
    if not connection or not meeting:
        return False
    account_id = (connection.google_account_id or '').strip()
    if not account_id:
        return False
    return account_id == (meeting.google_owner_account_id or '').strip()


def local_meeting_dates(meeting):
    start_local = to_local_datetime(meeting.starts_at) if meeting else None
    end_local = to_local_datetime(meeting.ends_at) if meeting else None
    return start_local, end_local


def meeting_time_summary(meeting):
    start_local, end_local = local_meeting_dates(meeting)
    if not start_local or not end_local:
        return 'Sem horário'
    if meeting.is_all_day:
        return 'Dia inteiro'
    if start_local.date() == end_local.date():
        return f'{start_local.strftime("%H:%M")} - {end_local.strftime("%H:%M")}'
    return f'{format_human_datetime(meeting.starts_at)} - {format_human_datetime(meeting.ends_at)}'


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

    google_event_id = (event.google_event_id or '').strip()
    if not google_event_id:
        return None

    query = ProjectStageMeeting.query.filter_by(google_event_id=google_event_id)
    if event.google_calendar_id:
        query = query.filter(ProjectStageMeeting.google_calendar_id == event.google_calendar_id)
    if connection is not None and connection.google_account_id:
        query = query.filter(ProjectStageMeeting.google_owner_account_id == connection.google_account_id)
    return query.first()


def mark_project_meeting_sync_error(meeting, *, message):
    if not meeting:
        return
    meeting.sync_status = 'error'
    meeting.sync_error = message
    if meeting.etapa is not None:
        meeting.etapa.iniciada = False
        meeting.etapa.done = False


def sync_local_calendar_event_mirrors(meeting, *, title):
    if not meeting or not meeting.google_event_id:
        return

    mirror_events = (
        CalendarEvent.query
        .filter(
            CalendarEvent.google_event_id == meeting.google_event_id,
            CalendarEvent.google_calendar_id == meeting.google_calendar_id,
        )
        .all()
    )
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

    mirror_events = (
        CalendarEvent.query
        .filter(
            CalendarEvent.google_event_id == meeting.google_event_id,
            CalendarEvent.google_calendar_id == meeting.google_calendar_id,
        )
        .all()
    )
    for event in mirror_events:
        db.session.delete(event)


def find_project_meeting_by_google_event(*, google_event_id, google_calendar_id=None, google_owner_account_id=None):
    if not google_event_id:
        return None

    query = ProjectStageMeeting.query.filter_by(google_event_id=google_event_id)
    if google_calendar_id:
        query = query.filter(ProjectStageMeeting.google_calendar_id == google_calendar_id)
    if google_owner_account_id:
        query = query.filter(ProjectStageMeeting.google_owner_account_id == google_owner_account_id)
    return query.first()
