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
from routes.tasks.permissions import _task_permission_flags
from routes.tasks.queries import (
    _build_task_filter_options,
    _build_task_listing_url,
    _build_visible_tasks_query,
    _read_task_filter_values,
)


def _group_hub_tasks_by_project(tasks):
    groups = {}

    for task in tasks:
        project = task.project
        project_id = project.id if project else None
        project_title = (project.titulo if project else 'Sem projeto') or 'Sem projeto'
        project_orgao_sigla = (project.orgao_ref.sigla if project and project.orgao_ref else None)
        project_value = str(project_id) if project_id else 'sem_projeto'
        group_key = f'project:{project_id}' if project_id else 'sem_projeto'

        if group_key not in groups:
            groups[group_key] = {
                'key': group_key,
                'project_id': project_id,
                'project_value': project_value,
                'project_titulo': project_title,
                'project_orgao_sigla': project_orgao_sigla,
                'tasks': [],
                # Compatibilidade com template/JS legado.
                'items': [],
            }

        task.hub_project_value = project_value
        task.hub_project_titulo = project_title
        task.hub_task_titulo = task.descricao
        task.hub_task_id = task.id
        permission_flags = _task_permission_flags(task)
        task.hub_can_delete = permission_flags['can_delete']
        task.hub_can_finalize = permission_flags['can_finalize']
        task.hub_is_author = permission_flags['is_author']

        groups[group_key]['tasks'].append(task)
        groups[group_key]['items'].append(task)

    ordered_groups = sorted(
        groups.values(),
        key=lambda group: (
            group['project_id'] is None,
            (group['project_titulo'] or '').casefold(),
        ),
    )

    return ordered_groups


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

    projects = query.order_by(db.func.lower(Project.titulo), Project.titulo.asc(), Project.id.asc()).all()
    options = [
        {
            'value': str(project.id),
            'label': project.titulo,
            'orgao_sigla': project.orgao_ref.sigla if project.orgao_ref else '',
        }
        for project in projects
    ]

    has_orphan_tasks = (
        orgao_filter_id is None
        and (
            _build_visible_tasks_query(
                include_archived=include_archived,
                project_filter='sem_projeto',
                include_relations=False,
            )
            .limit(1)
            .first()
            is not None
        )
    )
    if has_orphan_tasks:
        options.append(
            {
                'value': 'sem_projeto',
                'label': 'Sem projeto',
                'orgao_sigla': '',
            }
        )

    return options


def _render_task_hub(locked_project=None, template_name='tasks/hub.html', include_archived=False):
    filter_values = _read_task_filter_values(request.args)
    selected_orgao_id, invalid_orgao_filter = sanitize_orgao_filter_for_current_user(
        filter_values['orgao_filter']
    )
    if invalid_orgao_filter and locked_project is None:
        return redirect_to_current_route_without_orgao()
    if locked_project is not None:
        selected_orgao_id = None
    orgaos_disponiveis = list(g.get('ORGAOS_DISPONIVEIS') or [])
    orgao_label_map = {str(orgao_id): orgao_sigla for orgao_id, orgao_sigla, _orgao_nome in orgaos_disponiveis}
    selected_orgao_sigla = orgao_label_map.get(str(selected_orgao_id), '') if selected_orgao_id is not None else ''
    project_filter = filter_values['project_filter']
    prioridade_filter = filter_values['prioridade_filter']
    tipo_filter = filter_values['tipo_filter']
    status_filter = filter_values['status_filter']
    responsavel_filter = filter_values['responsavel_filter']

    if locked_project is not None:
        project_filter = str(locked_project.id)

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
    if locked_project is not None and not include_archived and not groups:
        groups = [
            {
                'key': f'project:{locked_project.id}',
                'project_id': locked_project.id,
                'project_value': str(locked_project.id),
                'project_titulo': locked_project.titulo,
                'project_orgao_sigla': locked_project.orgao_ref.sigla if locked_project.orgao_ref else None,
                'tasks': [],
                'items': [],
            }
        ]

    project_options = _build_task_hub_project_options(
        include_archived=include_archived,
        orgao_filter_id=selected_orgao_id,
    )

    project_label_map = {opt['value']: opt['label'] for opt in project_options}
    selected_project_label = project_label_map.get(project_filter, '')
    if not selected_project_label and project_filter == 'sem_projeto':
        selected_project_label = 'Sem projeto'
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
            'prioridade_filter': prioridade_filter,
            'tipo_filter': tipo_filter,
            'status_filter': status_filter,
            'responsavel_filter': responsavel_filter,
        },
    )

    filter_form_endpoint = 'main.list_tasks_archived' if include_archived else 'main.list_tasks'
    filter_form_action = _build_task_listing_url(filter_form_endpoint)
    clear_endpoint = 'main.list_tasks_archived' if include_archived else 'main.list_tasks'
    clear_url = _build_task_listing_url(clear_endpoint)

    archived_url = None
    active_url = None
    active_count = None
    if include_archived:
        active_url = _build_task_listing_url(
            'main.list_tasks',
            orgao_filter=str(selected_orgao_id or ''),
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
            'main.list_tasks_archived',
            orgao_filter=str(selected_orgao_id or ''),
            project_filter=project_filter,
            prioridade_filter=prioridade_filter,
            tipo_filter=tipo_filter,
            status_filter=status_filter,
            responsavel_filter=responsavel_filter,
        )

    if include_archived:
        page_title = 'Tarefas arquivadas'
        page_subtitle = 'Itens retirados da visão ativa'
        section_title = 'Tarefas arquivadas'
        empty_title = 'Nenhuma tarefa arquivada'
        empty_text = 'Ajuste os filtros ou arquive tarefas na visão ativa.'
    elif locked_project:
        page_title = 'Tarefas'
        page_subtitle = 'Gerenciamento de tarefas'
        section_title = 'Tarefas ativas'
        empty_title = 'Nenhuma tarefa neste projeto'
        empty_text = 'Não há tarefas ativas visíveis neste projeto.'
    else:
        page_title = 'Tarefas'
        page_subtitle = 'Gerenciamento de tarefas'
        section_title = 'Tarefas ativas'
        empty_title = 'Nenhuma tarefa encontrada'
        empty_text = 'Ajuste os filtros para visualizar tarefas ativas.'

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
        prioridade_options=filter_options['prioridade_options'],
        tipo_options=filter_options['tipo_options'],
        status_options=filter_options['status_options'],
        responsavel_options=filter_options['responsavel_options'],
        total_items=len(tasks),
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
