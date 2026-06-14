from flask import current_app, flash, redirect, url_for

from models import db

from routes.blueprint import main_bp
from routes.decorators import login_required
import routes.calendars.helpers as _cal_helpers
from routes.calendars.helpers import (
    _auto_disconnect,
    _connection_for_current_user,
    _EXPIRED_TOKEN_CODES,
    _stop_watch_channel,
    _describe_calendar_issue,
    _format_human_datetime,
)


@main_bp.route("/calendarios/google/disconnect", methods=["POST"])
@login_required
def disconnect_google_calendar():
    connection = _connection_for_current_user()
    if connection is None:
        flash("Nenhuma conexão Google Calendar para desconectar.", "info")
        return redirect(url_for("main.calendars_hub"))

    try:
        _stop_watch_channel(connection, suppress_errors=True)
        db.session.delete(connection)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception(
            "Falha ao desconectar Google Calendar: %s", type(exc).__name__
        )
        flash(
            "Não foi possível desconectar o Google Calendar. Tente novamente.", "danger"
        )
        return redirect(url_for("main.calendars_hub"))

    flash("Conexão Google Calendar removida.", "success")
    return redirect(url_for("main.calendars_hub"))


@main_bp.route("/calendarios/google/sync", methods=["POST"])
@login_required
def sync_google_calendar_now():
    connection = _connection_for_current_user()
    if connection is None:
        flash("Conecte sua conta Google antes de sincronizar.", "warning")
        return redirect(url_for("main.calendars_hub"))

    try:
        summary = _cal_helpers._sync_events_from_google(connection)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        desc = _describe_calendar_issue(exc)
        if desc in _EXPIRED_TOKEN_CODES:
            try:
                _auto_disconnect(connection)
                db.session.commit()
            except Exception:
                db.session.rollback()
            flash(
                "Sua conexão com o Google Calendar expirou e foi removida. Conecte novamente para retomar a sincronização.",
                "warning",
            )
        else:
            current_app.logger.exception(
                "Falha ao sincronizar Google Calendar: %s", type(exc).__name__
            )
            flash(
                "Não foi possível sincronizar com o Google Calendar. Tente novamente.",
                "danger",
            )
        return redirect(url_for("main.calendars_hub"))

    flash(
        (
            "Sincronização concluída: "
            f"{summary['upserted']} atualizado(s), "
            f"{summary['deleted']} removido(s), "
            f"{summary['ignored']} ignorado(s)."
        ),
        "success",
    )
    return redirect(url_for("main.calendars_hub"))


@main_bp.route("/calendarios/google/watch/renew", methods=["POST"])
@login_required
def renew_google_calendar_watch():
    connection = _connection_for_current_user()
    if connection is None:
        flash("Conecte sua conta Google antes de renovar watch.", "warning")
        return redirect(url_for("main.calendars_hub"))

    try:
        watch_summary = _cal_helpers._renew_watch_channel(connection)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        flash(
            f"Erro ao renovar watch do Google Calendar: {_describe_calendar_issue(exc)}",
            "danger",
        )
        return redirect(url_for("main.calendars_hub"))

    if watch_summary.get("expires_at"):
        flash(
            f"Watch renovado até {_format_human_datetime(watch_summary['expires_at'])}.",
            "success",
        )
    else:
        flash(
            "Watch renovado (sem data de expiração retornada pelo Google).", "success"
        )
    return redirect(url_for("main.calendars_hub"))
