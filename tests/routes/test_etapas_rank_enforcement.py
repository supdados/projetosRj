"""Regressão do enforcement de rank nas escritas de ETAPA e REUNIÃO (S3/F2-4).

Prova os dois lados exigidos pela sprint:
    - gestor (papel de todo vínculo após o backfill da S2) mantém EXATAMENTE o
      comportamento de hoje — nenhum usuário real perde acesso no deploy;
    - editor mantém as escritas de etapa/reunião; leitor perde todas elas.

Contrato HTTP (S5/F4-2): rank 0 (usuário de outro órgão) responde **404
``not_found``** com o corpo canônico do id inexistente; 403 ``forbidden`` fica
para quem já vê o projeto e tenta ação acima do rank (leitor nas escritas).
"""

import pytest
import time

from models import Etapa, User, UserOrgao, db
from services.authorization import PAPEL_EDITOR, PAPEL_GESTOR, PAPEL_LEITOR

AJAX_HEADERS = {"X-Requested-With": "XMLHttpRequest"}


def _cliente_com_papel(app, seed_data, username: str, papel: str):
    """Cria usuário vinculado ao órgão dono do projeto com o papel dado e loga."""
    with app.app_context():
        user = User(username=username, name=username, orgao="Orgao Teste")
        user.set_password("senha123")
        db.session.add(user)
        db.session.flush()
        db.session.add(
            UserOrgao(
                user_id=user.id,
                orgao_id=seed_data["auditoria_orgao_id"],
                papel=papel,
            )
        )
        db.session.commit()
        user_id = user.id

    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["login_at"] = time.time()
    return client


@pytest.fixture
def client_leitor(app, seed_data):
    return _cliente_com_papel(app, seed_data, "etapas_leitor", PAPEL_LEITOR)


@pytest.fixture
def client_editor(app, seed_data):
    return _cliente_com_papel(app, seed_data, "etapas_editor", PAPEL_EDITOR)


@pytest.fixture
def client_gestor(app, seed_data):
    return _cliente_com_papel(app, seed_data, "etapas_gestor", PAPEL_GESTOR)


def _erro(response) -> dict:
    payload = response.get_json()
    assert payload["ok"] is False
    return payload["error"]


def _payload_etapa() -> dict:
    return {
        "descricao": "Etapa nova",
        "data_inicio": "2026-05-04",
        "responsaveis": [{"area_id": None, "label": "Outras"}],
    }


# ── API enveloped (routes/api/etapas.py) ─────────────────────────────────────


def test_api_add_etapa_negado_para_leitor(app, client_leitor, seed_data):
    response = client_leitor.post(
        f"/api/projetos/{seed_data['project_id']}/etapas", json=_payload_etapa()
    )

    assert response.status_code == 403
    assert _erro(response)["code"] == "forbidden"


def test_api_add_etapa_permitido_para_editor(app, client_editor, seed_data):
    response = client_editor.post(
        f"/api/projetos/{seed_data['project_id']}/etapas", json=_payload_etapa()
    )

    assert response.status_code == 200


def test_api_add_etapa_permitido_para_gestor(app, client_gestor, seed_data):
    response = client_gestor.post(
        f"/api/projetos/{seed_data['project_id']}/etapas", json=_payload_etapa()
    )

    assert response.status_code == 200


def test_api_update_field_negado_para_leitor(app, client_leitor, seed_data):
    response = client_leitor.post(
        f"/api/etapas/{seed_data['etapa_id']}/update-field",
        json={"field": "descricao", "value": "x"},
    )

    assert response.status_code == 403
    assert (
        _erro(response)["message"]
        == "Você não tem permissão para alterar etapas deste projeto."
    )


def test_api_delete_etapa_negado_para_leitor(app, client_leitor, seed_data):
    response = client_leitor.post(f"/api/etapas/{seed_data['etapa_id']}/delete")

    assert response.status_code == 403


def test_api_delete_etapa_permitido_para_editor(app, client_editor, seed_data):
    response = client_editor.post(f"/api/etapas/{seed_data['etapa_id']}/delete")

    assert response.status_code == 200


def test_api_reordenar_negado_para_leitor(app, client_leitor, seed_data):
    response = client_leitor.post(
        f"/api/projetos/{seed_data['project_id']}/etapas/reordenar",
        json={"etapa_ids": [seed_data["etapa_id"]]},
    )

    assert response.status_code == 403


def test_api_reordenar_permitido_para_editor(app, client_editor, seed_data):
    response = client_editor.post(
        f"/api/projetos/{seed_data['project_id']}/etapas/reordenar",
        json={"etapa_ids": [seed_data["etapa_id"]]},
    )

    assert response.status_code == 200


def test_api_comentario_negado_para_leitor(app, client_leitor, seed_data):
    response = client_leitor.post(
        f"/api/etapas/{seed_data['etapa_id']}/comentario",
        json={"comentario": "nao deveria gravar"},
    )

    assert response.status_code == 403


def test_api_importar_modelo_negado_para_leitor(app, client_leitor, seed_data):
    response = client_leitor.post(
        f"/api/projetos/{seed_data['project_id']}/importar-modelo",
        json={"template_id": seed_data["template_id"], "start_date": "2026-05-04"},
    )

    assert response.status_code == 403


def test_api_rank_zero_responde_404_anti_enumeracao(app, client_outsider, seed_data):
    """S5/F4-2: fora de escopo é 404, byte a byte igual ao do id inexistente."""
    fora_do_escopo = client_outsider.post(
        f"/api/projetos/{seed_data['project_id']}/etapas", json=_payload_etapa()
    )
    inexistente = client_outsider.post(
        "/api/projetos/999999/etapas", json=_payload_etapa()
    )

    assert fora_do_escopo.status_code == 404
    assert _erro(fora_do_escopo)["code"] == "not_found"
    assert fora_do_escopo.get_json() == inexistente.get_json()


def test_api_projeto_inexistente_continua_404(app, client_editor):
    response = client_editor.post("/api/projetos/999999/etapas", json=_payload_etapa())

    assert response.status_code == 404
    assert _erro(response)["code"] == "not_found"


# ── Rotas ajax/Jinja (routes/etapas/crud.py) ─────────────────────────────────


def test_ajax_add_etapa_negado_para_leitor(app, client_leitor, seed_data):
    response = client_leitor.post(
        f"/project/{seed_data['project_id']}/etapa/add",
        data={"etapa_descricao": "Etapa leitor"},
        headers=AJAX_HEADERS,
    )

    assert response.status_code == 403
    assert response.get_json()["success"] is False


def test_ajax_add_etapa_permitido_para_editor(app, client_editor, seed_data):
    response = client_editor.post(
        f"/project/{seed_data['project_id']}/etapa/add",
        data={"etapa_descricao": "Etapa editor"},
        headers=AJAX_HEADERS,
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is True


def test_ajax_delete_etapa_negado_para_leitor(app, client_leitor, seed_data):
    response = client_leitor.post(
        f"/etapa/{seed_data['etapa_id']}/delete", headers=AJAX_HEADERS
    )

    assert response.status_code == 403


def test_ajax_reordenar_negado_para_leitor(app, client_leitor, seed_data):
    """Antes da S3 bastava ter vínculo (``user_can_access_project``)."""
    response = client_leitor.post(
        f"/project/{seed_data['project_id']}/etapas/reordenar",
        json={"etapa_ids": [seed_data["etapa_id"]]},
    )

    assert response.status_code == 403


def test_ajax_reordenar_permitido_para_gestor(app, client_gestor, seed_data):
    response = client_gestor.post(
        f"/project/{seed_data['project_id']}/etapas/reordenar",
        json={"etapa_ids": [seed_data["etapa_id"]]},
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is True


def test_ajax_toggle_iniciada_negado_para_leitor(app, client_leitor, seed_data):
    response = client_leitor.post(f"/etapa/{seed_data['etapa_id']}/toggle_iniciada")

    assert response.status_code == 403


def test_ajax_toggle_iniciada_permitido_para_editor(app, client_editor, seed_data):
    response = client_editor.post(f"/etapa/{seed_data['etapa_id']}/toggle_iniciada")

    assert response.status_code == 200
    assert response.get_json()["success"] is True


def test_ajax_update_field_negado_para_leitor(app, client_leitor, seed_data):
    response = client_leitor.post(
        f"/etapa/{seed_data['etapa_id']}/update_field",
        json={"field": "descricao", "value": "x"},
    )

    assert response.status_code == 403


def test_ajax_comentario_negado_para_leitor(app, client_leitor, seed_data):
    response = client_leitor.post(
        f"/etapa/{seed_data['etapa_id']}/comentario", json={"comentario": "x"}
    )

    assert response.status_code == 403


def test_ajax_cascade_update_negado_para_leitor(app, client_leitor, seed_data):
    response = client_leitor.post(
        f"/project/{seed_data['project_id']}/cascade_update",
        json={"etapa_id": seed_data["etapa_id"], "days_diff": 2},
    )

    assert response.status_code == 403


# ── Reuniões e importação de modelo (routes/etapas/meetings.py) ──────────────


def test_meeting_add_negado_para_leitor(app, client_leitor, seed_data):
    response = client_leitor.post(
        f"/project/{seed_data['project_id']}/meeting/add",
        data={"titulo": "Reuniao"},
        headers=AJAX_HEADERS,
    )

    assert response.status_code == 403


def test_meeting_add_passa_o_gate_para_editor(app, client_editor, seed_data):
    """Editor não é barrado por permissão: para na falta de conta Google (400)."""
    response = client_editor.post(
        f"/project/{seed_data['project_id']}/meeting/add",
        data={"titulo": "Reuniao"},
        headers=AJAX_HEADERS,
    )

    assert response.status_code == 400


def test_api_meeting_create_negado_para_leitor(app, client_leitor, seed_data):
    response = client_leitor.post(
        f"/api/projetos/{seed_data['project_id']}/reunioes", json={}
    )

    assert response.status_code == 403
    assert (
        _erro(response)["message"]
        == "Você não tem permissão para adicionar reuniões a este projeto."
    )


def test_api_meeting_create_passa_o_gate_para_editor(app, client_editor, seed_data):
    """Editor não é barrado por rank: para na falta de conta Google (400)."""
    response = client_editor.post(
        f"/api/projetos/{seed_data['project_id']}/reunioes", json={}
    )

    assert response.status_code == 400
    assert _erro(response)["code"] == "validation"


def test_api_meeting_create_passa_o_gate_para_gestor(app, client_gestor, seed_data):
    """Equivalência gestor: mesma resposta de antes da S3 (400 sem conta Google)."""
    response = client_gestor.post(
        f"/api/projetos/{seed_data['project_id']}/reunioes", json={}
    )

    assert response.status_code == 400
    assert _erro(response)["code"] == "validation"


def test_api_meeting_create_rank_zero_responde_404(app, client_outsider, seed_data):
    """S5/F4-2: rank 0 não recebe a mensagem de reunião — recebe o 404 canônico."""
    fora_do_escopo = client_outsider.post(
        f"/api/projetos/{seed_data['project_id']}/reunioes", json={}
    )
    inexistente = client_outsider.post("/api/projetos/999999/reunioes", json={})

    assert fora_do_escopo.status_code == 404
    assert _erro(fora_do_escopo)["code"] == "not_found"
    assert fora_do_escopo.get_json() == inexistente.get_json()


def test_api_meeting_edit_rank_zero_responde_404(app, client_outsider, seed_data):
    """Etapa de projeto invisível some: mesmo 404 da etapa inexistente."""
    fora_do_escopo = client_outsider.post(
        f"/api/etapas/{seed_data['etapa_id']}/reuniao", json={}
    )
    inexistente = client_outsider.post("/api/etapas/999999/reuniao", json={})

    assert fora_do_escopo.status_code == 404
    assert fora_do_escopo.get_json() == inexistente.get_json()


def test_api_meeting_edit_negado_para_leitor(app, client_leitor, seed_data):
    """403 de rank vem ANTES do 400 de etapa-não-reunião."""
    response = client_leitor.post(
        f"/api/etapas/{seed_data['etapa_id']}/reuniao", json={}
    )

    assert response.status_code == 403
    assert (
        _erro(response)["message"] == "Você não tem permissão para editar esta reunião."
    )


def test_api_meeting_edit_passa_o_gate_para_gestor(app, client_gestor, seed_data):
    response = client_gestor.post(
        f"/api/etapas/{seed_data['etapa_id']}/reuniao", json={}
    )

    assert response.status_code == 400
    assert _erro(response)["message"] == "Esta etapa não é uma reunião Google editável."


def test_api_meeting_delete_negado_para_leitor(app, client_leitor, seed_data):
    response = client_leitor.post(
        f"/api/etapas/{seed_data['etapa_id']}/reuniao/excluir"
    )

    assert response.status_code == 403
    assert (
        _erro(response)["message"]
        == "Você não tem permissão para excluir esta reunião."
    )


def test_api_meeting_delete_passa_o_gate_para_gestor(app, client_gestor, seed_data):
    response = client_gestor.post(
        f"/api/etapas/{seed_data['etapa_id']}/reuniao/excluir"
    )

    assert response.status_code == 422
    assert _erro(response)["message"] == "Esta etapa não é uma reunião Google."


def test_import_model_nao_cria_etapas_para_leitor(app, client_leitor, seed_data):
    with app.app_context():
        antes = Etapa.query.filter_by(project_id=seed_data["project_id"]).count()

    client_leitor.post(
        f"/project/{seed_data['project_id']}/import_model",
        data={
            "template_id": seed_data["template_id"],
            "start_date": "2026-05-04",
        },
    )

    with app.app_context():
        assert (
            Etapa.query.filter_by(project_id=seed_data["project_id"]).count() == antes
        )


def test_import_model_cria_etapas_para_gestor(app, client_gestor, seed_data):
    with app.app_context():
        antes = Etapa.query.filter_by(project_id=seed_data["project_id"]).count()

    client_gestor.post(
        f"/project/{seed_data['project_id']}/import_model",
        data={
            "template_id": seed_data["template_id"],
            "start_date": "2026-05-04",
        },
    )

    with app.app_context():
        assert Etapa.query.filter_by(project_id=seed_data["project_id"]).count() > antes
