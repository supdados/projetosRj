import datetime

from flask import flash, g, jsonify, redirect, render_template, request, url_for

from models import Etapa, Project, db
from services.etapas_cascade import cascade_subsequent_dates
from services.etapas_mutation import (
    create_etapa_record,
    delete_meeting_etapa,
    delete_regular_etapa,
    save_etapa_comentario,
    update_meeting_dates,
    update_regular_field,
)
from services.project_meetings import (
    can_manage_project_meeting,
    is_google_meeting_stage,
)

from routes.blueprint import main_bp
from routes.decorators import login_required
from routes.orgao_scope import user_can_access_project
from routes.shared import get_or_404, log_project_action
from routes.etapas.helpers import (
    _connection_for_current_user,
    _current_user_can_edit_project,
    _is_ajax_request,
    _serialize_etapa_payload,
)


@main_bp.route("/project/<int:project_id>/etapa/add", methods=["POST"])
@login_required
def add_etapa(project_id):
    ajax_request = _is_ajax_request()
    project = get_or_404(Project, project_id)
    if not _current_user_can_edit_project(project):
        if ajax_request:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Você não tem permissão para adicionar etapas a este projeto.",
                    }
                ),
                403,
            )
        flash("Você não tem permissão para adicionar etapas a este projeto.", "danger")
        return redirect(url_for("main.project_detail", project_id=project_id))

    descricao = (request.form.get("etapa_descricao") or "").strip()
    if not descricao:
        if ajax_request:
            return (
                jsonify(
                    {"success": False, "message": "A descrição da etapa é obrigatória."}
                ),
                400,
            )
        flash("A descrição da etapa é obrigatória.", "warning")
        return redirect(url_for("main.project_detail", project_id=project_id))

    reactivate_project = (
        request.form.get("reactivate_project") or ""
    ).strip().lower() in {"1", "true", "on", "sim"}
    if project.status == "Finalizado" and not reactivate_project:
        message = "Ao adicionar uma nova etapa, o projeto voltará para o status Vigente. Deseja continuar?"
        if ajax_request:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": message,
                        "confirmation_required": True,
                        "project_status": project.status,
                    }
                ),
                409,
            )
        flash(message, "warning")
        return redirect(url_for("main.project_detail", project_id=project_id))

    data_inicio_str = request.form.get("etapa_data_inicio")
    data_fim_str = request.form.get("etapa_data_fim")
    responsavel = (request.form.get("etapa_responsavel") or "").strip() or None
    comentarios = (request.form.get("etapa_comentarios") or "").strip() or None
    etapa_iniciada = request.form.get("etapa_iniciada") == "on"
    etapa_concluida = request.form.get("etapa_done") == "on"
    validation_warning = None

    if not etapa_iniciada and etapa_concluida:
        validation_warning = (
            "Uma etapa não pode ser marcada como concluída sem ser iniciada."
        )
        if not ajax_request:
            flash(validation_warning, "warning")
        etapa_concluida = False

    try:
        data_inicio = (
            datetime.datetime.strptime(data_inicio_str, "%Y-%m-%d").date()
            if data_inicio_str
            else None
        )
        data_fim = (
            datetime.datetime.strptime(data_fim_str, "%Y-%m-%d").date()
            if data_fim_str
            else None
        )
    except ValueError:
        if ajax_request:
            return (
                jsonify({"success": False, "message": "Formato de data inválido."}),
                400,
            )
        flash("Formato de data inválido.", "warning")
        return redirect(url_for("main.project_detail", project_id=project_id))

    try:
        new_etapa, project_was_reactivated = create_etapa_record(
            project,
            descricao=descricao,
            data_inicio=data_inicio,
            data_fim=data_fim,
            responsavel=responsavel,
            comentarios=comentarios,
            iniciada=etapa_iniciada,
            done=etapa_concluida,
        )
        db.session.commit()

        success_message = "Etapa adicionada com sucesso!"
        if project_was_reactivated:
            success_message = (
                "Etapa adicionada com sucesso! O projeto voltou para Vigente."
            )

        if ajax_request:
            return jsonify(
                {
                    "success": True,
                    "message": success_message,
                    "warning": validation_warning,
                    "project_status": project.status,
                    "project_reactivated": project_was_reactivated,
                    "reload_page": project_was_reactivated,
                    "etapa": _serialize_etapa_payload(
                        new_etapa, connection=_connection_for_current_user()
                    ),
                }
            )
    except Exception:
        db.session.rollback()
        if ajax_request:
            return (
                jsonify({"success": False, "message": "Erro ao adicionar etapa."}),
                500,
            )
        flash("Erro ao adicionar etapa.", "danger")
        return redirect(url_for("main.project_detail", project_id=project_id))

    flash(success_message, "success")
    return redirect(url_for("main.project_detail", project_id=project_id))


@main_bp.route("/etapa/<int:etapa_id>/edit", methods=["GET", "POST"])
@login_required
def edit_etapa(etapa_id):
    etapa = get_or_404(Etapa, etapa_id)
    project_of_etapa = etapa.project
    if not _current_user_can_edit_project(project_of_etapa):
        flash("Você não tem permissão para editar etapas deste projeto.", "danger")
        return redirect(url_for("main.project_detail", project_id=project_of_etapa.id))

    if is_google_meeting_stage(etapa):
        flash(
            "Reuniões do Google devem ser editadas pelo fluxo de calendário ou pelo ajuste rápido de datas.",
            "warning",
        )
        return redirect(url_for("main.project_detail", project_id=project_of_etapa.id))

    if request.method == "POST":
        old_descricao = etapa.descricao
        etapa.descricao = request.form.get("etapa_descricao")
        etapa.responsavel = request.form.get("etapa_responsavel")
        etapa.comentarios = request.form.get("etapa_comentarios")
        etapa.iniciada = request.form.get("etapa_iniciada") == "on"
        etapa_done_form = request.form.get("etapa_done") == "on"

        if not etapa.iniciada and etapa_done_form:
            flash(
                "A etapa não pode ser marcada como concluída pois não foi iniciada.",
                "warning",
            )
            etapa.done = False
        else:
            etapa.done = etapa_done_form

        data_inicio_str = request.form.get("etapa_data_inicio")
        etapa.data_inicio = (
            datetime.datetime.strptime(data_inicio_str, "%Y-%m-%d").date()
            if data_inicio_str
            else None
        )
        data_fim_str = request.form.get("etapa_data_fim")
        etapa.data_fim = (
            datetime.datetime.strptime(data_fim_str, "%Y-%m-%d").date()
            if data_fim_str
            else None
        )

        log_project_action(
            project_id=etapa.project_id,
            action_type="edit_etapa",
            description=f'Editou a etapa "{old_descricao}"',
        )

        db.session.commit()
        flash("Etapa atualizada com sucesso!", "success")
        return redirect(url_for("main.project_detail", project_id=etapa.project_id))

    data_inicio_f = etapa.data_inicio.strftime("%Y-%m-%d") if etapa.data_inicio else ""
    data_fim_f = etapa.data_fim.strftime("%Y-%m-%d") if etapa.data_fim else ""
    return render_template(
        "etapas/form.html",
        etapa=etapa,
        action=url_for("main.edit_etapa", etapa_id=etapa_id),
        data_inicio_form=data_inicio_f,
        data_fim_form=data_fim_f,
    )


@main_bp.route("/etapa/<int:etapa_id>/delete", methods=["POST"])
@login_required
def delete_etapa(etapa_id):
    ajax_request = _is_ajax_request()
    etapa_to_delete = get_or_404(Etapa, etapa_id)
    project_of_etapa = etapa_to_delete.project
    project_id_for_redirect = etapa_to_delete.project_id

    if not _current_user_can_edit_project(project_of_etapa):
        message = "Você não tem permissão para excluir etapas deste projeto."
        if ajax_request:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": message,
                        "etapa_id": etapa_id,
                        "project_id": project_id_for_redirect,
                    }
                ),
                403,
            )
        flash(message, "danger")
        return redirect(url_for("main.project_detail", project_id=project_of_etapa.id))

    # ── Exclusão de reunião Google ──
    meeting = (
        etapa_to_delete.meeting if is_google_meeting_stage(etapa_to_delete) else None
    )
    if meeting is not None:
        connection = _connection_for_current_user()
        if not can_manage_project_meeting(connection, meeting):
            message = "Somente quem estiver com a mesma conta Google conectada pode excluir esta reunião."
            if ajax_request:
                return (
                    jsonify(
                        {"success": False, "message": message, "etapa_id": etapa_id}
                    ),
                    403,
                )
            flash(message, "warning")
            return redirect(
                url_for("main.project_detail", project_id=project_id_for_redirect)
            )

        try:
            remote_warning = delete_meeting_etapa(etapa_to_delete, connection)
            if remote_warning:
                if ajax_request:
                    return (
                        jsonify(
                            {
                                "success": False,
                                "message": remote_warning,
                                "etapa_id": etapa_id,
                            }
                        ),
                        502,
                    )
                flash(remote_warning, "warning")
                return redirect(
                    url_for("main.project_detail", project_id=project_id_for_redirect)
                )
            db.session.commit()
        except Exception:
            db.session.rollback()
            if ajax_request:
                return (
                    jsonify(
                        {
                            "success": False,
                            "message": "Erro ao excluir reunião.",
                            "etapa_id": etapa_id,
                        }
                    ),
                    500,
                )
            flash("Erro ao excluir reunião.", "danger")
            return redirect(
                url_for("main.project_detail", project_id=project_id_for_redirect)
            )

        if ajax_request:
            project = db.session.get(Project, project_id_for_redirect)
            total_etapas = project.total_workflow_etapas if project is not None else 0
            return jsonify(
                {
                    "success": True,
                    "message": "Reunião excluída com sucesso.",
                    "etapa_id": etapa_id,
                    "project_id": project_id_for_redirect,
                    "total_etapas": total_etapas,
                }
            )
        flash("Reunião excluída com sucesso.", "success")
        return redirect(
            url_for("main.project_detail", project_id=project_id_for_redirect)
        )

    # ── Exclusão de etapa normal ──
    try:
        delete_regular_etapa(etapa_to_delete)
        db.session.commit()
    except Exception:
        db.session.rollback()
        if ajax_request:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Erro ao excluir etapa.",
                        "etapa_id": etapa_id,
                        "project_id": project_id_for_redirect,
                    }
                ),
                500,
            )
        flash("Erro ao excluir etapa.", "danger")
        return redirect(
            url_for("main.project_detail", project_id=project_id_for_redirect)
        )

    if ajax_request:
        project = db.session.get(Project, project_id_for_redirect)
        total_etapas = project.total_workflow_etapas if project is not None else 0
        return jsonify(
            {
                "success": True,
                "message": "Etapa excluída com sucesso.",
                "etapa_id": etapa_id,
                "project_id": project_id_for_redirect,
                "total_etapas": total_etapas,
            }
        )
    flash("Etapa excluída com sucesso.", "success")
    return redirect(url_for("main.project_detail", project_id=project_id_for_redirect))


@main_bp.route("/project/<int:project_id>/etapas/reordenar", methods=["POST"])
@login_required
def reorder_etapas(project_id):
    project = get_or_404(Project, project_id)
    if not user_can_access_project(g.user, project):
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Você não tem permissão para reordenar etapas deste projeto.",
                }
            ),
            403,
        )

    data = request.get_json() or {}
    etapa_ids_ordenadas = data.get("etapa_ids")

    if not etapa_ids_ordenadas or not isinstance(etapa_ids_ordenadas, list):
        return (
            jsonify({"success": False, "message": "Lista de IDs de etapas inválida."}),
            400,
        )

    try:
        for index, eid in enumerate(etapa_ids_ordenadas):
            etapa = Etapa.query.filter_by(id=eid, project_id=project.id).first()
            if etapa:
                etapa.ordem = index

        db.session.commit()
        return jsonify({"success": True, "message": "Ordem das etapas atualizada."})
    except Exception:
        db.session.rollback()
        return (
            jsonify(
                {"success": False, "message": "Erro ao atualizar a ordem das etapas."}
            ),
            500,
        )


@main_bp.route("/etapa/<int:etapa_id>/toggle_iniciada", methods=["POST"])
@login_required
def toggle_iniciada_etapa(etapa_id):
    etapa = get_or_404(Etapa, etapa_id)
    project_of_etapa = etapa.project
    if not _current_user_can_edit_project(project_of_etapa):
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Permissão negada para alterar esta etapa.",
                }
            ),
            403,
        )
    if is_google_meeting_stage(etapa):
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Reuniões Google não participam do fluxo de início/conclusão.",
                }
            ),
            400,
        )

    etapa.iniciada = not etapa.iniciada
    ajax_flash_message = None

    status_text = "iniciada" if etapa.iniciada else "não iniciada"
    log_project_action(
        project_id=etapa.project_id,
        action_type="toggle_iniciada",
        description=f'Marcou a etapa "{etapa.descricao}" como {status_text}',
    )

    if not etapa.iniciada and etapa.done:
        etapa.done = False
        ajax_flash_message = (
            "Etapa marcada como não iniciada e, consequentemente, como não concluída."
        )
    db.session.commit()
    return jsonify(
        {
            "success": True,
            "etapa_id": etapa.id,
            "iniciada": etapa.iniciada,
            "done": etapa.done,
            "message": ajax_flash_message,
        }
    )


@main_bp.route("/etapa/<int:etapa_id>/toggle", methods=["POST"])
@login_required
def toggle_etapa(etapa_id):
    etapa = get_or_404(Etapa, etapa_id)
    project_of_etapa = etapa.project
    if not _current_user_can_edit_project(project_of_etapa):
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Permissão negada para alterar esta etapa.",
                }
            ),
            403,
        )
    if is_google_meeting_stage(etapa):
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Reuniões Google não participam do fluxo de início/conclusão.",
                }
            ),
            400,
        )

    if not etapa.iniciada and not etapa.done:
        return jsonify(
            {
                "success": False,
                "etapa_id": etapa.id,
                "iniciada": etapa.iniciada,
                "done": etapa.done,
                "message": "Não é possível concluir uma etapa que não foi iniciada.",
            }
        )

    etapa.done = not etapa.done

    status_text = "concluída" if etapa.done else "não concluída"
    log_project_action(
        project_id=etapa.project_id,
        action_type="toggle_done",
        description=f'Marcou a etapa "{etapa.descricao}" como {status_text}',
    )

    db.session.commit()
    return jsonify(
        {
            "success": True,
            "etapa_id": etapa.id,
            "iniciada": etapa.iniciada,
            "done": etapa.done,
            "message": None,
        }
    )


@main_bp.route("/etapa/<int:etapa_id>/update_field", methods=["POST"])
@login_required
def update_etapa_field(etapa_id):
    etapa = get_or_404(Etapa, etapa_id)
    project_of_etapa = etapa.project

    if not _current_user_can_edit_project(project_of_etapa):
        return jsonify({"success": False, "message": "Permissão negada."}), 403

    data = request.get_json()
    field = data.get("field")
    value = data.get("value")

    # ── Reunião Google: somente datas ──
    if is_google_meeting_stage(etapa):
        meeting = etapa.meeting
        connection = _connection_for_current_user()
        if field not in ["data_inicio", "data_fim"]:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Nesta reunião só é permitido ajustar as datas.",
                    }
                ),
                400,
            )
        if meeting is None or not can_manage_project_meeting(connection, meeting):
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Somente a mesma conta Google conectada pode editar esta reunião.",
                    }
                ),
                403,
            )
        if meeting.sync_status == "error":
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Esta reunião está somente leitura porque o evento não está mais disponível no Google Calendar.",
                    }
                ),
                409,
            )

        try:
            new_date = (
                datetime.datetime.strptime(value, "%Y-%m-%d").date() if value else None
            )
        except ValueError:
            return (
                jsonify({"success": False, "message": "Formato de data inválido."}),
                400,
            )
        if new_date is None:
            return (
                jsonify(
                    {"success": False, "message": "A data da reunião é obrigatória."}
                ),
                400,
            )

        try:
            response_data = update_meeting_dates(etapa, field, new_date, connection)
            db.session.commit()
        except ValueError as exc:
            return jsonify({"success": False, "message": str(exc)}), 400
        except Exception:
            db.session.rollback()
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Erro ao salvar a alteração da reunião.",
                    }
                ),
                500,
            )
        return jsonify(response_data)

    # ── Campo regular ──
    if field not in ["descricao", "data_inicio", "data_fim", "responsavel"]:
        return jsonify({"success": False, "message": "Campo inválido."}), 400

    try:
        response_data = update_regular_field(etapa, field, value)
        db.session.commit()
        return jsonify(response_data)
    except Exception:
        db.session.rollback()
        return (
            jsonify({"success": False, "message": "Erro ao salvar a alteração."}),
            500,
        )


@main_bp.route("/etapa/<int:etapa_id>/comentario", methods=["POST"])
@login_required
def update_etapa_comentario(etapa_id):
    etapa = get_or_404(Etapa, etapa_id)
    project_of_etapa = etapa.project

    if not _current_user_can_edit_project(project_of_etapa):
        return jsonify({"success": False, "message": "Permissão negada."}), 403
    if is_google_meeting_stage(etapa):
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Reuniões Google não aceitam comentários de etapa.",
                }
            ),
            400,
        )
    if etapa.done:
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Não é possível editar comentários de uma etapa concluída.",
                }
            ),
            403,
        )

    data = request.get_json()
    comentario = data.get("comentario", "").strip()

    try:
        message = save_etapa_comentario(etapa, comentario)
        db.session.commit()
        return jsonify({"success": True, "message": message})
    except Exception:
        db.session.rollback()
        return jsonify({"success": False, "message": "Erro ao salvar comentário."}), 500


@main_bp.route("/project/<int:project_id>/cascade_update", methods=["POST"])
@login_required
def cascade_date_update(project_id):
    project = get_or_404(Project, project_id)
    if not _current_user_can_edit_project(project):
        return jsonify({"success": False, "message": "Permissão negada."}), 403

    data = request.get_json() or {}
    base_etapa_id = data.get("etapa_id")
    days_to_add = data.get("days_diff")

    if not all([base_etapa_id, days_to_add is not None]):
        return jsonify({"success": False, "message": "Parâmetros inválidos."}), 400

    try:
        days_to_add = int(days_to_add)
    except (TypeError, ValueError):
        return (
            jsonify({"success": False, "message": "Parâmetro de dias inválido."}),
            400,
        )

    try:
        base_etapa = db.session.get(Etapa, base_etapa_id)
        if not base_etapa or base_etapa.project_id != project_id:
            return (
                jsonify({"success": False, "message": "Etapa base não encontrada."}),
                404,
            )
        if is_google_meeting_stage(base_etapa):
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Reuniões Google não participam da cascata de datas.",
                    }
                ),
                400,
            )

        cascade_subsequent_dates(project_id, base_etapa.ordem, days_to_add)
        db.session.commit()
        return jsonify(
            {"success": True, "message": "Datas subsequentes atualizadas com sucesso."}
        )
    except Exception:
        db.session.rollback()
        return (
            jsonify(
                {"success": False, "message": "Erro ao atualizar datas subsequentes."}
            ),
            500,
        )
