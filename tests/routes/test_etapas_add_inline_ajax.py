from models import Etapa, db


AJAX_HEADERS = {
    'X-Requested-With': 'XMLHttpRequest',
    'Accept': 'application/json',
}


def test_add_etapa_inline_ajax_success_returns_json_payload(app, client_user, seed_data):
    response = client_user.post(
        f"/project/{seed_data['project_id']}/etapa/add",
        data={
            'etapa_descricao': 'Nova etapa inline',
            'etapa_data_inicio': '2026-03-10',
            'etapa_data_fim': '2026-03-15',
            'etapa_responsavel': 'Usuario Auditoria',
            'etapa_iniciada': 'on',
        },
        headers=AJAX_HEADERS,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True
    assert payload['etapa']['descricao'] == 'Nova etapa inline'
    assert payload['etapa']['data_inicio'] == '2026-03-10'
    assert payload['etapa']['data_inicio_display'] == '10/03/2026'
    assert payload['etapa']['ordem'] == 2

    with app.app_context():
        etapa = db.session.get(Etapa, payload['etapa']['id'])
        assert etapa is not None
        assert etapa.project_id == seed_data['project_id']
        assert etapa.descricao == 'Nova etapa inline'


def test_add_etapa_inline_ajax_requires_descricao(client_user, seed_data):
    response = client_user.post(
        f"/project/{seed_data['project_id']}/etapa/add",
        data={'etapa_descricao': '   '},
        headers=AJAX_HEADERS,
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload['success'] is False
    assert 'descrição' in payload['message'].lower()


def test_add_etapa_inline_ajax_forbidden_without_area_access(client_outsider, seed_data):
    response = client_outsider.post(
        f"/project/{seed_data['project_id']}/etapa/add",
        data={'etapa_descricao': 'Tentativa sem permissão'},
        headers=AJAX_HEADERS,
    )

    assert response.status_code == 403
    payload = response.get_json()
    assert payload['success'] is False


def test_add_etapa_inline_ajax_normalizes_done_when_not_started(client_user, seed_data):
    response = client_user.post(
        f"/project/{seed_data['project_id']}/etapa/add",
        data={
            'etapa_descricao': 'Etapa com done inválido',
            'etapa_done': 'on',
        },
        headers=AJAX_HEADERS,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True
    assert payload['etapa']['iniciada'] is False
    assert payload['etapa']['done'] is False
    assert payload['warning']
