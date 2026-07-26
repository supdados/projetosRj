from flask import g

from models import (
    TaskAccessAudit,
    db,
)
from routes.orgao_scope import user_can_access_project
from routes.tasks.constants import _preview_text
from services.authorization import user_can_edit_project, user_can_view_project

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
