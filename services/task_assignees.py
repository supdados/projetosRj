"""Leitura canônica dos responsáveis de tarefas para filtros e busca."""

from sqlalchemy import func, or_
from sqlalchemy.sql.elements import ColumnElement

from models import Task, TaskAssignee, User


def task_assignee_criterion(
    pattern: str, *, escape: str | None = None
) -> ColumnElement[bool]:
    """Casa usuários da N:N e nomes ainda legados, sem multiplicar as tarefas.

    Ex.: ``Task.query.filter(task_assignee_criterion('%Ana%'))``.
    """
    display_name = func.coalesce(func.nullif(User.name, ""), User.username)
    assigned = Task.assignees.any(
        TaskAssignee.user.has(display_name.ilike(pattern, escape=escape))
    )
    return or_(assigned, Task.responsavel.ilike(pattern, escape=escape))


def task_assignee_display(task: Task) -> str:
    """Nomes atuais ordenados, seguidos do legado ainda não associado a usuários.

    O backfill preserva nomes sem usuário em ``responsavel``, mesmo com N:N.
    Ex.: ``task_assignee_display(task) == 'Ana, Equipe externa'``.
    """
    names = {
        (row.user.name or row.user.username or "Usuário").strip()
        for row in task.assignees
        if row.user is not None
    }
    labels = sorted(names, key=str.casefold)
    legacy = (task.responsavel or "").strip()
    if legacy and legacy.casefold() not in {name.casefold() for name in names}:
        labels.append(legacy)
    return ", ".join(labels)
