import datetime

from models import Task, db


def test_tasks_hub_template_contains_view_toggle_and_project_filter(client_user):
    response = client_user.get('/tarefas')
    assert response.status_code == 200

    html = response.get_data(as_text=True)

    required_hooks = [
        'id="taskItemsViewToggle"',
        'data-view="list"',
        'data-view="kanban"',
        'id="taskItemsListView"',
        'id="taskItemsKanbanView"',
        'id="taskItemsKanbanBoard"',
        'id="filter_project_input"',
        'id="filterProjectDropdown"',
        'id="filter_prioridade"',
        'id="filter_tipo"',
        'id="filter_status"',
        'id="filter_responsavel"',
        'class="task-hub-group"',
        'task-hub-add-row',
    ]
    for hook in required_hooks:
        assert hook in html

    assert '>Filtrar<' not in html
    assert 'id="archiveFinalizedTasksForm"' in html
    assert '>Arquivadas<' in html


def test_tasks_hub_kanban_composer_requires_project_when_no_filter(client_user):
    response = client_user.get('/tarefas')
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'task-items-kanban-add-project-input' in html
    assert 'task-hub-kanban-project-dropdown' in html


def test_tasks_hub_kanban_composer_uses_filtered_project_without_project_input(client_user, seed_data):
    response = client_user.get(f'/tarefas?project={seed_data["project_id"]}')
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'task-items-kanban-add-project-input' not in html
    assert 'task-items-kanban-add-project-value' in html


def test_tasks_hub_admin_renders_project_filter_before_area_filter(client_admin):
    response = client_admin.get('/tarefas')
    assert response.status_code == 200

    html = response.get_data(as_text=True)
    assert 'id="filter_project_input"' in html
    assert 'id="filter_area"' in html
    assert html.index('id="filter_project_input"') < html.index('id="filter_area"')


def test_tasks_hub_uses_project_links_and_not_duplicate_task_detail_link(client_user, seed_data):
    response = client_user.get('/tarefas')
    assert response.status_code == 200

    html = response.get_data(as_text=True)
    assert f'href="/project/{seed_data["project_id"]}"' in html
    assert f'href="/tarefas/{seed_data["task_id"]}"' not in html


def test_tasks_archived_template_reuses_active_list_structure_in_readonly_mode(app, client_user, seed_data):
    with app.app_context():
        archived_task = Task(
            descricao='Tarefa arquivada readonly',
            status='finalizado',
            responsavel='Usuario Editavel',
            prioridade='alta',
            tipo_pedido='bug',
            ordem=99,
            project_id=seed_data['project_id'],
            created_by_id=seed_data['user_id'],
            is_archived=True,
            archived_at=datetime.datetime.utcnow(),
        )
        db.session.add(archived_task)
        db.session.commit()

    response = client_user.get('/tarefas/arquivadas')
    assert response.status_code == 200

    html = response.get_data(as_text=True)
    required_hooks = [
        'id="taskItemsListView"',
        'class="task-hub-group"',
        'task-item-col-desc',
        'task-item-col-prioridade',
        'task-item-col-tipo',
        'task-item-col-status',
        'task-item-col-responsavel',
        'task-item-status-readonly',
        'task-item-unarchive-form',
        '>Ativas<',
    ]
    for hook in required_hooks:
        assert hook in html

    assert 'id="taskItemsViewToggle"' not in html
    assert 'id="taskItemsKanbanView"' not in html
    assert 'task-hub-add-row' not in html
    assert 'task-item-desc-edit-btn' not in html
