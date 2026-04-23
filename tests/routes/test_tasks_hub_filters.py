from models import Task, db
from time_utils import utc_now


def test_tasks_hub_filters_by_priority_type_status_and_responsavel(app, client_user, seed_data):
    with app.app_context():
        matching_task = Task(
            descricao='Tarefa filtro alvo',
            status='em_andamento',
            responsavel='Usuario Editavel',
            prioridade='alta',
            tipo_pedido='bug',
            ordem=10,
            project_id=seed_data['project_id'],
            created_by_id=seed_data['user_id'],
        )
        other_task = Task(
            descricao='Tarefa fora do filtro',
            status='nao_iniciada',
            responsavel='Usuario Auditoria',
            prioridade='baixa',
            tipo_pedido='melhoria',
            ordem=11,
            project_id=seed_data['project_id'],
            created_by_id=seed_data['user_id'],
        )
        db.session.add_all([matching_task, other_task])
        db.session.commit()

    response = client_user.get(
        '/tarefas?prioridade=alta&tipo=bug&status=em_andamento&responsavel=Usuario+Editavel'
    )
    assert response.status_code == 200

    html = response.get_data(as_text=True)
    assert 'Tarefa filtro alvo' in html
    assert 'Tarefa fora do filtro' not in html
    assert 'Item Auditoria' not in html


def test_finalized_listing_filters_by_priority_type_status_and_responsavel(app, client_user, seed_data):
    with app.app_context():
        archived_match = Task(
            descricao='Arquivada filtro alvo',
            status='finalizada',
            responsavel='Usuario Editavel',
            prioridade='urgente',
            tipo_pedido='bug',
            ordem=20,
            project_id=seed_data['project_id'],
            created_by_id=seed_data['user_id'],
            is_archived=True,
            archived_at=utc_now(),
        )
        archived_other = Task(
            descricao='Arquivada fora do filtro',
            status='finalizada',
            responsavel='Usuario Auditoria',
            prioridade='media',
            tipo_pedido='melhoria',
            ordem=21,
            project_id=seed_data['project_id'],
            created_by_id=seed_data['user_id'],
            is_archived=True,
            archived_at=utc_now(),
        )
        db.session.add_all([archived_match, archived_other])
        db.session.commit()

    response = client_user.get(
        '/tarefas/arquivadas?prioridade=urgente&tipo=bug&status=finalizada&responsavel=Usuario+Editavel'
    )
    assert response.status_code == 200

    html = response.get_data(as_text=True)
    assert 'Arquivada filtro alvo' in html
    assert 'Arquivada fora do filtro' not in html


def test_tasks_hub_redirects_when_non_admin_forces_foreign_orgao(client_user, seed_data):
    response = client_user.get(
        '/tarefas',
        query_string={'orgao': str(seed_data['vpd_orgao_id']), 'status': 'em_andamento'},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/tarefas?status=em_andamento')


def test_tasks_hub_project_filter_respects_selected_orgao_for_admin(client_admin, seed_data):
    response = client_admin.get('/tarefas', query_string={'orgao': str(seed_data['vpd_orgao_id'])})
    assert response.status_code == 200

    html = response.get_data(as_text=True)
    assert f'data-value="{seed_data["foreign_project_id"]}"' in html
    assert f'data-value="{seed_data["project_id"]}"' not in html
