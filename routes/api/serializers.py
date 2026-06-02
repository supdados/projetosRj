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


def serialize_orgao_option(node: dict[str, Any]) -> dict[str, Any]:
    """Serializa um nó da árvore de órgãos visível como opção de ``<select>``.

    Recebe um nó já produzido por ``get_visible_orgao_tree`` (escopo server-side
    do usuário) e devolve apenas os campos necessários para popular um seletor de
    filtro de órgão na SPA — preservando ``pai_id`` para que o cliente possa, se
    quiser, reconstruir a hierarquia (indentação). NÃO expõe segredos.

    Args:
        node: ``dict`` com ``id``/``sigla``/``nome``/``tipo``/``pai_id`` e as
            flags ``is_user_orgao``/``is_user_ancestor``/``is_inactive``.

    Returns:
        ``dict`` JSON-safe ``{value, label, sigla, nome, tipo, pai_id,
        is_user_orgao, is_user_ancestor, is_inactive}``.

    Exemplo:
        >>> serialize_orgao_option({"id": 3, "sigla": "SETD", "nome": "...",
        ...     "tipo": "Secretaria", "pai_id": 1, "is_user_orgao": True,
        ...     "is_user_ancestor": False, "is_inactive": False})["value"]
        '3'
    """
    return {
        "value": str(node["id"]),
        "label": node.get("sigla") or node.get("nome") or str(node["id"]),
        "sigla": node.get("sigla"),
        "nome": node.get("nome"),
        "tipo": node.get("tipo"),
        "pai_id": node.get("pai_id"),
        "is_user_orgao": bool(node.get("is_user_orgao")),
        "is_user_ancestor": bool(node.get("is_user_ancestor")),
        "is_inactive": bool(node.get("is_inactive")),
    }


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


def serialize_etapa_card(etapa: Any) -> dict[str, Any]:
    """Serializa uma etapa para a tela "Projetos Pendentes".

    Usa CAMPOS REAIS de ``Etapa`` (``descricao``, ``data_inicio``, ``data_fim``,
    ``responsavel``, ``ordem``, ``done``, ``entry_type``). As datas viram ISO
    8601 (ou ``None``). O bucket de urgência e o progresso de tarefas NÃO ficam
    aqui — são derivados de listagem entregues à parte (mapas por ``etapa.id``).

    Args:
        etapa: Instância de ``Etapa``.

    Returns:
        ``dict`` JSON-safe com os campos da etapa.
    """
    return {
        "id": etapa.id,
        "descricao": etapa.descricao,
        "data_inicio": _iso_or_none(etapa.data_inicio),
        "data_fim": _iso_or_none(etapa.data_fim),
        "responsavel": etapa.responsavel,
        "ordem": etapa.ordem,
        "done": bool(etapa.done),
        "project_id": etapa.project_id,
        "entry_type": etapa.entry_type,
    }


def serialize_pending_project_row(row: dict[str, Any]) -> dict[str, Any]:
    """Serializa uma linha de "Projetos Pendentes" (projeto + etapas + contadores).

    Reusa ``serialize_project_card`` para o projeto e ``serialize_etapa_card``
    para as etapas visíveis/ocultas, preservando os contadores agregados já
    calculados no backend (``build_projetos_pendentes_context``). O cliente NÃO
    recalcula buckets/atraso.

    Args:
        row: Item de ``context["projetos_com_etapas"]`` — dict com ``projeto``,
            ``etapas_visiveis``/``etapas_outras`` e os contadores ``qtd_*``.

    Returns:
        ``dict`` JSON-safe com ``project``, ``etapas_visiveis``,
        ``etapas_outras`` e os contadores da linha.
    """
    return {
        "project": serialize_project_card(row["projeto"]),
        "etapas_visiveis": [
            serialize_etapa_card(etapa) for etapa in row["etapas_visiveis"]
        ],
        "etapas_outras": [serialize_etapa_card(etapa) for etapa in row["etapas_outras"]],
        "qtd_visiveis": row["qtd_visiveis"],
        "qtd_outras": row["qtd_outras"],
        "qtd_atrasadas": row["qtd_atrasadas"],
        "qtd_7dias": row["qtd_7dias"],
        "qtd_14dias": row["qtd_14dias"],
        "qtd_21dias": row["qtd_21dias"],
        "qtd_sem_data": row["qtd_sem_data"],
        "max_overdue_days": row["max_overdue_days"],
    }


def serialize_project_history_entry(entry: Any) -> dict[str, Any]:
    """Serializa uma entrada de ``ProjectHistory`` para a tela de histórico.

    Usa CAMPOS REAIS (``action_type``, ``action_description``, ``old_value``,
    ``new_value``, ``timestamp``) e inclui um vínculo mínimo do autor
    (``user``) — apenas ``id``/``name``/``username``, NUNCA segredos.

    Args:
        entry: Instância de ``ProjectHistory``.

    Returns:
        ``dict`` JSON-safe com os campos da entrada de histórico.
    """
    author = getattr(entry, "user", None)
    return {
        "id": entry.id,
        "project_id": entry.project_id,
        "action_type": entry.action_type,
        "action_description": entry.action_description,
        "old_value": entry.old_value,
        "new_value": entry.new_value,
        "timestamp": _iso_or_none(entry.timestamp),
        "user": (
            {
                "id": author.id,
                "name": author.name,
                "username": author.username,
            }
            if author is not None
            else None
        ),
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
