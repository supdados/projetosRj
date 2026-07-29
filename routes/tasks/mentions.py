"""Ponte entre o serviço puro de menções e o mundo Flask/ORM.

Existe para que as DUAS rotas de escrita de comentário (a da SPA em
``routes/api/task_comments.py`` e a legada em ``routes/tasks/comments.py``)
resolvam menções pela MESMA fonte de pessoas — a mesma do picker de responsável.
"""

from __future__ import annotations

from typing import Any

from services.comment_mentions import candidates_from_users, extract_mention_spans


def resolve_comment_mentions(task: Any, content: str) -> list[dict[str, Any]]:
    """Menções de ``content`` resolvidas contra quem tem acesso ao projeto.

    Args:
        task: Tarefa dona do comentário (usa ``task.project``).
        content: Texto do comentário como o autor escreveu.

    Returns:
        Lista de ``{user_id, name, start, length}`` pronta para gravar em
        ``TaskComment.mentions``; vazia quando não há menção reconhecível.

    Exemplo::

        comment.mentions = resolve_comment_mentions(task, "ok @Ana Luiza Ribeiro")
    """
    from routes.tasks.creation import _get_assignable_users_for_project

    users = _get_assignable_users_for_project(getattr(task, "project", None))
    return extract_mention_spans(content, candidates_from_users(users))
