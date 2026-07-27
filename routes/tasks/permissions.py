from flask import g, jsonify

from models import (
    TaskAccessAudit,
    db,
)
from routes.orgao_scope import user_can_access_project
from routes.tasks.constants import _preview_text
from services.authorization import (
    ACCESS_FORBIDDEN,
    ACCESS_NOT_FOUND,
    ACCESS_OK,
    AccessVerdict,
    user_can_edit_project,
    user_can_view_project,
)

#: Mensagem canônica quando alguém sem permissão tenta mover uma tarefa para
#: "finalizada". Definida aqui (junto de ``_can_transition_task_to_status``) para
#: que tanto a rota Jinja legada (``routes/tasks/crud.py``) quanto o endpoint
#: ``/api/*`` do Kanban (``routes/api/board.py``) compartilhem a MESMA string,
#: sem duplicação. ``crud.py`` reexporta este nome — comportamento inalterado.
FINALIZE_DENIED_MESSAGE = "Apenas o criador da tarefa pode movê-la para Finalizada."


def _can_view_task(user, task) -> bool:
    """Ver tarefa: rank >= leitor no projeto; tarefa avulsa só do criador (ou admin).

    Exemplo: ``_can_view_task(g.user, task)``.
    """
    if task is None or user is None:
        return False
    # Admin e projeto sem órgão já saem resolvidos por `area_project_rank`.
    if user_can_view_project(user, task.project):
        return True
    return task.project_id is None and task.created_by_id == user.id


def _can_edit_task(user, task) -> bool:
    """Escrever na tarefa: rank >= editor no projeto; avulsa segue a regra de visão."""
    if task is None or user is None:
        return False
    if task.project_id is None:
        return _can_view_task(user, task)
    return user_can_edit_project(user, task.project)


#: Mensagem 403 das superfícies de tarefa quando o usuário VÊ a tarefa mas a
#: ação exige rank >= editor (envelope ``/api/*`` e rotas legadas ``jsonify``).
TASK_FORBIDDEN_MESSAGE = "Você não tem permissão para acessar esta tarefa."
LEGACY_TASK_FORBIDDEN_MESSAGE = "Sem permissão"


def task_access_verdict(user, task, *, for_write: bool = False) -> AccessVerdict:
    """Decisão ÚNICA 404-vs-403 de tarefa (S5/F4-2) — não replicar por endpoint.

    - ``ACCESS_NOT_FOUND``: tarefa inexistente OU invisível (rank 0 no projeto;
      avulsa de outro autor). O chamador responde o MESMO corpo do caso "id
      inexistente" (anti-enumeração F4-2b), nunca uma mensagem própria.
    - ``ACCESS_FORBIDDEN``: vê a tarefa mas a escrita exige rank >= editor.
    - ``ACCESS_OK``: liberado.

    Exemplo: ``task_access_verdict(g.user, task, for_write=True)``.
    """
    if task is None or not _can_view_task(user, task):
        return ACCESS_NOT_FOUND
    if for_write and not _can_edit_task(user, task):
        return ACCESS_FORBIDDEN
    return ACCESS_OK


def api_task_denial(task, *, for_write: bool = False):
    """Negativa da tarefa no envelope canônico; ``None`` libera o endpoint.

    Exemplo:
        >>> denied = api_task_denial(task, for_write=True)
        >>> if denied is not None:
        ...     return denied
    """
    # Import local: `routes.api.envelope` executa `routes/api/__init__`, que
    # importa este módulo de volta — no topo o ciclo estoura no boot.
    from routes.api.envelope import fail, fail_not_found

    verdict = task_access_verdict(getattr(g, "user", None), task, for_write=for_write)
    if verdict == ACCESS_NOT_FOUND:
        return fail_not_found()
    if verdict == ACCESS_FORBIDDEN:
        return fail(TASK_FORBIDDEN_MESSAGE, status=403, code="forbidden")
    return None


def legacy_not_found():
    """404 canônico das rotas legadas (``jsonify``) — corpo único anti-enumeração."""
    from routes.api.envelope import NOT_FOUND_MESSAGE

    return jsonify({"success": False, "message": NOT_FOUND_MESSAGE}), 404


def legacy_task_denial(task, *, for_write: bool = False):
    """Mesma decisão de ``api_task_denial`` no formato ``jsonify`` das rotas legadas."""
    verdict = task_access_verdict(getattr(g, "user", None), task, for_write=for_write)
    if verdict == ACCESS_NOT_FOUND:
        return legacy_not_found()
    if verdict == ACCESS_FORBIDDEN:
        return (
            jsonify({"success": False, "message": LEGACY_TASK_FORBIDDEN_MESSAGE}),
            403,
        )
    return None


def _can_manage_task_restricted_actions(user, task):
    return bool(user and task and (user.is_admin or task.created_by_id == user.id))


def _can_transition_task_to_status(user, task, next_status, previous_status=None):
    normalized_next_status = (next_status or "").strip()
    normalized_previous_status = (previous_status or task.status or "").strip()

    if normalized_next_status != "finalizada":
        return True

    if normalized_previous_status == "finalizada":
        return True

    return _can_manage_task_restricted_actions(user, task)


def _audit_denied_task_action(task, action_type, *, attempted_status=None):
    actor = getattr(g, "user", None)
    if not task or not actor:
        return

    try:
        db.session.add(
            TaskAccessAudit(
                task_id=task.id,
                project_id=task.project_id,
                actor_user_id=actor.id,
                actor_name=actor.name or actor.username or "Usuário",
                task_author_user_id=task.created_by_id,
                action_type=action_type,
                reason="not_task_author",
                attempted_status=attempted_status,
                task_description=_preview_text(task.descricao, 240)
                or f"Tarefa #{task.id}",
            )
        )
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        print(f"Erro ao auditar tentativa negada em tarefa: {exc}")


def task_permission_flags(task, user=None):
    actor = user or getattr(g, "user", None)
    can_manage = _can_manage_task_restricted_actions(actor, task)
    return {
        "can_delete": can_manage,
        "can_finalize": can_manage,
        "is_author": bool(actor and task and task.created_by_id == actor.id),
    }


_task_permission_flags = task_permission_flags


def _can_access_project_in_tasks(project):
    if project is None:
        return True
    return user_can_access_project(g.user, project)


def _can_edit_project_in_tasks(project) -> bool:
    """Criar/editar tarefa DE PROJETO exige rank >= editor; avulsa (None) libera."""
    if project is None:
        return True
    return user_can_edit_project(g.user, project)
