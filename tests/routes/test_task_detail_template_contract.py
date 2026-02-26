def test_task_detail_route_redirects_to_project_board_with_focus_task(client_user, seed_data):
    response = client_user.get(f"/tarefas/{seed_data['task_id']}", follow_redirects=False)

    assert response.status_code == 302
    location = response.headers.get('Location') or ''
    assert f"/projeto/{seed_data['project_id']}/tarefas" in location
    assert f"focus_task={seed_data['task_id']}" in location


def test_task_detail_route_redirects_to_hub_for_sem_projeto_with_focus_task(client_user, seed_data):
    response = client_user.get(f"/tarefas/{seed_data['orphan_task_id']}", follow_redirects=False)

    assert response.status_code == 302
    location = response.headers.get('Location') or ''
    assert '/tarefas?focus_task=' in location
    assert f"focus_task={seed_data['orphan_task_id']}" in location
