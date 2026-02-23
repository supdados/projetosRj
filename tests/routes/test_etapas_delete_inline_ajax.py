from models import Etapa, db


AJAX_HEADERS = {
    'X-Requested-With': 'XMLHttpRequest',
    'Accept': 'application/json',
}


def test_delete_etapa_ajax_success_returns_json_and_removes_row(app, client_user, seed_data):
    etapa_id = seed_data['etapa_id']
    project_id = seed_data['project_id']

    with app.app_context():
        total_before = Etapa.query.filter_by(project_id=project_id).count()
        assert total_before >= 1

    response = client_user.post(
        f'/etapa/{etapa_id}/delete',
        headers=AJAX_HEADERS,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True
    assert payload['etapa_id'] == etapa_id
    assert payload['project_id'] == project_id
    assert payload['total_etapas'] == total_before - 1

    with app.app_context():
        etapa = db.session.get(Etapa, etapa_id)
        assert etapa is None
        assert Etapa.query.filter_by(project_id=project_id).count() == total_before - 1


def test_delete_etapa_ajax_forbidden_without_area_access(app, client_outsider, seed_data):
    etapa_id = seed_data['etapa_id']

    response = client_outsider.post(
        f'/etapa/{etapa_id}/delete',
        headers=AJAX_HEADERS,
    )

    assert response.status_code == 403
    payload = response.get_json()
    assert payload['success'] is False
    assert payload['etapa_id'] == etapa_id
    assert payload['project_id'] == seed_data['project_id']

    with app.app_context():
        etapa = db.session.get(Etapa, etapa_id)
        assert etapa is not None


def test_delete_etapa_non_ajax_keeps_redirect_contract(app, client_user, seed_data):
    etapa_id = seed_data['etapa_id']
    project_id = seed_data['project_id']

    response = client_user.post(f'/etapa/{etapa_id}/delete', follow_redirects=False)
    assert response.status_code == 302
    assert f'/project/{project_id}' in (response.headers.get('Location') or '')

    with app.app_context():
        etapa = db.session.get(Etapa, etapa_id)
        assert etapa is None
