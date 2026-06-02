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


def serialize_orgao_node(orgao: Any) -> dict[str, Any]:
    """Serializa um nó da árvore de órgãos (admin) recursivamente.

    Inclui os campos editáveis do nó (``id``, ``sigla``, ``nome``, ``tipo``,
    ``tipo_id``, ``pai_id``, ``ordem``, ``ativo``, ``codigo_externo``) e a lista
    ``filhos`` (serializados recursivamente, ordenados por ``ordem``/``sigla``).
    Espelha ``_serialize_orgao`` de ``routes/admin_orgaos.py`` somando a árvore.
    NÃO expõe segredos.

    Args:
        orgao: Instância de ``OrgaoUnidade``.

    Returns:
        ``dict`` JSON-safe com os campos do nó e ``filhos: [...]``.
    """
    filhos = sorted(
        getattr(orgao, "filhos", None) or [],
        key=lambda f: (f.ordem if f.ordem is not None else 0, f.sigla or ""),
    )
    return {
        "id": orgao.id,
        "sigla": orgao.sigla,
        "nome": orgao.nome,
        "tipo": orgao.tipo,
        "tipo_id": orgao.tipo_id,
        "pai_id": orgao.pai_id,
        "ordem": orgao.ordem,
        "ativo": bool(orgao.ativo),
        "codigo_externo": orgao.codigo_externo,
        "filhos": [serialize_orgao_node(filho) for filho in filhos],
    }


def serialize_orgao_form(orgao: Any) -> dict[str, Any]:
    """Serializa um órgão para o formulário de edição (sem ``filhos``).

    Espelha ``_serialize_orgao`` de ``routes/admin_orgaos.py``, somando as datas
    de vigência (ISO 8601) usadas pelo form. NÃO expõe segredos.

    Args:
        orgao: Instância de ``OrgaoUnidade``.

    Returns:
        ``dict`` JSON-safe com os campos do form do órgão.
    """
    return {
        "id": orgao.id,
        "sigla": orgao.sigla,
        "nome": orgao.nome,
        "tipo": orgao.tipo,
        "tipo_id": orgao.tipo_id,
        "pai_id": orgao.pai_id,
        "ordem": orgao.ordem,
        "ativo": bool(orgao.ativo),
        "codigo_externo": orgao.codigo_externo,
        "data_inicio_vigencia": _iso_or_none(
            getattr(orgao, "data_inicio_vigencia", None)
        ),
        "data_fim_vigencia": _iso_or_none(getattr(orgao, "data_fim_vigencia", None)),
    }


def serialize_orgao_tipo(tipo: Any) -> dict[str, Any]:
    """Serializa um tipo de órgão (catálogo/CRUD admin).

    Usa CAMPOS REAIS de ``OrgaoTipo`` (``nome``, ``slug``, ``nivel``,
    ``descricao``, ``ativo``, ``is_system``, ``permite_raiz``). ``is_system``
    sinaliza tipos-padrão protegidos. NÃO expõe segredos.

    Args:
        tipo: Instância de ``OrgaoTipo``.

    Returns:
        ``dict`` JSON-safe com os campos do tipo de órgão.
    """
    return {
        "id": tipo.id,
        "nome": tipo.nome,
        "slug": tipo.slug,
        "nivel": tipo.nivel,
        "descricao": tipo.descricao,
        "ativo": bool(tipo.ativo),
        "is_system": bool(tipo.is_system),
        "permite_raiz": bool(tipo.permite_raiz),
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


def serialize_admin_user(user: Any) -> dict[str, Any]:
    """Serializa um usuário para as telas de administração (CRUD de usuários).

    Diferente de ``serialize_user`` (consumido por ``/api/me``), inclui os campos
    relevantes ao painel admin — ``orgao`` (string legada), o vínculo Gov.br
    (``cpf_govbr``/``has_govbr_link``) e a flag ``govbr_link_locked`` (que sinaliza
    quando o CPF não é editável por já existir vínculo OAuth ativo, espelhando
    ``hide_govbr_link_fields`` em ``routes/admin_users.py``). NUNCA expõe
    ``password_hash``, ``govbr_sub`` nem qualquer segredo.

    Args:
        user: Instância de ``User``.

    Returns:
        ``dict`` JSON-safe ``{id, name, username, is_admin, orgao, orgaos,
        cpf_govbr, has_govbr_link, govbr_link_locked, auth_provider}``.
    """
    vinculos = getattr(user, "orgaos", None) or []
    orgaos = [
        _orgao_ref_brief(uo.orgao)
        for uo in vinculos
        if getattr(uo, "orgao", None) is not None
    ]
    has_govbr_link = bool(
        getattr(user, "cpf_govbr", None) and getattr(user, "govbr_sub", None)
    )
    return {
        "id": user.id,
        "name": user.name,
        "username": user.username,
        "is_admin": bool(user.is_admin),
        "orgao": user.orgao,
        "orgaos": orgaos,
        "cpf_govbr": user.cpf_govbr,
        "has_govbr_link": has_govbr_link,
        "govbr_link_locked": has_govbr_link,
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


def serialize_project_detail(project: Any) -> dict[str, Any]:
    """Serializa um projeto para a tela de Detalhe (card + campos editáveis).

    Reusa ``serialize_project_card`` (id/titulo/status/derivados read-only) e
    soma os demais campos editáveis inline do projeto que NÃO estão no card —
    ``observacao``, ``sei_process``, ``delivery_type``, ``abep_indicator``,
    ``github_link``, ``documentation_link``, ``product_link`` e a seleção de
    objetivo/resultado/indicadores. NUNCA expõe segredos.

    Args:
        project: Instância de ``Project``.

    Returns:
        ``dict`` JSON-safe com os campos do card mais os editáveis do detalhe.
    """
    card = serialize_project_card(project)
    card.update(
        {
            "observacao": project.observacao,
            "sei_process": project.sei_process,
            "delivery_type": project.delivery_type,
            "abep_indicator": project.abep_indicator,
            "github_link": project.github_link,
            "documentation_link": project.documentation_link,
            "product_link": project.product_link,
            "objetivo_id": project.objetivo_id,
            "resultado_esperado_id": project.resultado_esperado_id,
            "indicadores_ids": [ip.indicador_id for ip in project.indicadores],
        }
    )
    return card


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


def serialize_etapa_detail(
    etapa: Any,
    *,
    task_total: int = 0,
    task_done: int = 0,
) -> dict[str, Any]:
    """Serializa uma etapa para a tela de Detalhe do Projeto.

    Diferente de ``serialize_etapa_card`` (tela "Projetos Pendentes"), inclui os
    campos completos da etapa usados na seção de ETAPAS do detalhe — ``iniciada``
    (além de ``done``), os ``comentarios`` e a contagem de tarefas por etapa
    (SOMENTE LEITURA, entregue pelo backend; o cliente NÃO recalcula nem muta as
    tarefas — isso fica para a Fase 5b). As datas viram ISO 8601 (ou ``None``).
    NÃO expõe segredos.

    Args:
        etapa: Instância de ``Etapa``.
        task_total: Total de tarefas não arquivadas vinculadas à etapa.
        task_done: Tarefas finalizadas (subconjunto de ``task_total``).

    Returns:
        ``dict`` JSON-safe com os campos da etapa e ``task_count``
        ``{total, done}`` (read-only).
    """
    return {
        "id": etapa.id,
        "descricao": etapa.descricao,
        "data_inicio": _iso_or_none(etapa.data_inicio),
        "data_fim": _iso_or_none(etapa.data_fim),
        "responsavel": etapa.responsavel,
        "ordem": etapa.ordem,
        "iniciada": bool(etapa.iniciada),
        "done": bool(etapa.done),
        "comentarios": etapa.comentarios,
        "project_id": etapa.project_id,
        "entry_type": etapa.entry_type,
        "is_google_meeting": etapa.entry_type == "google_meeting",
        "task_count": {"total": int(task_total), "done": int(task_done)},
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
        "etapas_outras": [
            serialize_etapa_card(etapa) for etapa in row["etapas_outras"]
        ],
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


def serialize_template_stage_item(item: Any) -> dict[str, Any]:
    """Serializa uma etapa (``StageTemplateItem``) de um modelo de etapas.

    Usa CAMPOS REAIS de ``StageTemplateItem`` (``name``, ``duration_days``,
    ``order``). Consumido pelo form de edição/duplicação na SPA Admin.

    Args:
        item: Instância de ``StageTemplateItem``.

    Returns:
        ``dict`` JSON-safe ``{id, name, duration_days, order}``.
    """
    return {
        "id": item.id,
        "name": item.name,
        "duration_days": int(item.duration_days or 1),
        "order": item.order,
    }


def serialize_template_detail(template: Any) -> dict[str, Any]:
    """Serializa um modelo de etapas com suas etapas (form de edição).

    Usa CAMPOS REAIS de ``StageTemplate`` (``name``, ``description``,
    ``created_at``, ``updated_at``) somando as etapas ordenadas
    (``serialize_template_stage_item``) e os agregados read-only
    (``stage_count``/``total_duration``) computados no backend. NÃO expõe
    ``created_by_id``/``updated_by_id`` (apenas o nome do editor).

    Args:
        template: Instância de ``StageTemplate`` (com ``items`` carregados).

    Returns:
        ``dict`` JSON-safe com os campos do modelo e ``stages: [...]``.
    """
    items = sorted(
        getattr(template, "items", None) or [],
        key=lambda it: (it.order if it.order is not None else 0),
    )
    editor = template.updated_by or template.created_by
    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "stage_count": len(items),
        "total_duration": sum(int(it.duration_days or 0) for it in items),
        "created_at": _iso_or_none(template.created_at),
        "updated_at": _iso_or_none(template.updated_at),
        "editor_name": (editor.name if editor else None)
        or (editor.username if editor else None),
        "stages": [serialize_template_stage_item(it) for it in items],
    }


def serialize_template_row(row: dict[str, Any]) -> dict[str, Any]:
    """Serializa uma linha de lista de modelos vinda de ``_build_template_rows``.

    Recebe o ``dict`` já produzido por ``_build_template_rows``
    (``routes/admin_templates.py``) — preservando as métricas agregadas
    (``usage_count``/``stage_count``/``total_duration``) e os derivados de
    apresentação (``initials``/``is_new``/``editor_name``). Converte
    ``updated_at`` para ISO 8601 e descarta ``silhouette`` (artefato de
    renderização SVG do Jinja, não consumido pela SPA). NÃO expõe segredos.

    Args:
        row: ``dict`` de ``_build_template_rows`` (chaves ``id``/``name``/...).

    Returns:
        ``dict`` JSON-safe com as métricas e metadados do modelo para a lista.
    """
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "initials": row["initials"],
        "stage_count": row["stage_count"],
        "total_duration": row["total_duration"],
        "usage_count": row["usage_count"],
        "updated_at": _iso_or_none(row["updated_at"]),
        "updated_relative": row["updated_relative"],
        "editor_name": row["editor_name"],
        "is_new": bool(row["is_new"]),
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
