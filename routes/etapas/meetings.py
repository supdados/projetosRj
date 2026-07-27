from flask import current_app, flash, g, jsonify, redirect, request, url_for

from models import (
    StageTemplate,
    db,
)
from services.calendar_core import parse_event_form
from services.etapas_import import import_template_stages
from services.project_meetings import (
    can_manage_project_meeting,
    create_stage_meeting,
    is_google_meeting_stage,
    update_stage_meeting,
)

from routes.blueprint import main_bp
from routes.decorators import login_required
from routes.shared import get_or_404, log_project_action
from routes.etapas.helpers import (
    _connection_for_current_user,
    _is_ajax_request,
    _legacy_not_found,
    _load_etapa_for_write,
    _load_project_for_etapa_write,
    _serialize_etapa_payload,
)
from services.authorization import ACCESS_FORBIDDEN, ACCESS_NOT_FOUND


@main_bp.route("/project/<int:project_id>/meeting/add", methods=["POST"])
@login_required
def add_project_meeting(project_id):
    ajax_request = _is_ajax_request()
    project, verdict = _load_project_for_etapa_write(project_id)
    if verdict == ACCESS_NOT_FOUND:
        return _legacy_not_found()
    if verdict == ACCESS_FORBIDDEN:
        message = "Você não tem permissão para adicionar reuniões a este projeto."
        if ajax_request:
            return jsonify({"success": False, "message": message}), 403
        flash(message, "danger")
        return redirect(url_for("main.project_detail", project_id=project_id))

    connection = _connection_for_current_user()
    if connection is None or not (connection.google_account_id or "").strip():
        message = (
            "Conecte novamente sua conta Google antes de adicionar reuniões ao projeto."
        )
        if ajax_request:
            return jsonify({"success": False, "message": message}), 400
        flash(message, "warning")
        return redirect(url_for("main.project_detail", project_id=project_id))

    try:
        payload = parse_event_form(request.form)
    except ValueError as exc:
        if ajax_request:
            return jsonify({"success": False, "message": str(exc)}), 400
        flash(str(exc), "warning")
        return redirect(url_for("main.project_detail", project_id=project_id))

    etapa, sync_warning, weekend_shift_message = create_stage_meeting(
        current_app.config,
        project,
        connection,
        payload,
        actor_user_id=g.user.id,
    )

    try:
        log_project_action(
            project_id=project.id,
            action_type="add_google_meeting",
            description=f'Adicionou a reunião "{etapa.descricao}"',
        )
        if weekend_shift_message:
            log_project_action(
                project_id=project.id,
                action_type="google_meeting_weekend_shift",
                description=weekend_shift_message,
            )
        db.session.commit()
    except Exception:
        db.session.rollback()
        message = "Erro ao adicionar reunião ao projeto."
        if ajax_request:
            return jsonify({"success": False, "message": message}), 500
        flash(message, "danger")
        return redirect(url_for("main.project_detail", project_id=project_id))

    success_message = "Reunião adicionada ao projeto com sucesso!"
    if sync_warning:
        success_message = "Reunião adicionada ao projeto, mas houve falha na sincronização com o Google Calendar."

    if ajax_request:
        return jsonify(
            {
                "success": True,
                "message": success_message,
                "warning": sync_warning,
                "weekend_shift_message": weekend_shift_message,
                "etapa": _serialize_etapa_payload(etapa, connection=connection),
            }
        )

    flash(success_message, "warning" if sync_warning else "success")
    if sync_warning:
        flash(sync_warning, "warning")
    if weekend_shift_message:
        flash(weekend_shift_message, "warning")
    return redirect(url_for("main.project_detail", project_id=project_id))


@main_bp.route("/etapa/<int:etapa_id>/meeting/edit", methods=["POST"])
@login_required
def edit_project_meeting(etapa_id):
    ajax_request = _is_ajax_request()
    etapa, verdict = _load_etapa_for_write(etapa_id)
    if verdict == ACCESS_NOT_FOUND:
        return _legacy_not_found()
    project = etapa.project

    if verdict == ACCESS_FORBIDDEN:
        message = "Você não tem permissão para editar reuniões deste projeto."
        if ajax_request:
            return jsonify({"success": False, "message": message}), 403
        flash(message, "danger")
        return redirect(url_for("main.project_detail", project_id=project.id))

    if not is_google_meeting_stage(etapa) or etapa.meeting is None:
        message = "Esta etapa não é uma reunião Google editável."
        if ajax_request:
            return jsonify({"success": False, "message": message}), 400
        flash(message, "warning")
        return redirect(url_for("main.project_detail", project_id=project.id))

    meeting = etapa.meeting
    connection = _connection_for_current_user()
    if not can_manage_project_meeting(connection, meeting):
        message = "Somente quem estiver com a mesma conta Google conectada pode editar esta reunião."
        if ajax_request:
            return jsonify({"success": False, "message": message}), 403
        flash(message, "warning")
        return redirect(url_for("main.project_detail", project_id=project.id))

    if meeting.sync_status == "error":
        message = "Esta reunião está somente leitura porque o evento não está mais disponível no Google Calendar."
        if ajax_request:
            return jsonify({"success": False, "message": message}), 409
        flash(message, "warning")
        return redirect(url_for("main.project_detail", project_id=project.id))

    try:
        payload = parse_event_form(request.form)
    except ValueError as exc:
        if ajax_request:
            return jsonify({"success": False, "message": str(exc)}), 400
        flash(str(exc), "warning")
        return redirect(url_for("main.project_detail", project_id=project.id))

    etapa, sync_warning, weekend_shift_message = update_stage_meeting(
        current_app.config, etapa, connection, payload
    )

    try:
        log_project_action(
            project_id=project.id,
            action_type="edit_google_meeting",
            description=f'Editou a reunião "{etapa.descricao}"',
        )
        if weekend_shift_message:
            log_project_action(
                project_id=project.id,
                action_type="google_meeting_weekend_shift",
                description=weekend_shift_message,
            )
        db.session.commit()
    except Exception:
        db.session.rollback()
        message = "Erro ao salvar a reunião."
        if ajax_request:
            return jsonify({"success": False, "message": message}), 500
        flash(message, "danger")
        return redirect(url_for("main.project_detail", project_id=project.id))

    success_message = "Reunião atualizada com sucesso!"
    if sync_warning:
        success_message = "Reunião atualizada, mas houve falha na sincronização com o Google Calendar."

    if ajax_request:
        return jsonify(
            {
                "success": True,
                "message": success_message,
                "warning": sync_warning,
                "weekend_shift_message": weekend_shift_message,
                "etapa": _serialize_etapa_payload(etapa, connection=connection),
            }
        )

    flash(success_message, "warning" if sync_warning else "success")
    if sync_warning:
        flash(sync_warning, "warning")
    if weekend_shift_message:
        flash(weekend_shift_message, "warning")
    return redirect(url_for("main.project_detail", project_id=project.id))


@main_bp.route("/project/<int:project_id>/import_model", methods=["POST"])
@login_required
def import_model_to_project(project_id):
    """Importa etapas de um modelo para um projeto existente"""
    project, verdict = _load_project_for_etapa_write(project_id)
    if verdict == ACCESS_NOT_FOUND:
        return _legacy_not_found()
    if verdict == ACCESS_FORBIDDEN:
        flash("Você não tem permissão para importar modelos neste projeto.", "danger")
        return redirect(url_for("main.project_detail", project_id=project_id))

    template_id = request.form.get("template_id")
    start_date_str = request.form.get("start_date")

    if not template_id or not start_date_str:
        flash("Selecione um modelo e defina a data de início.", "warning")
        return redirect(url_for("main.project_detail", project_id=project_id))

    template = get_or_404(StageTemplate, template_id)

    if not template.items:
        flash("Este modelo não possui etapas.", "warning")
        return redirect(url_for("main.project_detail", project_id=project_id))

    try:
        from datetime import datetime

        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()

        etapas_criadas = import_template_stages(
            project,
            template,
            start_date,
            created_by_id=g.user.id if g.user else None,
            source="post_import",
        )

        db.session.commit()
        flash(
            f'{etapas_criadas} etapa(s) importada(s) com sucesso do modelo "{template.name}"!',
            "success",
        )

    except Exception as e:
        db.session.rollback()
        current_app.logger.exception(
            "Falha ao importar modelo de etapas: %s", type(e).__name__
        )
        flash("Não foi possível importar o modelo. Tente novamente.", "danger")

    return redirect(url_for("main.project_detail", project_id=project_id))
