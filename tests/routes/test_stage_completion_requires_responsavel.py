"""Concluir etapa exige área responsável (regressão do import de modelos).

Etapas importadas de modelo nascem sem responsável (por design) — mas NÃO podem
ser concluídas até ganharem um. A regra vive em
``services.etapas_mutation.motivo_bloqueio_conclusao`` e é aplicada nos dois
caminhos de conclusão: ``POST /api/etapas/<id>/toggle`` e o update completo
(``POST /api/etapas/<id>``).
"""

import datetime

from models import Etapa, db
from models.etapa import EtapaResponsavel
from services.etapas_mutation import MOTIVO_RESPONSAVEL_AUSENTE


def _make_etapa_sem_responsavel(app, seed_data):
    """Etapa iniciada, com datas e SEM responsável (nem lista, nem texto)."""
    with app.app_context():
        etapa = Etapa(
            descricao="Etapa importada sem responsavel",
            data_inicio=datetime.date(2026, 2, 2),
            data_fim=datetime.date(2026, 2, 6),
            responsavel=None,
            iniciada=True,
            done=False,
            project_id=seed_data["project_id"],
            ordem=99,
        )
        db.session.add(etapa)
        db.session.commit()
        return etapa.id


def test_api_toggle_bloqueia_conclusao_sem_responsavel(app, client_admin, seed_data):
    etapa_id = _make_etapa_sem_responsavel(app, seed_data)

    response = client_admin.post(f"/api/etapas/{etapa_id}/toggle")
    assert response.status_code == 422
    payload = response.get_json()
    assert payload["ok"] is False
    assert payload["error"]["message"] == MOTIVO_RESPONSAVEL_AUSENTE

    with app.app_context():
        assert db.session.get(Etapa, etapa_id).done is False


def test_api_toggle_conclui_com_area_responsavel(app, client_admin, seed_data):
    etapa_id = _make_etapa_sem_responsavel(app, seed_data)
    with app.app_context():
        db.session.add(
            EtapaResponsavel(etapa_id=etapa_id, area_id=None, label="Outras", ordem=0)
        )
        db.session.commit()

    response = client_admin.post(f"/api/etapas/{etapa_id}/toggle")
    assert response.status_code == 200
    assert response.get_json()["data"]["etapa"]["done"] is True


def test_api_toggle_aceita_responsavel_legado_em_texto(app, client_admin, seed_data):
    etapa_id = _make_etapa_sem_responsavel(app, seed_data)
    with app.app_context():
        db.session.get(Etapa, etapa_id).responsavel = "Equipe Legada"
        db.session.commit()

    response = client_admin.post(f"/api/etapas/{etapa_id}/toggle")
    assert response.status_code == 200
    assert response.get_json()["data"]["etapa"]["done"] is True


def test_api_update_completo_bloqueia_done_sem_responsavel(
    app, client_admin, seed_data
):
    etapa_id = _make_etapa_sem_responsavel(app, seed_data)

    response = client_admin.post(
        f"/api/etapas/{etapa_id}",
        json={
            "descricao": "Etapa importada sem responsavel",
            "responsavel": "   ",
            "comentarios": None,
            "iniciada": True,
            "done": True,
            "data_inicio": "2026-02-02",
            "data_fim": "2026-02-06",
        },
    )
    assert response.status_code == 422
    assert response.get_json()["error"]["message"] == MOTIVO_RESPONSAVEL_AUSENTE

    with app.app_context():
        assert db.session.get(Etapa, etapa_id).done is False


def test_desmarcar_done_nao_exige_responsavel(app, client_admin, seed_data):
    """Reabrir etapa concluída (dado legado) segue permitido sem responsável."""
    etapa_id = _make_etapa_sem_responsavel(app, seed_data)
    with app.app_context():
        db.session.get(Etapa, etapa_id).done = True
        db.session.commit()

    response = client_admin.post(f"/api/etapas/{etapa_id}/toggle")
    assert response.status_code == 200
    assert response.get_json()["data"]["etapa"]["done"] is False
