"""Exclusão de etapa pela SPA: ``POST /api/etapas/<id>/delete``."""

from models import Etapa, db


def test_delete_etapa_removes_row_and_returns_total(app, client_user, seed_data):
    etapa_id = seed_data["etapa_id"]
    project_id = seed_data["project_id"]

    with app.app_context():
        total_before = Etapa.query.filter_by(project_id=project_id).count()
        assert total_before >= 1

    response = client_user.post(f"/api/etapas/{etapa_id}/delete")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["deleted_id"] == etapa_id
    assert data["project_id"] == project_id
    assert data["total_etapas"] == total_before - 1

    with app.app_context():
        assert db.session.get(Etapa, etapa_id) is None
        assert Etapa.query.filter_by(project_id=project_id).count() == total_before - 1


def test_delete_etapa_not_found_without_area_access(app, client_outsider, seed_data):
    """S5/F4-2b: o 404 não devolve ``deleted_id``/``project_id`` — vazaria existência."""
    etapa_id = seed_data["etapa_id"]

    response = client_outsider.post(f"/api/etapas/{etapa_id}/delete")
    inexistente = client_outsider.post("/api/etapas/999999/delete")

    assert response.status_code == 404
    payload = response.get_json()
    assert payload["ok"] is False
    assert payload == inexistente.get_json()

    with app.app_context():
        assert db.session.get(Etapa, etapa_id) is not None
