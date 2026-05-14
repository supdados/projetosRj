from flask import g, render_template, request

from models import (
    Project,
    Task,
    db,
)
from routes.orgao_scope import (
    expand_orgao_filter_ids,
    get_user_orgao_subtree_ids,
    redirect_to_current_route_without_orgao,
    sanitize_orgao_filter_for_current_user,
)
from routes.shared import _get_orgaos_disponiveis_for_current_user
from routes.tasks.permissions import task_permission_flags as _public_task_permission_flags
from routes.tasks.queries import (
    _build_task_filter_options,
    _build_task_listing_url,
    _build_visible_tasks_query,
    _read_task_filter_values,
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


def _render_task_hub(
    locked_project=None, template_name="tasks/hub.html", include_archived=False
):
    filter_values = _read_task_filter_values(request.args)
    selected_orgao_id, invalid_orgao_filter = sanitize_orgao_filter_for_current_user(
        filter_values["orgao_filter"]
    )
    if invalid_orgao_filter and locked_project is None:
        return redirect_to_current_route_without_orgao()
    if locked_project is not None:
        selected_orgao_id = None
    # `ORGAOS_DISPONIVEIS` é injetado no contexto do template pelo context
    # processor `inject_current_year`, não em `flask.g` — chamamos o helper
    # diretamente para que `selected_orgao_sigla` não fique sempre vazio.
    orgaos_disponiveis = _get_orgaos_disponiveis_for_current_user()
    orgao_label_map = {
        str(orgao_id): orgao_sigla
        for orgao_id, orgao_sigla, _orgao_nome in orgaos_disponiveis
    }
    selected_orgao_sigla = (
        orgao_label_map.get(str(selected_orgao_id), "")
        if selected_orgao_id is not None
        else ""
    )
    project_filter = filter_values["project_filter"]
    prioridade_filter = filter_values["prioridade_filter"]
    tipo_filter = filter_values["tipo_filter"]
    status_filter = filter_values["status_filter"]
    responsavel_filter = filter_values["responsavel_filter"]

    if locked_project is not None:
        project_filter = str(locked_project.id)

    tasks_query = _build_visible_tasks_query(
        include_archived=include_archived,
        project_filter=project_filter,
        prioridade_filter=prioridade_filter,
        tipo_filter=tipo_filter,
        status_filter=status_filter,
        responsavel_filter=responsavel_filter,
        orgao_filter_id=selected_orgao_id,
    )
    archived_pagination = None
    if include_archived:
        page = request.args.get("page", 1, type=int)
        if page < 1:
            page = 1
        archived_pagination = tasks_query.paginate(
            page=page,
            per_page=ARCHIVED_TASKS_PER_PAGE,
            error_out=False,
        )
        tasks = archived_pagination.items
    else:
        tasks = tasks_query.all()
    groups = _group_hub_tasks_by_project(tasks)
    if locked_project is not None and not include_archived and not groups:
        groups = [
            {
                "key": f"project:{locked_project.id}",
                "project_id": locked_project.id,
                "project_value": str(locked_project.id),
                "project_titulo": locked_project.titulo,
                "project_orgao_sigla": (
                    locked_project.orgao_ref.sigla if locked_project.orgao_ref else None
                ),
                "tasks": [],
                "items": [],
            }
        ]

    project_options = _build_task_hub_project_options(
        include_archived=include_archived,
        orgao_filter_id=selected_orgao_id,
    )

    project_label_map = {opt["value"]: opt["label"] for opt in project_options}
    selected_project_label = project_label_map.get(project_filter, "")
    if not selected_project_label and project_filter == "sem_projeto":
        selected_project_label = "Sem projeto"
    if locked_project is not None and not selected_project_label:
        selected_project_label = locked_project.titulo

    attribute_scope_tasks = _build_visible_tasks_query(
        include_archived=include_archived,
        project_filter=project_filter,
        include_relations=False,
    ).all()
    filter_options = _build_task_filter_options(
        attribute_scope_tasks,
        selected_filters={
            "prioridade_filter": prioridade_filter,
            "tipo_filter": tipo_filter,
            "status_filter": status_filter,
            "responsavel_filter": responsavel_filter,
        },
    )

    filter_form_endpoint = (
        "main.list_tasks_archived" if include_archived else "main.list_tasks"
    )
    filter_form_action = _build_task_listing_url(filter_form_endpoint)
    clear_endpoint = (
        "main.list_tasks_archived" if include_archived else "main.list_tasks"
    )
    clear_url = _build_task_listing_url(clear_endpoint)

    archived_url = None
    active_url = None
    active_count = None
    archived_page_urls = {}
    archived_page_entries = []
    if include_archived:
        def archived_page_url(page_number):
            return _build_task_listing_url(
                "main.list_tasks_archived",
                orgao_filter=str(selected_orgao_id or ""),
                project_filter=project_filter,
                prioridade_filter=prioridade_filter,
                tipo_filter=tipo_filter,
                status_filter=status_filter,
                responsavel_filter=responsavel_filter,
                page=page_number,
            )

        if archived_pagination is not None:
            archived_page_urls = {
                "first": archived_page_url(1),
                "prev": archived_page_url(archived_pagination.prev_num),
                "next": archived_page_url(archived_pagination.next_num),
                "last": archived_page_url(archived_pagination.pages or 1),
            }
            archived_page_entries = [
                {"page": page_number, "url": archived_page_url(page_number)}
                if page_number
                else None
                for page_number in archived_pagination.iter_pages(
                    left_edge=1,
                    right_edge=1,
                    left_current=1,
                    right_current=2,
                )
            ]
        active_url = _build_task_listing_url(
            "main.list_tasks",
            orgao_filter=str(selected_orgao_id or ""),
            project_filter=project_filter,
            prioridade_filter=prioridade_filter,
            tipo_filter=tipo_filter,
            status_filter=status_filter,
            responsavel_filter=responsavel_filter,
        )
        active_count = _build_visible_tasks_query(
            include_archived=False,
            project_filter=project_filter,
            prioridade_filter=prioridade_filter,
            tipo_filter=tipo_filter,
            status_filter=status_filter,
            responsavel_filter=responsavel_filter,
            orgao_filter_id=selected_orgao_id,
            include_relations=False,
        ).count()
    else:
        archived_url = _build_task_listing_url(
            "main.list_tasks_archived",
            orgao_filter=str(selected_orgao_id or ""),
            project_filter=project_filter,
            prioridade_filter=prioridade_filter,
            tipo_filter=tipo_filter,
            status_filter=status_filter,
            responsavel_filter=responsavel_filter,
        )

    if include_archived:
        page_title = "Tarefas arquivadas"
        page_subtitle = "Itens retirados da visão ativa"
        section_title = "Tarefas arquivadas"
        empty_title = "Nenhuma tarefa arquivada"
        empty_text = "Ajuste os filtros ou arquive tarefas na visão ativa."
    elif locked_project:
        page_title = "Tarefas"
        page_subtitle = "Gerenciamento de tarefas"
        section_title = "Tarefas ativas"
        empty_title = "Nenhuma tarefa neste projeto"
        empty_text = "Não há tarefas ativas visíveis neste projeto."
    else:
        page_title = "Tarefas"
        page_subtitle = "Gerenciamento de tarefas"
        section_title = "Tarefas ativas"
        empty_title = "Nenhuma tarefa encontrada"
        empty_text = "Ajuste os filtros para visualizar tarefas ativas."

    return render_template(
        template_name,
        archived_mode=include_archived,
        groups=groups,
        project_options=project_options,
        selected_project=project_filter,
        selected_project_label=selected_project_label,
        selected_orgao=selected_orgao_id,
        selected_orgao_sigla=selected_orgao_sigla,
        selected_prioridade=prioridade_filter,
        selected_tipo=tipo_filter,
        selected_status=status_filter,
        selected_responsavel=responsavel_filter,
        prioridade_options=filter_options["prioridade_options"],
        tipo_options=filter_options["tipo_options"],
        status_options=filter_options["status_options"],
        responsavel_options=filter_options["responsavel_options"],
        total_items=archived_pagination.total if archived_pagination else len(tasks),
        archived_pagination=archived_pagination,
        archived_per_page=ARCHIVED_TASKS_PER_PAGE if include_archived else None,
        archived_page_urls=archived_page_urls,
        archived_page_entries=archived_page_entries,
        project_locked=bool(locked_project),
        project_locked_obj=locked_project,
        page_title=page_title,
        page_subtitle=page_subtitle,
        section_title=section_title,
        empty_title=empty_title,
        empty_text=empty_text,
        filter_form_action=filter_form_action,
        clear_url=clear_url,
        archived_url=archived_url,
        active_url=active_url,
        active_count=active_count,
    )
