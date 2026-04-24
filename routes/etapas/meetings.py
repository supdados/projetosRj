from flask import current_app, flash, g, jsonify, redirect, request, url_for

from models import (
    CalendarEvent,
    Etapa,
    Project,
    ProjectStageMeeting,
    StageTemplate,
    StageTemplateUsage,
    db,
)
from services.calendar_core import parse_event_form
from services.calendar_sync import sync_local_event_to_google
from services.project_meetings import (
    MEETING_ENTRY_TYPE,
    can_manage_project_meeting,
    is_google_meeting_stage,
    meeting_time_display,
    meeting_time_summary,
    sync_etapa_from_meeting,
    sync_local_calendar_event_mirrors,
    update_meeting_from_calendar_event,
)

from routes.blueprint import main_bp
from routes.decorators import login_required
from routes.orgao_scope import user_can_access_project
from routes.shared import get_or_404, log_project_action
from routes.etapas.helpers import (
    _connection_for_current_user,
    _current_user_can_edit_project,
    _is_ajax_request,
    _next_etapa_order,
    _serialize_etapa_payload,
)


@main_bp.route("/project/<int:project_id>/meeting/add", methods=["POST"])
@login_required
def add_project_meeting(project_id):
    ajax_request = _is_ajax_request()
    project = get_or_404(Project, project_id)
    if not _current_user_can_edit_project(project):
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

    nova_ordem = _next_etapa_order(project.id)
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
    etapa = Etapa(
        descricao=payload["title"],
        project_id=project.id,
        ordem=nova_ordem,
        entry_type=MEETING_ENTRY_TYPE,
    )
    db.session.add_all([event, etapa])
    db.session.flush()

    sync_warning = None
    try:
        sync_local_event_to_google(
            current_app.config,
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
        creator_user_id=g.user.id,
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

    try:
        log_project_action(
            project_id=project.id,
            action_type="add_google_meeting",
            description=f'Adicionou a reunião "{event.title}"',
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
                "etapa": _serialize_etapa_payload(etapa, connection=connection),
            }
        )

    flash(success_message, "warning" if sync_warning else "success")
    if sync_warning:
        flash(sync_warning, "warning")
    return redirect(url_for("main.project_detail", project_id=project_id))


@main_bp.route("/etapa/<int:etapa_id>/meeting/edit", methods=["POST"])
@login_required
def edit_project_meeting(etapa_id):
    ajax_request = _is_ajax_request()
    etapa = get_or_404(Etapa, etapa_id)
    project = etapa.project

    if not is_google_meeting_stage(etapa) or etapa.meeting is None:
        message = "Esta etapa não é uma reunião Google editável."
        if ajax_request:
            return jsonify({"success": False, "message": message}), 400
        flash(message, "warning")
        return redirect(url_for("main.project_detail", project_id=project.id))

    if not _current_user_can_edit_project(project):
        message = "Você não tem permissão para editar reuniões deste projeto."
        if ajax_request:
            return jsonify({"success": False, "message": message}), 403
        flash(message, "danger")
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
            current_app.config,
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

    try:
        log_project_action(
            project_id=project.id,
            action_type="edit_google_meeting",
            description=f'Editou a reunião "{event.title}"',
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
                "etapa": _serialize_etapa_payload(etapa, connection=connection),
            }
        )

    flash(success_message, "warning" if sync_warning else "success")
    if sync_warning:
        flash(sync_warning, "warning")
    return redirect(url_for("main.project_detail", project_id=project.id))


@main_bp.route("/project/<int:project_id>/import_model", methods=["POST"])
@login_required
def import_model_to_project(project_id):
    """Importa etapas de um modelo para um projeto existente"""
    project = get_or_404(Project, project_id)

    # Verificar permissão
    if not user_can_access_project(g.user, project):
        flash("Você não tem permissão para importar modelos neste projeto.", "danger")
        return redirect(url_for("main.project_detail", project_id=project_id))

    template_id = request.form.get("template_id")
    start_date_str = request.form.get("start_date")

    if not template_id or not start_date_str:
        flash("Selecione um modelo e defina a data de início.", "warning")
        return redirect(url_for("main.project_detail", project_id=project_id))

    # Buscar o modelo
    template = get_or_404(StageTemplate, template_id)

    if not template.items:
        flash("Este modelo não possui etapas.", "warning")
        return redirect(url_for("main.project_detail", project_id=project_id))

    try:
        from datetime import datetime, timedelta

        # Converter data de início
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        current_date = start_date

        # Calcular a próxima ordem disponível
        ultima_etapa = (
            db.session.query(Etapa)
            .filter(Etapa.project_id == project.id)
            .order_by(Etapa.ordem.desc())
            .first()
        )
        ordem_inicial = (ultima_etapa.ordem + 1) if ultima_etapa else 0

        # Criar etapas baseadas no modelo
        etapas_criadas = 0
        for index, item in enumerate(template.items):
            # Calcular datas
            data_inicio = current_date
            data_fim = current_date + timedelta(days=item.duration_days - 1)

            # Criar etapa
            nova_etapa = Etapa(
                descricao=item.name,
                data_inicio=data_inicio,
                data_fim=data_fim,
                project_id=project.id,
                ordem=ordem_inicial + index,
                iniciada=False,
                done=False,
            )
            db.session.add(nova_etapa)
            etapas_criadas += 1

            # Próxima etapa começa no dia seguinte ao fim desta
            current_date = data_fim + timedelta(days=1)

        # Registrar no histórico
        log_project_action(
            project_id=project.id,
            action_type="import_model",
            description=f'Importou {etapas_criadas} etapa(s) do modelo "{template.name}"',
        )

        usage = StageTemplateUsage(
            template_id=template.id,
            project_id=project.id,
            created_by_id=g.user.id if g.user else None,
            source="post_import",
        )
        db.session.add(usage)

        db.session.commit()
        flash(
            f'{etapas_criadas} etapa(s) importada(s) com sucesso do modelo "{template.name}"!',
            "success",
        )

    except Exception as e:
        db.session.rollback()
        flash(f"Erro ao importar modelo: {str(e)}", "danger")

    return redirect(url_for("main.project_detail", project_id=project_id))
