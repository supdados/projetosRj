from flask import flash, g, jsonify, redirect, request, url_for

from models import (
    Task,
    TaskComment,
    db,
)
from services.notifications import notify_task_event
from time_utils import utc_now

from routes.blueprint import main_bp
from routes.decorators import login_required
from routes.shared import format_local_time

from routes.tasks.helpers import (
    _can_view_task,
    _preview_text,
)


@main_bp.route("/tarefas/<int:task_id>/comentarios/add", methods=["POST"])
@login_required
def add_task_comment(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        return jsonify({"success": False, "message": "Tarefa não encontrada"}), 404

    is_ajax = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.accept_mimetypes.best == "application/json"
    )

    if not _can_view_task(g.user, task):
        if is_ajax:
            return (
                jsonify({"success": False, "message": "Sem permissão para comentar."}),
                403,
            )
        flash("Você não tem permissão para comentar nesta tarefa.", "danger")
        return redirect(url_for("main.list_tasks"))

    content = request.form.get("content", "").strip()
    if not content:
        if is_ajax:
            return (
                jsonify(
                    {"success": False, "message": "O comentário não pode estar vazio."}
                ),
                400,
            )
        flash("O comentário não pode estar vazio.", "warning")
        return redirect(url_for("main.list_tasks"))

    comment = TaskComment(content=content, user_id=g.user.id, task_id=task_id)

    try:
        db.session.add(comment)
        db.session.flush()
        notify_task_event(
            task,
            actor_user_id=g.user.id,
            event_type="task_comment_added",
            title="Novo comentário em tarefa",
            message=f'{g.user.name} comentou: "{_preview_text(comment.content, 120)}".',
        )
        db.session.commit()

        if is_ajax:
            return jsonify(
                {
                    "success": True,
                    "comment": {
                        "id": comment.id,
                        "content": comment.content,
                        "author_name": g.user.name,
                        "user_id": g.user.id,
                        "created_at": format_local_time(comment.created_at),
                        "is_own": True,
                    },
                }
            )

        flash("Comentário adicionado.", "success")
        return redirect(url_for("main.list_tasks"))
    except Exception as e:
        db.session.rollback()
        if is_ajax:
            return jsonify({"success": False, "message": str(e)}), 500
        flash(f"Erro ao adicionar comentário: {str(e)}", "danger")
        return redirect(url_for("main.list_tasks"))


@main_bp.route("/tarefas/comentarios/<int:comment_id>/edit", methods=["POST"])
@login_required
def edit_task_item_comment(comment_id):
    comment = db.session.get(TaskComment, comment_id)
    if not comment:
        return jsonify({"success": False, "message": "Comentário não encontrado."}), 404

    is_ajax = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.accept_mimetypes.best == "application/json"
    )

    if comment.user_id != g.user.id:
        if is_ajax:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Você só pode editar seus próprios comentários.",
                    }
                ),
                403,
            )
        flash("Você só pode editar seus próprios comentários.", "danger")
        return redirect(url_for("main.list_tasks"))

    content = request.form.get("content", "").strip()
    if not content:
        if is_ajax:
            return (
                jsonify(
                    {"success": False, "message": "O comentário não pode estar vazio."}
                ),
                400,
            )
        flash("O comentário não pode estar vazio.", "warning")
        return redirect(url_for("main.list_tasks"))

    old_content = comment.content
    comment.content = content
    comment.updated_at = utc_now()

    try:
        notify_task_event(
            comment.task,
            actor_user_id=g.user.id,
            event_type="task_comment_updated",
            title="Comentário atualizado em tarefa",
            message=(
                f'{g.user.name} editou um comentário na tarefa "{_preview_text(comment.task.descricao, 90)}": '
                f'"{_preview_text(old_content, 70)}" -> "{_preview_text(comment.content, 70)}".'
            ),
        )
        db.session.commit()

        if is_ajax:
            return jsonify(
                {
                    "success": True,
                    "comment": {
                        "id": comment.id,
                        "content": comment.content,
                        "updated_at": (
                            format_local_time(comment.updated_at)
                            if comment.updated_at
                            else None
                        ),
                    },
                }
            )

        flash("Comentário atualizado.", "success")
        return redirect(url_for("main.list_tasks"))
    except Exception as e:
        db.session.rollback()
        if is_ajax:
            return jsonify({"success": False, "message": str(e)}), 500
        flash(f"Erro ao atualizar comentário: {str(e)}", "danger")
        return redirect(url_for("main.list_tasks"))


@main_bp.route("/tarefas/comentarios/<int:comment_id>/delete", methods=["POST"])
@login_required
def delete_task_item_comment(comment_id):
    comment = db.session.get(TaskComment, comment_id)
    if not comment:
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Comentário não encontrado.",
                    "comment_id": comment_id,
                }
            ),
            404,
        )

    is_ajax = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.accept_mimetypes.best == "application/json"
    )

    if comment.user_id != g.user.id:
        message = "Você só pode excluir seus próprios comentários."
        if is_ajax:
            return (
                jsonify(
                    {"success": False, "message": message, "comment_id": comment_id}
                ),
                403,
            )
        flash(message, "danger")
        return redirect(url_for("main.list_tasks"))

    try:
        notify_task_event(
            comment.task,
            actor_user_id=g.user.id,
            event_type="task_comment_deleted",
            title="Comentário removido em tarefa",
            message=f'{g.user.name} removeu um comentário na tarefa "{_preview_text(comment.task.descricao, 90)}".',
        )
        db.session.delete(comment)
        db.session.commit()

        if is_ajax:
            return jsonify(
                {
                    "success": True,
                    "message": "Comentário excluído.",
                    "comment_id": comment_id,
                }
            )

        flash("Comentário excluído.", "success")
        return redirect(url_for("main.list_tasks"))
    except Exception as e:
        db.session.rollback()
        if is_ajax:
            return (
                jsonify(
                    {"success": False, "message": str(e), "comment_id": comment_id}
                ),
                500,
            )
        flash(f"Erro ao excluir comentário: {str(e)}", "danger")
        return redirect(url_for("main.list_tasks"))
