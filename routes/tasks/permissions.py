from flask import g

from models import (
    TaskAccessAudit,
    db,
)
from routes.tasks.constants import _preview_text


def _can_view_task(user, task):
    return (
        user.is_admin
        or (task.project_id is None and task.created_by_id == user.id)
        or (task.project_id and task.project and task.project.area_responsavel in user.get_areas())
    )


def _can_manage_task_restricted_actions(user, task):
    return bool(user and task and (user.is_admin or task.created_by_id == user.id))


def _can_transition_task_to_status(user, task, next_status, previous_status=None):
    normalized_next_status = (next_status or '').strip()
    normalized_previous_status = (previous_status or task.status or '').strip()

    if normalized_next_status != 'finalizada':
        return True

    if normalized_previous_status == 'finalizada':
        return True

    return _can_manage_task_restricted_actions(user, task)


def _audit_denied_task_action(task, action_type, *, attempted_status=None):
    actor = getattr(g, 'user', None)
    if not task or not actor:
        return

    try:
        db.session.add(
            TaskAccessAudit(
                task_id=task.id,
                project_id=task.project_id,
                actor_user_id=actor.id,
                actor_name=actor.name or actor.username or 'Usuário',
                task_author_user_id=task.created_by_id,
                action_type=action_type,
                reason='not_task_author',
                attempted_status=attempted_status,
                task_description=_preview_text(task.descricao, 240) or f'Tarefa #{task.id}',
            )
        )
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        print(f'Erro ao auditar tentativa negada em tarefa: {exc}')


def _task_permission_flags(task, user=None):
    actor = user or getattr(g, 'user', None)
    can_manage = _can_manage_task_restricted_actions(actor, task)
    return {
        'can_delete': can_manage,
        'can_finalize': can_manage,
        'is_author': bool(actor and task and task.created_by_id == actor.id),
    }


def _can_access_project_in_tasks(project):
    if project is None:
        return True
    if g.user.is_admin:
        return True
    return g.user.has_access_to_area(project.area_responsavel)
