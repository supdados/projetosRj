from models import Task, db
from time_utils import utc_now


def test_finalize_keeps_task_active_and_only_updates_status(app, client_user, seed_data):
    task_id = seed_data['task_id']

    response = client_user.post(f'/tarefas/{task_id}/finalizar', follow_redirects=False)
    assert response.status_code == 302

    with app.app_context():
        task = db.session.get(Task, task_id)
        assert task is not None
        assert task.status == 'finalizada'
        assert task.is_finalized is False
        assert task.finalized_at is None

    active_page = client_user.get('/tarefas')
    assert active_page.status_code == 200
    assert b'Item Auditoria' in active_page.data

    archived_page = client_user.get('/tarefas/arquivadas')
    assert archived_page.status_code == 200
    assert b'Item Auditoria' not in archived_page.data


def test_archive_finalized_moves_task_to_archived_listing(app, client_user, seed_data):
    task_id = seed_data['task_id']
    client_user.post(f'/tarefas/{task_id}/finalizar', follow_redirects=False)

    response = client_user.post('/tarefas/arquivar-finalizadas', follow_redirects=False)
    assert response.status_code == 302

    with app.app_context():
        task = db.session.get(Task, task_id)
        assert task is not None
        assert task.status == 'finalizada'
        assert task.is_finalized is True
        assert task.finalized_at is not None

    active_page = client_user.get('/tarefas')
    assert active_page.status_code == 200
    assert b'Item Auditoria' not in active_page.data

    archived_page = client_user.get('/tarefas/arquivadas')
    assert archived_page.status_code == 200
    assert b'Item Auditoria' in archived_page.data


def test_reactivate_returns_archived_task_to_active_listing_as_programado(app, client_user, seed_data):
    task_id = seed_data['task_id']
    client_user.post(f'/tarefas/{task_id}/finalizar', follow_redirects=False)
    client_user.post('/tarefas/arquivar-finalizadas', follow_redirects=False)

    response = client_user.post(f'/tarefas/{task_id}/reativar', follow_redirects=False)
    assert response.status_code == 302

    with app.app_context():
        task = db.session.get(Task, task_id)
        assert task is not None
        assert task.is_finalized is False
        assert task.finalized_at is None
        assert task.status == 'nao_iniciada'

    active_page = client_user.get('/tarefas')
    assert active_page.status_code == 200
    assert b'Item Auditoria' in active_page.data

    archived_page = client_user.get('/tarefas/arquivadas')
    assert archived_page.status_code == 200
    assert b'Item Auditoria' not in archived_page.data


def test_archive_finalized_ajax_returns_archived_ids(app, client_user, seed_data):
    task_id = seed_data['task_id']
    client_user.post(f'/tarefas/{task_id}/finalizar', follow_redirects=False)

    response = client_user.post(
        '/tarefas/arquivar-finalizadas',
        headers={
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json',
        },
    )
    assert response.status_code == 200
    payload = response.get_json()

    assert payload['success'] is True
    assert payload['archived_count'] == 1
    assert payload['archived_task_ids'] == [str(task_id)]


def test_unarchive_ajax_returns_programado_payload(app, client_user, seed_data):
    task_id = seed_data['task_id']
    client_user.post(f'/tarefas/{task_id}/finalizar', follow_redirects=False)
    client_user.post('/tarefas/arquivar-finalizadas', follow_redirects=False)

    response = client_user.post(
        f'/tarefas/{task_id}/desarquivar',
        headers={
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json',
        },
    )
    assert response.status_code == 200
    payload = response.get_json()

    assert payload['success'] is True
    assert payload['task']['status'] == 'nao_iniciada'
    assert payload['item']['status'] == 'nao_iniciada'


def test_archived_alias_redirects_to_archived_route(client_user):
    response = client_user.get('/tarefas/finalizadas?status=finalizado', follow_redirects=False)
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/tarefas/arquivadas?status=finalizado')


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
        assert task.status == 'nao_iniciada'


def test_tasks_hub_hides_projects_without_items_until_first_item_is_created(app, client_user, seed_data):
    with app.app_context():
        archived_task = Task(
            descricao='Tarefa arquivada para esconder projeto',
            status='finalizada',
            is_archived=True,
            archived_at=utc_now(),
            project_id=seed_data['project_complete_id'],
            created_by_id=seed_data['user_id'],
        )
        db.session.add(archived_task)
        db.session.commit()

    hub_without_item = client_user.get('/tarefas')
    assert hub_without_item.status_code == 200
    assert b'Projeto Concluivel' not in hub_without_item.data

    with app.app_context():
        db.session.add(
            Task(
                descricao='Primeira tarefa ativa do projeto completo',
                status='nao_iniciada',
                project_id=seed_data['project_complete_id'],
                created_by_id=seed_data['user_id'],
            )
        )
        db.session.commit()

    hub_with_item = client_user.get('/tarefas')
    assert hub_with_item.status_code == 200
    assert b'Projeto Concluivel' in hub_with_item.data


def test_tasks_hub_hides_area_selector_for_single_area_user_and_shows_for_admin(client, seed_data):
    with client.session_transaction() as session:
        session['user_id'] = seed_data['user_id']

    user_response = client.get('/tarefas')
    assert user_response.status_code == 200
    assert b'name="area"' not in user_response.data

    with client.session_transaction() as session:
        session['user_id'] = seed_data['admin_id']

    admin_response = client.get('/tarefas')
    assert admin_response.status_code == 200
    assert b'name="area"' in admin_response.data


def test_finalized_task_is_hidden_from_project_tasks_and_dashboard(app, client_user, seed_data):
    task_id = seed_data['task_id']
    project_id = seed_data['project_id']
    task_title = b'Item Auditoria'

    client_user.post(f'/tarefas/{task_id}/finalizar', follow_redirects=False)
    client_user.post('/tarefas/arquivar-finalizadas', follow_redirects=False)

    project_tasks_page = client_user.get(f'/projeto/{project_id}/tarefas')
    assert project_tasks_page.status_code == 200
    assert task_title not in project_tasks_page.data
    assert f'/tarefas/arquivadas?project={project_id}'.encode() in project_tasks_page.data

    dashboard_page = client_user.get('/dashboard')
    assert dashboard_page.status_code == 200
    assert task_title not in dashboard_page.data


def test_project_tasks_template_contract_keeps_project_context_but_allows_switching_project_filter(client_user, seed_data):
    response = client_user.get(f"/projeto/{seed_data['project_id']}/tarefas")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert f'/tarefas/arquivadas?project={seed_data["project_id"]}' in html
    assert '/tarefas/arquivar-finalizadas' in html
    assert 'title="Tarefas arquivadas"' in html
    assert 'aria-label="Tarefas arquivadas"' in html
    assert 'data-project-locked="1"' in html
    assert 'id="filter_project_input"' in html
    assert f'<input type="hidden" name="project" id="filter_project" value="{seed_data["project_id"]}">' in html
    assert 'id="project_locked"' not in html
    assert 'action="/tarefas"' in html
    assert 'href="/tarefas"' in html


def test_project_tasks_empty_state_has_no_create_first_button(client_user, seed_data):
    response = client_user.get(f"/projeto/{seed_data['project_complete_id']}/tarefas")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert '<section class="tasks-empty-state">' not in html
    assert 'Adicionar nova tarefa' in html
    assert 'task-hub-add-row' in html
