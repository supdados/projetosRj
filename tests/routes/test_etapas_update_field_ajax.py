"""Edição inline de campo da etapa: ``POST /api/etapas/<id>/update-field``."""

import datetime

from models import Etapa, db


def _field_update(response):
    payload = response.get_json()
    assert payload["ok"] is True
    return payload["data"]["field_update"]


def test_update_etapa_responsavel_agora_e_campo_invalido(app, client_user, seed_data):
    # Auditoria 2026-08-15 (item 1.2): inline não escreve mais o espelho sozinho.
    response = client_user.post(
        f"/api/etapas/{seed_data['etapa_started_id']}/update-field",
        json={"field": "responsavel", "value": ""},
    )

    assert response.status_code == 422
    payload = response.get_json()
    assert payload["ok"] is False
    assert payload["error"]["message"] == "Campo inválido."

    with app.app_context():
        etapa = db.session.get(Etapa, seed_data["etapa_started_id"])
        assert etapa.responsavel == "Usuario Auditoria"


def test_update_etapa_data_inicio_empty_returns_sem_data(app, client_user, seed_data):
    response = client_user.post(
        f"/api/etapas/{seed_data['etapa_started_id']}/update-field",
        json={"field": "data_inicio", "value": ""},
    )

    assert response.status_code == 200
    field_update = _field_update(response)
    assert field_update["newValue"] == ""
    assert field_update["displayValue"] == "Sem data"

    with app.app_context():
        etapa = db.session.get(Etapa, seed_data["etapa_started_id"])
        assert etapa.data_inicio is None


def test_update_etapa_data_inicio_uses_business_days_and_shifts_end_date(
    app, client_user, seed_data
):
    response = client_user.post(
        f"/api/etapas/{seed_data['etapa_started_id']}/update-field",
        json={"field": "data_inicio", "value": "2026-01-26"},
    )

    assert response.status_code == 200
    field_update = _field_update(response)
    assert field_update["newValue"] == "2026-01-26"
    assert field_update["displayValue"] == "26/01/2026"
    assert field_update["daysDiff"] == 6
    assert field_update["updatedEndDate"] == "2026-01-28"
    assert field_update["updatedEndDateDisplay"] == "28/01/2026"

    with app.app_context():
        etapa = db.session.get(Etapa, seed_data["etapa_started_id"])
        assert etapa is not None
        assert etapa.data_inicio == datetime.date(2026, 1, 26)
        assert etapa.data_fim == datetime.date(2026, 1, 28)


def test_update_etapa_data_fim_weekend_is_normalized_to_next_business_day(
    app, client_user, seed_data
):
    response = client_user.post(
        f"/api/etapas/{seed_data['etapa_started_id']}/update-field",
        json={"field": "data_fim", "value": "2026-01-24"},
    )

    assert response.status_code == 200
    field_update = _field_update(response)
    assert field_update["newValue"] == "2026-01-26"
    assert field_update["displayValue"] == "26/01/2026"

    with app.app_context():
        etapa = db.session.get(Etapa, seed_data["etapa_started_id"])
        assert etapa is not None
        assert etapa.data_fim == datetime.date(2026, 1, 26)
