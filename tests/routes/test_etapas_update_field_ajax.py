import datetime

from models import Etapa, db

AJAX_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json",
}


def test_update_etapa_responsavel_agora_e_campo_invalido(app, client_user, seed_data):
    # Auditoria 2026-08-15 (item 1.2): inline não escreve mais o espelho sozinho.
    response = client_user.post(
        f"/etapa/{seed_data['etapa_started_id']}/update_field",
        json={"field": "responsavel", "value": ""},
        headers=AJAX_HEADERS,
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["message"] == "Campo inválido."

    with app.app_context():
        etapa = db.session.get(Etapa, seed_data["etapa_started_id"])
        assert etapa.responsavel == "Usuario Auditoria"


def test_update_etapa_data_inicio_empty_returns_sem_data(app, client_user, seed_data):
    response = client_user.post(
        f"/etapa/{seed_data['etapa_started_id']}/update_field",
        json={"field": "data_inicio", "value": ""},
        headers=AJAX_HEADERS,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["newValue"] == ""
    assert payload["displayValue"] == "Sem data"

    with app.app_context():
        etapa = db.session.get(Etapa, seed_data["etapa_started_id"])
        assert etapa.data_inicio is None


def test_update_etapa_data_inicio_uses_business_days_and_shifts_end_date(
    app, client_user, seed_data
):
    response = client_user.post(
        f"/etapa/{seed_data['etapa_started_id']}/update_field",
        json={"field": "data_inicio", "value": "2026-01-26"},
        headers=AJAX_HEADERS,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["newValue"] == "2026-01-26"
    assert payload["displayValue"] == "26/01/2026"
    assert payload["daysDiff"] == 6
    assert payload["updatedEndDate"] == "2026-01-28"
    assert payload["updatedEndDateDisplay"] == "28/01/2026"

    with app.app_context():
        etapa = db.session.get(Etapa, seed_data["etapa_started_id"])
        assert etapa is not None
        assert etapa.data_inicio == datetime.date(2026, 1, 26)
        assert etapa.data_fim == datetime.date(2026, 1, 28)


def test_update_etapa_data_fim_weekend_is_normalized_to_next_business_day(
    app, client_user, seed_data
):
    response = client_user.post(
        f"/etapa/{seed_data['etapa_started_id']}/update_field",
        json={"field": "data_fim", "value": "2026-01-24"},
        headers=AJAX_HEADERS,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["newValue"] == "2026-01-26"
    assert payload["displayValue"] == "26/01/2026"

    with app.app_context():
        etapa = db.session.get(Etapa, seed_data["etapa_started_id"])
        assert etapa is not None
        assert etapa.data_fim == datetime.date(2026, 1, 26)
