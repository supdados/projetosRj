def test_task_detail_template_contains_view_toggle_hooks(client_user, seed_data):
    response = client_user.get(f"/tarefas/{seed_data['task_id']}")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    required_hooks = [
        'id="taskItemsViewToggle"',
        'data-view="list"',
        'data-view="kanban"',
        'id="taskItemsListView"',
        'id="taskItemsKanbanView"',
        'id="taskItemsKanbanBoard"',
        'data-reorder-url="',
    ]

    for hook in required_hooks:
        assert hook in html


def test_task_detail_template_contains_kanban_status_columns(client_user, seed_data):
    response = client_user.get(f"/tarefas/{seed_data['task_id']}")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    required_status_columns = [
        'data-status="programado"',
        'data-status="em_andamento"',
        'data-status="validacao"',
        'data-status="finalizado"',
    ]

    for status_hook in required_status_columns:
        assert status_hook in html
