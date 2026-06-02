"""Serializadores canônicos de entidades para a API da SPA.

Princípios (CLAUDE.md + plano de migração):
    - Campos REAIS dos modelos; sem aliases legados vazando para o frontend.
    - NUNCA serializar segredos: ``password_hash`` (``models/user.py``) nem
      tokens OAuth (``EncryptedText`` em ``models/calendar.py``).
    - Derivados de projeto (``data_inicio_projeto``, ``todas_etapas_concluidas``,
      etc.) são computados no backend (properties do modelo) e entregues
      read-only; o cliente NÃO os recalcula.

Cada serializer recebe uma instância de modelo e devolve um ``dict`` JSON-safe.
"""

from __future__ import annotations

from typing import Any, Optional


def _orgao_ref_brief(orgao: Any) -> dict[str, Any]:
    """Serializa o vínculo mínimo de um órgão (id/sigla/nome).

    Args:
        orgao: Instância de ``OrgaoUnidade``.

    Returns:
        ``{"id": int, "sigla": str, "nome": str}``.
    """
    return {"id": orgao.id, "sigla": orgao.sigla, "nome": orgao.nome}


def _resolve_auth_provider(user: Any) -> str:
    """Deriva o provedor de autenticação a partir do vínculo Gov.br.

    Returns ``"govbr"`` quando o usuário está vinculado ao Gov.br
    (``cpf_govbr`` e ``govbr_sub`` presentes), senão ``"local"``.

    Args:
        user: Instância de ``User``.

    Returns:
        ``"govbr"`` ou ``"local"``.
    """
    if getattr(user, "cpf_govbr", None) and getattr(user, "govbr_sub", None):
        return "govbr"
    return "local"


def serialize_user(user: Any) -> dict[str, Any]:
    """Serializa um usuário para ``/api/me`` e afins.

    Inclui apenas dados seguros e os órgãos vinculados (via ``user.orgaos`` ->
    ``UserOrgao.orgao``). NUNCA expõe ``password_hash`` nem credenciais.

    Args:
        user: Instância de ``User``.

    Returns:
        ``{id, name, username, is_admin, orgaos: [{id, sigla, nome}],
        auth_provider}``.

    Exemplo:
        >>> serialize_user(g.user)
        {'id': 1, 'name': 'Ana', 'username': 'ana', 'is_admin': False,
         'orgaos': [{'id': 3, 'sigla': 'SETD', 'nome': '...'}],
         'auth_provider': 'govbr'}
    """
    vinculos = getattr(user, "orgaos", None) or []
    orgaos = [
        _orgao_ref_brief(uo.orgao)
        for uo in vinculos
        if getattr(uo, "orgao", None) is not None
    ]
    return {
        "id": user.id,
        "name": user.name,
        "username": user.username,
        "is_admin": bool(user.is_admin),
        "orgaos": orgaos,
        "auth_provider": _resolve_auth_provider(user),
    }


def _iso_or_none(value: Any) -> Optional[str]:
    """Converte ``date``/``datetime`` para ISO 8601, ou ``None``."""
    if value is None:
        return None
    return value.isoformat()


def serialize_project_card(project: Any) -> dict[str, Any]:
    """Serializa um projeto no formato de "card" para listas/dashboard.

    Usa CAMPOS REAIS do modelo ``Project`` mais os derivados read-only
    (properties calculadas no backend). ``orgao`` (string) é o campo legado;
    ``orgao_id``/``orgao_sigla`` refletem o vínculo relacional atual.

    Args:
        project: Instância de ``Project``.

    Returns:
        ``dict`` JSON-safe com os campos do card.
    """
    orgao_ref = getattr(project, "orgao_ref", None)
    return {
        "id": project.id,
        "titulo": project.titulo,
        "status": project.status,
        "prioridade": project.prioridade,
        "orgao": project.orgao,  # legado: string livre
        "orgao_id": project.orgao_id,
        "orgao_sigla": orgao_ref.sigla if orgao_ref is not None else None,
        "short_description": project.short_description,
        "special_project": project.special_project,
        # derivados read-only (computados no backend; NÃO recalcular no cliente)
        "data_inicio_projeto": _iso_or_none(project.data_inicio_projeto),
        "data_fim_projeto": _iso_or_none(project.data_fim_projeto),
        "total_workflow_etapas": project.total_workflow_etapas,
        "todas_etapas_concluidas": project.todas_etapas_concluidas,
    }


def serialize_task_card(task: Any) -> dict[str, Any]:
    """Serializa uma tarefa no formato de "card" para listas/dashboard.

    Task e TaskItem são a MESMA tabela; existe um único tipo ``Task``. Usa
    CAMPOS REAIS (``descricao``, ``is_archived``, ``archived_at``) — sem aliases
    legados (``titulo``/``is_finalized``) vazando para o frontend.

    Args:
        task: Instância de ``Task``.

    Returns:
        ``dict`` JSON-safe com os campos do card da tarefa.
    """
    return {
        "id": task.id,
        "descricao": task.descricao,
        "status": task.status,
        "responsavel": task.responsavel,
        "prioridade": task.prioridade,
        "tipo_pedido": task.tipo_pedido,
        "ordem": task.ordem,
        "project_id": task.project_id,
        "etapa_id": task.etapa_id,
        "created_by_id": task.created_by_id,
        "created_at": _iso_or_none(task.created_at),
        "is_archived": bool(task.is_archived),
        "archived_at": _iso_or_none(task.archived_at),
    }
