"""Endpoints JSON/binário de ANEXOS do DRAWER de Tarefa (Fase 5b-2) para a SPA.

O drawer lista/sobe/baixa/exclui anexos de UMA tarefa. Os endpoints de
listar/upload/excluir respondem no envelope canônico (``ok``/``fail``); o
DOWNLOAD é BINÁRIO (``send_file``) e NÃO é envelopado — o front abre via link /
nova aba (mesma origin, cookie de sessão).

Endpoints (anexados ao ``main_bp`` ÚNICO; ADITIVO — NÃO altera as rotas Jinja
legadas em ``routes/tasks/attachments.py`` nem o JS legado):

    - ``GET  /api/tarefas/<id>/anexos``    — lista anexos da tarefa.
    - ``POST /api/tarefas/<id>/anexos``    — UPLOAD via ``request.files["file"]``
      (multipart), rank >= editor (``_can_edit_task``, S3/F2-5). Valida
      tipo/conteúdo (reusa os helpers legados) e o limite de tamanho
      (``MAX_CONTENT_LENGTH`` = 10MB, ``config.py:65``): excesso => 413.
    - ``GET  /api/anexos/<id>``            — DOWNLOAD binário (``send_file``); NÃO
      envelopado, mas protegido por ``api_login_required`` + ``_can_view_task``.
    - ``POST /api/anexos/<id>/delete``     — exclui o anexo (autor/admin).

SERVIDOR AUTORITATIVO: as regras de visão (``_can_view_task``) e a validação de
arquivo (``_allowed_attachment``/``_file_content_matches_extension``) são REUSADAS
das rotas legadas, sem duplicação. NUNCA expomos ``stored_filename`` (caminho
físico) no payload — só o ``download_url`` (rota deste módulo).
"""

from __future__ import annotations

import os
import uuid
from typing import Any

from flask import Response, g, request, send_file, url_for
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

from models import Task, TaskAnexo, db
from services.notifications import notify_task_event

from ..blueprint import main_bp
from ..tasks.constants import (
    _allowed_attachment,
    _extension_of,
    _file_content_matches_extension,
    _get_upload_folder,
    _preview_text,
)
from ..tasks.permissions import (
    _audit_denied_task_action,
    _can_manage_task_restricted_actions,
    api_task_denial,
)
from .envelope import fail, fail_not_found, ok
from .negotiation import api_login_required
from .serializers import _serialize_task_anexo


def _anexo_download_url(anexo: TaskAnexo) -> str:
    """Monta a URL do download binário (rota ``api_anexo_download`` deste módulo).

    O drawer abre este link em nova aba / via ``<a download>`` (mesma origin,
    cookie de sessão). NÃO envelopamos o download — é octet-stream.
    """
    return url_for("main.api_anexo_download", anexo_id=anexo.id)


def _serialize_anexo_list(task: Task) -> list[dict[str, Any]]:
    """Serializa todos os anexos de ``task`` (sem segredos, com URL de download).

    Args:
        task: Tarefa carregada/validada.

    Returns:
        Lista de anexos JSON-safe na ordem da relação ``task.anexos``.
    """
    return [
        _serialize_task_anexo(anexo, download_url=_anexo_download_url(anexo))
        for anexo in (task.anexos or [])
    ]


def _load_viewable_task(
    task_id: int, *, for_write: bool = False
) -> tuple[Task | None, Any]:
    """Carrega a tarefa aplicando o contrato S5 (404 invisível, 403 rank baixo).

    ``for_write=True`` exige rank >= editor (``_can_edit_task``, S3/F2-5 — MESMA
    regra das demais escritas de tarefa); o padrão exige rank >= leitor
    (``_can_view_task``, MESMA regra das rotas legadas de anexo).

    Args:
        task_id: ID da tarefa.
        for_write: Se a chamada antecede uma escrita na tarefa (upload).

    Returns:
        ``(task, None)`` quando autorizado; ``(None, fail_response)`` com 404
        (inexistente/invisível, mesmo corpo) ou 403 (vê a tarefa, rank < editor).
    """
    task = db.session.get(Task, task_id)
    denied = api_task_denial(task, for_write=for_write)
    if denied is not None:
        return None, denied
    return task, None


def _validate_upload_file() -> tuple[Any, Any]:
    """Valida o arquivo enviado via ``request.files["file"]`` (multipart).

    Reusa os helpers legados (``_allowed_attachment`` para a extensão e
    ``_file_content_matches_extension`` para os magic bytes). Espelha a validação
    de ``add_task_anexo`` legada, devolvendo 422 ``validation`` em vez do 400 do
    Jinja para inputs malformados.

    Returns:
        ``(file_storage, None)`` válido; ou ``(None, fail_response)`` (422).
    """
    if "file" not in request.files:
        return None, fail("Nenhum arquivo enviado.", status=422, code="validation")

    file = request.files["file"]
    if not file or not file.filename:
        return None, fail("Arquivo inválido.", status=422, code="validation")

    if not _allowed_attachment(file.filename):
        return None, fail(
            "Tipo de arquivo não permitido.", status=422, code="validation"
        )

    extension = _extension_of(file.filename)
    if not _file_content_matches_extension(file, extension):
        return None, fail(
            "Conteúdo do arquivo não corresponde à extensão informada.",
            status=422,
            code="validation",
        )
    return file, None


@main_bp.route("/api/tarefas/<int:task_id>/anexos", methods=["GET"])
@api_login_required
def api_tarefa_anexos_list(task_id: int) -> Response | tuple[Response, int]:
    """Lista os anexos de uma tarefa (drawer).

    Args:
        task_id: ID da tarefa.

    Returns:
        Envelope ``{"ok": true, "data": {"anexos": [...], "count": <int>}}`` (200);
        404/403; 401 JSON sem sessão.
    """
    task, error = _load_viewable_task(task_id)
    if error is not None:
        return error

    anexos = _serialize_anexo_list(task)
    return ok({"anexos": anexos, "count": len(anexos)})


@main_bp.route("/api/tarefas/<int:task_id>/anexos", methods=["POST"])
@api_login_required
def api_tarefa_anexo_upload(task_id: int) -> Response | tuple[Response, int]:
    """Faz UPLOAD de um anexo via multipart (``request.files["file"]``).

    Reusa toda a validação/persistência de ``add_task_anexo`` legada (extensão,
    magic bytes, ``secure_filename`` + UUID no disco) e dispara o mesmo evento de
    domínio (``task_attachment_added``). O limite de 10MB (``MAX_CONTENT_LENGTH``)
    é aplicado pelo Flask ANTES da view (gera 413 ``RequestEntityTooLarge``,
    tratado em ``api_payload_too_large``). Devolve o anexo criado e a lista
    atualizada (sem ``stored_filename``).

    Form multipart: campo ``file`` (NÃO JSON).

    Args:
        task_id: ID da tarefa.

    Returns:
        Envelope ``{"ok": true, "data": {"anexo": {...}, "anexos": [...],
        "count": <int>}}`` (200); 404/403/422; 413 (excesso); 401 JSON sem sessão.
    """
    task, error = _load_viewable_task(task_id, for_write=True)
    if error is not None:
        return error

    file, validation_error = _validate_upload_file()
    if validation_error is not None:
        return validation_error

    original_name = file.filename[:255]
    safe_name = secure_filename(file.filename)
    ext = safe_name.rsplit(".", 1)[1].lower() if "." in safe_name else ""
    stored_name = str(uuid.uuid4()) + ("." + ext if ext else "")
    content_type = file.content_type or "application/octet-stream"

    upload_folder = _get_upload_folder()
    file_path = os.path.join(upload_folder, stored_name)
    try:
        file.save(file_path)
    except OSError:
        return fail("Erro ao salvar o arquivo.", status=422, code="validation")

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
            message=(
                f'{g.user.name} anexou "{_preview_text(anexo.filename, 90)}" à '
                f'tarefa "{_preview_text(task.descricao, 90)}".'
            ),
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        try:
            os.remove(file_path)
        except OSError:
            pass
        return fail("Erro ao salvar o anexo.", status=422, code="validation")

    anexos = _serialize_anexo_list(task)
    return ok(
        {
            "anexo": _serialize_task_anexo(
                anexo, download_url=_anexo_download_url(anexo)
            ),
            "anexos": anexos,
            "count": len(anexos),
        }
    )


@main_bp.route("/api/anexos/<int:anexo_id>", methods=["GET"])
@api_login_required
def api_anexo_download(anexo_id: int) -> Response | tuple[Response, int]:
    """DOWNLOAD binário de um anexo (``send_file``) — NÃO envelopado.

    Protegido por ``api_login_required`` + ``_can_view_task`` (escopo de órgão). O
    erro (404/403) ainda usa o envelope canônico; o SUCESSO é octet-stream cru
    (``as_attachment=False``: o browser decide exibir/baixar). Reusa a MESMA
    leitura de ``_get_upload_folder``/``stored_filename`` da rota legada.

    Args:
        anexo_id: ID do anexo.

    Returns:
        ``send_file`` (200, binário) em sucesso; 404/403 envelopados; 401 JSON.
    """
    anexo = db.session.get(TaskAnexo, anexo_id)
    # Anexo inexistente e anexo de tarefa invisível respondem o MESMO 404 (F4-2b).
    if anexo is None:
        return fail_not_found()
    denied = api_task_denial(anexo.task)
    if denied is not None:
        return denied

    file_path = os.path.join(_get_upload_folder(), anexo.stored_filename)
    if not os.path.exists(file_path):
        return fail("Arquivo não encontrado.", status=404, code="not_found")

    return send_file(file_path, download_name=anexo.filename, as_attachment=False)


@main_bp.route("/api/anexos/<int:anexo_id>/delete", methods=["POST"])
@api_login_required
def api_anexo_delete(anexo_id: int) -> Response | tuple[Response, int]:
    """Exclui um anexo (autor/admin) e remove o arquivo do disco.

    Restrito a ``_can_manage_task_restricted_actions`` (autor da tarefa ou admin),
    espelhando o escopo das ações restritas do drawer. Dispara
    ``task_attachment_deleted`` e devolve a lista atualizada.

    Args:
        anexo_id: ID do anexo.

    Returns:
        Envelope ``{"ok": true, "data": {"anexo_id": <id>, "anexos": [...],
        "count": <int>}}`` (200); 404/403; 401 JSON sem sessão.
    """
    anexo = db.session.get(TaskAnexo, anexo_id)
    if anexo is None:
        return fail_not_found()

    task = anexo.task
    denied = api_task_denial(task)
    if denied is not None:
        return denied
    if not _can_manage_task_restricted_actions(g.user, task):
        _audit_denied_task_action(task, "forbidden_edit_restricted")
        return fail(
            "Somente o autor da tarefa ou um administrador pode excluir anexos.",
            status=403,
            code="forbidden",
        )

    file_path = os.path.join(_get_upload_folder(), anexo.stored_filename)
    try:
        notify_task_event(
            task,
            actor_user_id=g.user.id,
            event_type="task_attachment_deleted",
            title="Anexo removido em tarefa",
            message=(
                f'{g.user.name} removeu o anexo "{_preview_text(anexo.filename, 90)}" '
                f'da tarefa "{_preview_text(task.descricao, 90)}".'
            ),
        )
        db.session.delete(anexo)
        db.session.commit()
    except Exception:
        db.session.rollback()
        return fail("Erro ao excluir o anexo.", status=422, code="validation")

    try:
        os.remove(file_path)
    except OSError:
        pass

    anexos = _serialize_anexo_list(task)
    return ok({"anexo_id": anexo_id, "anexos": anexos, "count": len(anexos)})


#: Limite de upload em MB para a mensagem do 413 (espelha ``MAX_CONTENT_LENGTH``
#: = 10MB em ``config.py:65``); usado só para compor a mensagem ao usuário.
_MAX_UPLOAD_MB = 10


@main_bp.app_errorhandler(RequestEntityTooLarge)
def api_payload_too_large(
    error: RequestEntityTooLarge,
) -> Response | tuple[Response, int] | RequestEntityTooLarge:
    """Converte o 413 do Flask (``MAX_CONTENT_LENGTH``) em envelope para a SPA.

    O ``MAX_CONTENT_LENGTH`` (10MB) é aplicado ANTES da view rodar, então o upload
    em excesso nunca alcança ``api_tarefa_anexo_upload``. Este handler só atua nas
    requisições ``/api/*`` (onde a SPA espera JSON estruturado); fora delas, deixa
    o comportamento legado (HTML) inalterado re-levantando o erro.

    Args:
        error: A exceção ``RequestEntityTooLarge`` levantada pelo Werkzeug.

    Returns:
        ``fail(..., 413, "validation")`` para paths ``/api/*``; senão, o ``error``
        original (Flask renderiza a página de erro padrão).
    """
    if not request.path.startswith("/api/"):
        return error
    return fail(
        f"Arquivo excede o limite de {_MAX_UPLOAD_MB}MB.",
        status=413,
        code="validation",
    )
