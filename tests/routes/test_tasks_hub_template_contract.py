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
