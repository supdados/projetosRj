"""Endpoints JSON de COMENTÁRIOS do DRAWER de Tarefa (Fase 5b-2) para a SPA.

O drawer lista/adiciona/edita/exclui comentários de UMA tarefa. Todos os
endpoints aqui respondem no envelope canônico (``ok``/``fail``) e são protegidos
por ``api_login_required`` (401 JSON).

Endpoints (anexados ao ``main_bp`` ÚNICO; ADITIVO — NÃO altera as rotas Jinja
legadas em ``routes/tasks/comments.py`` nem o JS legado):

    - ``POST /api/tarefas/<id>/comentarios``        — adiciona um comentário.
    - ``POST /api/comentarios/<id>``                — edita um comentário (autor).
    - ``POST /api/comentarios/<id>/delete``         — exclui um comentário (autor).

SERVIDOR AUTORITATIVO: as regras são REUSADAS das rotas legadas (``_can_view_task``
para comentar; só o próprio autor edita/exclui — espelhando ``comments.py``), sem
duplicação. A resposta devolve o comentário afetado e a lista atualizada de
comentários (``_serialize_task_comment``), para o drawer reconciliar sem segredos.
"""

from __future__ import annotations

from typing import Any

from flask import Response, g, request

from models import Task, TaskComment, db
from services.notifications import notify_task_event
from time_utils import utc_now

from ..blueprint import main_bp
from ..tasks.constants import _preview_text
from ..tasks.permissions import api_task_denial
from .envelope import fail, fail_not_found, ok
from .negotiation import api_login_required
from .serializers import _serialize_task_comment


def _serialize_comment_list(task: Task) -> list[dict[str, Any]]:
    """Serializa todos os comentários de ``task`` para o usuário corrente.

    Reusa ``_serialize_task_comment`` (campos reais + flags ``is_own``/``can_*``;
    sem segredos), derivando o autor corrente de ``flask.g``.

    Args:
        task: Tarefa carregada/validada.

    Returns:
        Lista de comentários JSON-safe na ordem da relação ``task.comments``.
    """
    current_user_id = getattr(getattr(g, "user", None), "id", None)
    return [
        _serialize_task_comment(comment, current_user_id=current_user_id)
        for comment in (task.comments or [])
    ]


def _load_commentable_task(task_id: int) -> tuple[Task | None, Any]:
    """Carrega a tarefa validando existência e escopo de visão (contrato S5).

    Reusa ``_can_view_task`` (MESMA regra de ``add_task_comment`` legada): quem
    enxerga a tarefa pode comentar. Tarefa inexistente e tarefa invisível
    respondem o MESMO 404 (anti-enumeração F4-2b).

    Args:
        task_id: ID da tarefa.

    Returns:
        ``(task, None)`` quando autorizado; ``(None, fail_response)`` (404).
    """
    task = db.session.get(Task, task_id)
    denied = api_task_denial(task)
    if denied is not None:
        return None, denied
    return task, None


def _load_own_comment(comment_id: int) -> tuple[TaskComment | None, Any]:
    """Carrega um comentário exigindo autoria (404/403).

    Reusa a regra legada (``edit_task_item_comment``/``delete_task_item_comment``):
    só o próprio autor pode editar/excluir — o autor passa mesmo sem enxergar a
    tarefa hoje (enforcement inalterado na S5). Quem não é autor e não vê a
    tarefa recebe o MESMO 404 do comentário inexistente (F4-2b); quem vê a
    tarefa recebe 403.

    Args:
        comment_id: ID do comentário.

    Returns:
        ``(comment, None)`` quando autorizado; ``(None, fail_response)`` (404/403).
    """
    comment = db.session.get(TaskComment, comment_id)
    if comment is None:
        return None, fail_not_found()
    if comment.user_id != g.user.id:
        invisible = api_task_denial(comment.task)
        return None, invisible or fail(
            "Você só pode editar seus próprios comentários.",
            status=403,
            code="forbidden",
        )
    return comment, None


def _read_comment_content() -> tuple[str | None, Any]:
    """Lê e valida o conteúdo do comentário do corpo JSON.

    Aceita ``{"content": <str>}``; conteúdo vazio (após strip) => 422.

    Returns:
        ``(content, None)`` válido; ou ``(None, fail_response)`` (422).
    """
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return None, fail("Corpo JSON inválido.", status=422, code="validation")
    content = (payload.get("content") or "").strip()
    if not content:
        return None, fail(
            "O comentário não pode estar vazio.", status=422, code="validation"
        )
    return content, None


@main_bp.route("/api/tarefas/<int:task_id>/comentarios", methods=["POST"])
@api_login_required
def api_tarefa_comentario_add(task_id: int) -> Response | tuple[Response, int]:
    """Adiciona um comentário à tarefa (drawer).

    Reusa ``_can_view_task`` (quem vê pode comentar) e dispara o mesmo evento de
    domínio da rota legada (``task_comment_added``). Devolve o comentário criado e
    a lista atualizada para o drawer reconciliar.

    Body JSON: ``{"content": <str não vazio>}``.

    Args:
        task_id: ID da tarefa.

    Returns:
        Envelope ``{"ok": true, "data": {"comment": {...}, "comentarios": [...]}}``
        (200); 404/403/422; 401 JSON sem sessão.
    """
    task, error = _load_commentable_task(task_id)
    if error is not None:
        return error

    content, parse_error = _read_comment_content()
    if parse_error is not None:
        return parse_error

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
    except Exception:
        db.session.rollback()
        return fail("Erro ao adicionar comentário.", status=422, code="validation")

    return ok(
        {
            "comment": _serialize_task_comment(comment, current_user_id=g.user.id),
            "comentarios": _serialize_comment_list(task),
        }
    )


@main_bp.route("/api/comentarios/<int:comment_id>", methods=["POST"])
@api_login_required
def api_comentario_edit(comment_id: int) -> Response | tuple[Response, int]:
    """Edita um comentário (somente o autor).

    Reusa a regra legada (autoria) e dispara ``task_comment_updated``. Devolve o
    comentário atualizado e a lista da tarefa.

    Body JSON: ``{"content": <str não vazio>}``.

    Args:
        comment_id: ID do comentário.

    Returns:
        Envelope ``{"ok": true, "data": {"comment": {...}, "comentarios": [...]}}``
        (200); 404/403/422; 401 JSON sem sessão.
    """
    comment, error = _load_own_comment(comment_id)
    if error is not None:
        return error

    content, parse_error = _read_comment_content()
    if parse_error is not None:
        return parse_error

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
                f"{g.user.name} editou um comentário na tarefa "
                f'"{_preview_text(comment.task.descricao, 90)}": '
                f'"{_preview_text(old_content, 70)}" -> '
                f'"{_preview_text(comment.content, 70)}".'
            ),
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        return fail("Erro ao atualizar comentário.", status=422, code="validation")

    return ok(
        {
            "comment": _serialize_task_comment(comment, current_user_id=g.user.id),
            "comentarios": _serialize_comment_list(comment.task),
        }
    )


@main_bp.route("/api/comentarios/<int:comment_id>/delete", methods=["POST"])
@api_login_required
def api_comentario_delete(comment_id: int) -> Response | tuple[Response, int]:
    """Exclui um comentário (somente o autor).

    Reusa a regra legada (autoria) e dispara ``task_comment_deleted``. Devolve o
    ``comment_id`` removido e a lista atualizada da tarefa.

    Args:
        comment_id: ID do comentário.

    Returns:
        Envelope ``{"ok": true, "data": {"comment_id": <id>, "comentarios": [...]}}``
        (200); 404/403; 401 JSON sem sessão.
    """
    comment, error = _load_own_comment(comment_id)
    if error is not None:
        return error

    task = comment.task
    try:
        notify_task_event(
            task,
            actor_user_id=g.user.id,
            event_type="task_comment_deleted",
            title="Comentário removido em tarefa",
            message=(
                f"{g.user.name} removeu um comentário na tarefa "
                f'"{_preview_text(task.descricao, 90)}".'
            ),
        )
        db.session.delete(comment)
        db.session.commit()
    except Exception:
        db.session.rollback()
        return fail("Erro ao excluir comentário.", status=422, code="validation")

    return ok(
        {
            "comment_id": comment_id,
            "comentarios": _serialize_comment_list(task),
        }
    )
