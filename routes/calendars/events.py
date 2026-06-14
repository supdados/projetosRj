from flask import current_app, flash, g, jsonify, redirect, request, url_for

from models import CalendarEvent, db
from services.calendar_sync import delete_remote_event
from services.project_meetings import (
    can_manage_project_meeting,
    find_project_meeting_for_calendar_event,
)

from routes.blueprint import main_bp
from routes.decorators import login_required
import routes.calendars.helpers as _cal_helpers
from routes.calendars.helpers import (
    _event_json,
    _connection_for_current_user,
    _parse_event_form,
    _sync_project_meeting_from_calendar_event,
    _delete_project_meeting,
    _get_user_event_or_404,
    _user_can_edit_meeting_project,
)


def _wants_json():
    return "application/json" in request.headers.get("Accept", "")


@main_bp.route("/calendarios/eventos", methods=["POST"])
@login_required
def create_calendar_event():
    try:
        payload = _parse_event_form(request.form)
    except ValueError as exc:
        flash(str(exc), "warning")
        return redirect(url_for("main.calendars_hub"))

    event = CalendarEvent(
        user_id=g.user.id,
        title=payload["title"],
        description=payload["description"],
        location=payload["location"],
        starts_at=payload["starts_at"],
        ends_at=payload["ends_at"],
        is_all_day=payload["is_all_day"],
        timezone="America/Sao_Paulo",
        source="app",
    )
    db.session.add(event)

    connection = _connection_for_current_user()
    sync_warning = None
    if connection is not None:
        try:
            _cal_helpers._sync_local_event_to_google(
                event, connection, create_conference=payload["create_conference"]
            )
        except Exception as exc:
            event.sync_status = "error"
            event.sync_error = str(exc)
            sync_warning = str(exc)
    else:
        event.sync_status = "pending"
        event.sync_error = (
            "Evento salvo localmente. Conecte o Google Calendar para sincronizar."
        )

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception("Falha ao salvar evento: %s", type(exc).__name__)
        flash("Não foi possível salvar o evento. Tente novamente.", "danger")
        return redirect(url_for("main.calendars_hub"))

    if _wants_json():
        return jsonify({"ok": True, "event": _event_json(event)})

    if sync_warning:
        flash(
            "Evento salvo localmente, mas falhou ao enviar para Google Calendar.",
            "warning",
        )
        flash(sync_warning, "warning")
    elif connection is None:
        flash(
            "Evento salvo localmente. Conecte o Google Calendar para sincronizar.",
            "success",
        )
    else:
        flash("Evento salvo e sincronizado com Google Calendar.", "success")
    return redirect(url_for("main.calendars_hub"))


@main_bp.route("/calendarios/eventos/<int:event_id>/editar", methods=["POST"])
@login_required
def edit_calendar_event(event_id):
    event = _get_user_event_or_404(event_id)
    connection = _connection_for_current_user()
    linked_meeting = find_project_meeting_for_calendar_event(
        event, connection=connection
    )

    if linked_meeting is not None and not can_manage_project_meeting(
        connection, linked_meeting
    ):
        flash(
            "Somente quem estiver com a mesma conta Google conectada pode editar esta reunião.",
            "warning",
        )
        return redirect(url_for("main.calendars_hub"))
    if linked_meeting is not None and not _user_can_edit_meeting_project(
        g.user, linked_meeting
    ):
        flash("Permissão negada.", "warning")
        return redirect(url_for("main.calendars_hub"))

    try:
        payload = _parse_event_form(request.form)
    except ValueError as exc:
        flash(str(exc), "warning")
        return redirect(url_for("main.calendars_hub"))

    event.title = payload["title"]
    event.description = payload["description"]
    event.location = payload["location"]
    event.starts_at = payload["starts_at"]
    event.ends_at = payload["ends_at"]
    event.is_all_day = payload["is_all_day"]
    event.source = "app"

    sync_warning = None
    if connection is not None:
        try:
            _cal_helpers._sync_local_event_to_google(
                event, connection, create_conference=payload["create_conference"]
            )
        except Exception as exc:
            event.sync_status = "error"
            event.sync_error = str(exc)
            sync_warning = str(exc)
    else:
        event.sync_status = "pending"
        event.sync_error = (
            "Evento editado localmente. Conecte o Google Calendar para sincronizar."
        )

    if linked_meeting is not None:
        _sync_project_meeting_from_calendar_event(
            event, connection=connection, user=g.user
        )

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception(
            "Falha ao atualizar evento: %s", type(exc).__name__
        )
        flash("Não foi possível atualizar o evento. Tente novamente.", "danger")
        return redirect(url_for("main.calendars_hub"))

    if _wants_json():
        return jsonify({"ok": True, "event": _event_json(event)})

    if sync_warning:
        flash(
            "Evento atualizado localmente, mas falhou no sync com Google Calendar.",
            "warning",
        )
        flash(sync_warning, "warning")
    elif connection is None:
        flash("Evento atualizado localmente.", "success")
    else:
        flash("Evento atualizado e sincronizado com Google Calendar.", "success")
    return redirect(url_for("main.calendars_hub"))


@main_bp.route("/calendarios/eventos/<int:event_id>/gerar-meet", methods=["POST"])
@login_required
def generate_meet_link(event_id):
    event = _get_user_event_or_404(event_id)
    connection = _connection_for_current_user()
    if connection is None:
        flash("Conecte o Google Calendar para gerar um link do Meet.", "warning")
        return redirect(url_for("main.calendars_hub"))

    linked_meeting = find_project_meeting_for_calendar_event(
        event, connection=connection
    )
    if linked_meeting is not None and not can_manage_project_meeting(
        connection, linked_meeting
    ):
        flash(
            "Somente quem estiver com a mesma conta Google conectada pode gerar Meet para esta reunião.",
            "warning",
        )
        return redirect(url_for("main.calendars_hub"))
    if linked_meeting is not None and not _user_can_edit_meeting_project(
        g.user, linked_meeting
    ):
        flash("Permissão negada.", "warning")
        return redirect(url_for("main.calendars_hub"))

    try:
        _cal_helpers._sync_local_event_to_google(
            event, connection, create_conference=True
        )
        if linked_meeting is not None:
            _sync_project_meeting_from_calendar_event(
                event, connection=connection, user=g.user
            )
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception(
            "Falha ao gerar link do Meet: %s", type(exc).__name__
        )
        flash("Não foi possível gerar o link do Meet. Tente novamente.", "danger")
        return redirect(url_for("main.calendars_hub"))

    if _wants_json():
        return jsonify({"ok": True, "event": _event_json(event)})

    flash("Link do Google Meet gerado com sucesso.", "success")
    return redirect(url_for("main.calendars_hub"))


@main_bp.route("/calendarios/eventos/<int:event_id>/excluir", methods=["POST"])
@login_required
def delete_calendar_event(event_id):
    event = _get_user_event_or_404(event_id)
    connection = _connection_for_current_user()
    linked_meeting = find_project_meeting_for_calendar_event(
        event, connection=connection
    )
    if linked_meeting is not None and not can_manage_project_meeting(
        connection, linked_meeting
    ):
        flash(
            "Somente quem estiver com a mesma conta Google conectada pode excluir esta reunião.",
            "warning",
        )
        return redirect(url_for("main.calendars_hub"))
    if linked_meeting is not None and not _user_can_edit_meeting_project(
        g.user, linked_meeting
    ):
        flash("Permissão negada.", "warning")
        return redirect(url_for("main.calendars_hub"))

    remote_warning = None

    if connection is not None and event.google_event_id:
        try:
            delete_remote_event(
                current_app.config,
                connection,
                google_event_id=event.google_event_id,
                google_calendar_id=event.google_calendar_id,
            )
        except Exception as exc:
            remote_warning = str(exc)

    if linked_meeting is not None:
        if remote_warning:
            flash("Não foi possível remover a reunião no Google Calendar.", "warning")
            flash(remote_warning, "warning")
            return redirect(url_for("main.calendars_hub"))
        _delete_project_meeting(linked_meeting)
    else:
        db.session.delete(event)

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception("Falha ao excluir evento: %s", type(exc).__name__)
        flash("Não foi possível excluir o evento. Tente novamente.", "danger")
        return redirect(url_for("main.calendars_hub"))

    if remote_warning:
        flash(
            "Evento removido localmente, mas houve falha ao remover no Google Calendar.",
            "warning",
        )
        flash(remote_warning, "warning")
    else:
        flash("Evento removido com sucesso.", "success")
    return redirect(url_for("main.calendars_hub"))
