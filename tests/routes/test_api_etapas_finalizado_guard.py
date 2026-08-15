"""Regressão do guard de projeto Finalizado nas rotas de mutação de etapas.

Auditoria 2026-08-15 (item 1.1): comentário, reordenar, cascade e importar
modelo eram alcançáveis pela SPA em projeto Finalizado. Todos devem responder
422 via ``assert_etapa_editavel``/``assert_projeto_permite_mutacao_de_etapas``.
As exceções LEGÍTIMAS (add reativa o projeto; mover tarefa usa
``allow_done=True``) têm teste próprio.
"""

import datetime

from models import Etapa, Project, db
from services.etapas_mutation import MOTIVO_PROJETO_FINALIZADO


def _error(response):
    payload = response.get_json()
    assert payload["ok"] is False
    return payload["error"]


def _finalizar_projeto(app, project_id: int) -> None:
    with app.app_context():
        db.session.get(Project, project_id).status = "Finalizado"
        db.session.commit()


def test_comentario_em_projeto_finalizado_retorna_422(app, client_user, seed_data):
    _finalizar_projeto(app, seed_data["project_id"])

    response = client_user.post(
        f"/api/etapas/{seed_data['etapa_id']}/comentario",
        json={"comentario": "tentativa"},
    )

    assert response.status_code == 422
    error = _error(response)
    assert error["code"] == "validation"
    assert error["message"] == MOTIVO_PROJETO_FINALIZADO
    with app.app_context():
        etapa = db.session.get(Etapa, seed_data["etapa_id"])
        assert etapa.comentarios == "Sem comentarios"


def test_reordenar_em_projeto_finalizado_retorna_422(app, client_user, seed_data):
    _finalizar_projeto(app, seed_data["project_id"])

    response = client_user.post(
        f"/api/projetos/{seed_data['project_id']}/etapas/reordenar",
        json={"etapa_ids": [seed_data["etapa_started_id"], seed_data["etapa_id"]]},
    )

    assert response.status_code == 422
    error = _error(response)
    assert error["code"] == "validation"
    assert error["message"] == MOTIVO_PROJETO_FINALIZADO
    with app.app_context():
        etapa = db.session.get(Etapa, seed_data["etapa_id"])
        assert etapa.ordem == 0


def test_cascade_em_projeto_finalizado_retorna_422(app, client_user, seed_data):
    _finalizar_projeto(app, seed_data["project_id"])

    response = client_user.post(
        f"/api/projetos/{seed_data['project_id']}/cascade",
        json={"etapa_id": seed_data["etapa_id"], "days_diff": 3},
    )

    assert response.status_code == 422
    error = _error(response)
    assert error["code"] == "validation"
    assert error["message"] == MOTIVO_PROJETO_FINALIZADO
    with app.app_context():
        subsequente = db.session.get(Etapa, seed_data["etapa_started_id"])
        assert subsequente.data_inicio == datetime.date(2026, 1, 16)


def test_importar_modelo_em_projeto_finalizado_retorna_422(app, client_user, seed_data):
    _finalizar_projeto(app, seed_data["project_id"])
    with app.app_context():
        antes = Etapa.query.filter_by(project_id=seed_data["project_id"]).count()

    response = client_user.post(
        f"/api/projetos/{seed_data['project_id']}/importar-modelo",
        json={"template_id": seed_data["template_id"], "start_date": "2026-05-04"},
    )

    assert response.status_code == 422
    error = _error(response)
    assert error["code"] == "validation"
    assert error["message"] == MOTIVO_PROJETO_FINALIZADO
    with app.app_context():
        depois = Etapa.query.filter_by(project_id=seed_data["project_id"]).count()
        assert depois == antes


def test_add_etapa_reativa_projeto_finalizado(app, client_user, seed_data):
    # Isenção intencional: adicionar etapa REATIVA o projeto (não é bloqueado).
    _finalizar_projeto(app, seed_data["project_id"])

    response = client_user.post(
        f"/api/projetos/{seed_data['project_id']}/etapas",
        json={
            "descricao": "Etapa pós-finalização",
            "responsaveis": [{"area_id": None, "label": "Outras"}],
            "reactivate": True,
        },
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["project_reactivated"] is True
    assert data["project_status"] == "Vigente"
    with app.app_context():
        assert db.session.get(Project, seed_data["project_id"]).status == "Vigente"


def test_add_etapa_sem_reactivate_pede_confirmacao_409(app, client_user, seed_data):
    _finalizar_projeto(app, seed_data["project_id"])

    response = client_user.post(
        f"/api/projetos/{seed_data['project_id']}/etapas",
        json={
            "descricao": "Etapa pós-finalização",
            "responsaveis": [{"area_id": None, "label": "Outras"}],
        },
    )

    assert response.status_code == 409
    assert _error(response)["code"] == "validation"


def test_mover_tarefa_para_etapa_concluida_continua_permitido(
    app, client_user, seed_data
):
    # allow_done=True do fluxo de mover tarefa segue valendo (warning, não 422).
    with app.app_context():
        etapa = db.session.get(Etapa, seed_data["etapa_started_id"])
        etapa.done = True
        db.session.commit()

    response = client_user.post(
        f"/api/tarefas/{seed_data['task_id']}/mover-etapa",
        json={"etapa_id": seed_data["etapa_started_id"]},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["etapa_id"] == seed_data["etapa_started_id"]
    assert "warning" in data
