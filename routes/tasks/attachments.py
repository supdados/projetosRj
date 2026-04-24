import os
import uuid

from flask import g, jsonify, request, send_file, url_for
from werkzeug.utils import secure_filename

from models import (
    Task,
    TaskAnexo,
    db,
)
from services.notifications import notify_task_event

from routes.blueprint import main_bp
from routes.decorators import login_required
from routes.shared import format_local_time

import routes.tasks.helpers as _task_helpers
from routes.tasks.helpers import (
    _allowed_attachment,
    _can_view_task,
    _extension_of,
    _file_content_matches_extension,
    _preview_text,
)


@main_bp.route("/tarefas/<int:task_id>/anexos", methods=["GET"])
@login_required
def list_task_anexos(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        return jsonify({"success": False, "message": "Tarefa não encontrada"}), 404
    if not _can_view_task(g.user, task):
        return jsonify({"success": False, "message": "Sem permissão"}), 403

    return jsonify(
        {
            "success": True,
            "anexos": [
                {
                    "id": a.id,
                    "filename": a.filename,
                    "content_type": a.content_type or "",
                    "uploaded_by": a.uploaded_by.name,
                    "created_at": format_local_time(a.created_at),
                    "is_image": (a.content_type or "").startswith("image/"),
                    "url": url_for("main.view_task_item_anexo", anexo_id=a.id),
                }
                for a in task.anexos
            ],
            "count": len(task.anexos),
        }
    )


@main_bp.route("/tarefas/<int:task_id>/anexos/add", methods=["POST"])
@login_required
def add_task_anexo(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        return jsonify({"success": False, "message": "Tarefa não encontrada"}), 404
    if not _can_view_task(g.user, task):
        return jsonify({"success": False, "message": "Sem permissão"}), 403

    if "file" not in request.files:
        return jsonify({"success": False, "message": "Nenhum arquivo enviado."}), 400

    file = request.files["file"]
    if not file or not file.filename:
        return jsonify({"success": False, "message": "Arquivo inválido."}), 400

    if not _allowed_attachment(file.filename):
        return (
            jsonify({"success": False, "message": "Tipo de arquivo não permitido."}),
            400,
        )

    extension = _extension_of(file.filename)
    if not _file_content_matches_extension(file, extension):
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Conteúdo do arquivo não corresponde à extensão informada.",
                }
            ),
            400,
        )

    original_name = file.filename[:255]
    safe_name = secure_filename(file.filename)
    ext = safe_name.rsplit(".", 1)[1].lower() if "." in safe_name else ""
    stored_name = str(uuid.uuid4()) + ("." + ext if ext else "")
    content_type = file.content_type or "application/octet-stream"

    upload_folder = _task_helpers._get_upload_folder()
    file_path = os.path.join(upload_folder, stored_name)

    try:
        file.save(file_path)
    except Exception as e:
        return (
            jsonify({"success": False, "message": f"Erro ao salvar arquivo: {str(e)}"}),
            500,
        )

    anexo = TaskAnexo(
        task_id=task_id,
        filename=original_name,
        stored_filename=stored_name,
        content_type=content_type,
        uploaded_by_id=g.user.id,
    )

    try:
        db.session.add(anexo)
        db.session.flush()
        notify_task_event(
            task,
            actor_user_id=g.user.id,
            event_type="task_attachment_added",
            title="Novo anexo em tarefa",
            message=f'{g.user.name} anexou "{_preview_text(anexo.filename, 90)}" à tarefa "{_preview_text(task.descricao, 90)}".',
        )
        db.session.commit()
        return jsonify(
            {
                "success": True,
                "anexo": {
                    "id": anexo.id,
                    "filename": anexo.filename,
                    "content_type": content_type,
                    "uploaded_by": g.user.name,
                    "created_at": format_local_time(anexo.created_at),
                    "is_image": content_type.startswith("image/"),
                    "url": url_for("main.view_task_item_anexo", anexo_id=anexo.id),
                },
                "anexos_count": len(task.anexos),
            }
        )
    except Exception as e:
        db.session.rollback()
        try:
            os.remove(file_path)
        except OSError:
            pass
        return jsonify({"success": False, "message": str(e)}), 500


@main_bp.route("/tarefas/anexos/<int:anexo_id>", methods=["GET"])
@login_required
def view_task_item_anexo(anexo_id):
    anexo = db.session.get(TaskAnexo, anexo_id)
    if not anexo:
        return jsonify({"success": False, "message": "Anexo não encontrado."}), 404
    if not _can_view_task(g.user, anexo.task):
        return jsonify({"success": False, "message": "Sem permissão"}), 403

    upload_folder = _task_helpers._get_upload_folder()
    file_path = os.path.join(upload_folder, anexo.stored_filename)
    if not os.path.exists(file_path):
        return jsonify({"success": False, "message": "Arquivo não encontrado."}), 404

    return send_file(file_path, download_name=anexo.filename, as_attachment=False)


@main_bp.route("/tarefas/anexos/<int:anexo_id>/delete", methods=["POST"])
@login_required
def delete_task_item_anexo(anexo_id):
    anexo = db.session.get(TaskAnexo, anexo_id)
    if not anexo:
        return jsonify({"success": False, "message": "Anexo não encontrado."}), 404

    task = anexo.task
    if not _can_view_task(g.user, task):
        return jsonify({"success": False, "message": "Sem permissão"}), 403

    upload_folder = _task_helpers._get_upload_folder()
    file_path = os.path.join(upload_folder, anexo.stored_filename)

    try:
        notify_task_event(
            task,
            actor_user_id=g.user.id,
            event_type="task_attachment_deleted",
            title="Anexo removido em tarefa",
            message=f'{g.user.name} removeu o anexo "{_preview_text(anexo.filename, 90)}" da tarefa "{_preview_text(task.descricao, 90)}".',
        )
        db.session.delete(anexo)
        db.session.commit()
        try:
            os.remove(file_path)
        except OSError:
            pass
        return jsonify(
            {
                "success": True,
                "message": "Anexo excluído.",
                "anexos_count": len(task.anexos),
            }
        )
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
