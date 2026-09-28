"""P2-06: todos os caminhos validam o estado final de uma etapa concluída."""

import datetime

import pytest

from models import Etapa, Project, db
from services.etapas_mutation import MOTIVO_DATAS_AUSENTES


@pytest.mark.parametrize(
    "dates", [(None, None), (None, "2026-09-29"), ("2026-09-28", None)]
)
@pytest.mark.parametrize("operation", ["create", "edit", "toggle"])
def test_completed_stage_requires_both_dates(
    app, client_user, seed_data, dates, operation
) -> None:
    start, end = dates
    payload = {
        "descricao": "Etapa concluída",
        "data_inicio": start,
        "data_fim": end,
        "iniciada": True,
        "done": True,
    }
    if operation == "create":
        payload["responsaveis"] = [{"area_id": seed_data["auditoria_orgao_id"]}]
        url = f"/api/projetos/{seed_data['project_id']}/etapas"
    else:
        with app.app_context():
            stage = Etapa(
                descricao="Etapa concluída",
                project_id=seed_data["project_id"],
                iniciada=True,
                done=operation == "edit",
                responsavel="Auditoria",
                data_inicio=datetime.date(2026, 9, 28),
                data_fim=datetime.date(2026, 9, 29),
                ordem=20,
            )
            if operation == "toggle":
                stage.data_inicio = (
                    datetime.date.fromisoformat(start) if start else None
                )
                stage.data_fim = datetime.date.fromisoformat(end) if end else None
            db.session.add(stage)
            db.session.commit()
            stage_id = stage.id
        url = f"/api/etapas/{stage_id}" + ("/toggle" if operation == "toggle" else "")
    response = client_user.post(url, json=payload)
    assert response.status_code == 422
    assert response.get_json()["error"]["message"] == MOTIVO_DATAS_AUSENTES
    with app.app_context():
        if operation == "create":
            assert Etapa.query.filter_by(descricao="Etapa concluída").count() == 0
        elif operation == "edit":
            stage = db.session.get(Etapa, stage_id)
            assert stage.done
            assert stage.data_inicio == datetime.date(2026, 9, 28)
            assert stage.data_fim == datetime.date(2026, 9, 29)


def test_invalid_completed_creation_does_not_reactivate_project(
    app, client_user, seed_data
) -> None:
    project_id = seed_data["project_id"]
    with app.app_context():
        db.session.get(Project, project_id).status = "Finalizado"
        db.session.commit()
    response = client_user.post(
        f"/api/projetos/{project_id}/etapas",
        json={
            "descricao": "Etapa inválida",
            "iniciada": True,
            "done": True,
            "reactivate": True,
            "responsaveis": [{"area_id": None}],
        },
    )
    assert response.status_code == 422
    with app.app_context():
        assert db.session.get(Project, project_id).status == "Finalizado"


def test_valid_completed_stage_can_be_created_edited_and_reopened(
    app, client_user, seed_data
) -> None:
    payload = {
        "descricao": "Etapa válida",
        "data_inicio": "2026-09-28",
        "data_fim": "2026-09-29",
        "iniciada": True,
        "done": True,
        "responsaveis": [{"area_id": seed_data["auditoria_orgao_id"]}],
    }
    created = client_user.post(
        f"/api/projetos/{seed_data['project_id']}/etapas", json=payload
    )
    assert created.status_code == 200
    stage_id = created.get_json()["data"]["etapa"]["id"]
    assert created.get_json()["data"]["etapa"]["done"] is True
    payload["descricao"] = "Etapa revisada"
    assert client_user.post(f"/api/etapas/{stage_id}", json=payload).status_code == 200
    payload.update(done=False, data_inicio=None, data_fim=None)
    reopened = client_user.post(f"/api/etapas/{stage_id}", json=payload)
    assert reopened.status_code == 200
    assert reopened.get_json()["data"]["etapa"]["done"] is False


def test_creation_cannot_silently_accept_done_without_started(
    client_user, seed_data
) -> None:
    response = client_user.post(
        f"/api/projetos/{seed_data['project_id']}/etapas",
        json={
            "descricao": "Etapa inválida",
            "iniciada": False,
            "done": True,
            "data_inicio": "2026-09-28",
            "data_fim": "2026-09-29",
            "responsaveis": [{"area_id": None}],
        },
    )
    assert response.status_code == 422
    assert "sem ser iniciada" in response.get_json()["error"]["message"]
