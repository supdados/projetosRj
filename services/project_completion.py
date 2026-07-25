"""Conclusão de projeto.

Centraliza as 3 validações (permissão, status Vigente, todas as etapas
concluídas) e a mutação ``status = "Finalizado"`` + histórico, SEM commit —
o chamador decide o envelope.

A celebração épica do front (som + confetes + overlay) é puramente client-side;
este service só garante a transição autoritativa de estado.
"""

from __future__ import annotations

from dataclasses import dataclass

from routes.orgao_scope import user_can_access_project
from routes.shared import log_project_action


@dataclass
class ProjectCompletionError(Exception):
    """Erro de regra ao concluir projeto, com mensagem/categoria/status HTTP.

    ``category`` é a severidade da mensagem ("danger"/"warning") e ``status``
    o HTTP que a API deve devolver (403/400).
    """

    message: str
    category: str
    status: int


def complete_project(project, user) -> None:
    """Valida e conclui o ``project`` para o ``user`` SEM commit.

    Args:
        project: ``Project`` a concluir.
        user: Usuário corrente (``g.user``).

    Raises:
        ProjectCompletionError: permissão (403/danger), status != Vigente
            (400/warning) ou etapas incompletas (400/warning).

    Exemplo:
        >>> complete_project(project, g.user)
        >>> db.session.commit()
    """
    if not user_can_access_project(user, project):
        raise ProjectCompletionError(
            "Você não tem permissão para concluir este projeto.",
            category="danger",
            status=403,
        )
    if project.status != "Vigente":
        raise ProjectCompletionError(
            'Apenas projetos com status "Vigente" podem ser concluídos.',
            category="warning",
            status=400,
        )
    if not project.todas_etapas_concluidas:
        raise ProjectCompletionError(
            "Todas as etapas devem estar iniciadas e concluídas para "
            "finalizar o projeto.",
            category="warning",
            status=400,
        )

    project.status = "Finalizado"
    log_project_action(
        project_id=project.id,
        action_type="finalize",
        description=f'Concluiu o projeto "{project.titulo}"',
    )
