from flask import g

from models import (
    Project,
    Task,
    db,
)
from routes.orgao_scope import (
    expand_orgao_filter_ids,
    get_user_orgao_subtree_ids,
)
from routes.tasks.permissions import (
    task_permission_flags as _public_task_permission_flags,
)
from routes.tasks.queries import (
    _build_visible_tasks_query,
)

ARCHIVED_TASKS_PER_PAGE = 20


_NO_STAGE_BUCKET = {
    "etapa_id": None,
    "etapa_value": "sem_etapa",
    "etapa_titulo": "Sem etapa",
    "etapa_ordem": -1,
    "etapa_done": False,
    "is_legacy_bucket": True,
}

_task_permission_flags = _public_task_permission_flags


def task_permission_flags(task):
    return _task_permission_flags(task)


def _ensure_stage_bucket(stages_by_id, project_id, etapa):
    """Cria (ou retorna) o subgrupo de etapa dentro do grupo do projeto.

    ``etapa`` pode ser ``None`` (subgrupo 'Sem etapa', usado para tarefas legadas).
    """
    if etapa is None:
        key = "no_stage"
        if key in stages_by_id:
            return stages_by_id[key]
        bucket = {**_NO_STAGE_BUCKET, "tasks": [], "items": []}
        stages_by_id[key] = bucket
        return bucket
    key = f"stage:{etapa.id}"
    if key in stages_by_id:
        return stages_by_id[key]
    bucket = {
        "etapa_id": etapa.id,
        "etapa_value": str(etapa.id),
        "etapa_titulo": etapa.descricao or "Etapa sem descrição",
        "etapa_ordem": int(etapa.ordem) if etapa.ordem is not None else 0,
        "etapa_done": bool(etapa.done),
        "is_legacy_bucket": False,
        "tasks": [],
        "items": [],
    }
    stages_by_id[key] = bucket
    return bucket


def _sort_stage_buckets(stages_by_id):
    """Sem-etapa primeiro, depois etapas por ordem natural."""
    return sorted(
        stages_by_id.values(),
        key=lambda stage: (
            not stage["is_legacy_bucket"],
            stage["etapa_ordem"],
            (stage["etapa_titulo"] or "").casefold(),
        ),
    )


def _group_hub_tasks_by_project(tasks):
    groups = {}
    stages_by_group = {}

    for task in tasks:
        project = task.project
        project_id = project.id if project else None
        project_title = (project.titulo if project else "Sem projeto") or "Sem projeto"
        project_orgao_sigla = (
            project.orgao_ref.sigla if project and project.orgao_ref else None
        )
        project_value = str(project_id) if project_id else "sem_projeto"
        group_key = f"project:{project_id}" if project_id else "sem_projeto"

        if group_key not in groups:
            groups[group_key] = {
                "key": group_key,
                "project_id": project_id,
                "project_value": project_value,
                "project_titulo": project_title,
                "project_orgao_sigla": project_orgao_sigla,
                "tasks": [],
                # Compatibilidade com template/JS legado.
                "items": [],
                "stages": [],
            }
            stages_by_group[group_key] = {}

        task.hub_project_value = project_value
        task.hub_project_titulo = project_title
        task.hub_task_titulo = task.descricao
        task.hub_task_id = task.id
        permission_flags = task_permission_flags(task)
        task.hub_can_delete = permission_flags["can_delete"]
        task.hub_can_finalize = permission_flags["can_finalize"]
        task.hub_is_author = permission_flags["is_author"]

        groups[group_key]["tasks"].append(task)
        groups[group_key]["items"].append(task)

        # Subgrupo por etapa só faz sentido quando há projeto — tarefas sem
        # projeto continuam ficando no bucket 'sem_projeto' direto.
        if project_id is not None:
            stage_bucket = _ensure_stage_bucket(
                stages_by_group[group_key], project_id, task.etapa
            )
            stage_bucket["tasks"].append(task)
            stage_bucket["items"].append(task)

    for group_key, stages_by_id in stages_by_group.items():
        stages = _sort_stage_buckets(stages_by_id)
        visible_stage_index = 0
        for stage in stages:
            if stage["is_legacy_bucket"]:
                stage["etapa_display_id"] = ""
                continue
            visible_stage_index += 1
            stage["etapa_display_id"] = (
                f"{groups[group_key]['project_id']}.{visible_stage_index}"
            )
        groups[group_key]["stages"] = stages
        _flatten_stage_tasks_into_group(groups[group_key], stages)

    ordered_groups = sorted(
        groups.values(),
        key=lambda group: (
            group["project_id"] is None,
            (group["project_titulo"] or "").casefold(),
        ),
    )

    return ordered_groups


def _flatten_stage_tasks_into_group(group, stages):
    """Reordena group['tasks'] para refletir a hierarquia de etapas.

    Sem etapa primeiro, depois etapas por ordem natural; tasks dentro de cada
    etapa preservam a ordenação que veio do banco. Marca a primeira task de
    cada etapa com ``hub_is_first_of_stage`` — o template usa esse flag para
    renderizar o sub-cabeçalho sem duplicar markup.
    """
    flat = []
    for stage in stages:
        for index, task in enumerate(stage["tasks"]):
            task.hub_stage_id = stage["etapa_id"]
            task.hub_stage_value = stage["etapa_value"]
            task.hub_stage_titulo = stage["etapa_titulo"]
            task.hub_stage_display_id = stage.get("etapa_display_id") or None
            task.hub_stage_is_legacy_bucket = stage["is_legacy_bucket"]
            task.hub_stage_done = stage["etapa_done"]
            task.hub_is_first_of_stage = index == 0
            flat.append(task)
    if flat:
        group["tasks"] = flat
        group["items"] = list(flat)


def _build_task_hub_project_options(include_archived=False, orgao_filter_id=None):
    query = Project.query

    if not g.user.is_admin:
        subtree_ids = get_user_orgao_subtree_ids(g.user)
        if subtree_ids:
            query = query.filter(Project.orgao_id.in_(subtree_ids))
        else:
            query = query.filter(db.false())

    if orgao_filter_id is not None:
        filter_subtree_ids = expand_orgao_filter_ids(orgao_filter_id)
        if filter_subtree_ids:
            query = query.filter(Project.orgao_id.in_(filter_subtree_ids))
        else:
            query = query.filter(db.false())

    projects = query.order_by(
        db.func.lower(Project.titulo), Project.titulo.asc(), Project.id.asc()
    ).all()
    options = [
        {
            "value": str(project.id),
            "label": project.titulo,
            "orgao_sigla": project.orgao_ref.sigla if project.orgao_ref else "",
        }
        for project in projects
    ]

    has_orphan_tasks = orgao_filter_id is None and (
        _build_visible_tasks_query(
            include_archived=include_archived,
            project_filter="sem_projeto",
            include_relations=False,
        )
        .limit(1)
        .first()
        is not None
    )
    if has_orphan_tasks:
        options.append(
            {
                "value": "sem_projeto",
                "label": "Sem projeto",
                "orgao_sigla": "",
            }
        )

    return options


def build_task_hub_context(
    *,
    project_filter="",
    prioridade_filter="",
    tipo_filter="",
    status_filter="",
    responsavel_filter="",
    selected_orgao_id=None,
    include_archived=False,
):
    """Monta os dados do Hub de Tarefas em modo lista (sem kanban).

    Centraliza a montagem das tarefas agrupadas por projeto e das opções de
    projeto reusando os MESMOS helpers de query e agrupamento
    (``_build_visible_tasks_query`` / ``_group_hub_tasks_by_project`` /
    ``_build_task_hub_project_options``). Os consumidores são ``GET
    /api/tarefas`` (``routes/api/tasks.py:30``) e ``routes/tasks/helpers.py:43``
    — a fonte de verdade dos dados do hub; a rota ``/tarefas`` hoje serve
    apenas a shell da SPA. O escopo de órgão é server-side; o chamador sanitiza
    o filtro de órgão.

    Args:
        project_filter: ID do projeto como string, "sem_projeto" ou "" (todos).
        prioridade_filter: Filtro de prioridade (ou "").
        tipo_filter: Filtro de tipo de pedido (ou "").
        status_filter: Filtro de status da tarefa (ou "").
        responsavel_filter: Filtro de responsável (substring, normalizado).
        selected_orgao_id: ID de órgão já validado para o usuário (ou ``None``).
        include_archived: Quando ``True``, lista tarefas arquivadas.

    Returns:
        ``dict`` com ``groups`` (tarefas agrupadas por projeto e subagrupadas por
        etapa), ``project_options``, os filtros selecionados e ``total_items``.
    """
    tasks = _build_visible_tasks_query(
        include_archived=include_archived,
        project_filter=project_filter,
        prioridade_filter=prioridade_filter,
        tipo_filter=tipo_filter,
        status_filter=status_filter,
        responsavel_filter=responsavel_filter,
        orgao_filter_id=selected_orgao_id,
    ).all()
    groups = _group_hub_tasks_by_project(tasks)
    project_options = _build_task_hub_project_options(
        include_archived=include_archived,
        orgao_filter_id=selected_orgao_id,
    )
    return {
        "groups": groups,
        "project_options": project_options,
        "selected_orgao": selected_orgao_id,
        "selected_project": project_filter,
        "selected_prioridade": prioridade_filter,
        "selected_tipo": tipo_filter,
        "selected_status": status_filter,
        "selected_responsavel": responsavel_filter,
        "include_archived": include_archived,
        "total_items": len(tasks),
    }
