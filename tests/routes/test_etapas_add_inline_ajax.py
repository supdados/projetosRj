"""Criação de etapa pela SPA: ``POST /api/projetos/<id>/etapas``."""

from models import Etapa, Project, db

RESPONSAVEIS = [{"area_id": None, "label": "Outras"}]


def _data(response):
    payload = response.get_json()
    assert payload["ok"] is True
    return payload["data"]


def test_add_etapa_success_returns_envelope_and_persists(app, client_user, seed_data):
    response = client_user.post(
        f"/api/projetos/{seed_data['project_id']}/etapas",
        json={
            "descricao": "Nova etapa inline",
            "data_inicio": "2026-03-10",
            "data_fim": "2026-03-15",
            "responsaveis": RESPONSAVEIS,
            "iniciada": True,
        },
    )

    assert response.status_code == 200
    etapa_payload = _data(response)["etapa"]
    assert etapa_payload["descricao"] == "Nova etapa inline"
    assert etapa_payload["data_inicio"] == "2026-03-10"
    assert etapa_payload["ordem"] == 2

    with app.app_context():
        etapa = db.session.get(Etapa, etapa_payload["id"])
        assert etapa is not None
        assert etapa.project_id == seed_data["project_id"]
        assert etapa.descricao == "Nova etapa inline"


def test_add_etapa_requires_descricao(client_user, seed_data):
    response = client_user.post(
        f"/api/projetos/{seed_data['project_id']}/etapas",
        json={"descricao": "   ", "responsaveis": RESPONSAVEIS},
    )

    assert response.status_code == 422
    payload = response.get_json()
    assert payload["ok"] is False
    assert "descrição" in payload["error"]["message"].lower()


def test_add_etapa_normalizes_done_when_not_started(client_user, seed_data):
    response = client_user.post(
        f"/api/projetos/{seed_data['project_id']}/etapas",
        json={
            "descricao": "Etapa com done inválido",
            "responsaveis": RESPONSAVEIS,
            "done": True,
        },
    )

    assert response.status_code == 200
    etapa_payload = _data(response)["etapa"]
    assert etapa_payload["iniciada"] is False
    assert etapa_payload["done"] is False


def test_add_etapa_requires_confirmation_for_finalized_project(
    app, client_user, seed_data
):
    with app.app_context():
        project = db.session.get(Project, seed_data["project_complete_id"])
        project.status = "Finalizado"
        db.session.commit()

    response = client_user.post(
        f"/api/projetos/{seed_data['project_complete_id']}/etapas",
        json={"descricao": "Nova etapa sem confirmar", "responsaveis": RESPONSAVEIS},
    )

    assert response.status_code == 409
    payload = response.get_json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "validation"

    with app.app_context():
        project = db.session.get(Project, seed_data["project_complete_id"])
        assert project.status == "Finalizado"
        etapa = Etapa.query.filter_by(
            project_id=seed_data["project_complete_id"],
            descricao="Nova etapa sem confirmar",
        ).first()
        assert etapa is None


def test_add_etapa_reactivates_project_when_confirmation_is_sent(
    app, client_user, seed_data
):
    with app.app_context():
        project = db.session.get(Project, seed_data["project_complete_id"])
        project.status = "Finalizado"
        db.session.commit()

    response = client_user.post(
        f"/api/projetos/{seed_data['project_complete_id']}/etapas",
        json={
            "descricao": "Nova etapa reativada",
            "responsaveis": RESPONSAVEIS,
            "reactivate": True,
        },
    )

    assert response.status_code == 200
    data = _data(response)
    assert data["project_reactivated"] is True
    assert data["project_status"] == "Vigente"

    with app.app_context():
        project = db.session.get(Project, seed_data["project_complete_id"])
        assert project.status == "Vigente"
        etapa = Etapa.query.filter_by(
            project_id=seed_data["project_complete_id"],
            descricao="Nova etapa reativada",
        ).first()
        assert etapa is not None
