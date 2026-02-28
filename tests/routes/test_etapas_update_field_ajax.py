from models import Etapa, db


AJAX_HEADERS = {
    'X-Requested-With': 'XMLHttpRequest',
    'Accept': 'application/json',
}


def test_update_etapa_responsavel_empty_returns_sem_responsavel(app, client_user, seed_data):
    response = client_user.post(
        f"/etapa/{seed_data['etapa_started_id']}/update_field",
        json={'field': 'responsavel', 'value': ''},
        headers=AJAX_HEADERS,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True
    assert payload['newValue'] == ''
    assert payload['displayValue'] == 'Sem responsável'

    with app.app_context():
        etapa = db.session.get(Etapa, seed_data['etapa_started_id'])
        assert etapa.responsavel == ''
