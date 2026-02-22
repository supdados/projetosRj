from models import Task, db


def test_finalize_moves_task_to_finalized_listing(app, client_user, seed_data):
    task_id = seed_data['task_id']

    response = client_user.post(f'/tarefas/{task_id}/finalizar', follow_redirects=False)
    assert response.status_code == 302

    with app.app_context():
        task = db.session.get(Task, task_id)
        assert task is not None
        assert task.is_finalized is True
        assert task.finalized_at is not None

    active_page = client_user.get('/tarefas')
    assert active_page.status_code == 200
    assert b'Tarefa Auditoria' not in active_page.data

    finalized_page = client_user.get('/tarefas/finalizadas')
    assert finalized_page.status_code == 200
    assert b'Tarefa Auditoria' in finalized_page.data


def test_reactivate_returns_task_to_active_listing(app, client_user, seed_data):
    task_id = seed_data['task_id']
    client_user.post(f'/tarefas/{task_id}/finalizar', follow_redirects=False)

    response = client_user.post(f'/tarefas/{task_id}/reativar', follow_redirects=False)
    assert response.status_code == 302

    with app.app_context():
        task = db.session.get(Task, task_id)
        assert task is not None
        assert task.is_finalized is False
        assert task.finalized_at is None

    active_page = client_user.get('/tarefas')
    assert active_page.status_code == 200
    assert b'Tarefa Auditoria' in active_page.data

    finalized_page = client_user.get('/tarefas/finalizadas')
    assert finalized_page.status_code == 200
    assert b'Tarefa Auditoria' not in finalized_page.data


def test_outsider_cannot_finalize_task(app, client_outsider, seed_data):
    task_id = seed_data['task_id']

    response = client_outsider.post(f'/tarefas/{task_id}/finalizar', follow_redirects=False)
    assert response.status_code == 302
    assert '/tarefas' in (response.headers.get('Location') or '')

    with app.app_context():
        task = db.session.get(Task, task_id)
        assert task is not None
        assert task.is_finalized is False
        assert task.finalized_at is None


def test_tasks_pagination_uses_20_and_keeps_continuous_index_with_filters(app, client_user, seed_data):
    with app.app_context():
        for idx in range(1, 26):
            db.session.add(
                Task(
                    titulo=f'Paginated Task {idx:02d}',
                    project_id=seed_data['project_id'],
                    created_by_id=seed_data['user_id'],
                )
            )
        db.session.commit()

    project_id = seed_data['project_id']
    response = client_user.get(f'/tarefas?search=Paginated+Task&project={project_id}&page=2')
    assert response.status_code == 200

    assert b'data-task-index=\"21\"' in response.data
    assert b'data-task-index=\"25\"' in response.data
    assert b'data-task-index=\"26\"' not in response.data
    assert 'Página 2 de 2'.encode('utf-8') in response.data
    assert b'search=Paginated+Task' in response.data
    assert f'project={project_id}'.encode() in response.data


def test_finalized_task_is_hidden_from_project_tasks_and_dashboard(app, client_user, seed_data):
    task_id = seed_data['task_id']
    project_id = seed_data['project_id']
    task_title = b'Tarefa Auditoria'

    client_user.post(f'/tarefas/{task_id}/finalizar', follow_redirects=False)

    project_tasks_page = client_user.get(f'/projeto/{project_id}/tarefas')
    assert project_tasks_page.status_code == 200
    assert task_title not in project_tasks_page.data
    assert f'/tarefas/finalizadas?project={project_id}'.encode() in project_tasks_page.data

    dashboard_page = client_user.get('/dashboard')
    assert dashboard_page.status_code == 200
    assert task_title not in dashboard_page.data


def test_project_tasks_template_contract_has_modal_project_locked_and_no_view_button(client_user, seed_data):
    response = client_user.get(f"/projeto/{seed_data['project_id']}/tarefas")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert f'/tarefas/finalizadas?project={seed_data["project_id"]}' in html
    assert f'/tarefas/{seed_data["task_id"]}/finalizar' in html
    assert 'btn-view-clean' not in html
    assert 'class="project-view-breadcrumb"' in html
    assert 'breadcrumb-item' not in html
    assert 'id="project_locked"' in html
    assert 'readonly' in html
    assert f'<input type="hidden" name="project_id" value="{seed_data["project_id"]}">' in html


def test_project_tasks_empty_state_has_no_create_first_button(client_user, seed_data):
    response = client_user.get(f"/projeto/{seed_data['project_complete_id']}/tarefas")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'Nenhuma tarefa neste projeto' in html
    assert 'Crie a primeira tarefa para este projeto' not in html
    assert 'Criar Primeira Tarefa' not in html
