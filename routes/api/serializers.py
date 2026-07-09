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

from services.calendar_core import format_human_datetime, format_input_datetime


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


def _author_display_name(user: Any, *, fallback: str = "Usuário") -> str:
    """Nome de exibição de um autor, sufixado "(removido)" se soft-deletado.

    Soft-delete C4: em contextos HISTÓRICOS (autor de comentário/anexo/histórico)
    o usuário removido continua resolvendo o nome, mas sinalizamos a remoção para
    a UI. NUNCA quebra quando ``user`` é ``None``.

    Args:
        user: Instância de ``User`` (ou ``None``).
        fallback: Nome usado quando ``user`` é ``None`` ou sem nome.

    Returns:
        ``str`` com o nome (mais " (removido)" quando ``deleted_at`` está setado).
    """
    if user is None:
        return fallback
    base = user.name or user.username or fallback
    if getattr(user, "deleted_at", None) is not None:
        return f"{base} (removido)"
    return base


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
        # delivery_type também no card (lista de projetos): o front filtra/exibe
        # o tipo de entrega sem precisar do payload completo de detalhe.
        "delivery_type": project.delivery_type,
        # derivados read-only (computados no backend; NÃO recalcular no cliente)
        "data_inicio_projeto": _iso_or_none(project.data_inicio_projeto),
        "data_fim_projeto": _iso_or_none(project.data_fim_projeto),
        "total_workflow_etapas": project.total_workflow_etapas,
        "etapas_concluidas": project.etapas_concluidas,
        "todas_etapas_concluidas": project.todas_etapas_concluidas,
    }


def serialize_project_detail(project: Any) -> dict[str, Any]:
    """Serializa um projeto para a tela de Detalhe (card + campos editáveis).

    Reusa ``serialize_project_card`` (id/titulo/status/derivados read-only) e
    soma os demais campos editáveis inline do projeto que NÃO estão no card —
    ``observacao``, ``sei_processes``, ``delivery_type``, ``abep_indicator``,
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
            "sei_processes": [item.numero for item in project.sei_processes],
            # Compat 1 release: bundle SPA cacheado pré-deploy lê o escalar antigo.
            "sei_process": (
                project.sei_processes[0].numero if project.sei_processes else None
            ),
            "delivery_type": project.delivery_type,
            "abep_indicator": project.abep_indicator,
            "github_link": project.github_link,
            "documentation_link": project.documentation_link,
            "product_link": project.product_link,
            "objetivo_id": project.objetivo_id,
            "resultado_esperado_id": project.resultado_esperado_id,
            "indicadores_ids": [ip.indicador_id for ip in project.indicadores],
            # Descrições EEGG (somente leitura) para a seção de detalhes — o
            # cliente só tem os IDs, então enviamos os textos prontos.
            "objetivo_descricao": (
                project.objetivo.descricao if project.objetivo else None
            ),
            "resultado_esperado_descricao": (
                project.resultado_esperado.descricao
                if project.resultado_esperado
                else None
            ),
            "indicadores_descricoes": [
                ip.indicador.descricao
                for ip in project.indicadores
                if ip.indicador is not None
            ],
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
        "iniciada": bool(etapa.iniciada),
        "done": bool(etapa.done),
        "project_id": etapa.project_id,
        "entry_type": etapa.entry_type,
    }


def serialize_etapa_detail(
    etapa: Any,
    *,
    task_total: int = 0,
    task_done: int = 0,
    meeting: dict[str, Any] | None = None,
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
    payload: dict[str, Any] = {
        "id": etapa.id,
        "descricao": etapa.descricao,
        "data_inicio": _iso_or_none(etapa.data_inicio),
        "data_fim": _iso_or_none(etapa.data_fim),
        "responsavel": etapa.responsavel,
        "responsaveis": [
            {
                "area_id": r.area_id,
                "label": r.area.sigla if r.area is not None else r.label,
            }
            for r in etapa.responsaveis
        ],
        "ordem": etapa.ordem,
        "iniciada": bool(etapa.iniciada),
        "done": bool(etapa.done),
        "comentarios": etapa.comentarios,
        "project_id": etapa.project_id,
        "entry_type": etapa.entry_type,
        "is_google_meeting": etapa.entry_type == "google_meeting",
        "task_count": {"total": int(task_total), "done": int(task_done)},
    }
    # Reuniões Google (Fase 6): bloco read-only com os dados do evento Google e
    # as permissões de gerência/edição já calculadas no backend. NUNCA inclui
    # tokens OAuth — apenas o e-mail do dono já exposto no payload de etapa.
    if meeting is not None:
        payload["meeting"] = meeting
    return payload


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
                "is_deleted": getattr(author, "deleted_at", None) is not None,
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
    ``updated_at`` para ISO 8601 e repassa ``silhouette`` — lista de pares
    ``[altura, duracao]`` (de ``_silhouette_bars``) que a coluna Silhueta da tela
    de templates renderiza como mini-gráfico. NÃO expõe segredos.

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
        # Pares [altura, duracao]: ``_silhouette_bars`` devolve tuplas; JSON as
        # serializa como listas — o front desenha as barras direto desses pares.
        "silhouette": [list(bar) for bar in (row.get("silhouette") or [])],
        "usage_count": row["usage_count"],
        "updated_at": _iso_or_none(row["updated_at"]),
        "updated_relative": row["updated_relative"],
        "editor_name": row["editor_name"],
        "is_new": bool(row["is_new"]),
    }


def serialize_task_card(task: Any) -> dict[str, Any]:
    """Serializa uma tarefa no formato de "card" para listas/dashboard/Kanban.

    Task e TaskItem são a MESMA tabela; existe um único tipo ``Task``. Usa
    CAMPOS REAIS (``descricao``, ``is_archived``, ``archived_at``) — sem aliases
    legados (``titulo``/``is_finalized``) vazando para o frontend.

    Inclui ``permissions.can_finalize`` (derivado de
    ``routes/tasks/permissions.task_permission_flags`` para o usuário corrente em
    ``flask.g``). O Kanban (Fase 5b-1) usa esse flag SÓ para UX (habilitar/desabilitar
    o drop na coluna "finalizada"); a decisão autoritativa continua server-side em
    ``_can_transition_task_to_status``. Quando não há contexto de usuário (ex.: uso
    fora de request), ``can_finalize`` cai para ``False``.

    Args:
        task: Instância de ``Task``.

    Returns:
        ``dict`` JSON-safe com os campos do card da tarefa, incluindo
        ``permissions.can_finalize``.
    """
    from routes.tasks.permissions import task_permission_flags
    from routes.tasks.queries import serialize_task_assignees

    flags = task_permission_flags(task)
    # ``task.project`` é o relacionamento já carregado (backref em models/task.py);
    # a mini-lista "Recentes" mostra o nome do projeto em vez de "Projeto #id".
    project = getattr(task, "project", None)
    return {
        "id": task.id,
        "descricao": task.descricao,
        "status": task.status,
        "responsavel": task.responsavel,
        "assignees": serialize_task_assignees(task),
        "prioridade": task.prioridade,
        "tipo_pedido": task.tipo_pedido,
        "ordem": task.ordem,
        "project_id": task.project_id,
        "project_titulo": project.titulo if project is not None else None,
        "etapa_id": task.etapa_id,
        "created_by_id": task.created_by_id,
        "created_at": _iso_or_none(task.created_at),
        "is_archived": bool(task.is_archived),
        "archived_at": _iso_or_none(task.archived_at),
        # Contadores exibidos no rodapé do card do Kanban (balão de comentários e
        # clipe de anexos). A query do board (`_build_visible_tasks_query` com
        # ``include_relations=True``) já faz joinedload de ambos — sem N+1 ali.
        "comments_count": len(task.comments),
        "anexos_count": len(task.anexos),
        "permissions": {"can_finalize": bool(flags["can_finalize"])},
    }


def _serialize_task_comment(
    comment: Any, *, current_user_id: int | None
) -> dict[str, Any]:
    """Serializa um comentário de tarefa para o drawer (sem segredos).

    Usa CAMPOS REAIS de ``TaskComment`` (``content``, ``created_at``,
    ``updated_at``) e um vínculo mínimo do autor (id/nome) — NUNCA expõe
    ``password_hash`` nem credenciais. ``can_edit``/``can_delete`` espelham a
    regra das rotas legadas (``comments.py``): só o próprio autor edita/exclui.

    Args:
        comment: Instância de ``TaskComment``.
        current_user_id: ID do usuário corrente (para derivar ``is_own``).

    Returns:
        ``dict`` JSON-safe com os campos do comentário e flags de permissão.
    """
    author = getattr(comment, "author", None)
    is_own = bool(current_user_id is not None and comment.user_id == current_user_id)
    return {
        "id": comment.id,
        "content": comment.content,
        "user_id": comment.user_id,
        "author_name": _author_display_name(author),
        "author_is_deleted": bool(
            author is not None and getattr(author, "deleted_at", None) is not None
        ),
        "created_at": _iso_or_none(comment.created_at),
        "updated_at": _iso_or_none(comment.updated_at),
        "is_own": is_own,
        "can_edit": is_own,
        "can_delete": is_own,
    }


def _serialize_task_anexo(
    anexo: Any, *, download_url: str | None = None
) -> dict[str, Any]:
    """Serializa um anexo de tarefa para o drawer (sem segredos).

    Usa CAMPOS REAIS de ``TaskAnexo`` (``filename``, ``content_type``,
    ``created_at``) e o nome de quem subiu (sem expor ids internos sensíveis).
    NÃO inclui ``stored_filename`` (nome físico no disco) no payload. O
    ``download_url`` aponta para o ``send_file`` binário legado (mesma origin).

    Args:
        anexo: Instância de ``TaskAnexo``.
        download_url: URL absoluta/relativa do download binário (``view_task_item_anexo``).

    Returns:
        ``dict`` JSON-safe com os campos do anexo e ``url`` de download.
    """
    content_type = anexo.content_type or ""
    uploaded_by = getattr(anexo, "uploaded_by", None)
    return {
        "id": anexo.id,
        "filename": anexo.filename,
        "content_type": content_type,
        "is_image": content_type.startswith("image/"),
        "uploaded_by": _author_display_name(uploaded_by),
        "created_at": _iso_or_none(anexo.created_at),
        "url": download_url,
    }


def serialize_task_detail(
    task: Any,
    *,
    permissions: dict[str, bool] | None = None,
    anexo_url_for: Any = None,
) -> dict[str, Any]:
    """Serializa o payload completo de uma tarefa para o DRAWER (Fase 5b-2).

    Reusa ``serialize_task_card`` (campos editáveis inline + ``permissions.can_finalize``
    UX-only) e SOMA o contexto do drawer que o card não traz: o vínculo de
    etapa/projeto (para o cabeçalho de contexto), a lista de ``comentarios`` e de
    ``anexos`` (serializados sem segredos) e o bloco autoritativo de
    ``permissions`` ``{can_edit, can_finalize, can_delete}`` derivado server-side
    (``task_permission_flags``). Task e TaskItem são a MESMA tabela.

    NUNCA expõe segredos: ``stored_filename`` do anexo (caminho físico) e
    ``password_hash``/credenciais de autores ficam de fora.

    Args:
        task: Instância de ``Task``.
        permissions: Flags autoritativos do usuário corrente
            (``task_permission_flags``); quando ``None``, cai para tudo ``False``.
        anexo_url_for: Callable ``(anexo) -> str`` que monta a URL de download
            binário (``url_for("main.view_task_item_anexo", ...)``). Quando
            ``None``, ``url`` do anexo fica ``None`` (ex.: uso fora de request).

    Returns:
        ``dict`` JSON-safe com os campos do card mais ``etapa``/``project``
        (contexto), ``comentarios: [...]``, ``anexos: [...]`` e ``permissions``.
    """
    from flask import g

    perms = permissions or {}
    current_user = getattr(g, "user", None)
    current_user_id = getattr(current_user, "id", None)

    card = serialize_task_card(task)
    etapa = getattr(task, "etapa", None)
    project = getattr(task, "project", None)
    card.update(
        {
            "etapa": (
                {"id": etapa.id, "descricao": etapa.descricao, "done": bool(etapa.done)}
                if etapa is not None
                else None
            ),
            "project": (
                {"id": project.id, "titulo": project.titulo}
                if project is not None
                else None
            ),
            "comentarios": [
                _serialize_task_comment(comment, current_user_id=current_user_id)
                for comment in (task.comments or [])
            ],
            "anexos": [
                _serialize_task_anexo(
                    anexo,
                    download_url=(anexo_url_for(anexo) if anexo_url_for else None),
                )
                for anexo in (task.anexos or [])
            ],
            "permissions": {
                "can_edit": bool(perms.get("can_edit", perms.get("can_manage", False))),
                "can_finalize": bool(perms.get("can_finalize", False)),
                "can_delete": bool(perms.get("can_delete", False)),
            },
        }
    )
    return card


def serialize_calendar_event(event: Any) -> dict[str, Any]:
    """Serializa um ``CalendarEvent`` para o hub de calendário da SPA.

    Espelha ``routes/calendars/helpers._event_json`` (datas em formato de input
    + display, ``sync_status``/``source``/``meet_link``/``is_all_day``) e
    ACRESCENTA ``sync_error`` (mensagem de erro de sincronização, quando houver),
    necessário ao hub. Reusa ``format_human_datetime``/``format_input_datetime``
    de ``services.calendar_core`` — a mesma fonte que ``helpers`` encapsula — sem
    tocar ``helpers.py``. NÃO expõe tokens.

    Args:
        event: Instância de ``CalendarEvent``.

    Returns:
        ``dict`` JSON-safe com os campos do evento + ``sync_error``.
    """
    return {
        "id": event.id,
        "title": event.title,
        "description": event.description or "",
        "location": event.location or "",
        "starts_at": format_input_datetime(event.starts_at),
        "ends_at": format_input_datetime(event.ends_at),
        "starts_at_display": format_human_datetime(event.starts_at),
        "ends_at_display": format_human_datetime(event.ends_at),
        "sync_status": event.sync_status,
        "sync_error": event.sync_error or "",
        "source": event.source,
        "meet_link": event.meet_link or "",
        "is_all_day": bool(event.is_all_day),
    }
