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
        'data-current-user-id="',
        'id="taskItemDrawer"',
        'id="taskItemDrawerBackdrop"',
        'id="taskItemDrawerDesc"',
        'id="taskItemDrawerAutosaveStatus"',
        'id="taskItemDrawerResponsavelTrigger"',
        'id="taskItemDrawerCommentsList"',
        'id="taskItemDrawerCommentForm"',
        'id="taskItemDrawerCommentsToggle"',
        'id="taskItemDrawerCommentsBody"',
        'id="taskItemDrawerDeleteIcon"',
        'id="taskItemDrawerCommentsStatus"',
        'id="taskItemDrawerDeleteConfirmBtn"',
        'id="taskQuickAnexoInput"',
        'id="taskAnexoPreviewModal"',
        'id="taskAnexoPreviewBackdrop"',
        'task-items-kanban-delete-btn',
        'kanban-open-comments',
        'kanban-open-anexos',
    ]

    for hook in required_hooks:
        assert hook in html

    assert 'task-items-kanban-open-list' not in html
    assert 'Abrir na lista' not in html
    assert 'id="taskHeaderSave"' not in html
    assert 'id="taskHeaderCancel"' not in html
    assert 'id="taskItemDrawerSave"' not in html
    assert 'id="taskItemDrawerDeleteTrigger"' not in html


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


def test_task_detail_template_contains_kanban_column_add_hooks(client_user, seed_data):
    response = client_user.get(f"/tarefas/{seed_data['task_id']}")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    required_add_hooks = [
        'task-items-kanban-composer',
        'task-items-kanban-add-btn',
        'task-items-kanban-add-form',
        'task-items-kanban-add-desc',
    ]

    for add_hook in required_add_hooks:
        assert add_hook in html
