"""Testes de contrato dos endpoints JSON de mutação de ETAPAS (Fase 5a).

Cobrem o envelope canônico, a cascata de datas SEMPRE server-side (reordenar e
editar data disparam ``cascade_subsequent_dates``; o endpoint devolve o estado
atualizado) e o escopo de órgão (403 fora de escopo).
"""

import datetime

from models import Etapa, db


def _data(response):
    payload = response.get_json()
    assert payload["ok"] is True
    return payload["data"]


def _error(response):
    payload = response.get_json()
    assert payload["ok"] is False
    return payload["error"]


# ── CRUD ──────────────────────────────────────────────────────────────────────


def test_add_etapa_returns_envelope_with_etapa(app, client_user, seed_data):
    response = client_user.post(
        f"/api/projetos/{seed_data['project_id']}/etapas",
        json={"descricao": "Etapa criada", "data_inicio": "2026-04-01"},
    )

    assert response.status_code == 200
    data = _data(response)
    assert data["etapa"]["descricao"] == "Etapa criada"
    assert data["etapa"]["task_count"] == {"total": 0, "done": 0}


def test_edit_etapa_rejects_done_without_iniciada(app, client_user, seed_data):
    response = client_user.post(
        f"/api/etapas/{seed_data['etapa_id']}",
        json={"descricao": "x", "iniciada": False, "done": True},
    )

    assert response.status_code == 422
    assert _error(response)["code"] == "validation"


def test_delete_etapa_returns_total(app, client_user, seed_data):
    response = client_user.post(f"/api/etapas/{seed_data['etapa_id']}/delete")

    assert response.status_code == 200
    data = _data(response)
    assert data["deleted_id"] == seed_data["etapa_id"]
    assert data["project_id"] == seed_data["project_id"]


# ── Edição inline de data dispara cascata (server-side) ───────────────────────


def test_update_field_data_inicio_triggers_business_day_cascade(
    app, client_user, seed_data
):
    # etapa (ordem 0) tem data_inicio 2026-01-10 / data_fim 2026-01-15.
    # Mover o início para frente desloca o próprio data_fim em dias úteis.
    response = client_user.post(
        f"/api/etapas/{seed_data['etapa_id']}/update-field",
        json={"field": "data_inicio", "value": "2026-01-19"},
    )

    assert response.status_code == 200
    data = _data(response)
    field_update = data["field_update"]
    assert field_update["success"] is True
    # O serviço propaga a diferença em dias úteis ao data_fim (server-side).
    assert "updatedEndDate" in field_update
    assert data["etapa"]["data_inicio"] == "2026-01-19"

    with app.app_context():
        etapa = db.session.get(Etapa, seed_data["etapa_id"])
        # data_fim foi recalculado server-side (não pelo front).
        assert etapa.data_fim is not None
        assert etapa.data_fim > datetime.date(2026, 1, 15)


# ── Reordenar dispara cascata e devolve estado atualizado ─────────────────────


def test_reordenar_triggers_cascade_and_returns_updated_etapas(
    app, client_user, seed_data
):
    with app.app_context():
        before = db.session.get(Etapa, seed_data["etapa_started_id"]).data_inicio

    response = client_user.post(
        f"/api/projetos/{seed_data['project_id']}/etapas/reordenar",
        json={
            "etapa_ids": [seed_data["etapa_started_id"], seed_data["etapa_id"]],
            "etapa_id": seed_data["etapa_id"],
            "days_diff": 5,
        },
    )

    assert response.status_code == 200
    data = _data(response)
    # O endpoint RE-BUSCA e devolve as etapas para o front re-renderizar.
    assert isinstance(data["etapas"], list)
    assert len(data["etapas"]) >= 2

    with app.app_context():
        # etapa base = etapa (ordem 0); a subsequente (etapa_started) foi
        # deslocada em 5 dias úteis pela cascata server-side.
        after = db.session.get(Etapa, seed_data["etapa_started_id"]).data_inicio
        assert after is not None and before is not None
        assert after > before


def test_cascade_endpoint_shifts_subsequent_dates(app, client_user, seed_data):
    with app.app_context():
        before = db.session.get(Etapa, seed_data["etapa_started_id"]).data_inicio

    response = client_user.post(
        f"/api/projetos/{seed_data['project_id']}/cascade",
        json={"etapa_id": seed_data["etapa_id"], "days_diff": 3},
    )

    assert response.status_code == 200
    assert isinstance(_data(response)["etapas"], list)

    with app.app_context():
        after = db.session.get(Etapa, seed_data["etapa_started_id"]).data_inicio
        assert after > before


def test_cascade_rejects_excessive_days(app, client_user, seed_data):
    response = client_user.post(
        f"/api/projetos/{seed_data['project_id']}/cascade",
        json={"etapa_id": seed_data["etapa_id"], "days_diff": 9999},
    )

    assert response.status_code == 422
    assert _error(response)["code"] == "validation"


# ── Toggles ───────────────────────────────────────────────────────────────────


def test_toggle_iniciada_flips_flag(app, client_user, seed_data):
    response = client_user.post(
        f"/api/etapas/{seed_data['etapa_id']}/toggle-iniciada"
    )

    assert response.status_code == 200
    assert _data(response)["etapa"]["iniciada"] is True


def test_toggle_done_rejects_when_not_iniciada(app, client_user, seed_data):
    response = client_user.post(f"/api/etapas/{seed_data['etapa_id']}/toggle")

    assert response.status_code == 422
    assert _error(response)["code"] == "validation"


# ── Importar modelo ───────────────────────────────────────────────────────────


def test_importar_modelo_creates_stages(app, client_user, seed_data):
    response = client_user.post(
        f"/api/projetos/{seed_data['project_id']}/importar-modelo",
        json={"template_id": seed_data["template_id"], "start_date": "2026-05-04"},
    )

    assert response.status_code == 200
    data = _data(response)
    assert data["etapas_criadas"] >= 1
    assert isinstance(data["etapas"], list)


# ── Escopo de órgão (403) ─────────────────────────────────────────────────────


def test_update_field_forbidden_out_of_scope(app, client_user, seed_data):
    # foreign_etapa pertence ao projeto VPD, fora do escopo do usuário Auditoria.
    response = client_user.post(
        f"/api/etapas/{seed_data['foreign_etapa_id']}/update-field",
        json={"field": "descricao", "value": "hack"},
    )

    assert response.status_code == 403
    assert _error(response)["code"] == "forbidden"


def test_add_etapa_forbidden_out_of_scope(app, client_user, seed_data):
    response = client_user.post(
        f"/api/projetos/{seed_data['foreign_project_id']}/etapas",
        json={"descricao": "hack"},
    )

    assert response.status_code == 403
    assert _error(response)["code"] == "forbidden"


def test_etapa_not_found_returns_404(app, client_user, seed_data):
    response = client_user.post(
        "/api/etapas/99999/update-field",
        json={"field": "descricao", "value": "x"},
    )

    assert response.status_code == 404
    assert _error(response)["code"] == "not_found"


def test_unauthenticated_returns_401(app, client, seed_data):
    response = client.post(
        f"/api/etapas/{seed_data['etapa_id']}/toggle-iniciada"
    )

    assert response.status_code == 401
    assert _error(response)["code"] == "unauthenticated"
