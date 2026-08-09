"""Testes de contrato dos endpoints JSON do Detalhe de Projeto (Fase 5a).

Afirmam o envelope canônico ``{"ok": true, "data": ...}`` /
``{"ok": false, "error": {"code", "message"}}`` de
``GET  /api/projetos/<id>/detalhe``,
``POST /api/projetos/<id>/inline`` e
``GET  /api/projetos/<id>/tarefas-etapa``, além dos guards de acesso (401 sem
sessão; 404 para projeto inexistente E para rank 0 — mesmo corpo, S5/F4-2b; 403
só quando o usuário já vê o projeto mas a ação exige mais rank) e da validação
(422).

Reutiliza as fixtures de ``tests/conftest.py`` (``client`` anônimo,
``client_user`` como ``user_auditoria``, ``client_outsider`` como ``user_vpd`` e
``seed_data``). Sem mocks de rede: operam sobre a sessão e o banco semeado.
"""

from __future__ import annotations

from typing import Any

import pytest
import time

from models import ProjectMember, User, db
from services.authorization import PAPEL_LEITOR


@pytest.fixture
def client_convidado_leitor(app, seed_data):
    """Usuário SEM vínculo de área, com convite ``leitor`` no projeto semeado.

    Prova o outro lado do par S5: quem enxerga o projeto nunca cai no 404 de
    autorização — recebe 403 quando a ação exige rank acima do seu.
    """
    with app.app_context():
        convidado = User(
            username="convidado_leitor",
            name="Convidado Leitor",
            orgao="Orgao Teste",
        )
        convidado.set_password("senha123")
        db.session.add(convidado)
        db.session.flush()
        db.session.add(
            ProjectMember(
                project_id=seed_data["project_id"],
                user_id=convidado.id,
                papel=PAPEL_LEITOR,
                granted_by_id=seed_data["admin_id"],
            )
        )
        db.session.commit()
        convidado_id = convidado.id

    http_client = app.test_client()
    with http_client.session_transaction() as session:
        session["user_id"] = convidado_id
        session["login_at"] = time.time()
    return http_client


def _assert_ok_envelope(payload: Any) -> dict[str, Any]:
    assert isinstance(payload, dict)
    assert payload["ok"] is True
    assert "data" in payload
    assert "error" not in payload
    return payload["data"]


def _assert_fail_envelope(payload: Any, *, code: str) -> None:
    assert isinstance(payload, dict)
    assert payload["ok"] is False
    assert "data" not in payload
    error = payload["error"]
    assert error["code"] == code
    assert isinstance(error["message"], str)
    assert error["message"]


# ---------------------------------------------------------------------------
# GET /api/projetos/<id>/detalhe
# ---------------------------------------------------------------------------


def test_api_projeto_detalhe_returns_ok_envelope_with_expected_shape(
    client_user, seed_data
):
    project_id = seed_data["project_id"]
    response = client_user.get(f"/api/projetos/{project_id}/detalhe")

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data["project"]["id"] == project_id
    assert "password_hash" not in data["project"]
    assert isinstance(data["etapas"], list)
    assert data["etapas"], "seed_data registra etapas no projeto"
    assert set(data["derived"].keys()) == {
        "data_inicio_projeto",
        "data_fim_projeto",
        "total_workflow_etapas",
        "todas_etapas_concluidas",
    }
    assert set(data["options"].keys()) == {
        "status",
        "prioridade",
        "special_project",
        "delivery_type",
        "abep_indicator",
        "orgaos",
    }
    assert data["permissions"]["can_edit"] is True


def test_api_projeto_detalhe_etapa_has_readonly_task_count(client_user, seed_data):
    """Cada etapa traz contagem de tarefas read-only (sem mutacao na Fase 5a)."""
    project_id = seed_data["project_id"]
    data = _assert_ok_envelope(
        client_user.get(f"/api/projetos/{project_id}/detalhe").get_json()
    )
    etapa = data["etapas"][0]
    assert set(etapa["task_count"].keys()) == {"total", "done"}
    assert "iniciada" in etapa
    assert "comentarios" in etapa
    assert "entry_type" in etapa


def test_api_projeto_detalhe_returns_401_json_when_unauthenticated(client, seed_data):
    project_id = seed_data["project_id"]
    response = client.get(f"/api/projetos/{project_id}/detalhe")

    assert response.status_code == 401
    _assert_fail_envelope(response.get_json(), code="unauthenticated")


def test_api_projeto_detalhe_returns_404_for_missing_project(client_user):
    response = client_user.get("/api/projetos/999999/detalhe")

    assert response.status_code == 404
    _assert_fail_envelope(response.get_json(), code="not_found")


def test_api_projeto_detalhe_returns_404_for_rank_zero(client_outsider, seed_data):
    """S5/F4-2: rank 0 recebe o MESMO 404 do id inexistente (anti-enumeração)."""
    project_id = seed_data["project_id"]
    fora_do_escopo = client_outsider.get(f"/api/projetos/{project_id}/detalhe")
    inexistente = client_outsider.get("/api/projetos/999999/detalhe")

    assert fora_do_escopo.status_code == 404
    _assert_fail_envelope(fora_do_escopo.get_json(), code="not_found")
    assert fora_do_escopo.get_json() == inexistente.get_json()


def test_api_projeto_detalhe_libera_convidado_leitor(
    client_convidado_leitor, seed_data
):
    """Convite leitor (F3-7) dá visão do projeto mesmo sem vínculo de área."""
    project_id = seed_data["project_id"]
    response = client_convidado_leitor.get(f"/api/projetos/{project_id}/detalhe")

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data["project"]["id"] == project_id
    assert data["permissions"]["can_edit"] is False


# ---------------------------------------------------------------------------
# POST /api/projetos/<id>/inline
# ---------------------------------------------------------------------------


def test_api_projeto_inline_updates_field_and_returns_project(client_user, seed_data):
    project_id = seed_data["project_id"]
    response = client_user.post(
        f"/api/projetos/{project_id}/inline",
        json={"titulo": "Projeto Detalhe Editado"},
    )

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data["project"]["titulo"] == "Projeto Detalhe Editado"
    assert "changed" in data


def test_api_projeto_inline_returns_401_json_when_unauthenticated(client, seed_data):
    project_id = seed_data["project_id"]
    response = client.post(f"/api/projetos/{project_id}/inline", json={"titulo": "X"})

    assert response.status_code == 401
    _assert_fail_envelope(response.get_json(), code="unauthenticated")


def test_api_projeto_inline_returns_404_for_missing_project(client_user):
    response = client_user.post("/api/projetos/999999/inline", json={"titulo": "X"})

    assert response.status_code == 404
    _assert_fail_envelope(response.get_json(), code="not_found")


def test_api_projeto_inline_returns_404_for_rank_zero(client_outsider, seed_data):
    project_id = seed_data["project_id"]
    fora_do_escopo = client_outsider.post(
        f"/api/projetos/{project_id}/inline", json={"titulo": "X"}
    )
    inexistente = client_outsider.post(
        "/api/projetos/999999/inline", json={"titulo": "X"}
    )

    assert fora_do_escopo.status_code == 404
    _assert_fail_envelope(fora_do_escopo.get_json(), code="not_found")
    assert fora_do_escopo.get_json() == inexistente.get_json()


def test_api_projeto_inline_returns_403_para_convidado_leitor(
    client_convidado_leitor, seed_data
):
    """Quem VÊ o projeto mas não alcança editor continua em 403 `forbidden`."""
    project_id = seed_data["project_id"]
    response = client_convidado_leitor.post(
        f"/api/projetos/{project_id}/inline", json={"titulo": "X"}
    )

    assert response.status_code == 403
    _assert_fail_envelope(response.get_json(), code="forbidden")


def test_api_projeto_inline_invalid_body_returns_422(client_user, seed_data):
    project_id = seed_data["project_id"]
    response = client_user.post(
        f"/api/projetos/{project_id}/inline",
        data="not-json",
        content_type="application/json",
    )

    assert response.status_code == 422
    _assert_fail_envelope(response.get_json(), code="validation")


def test_api_projeto_inline_invalid_orgao_returns_422(client_user, seed_data):
    """Órgão inexistente => 422 (``validation``), espelhando o 400 do Jinja."""
    project_id = seed_data["project_id"]
    response = client_user.post(
        f"/api/projetos/{project_id}/inline",
        json={"orgao_id": 999999},
    )

    assert response.status_code == 422
    _assert_fail_envelope(response.get_json(), code="validation")


# ---------------------------------------------------------------------------
# GET /api/projetos/<id>/tarefas-etapa
# ---------------------------------------------------------------------------


def test_api_projeto_tarefas_etapa_returns_ok_envelope(client_user, seed_data):
    project_id = seed_data["project_id"]
    etapa_id = seed_data["etapa_id"]
    response = client_user.get(
        f"/api/projetos/{project_id}/tarefas-etapa?etapa_id={etapa_id}"
    )

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data["etapa_id"] == etapa_id
    assert isinstance(data["tasks"], list)
    for task in data["tasks"]:
        assert "descricao" in task
        assert "password_hash" not in task


def test_api_projeto_tarefas_etapa_requires_etapa_id(client_user, seed_data):
    project_id = seed_data["project_id"]
    response = client_user.get(f"/api/projetos/{project_id}/tarefas-etapa")

    assert response.status_code == 422
    _assert_fail_envelope(response.get_json(), code="validation")


def test_api_projeto_tarefas_etapa_returns_401_json_when_unauthenticated(
    client, seed_data
):
    project_id = seed_data["project_id"]
    etapa_id = seed_data["etapa_id"]
    response = client.get(
        f"/api/projetos/{project_id}/tarefas-etapa?etapa_id={etapa_id}"
    )

    assert response.status_code == 401
    _assert_fail_envelope(response.get_json(), code="unauthenticated")


def test_api_projeto_tarefas_etapa_returns_404_for_rank_zero(
    client_outsider, seed_data
):
    project_id = seed_data["project_id"]
    etapa_id = seed_data["etapa_id"]
    fora_do_escopo = client_outsider.get(
        f"/api/projetos/{project_id}/tarefas-etapa?etapa_id={etapa_id}"
    )
    inexistente = client_outsider.get(
        f"/api/projetos/999999/tarefas-etapa?etapa_id={etapa_id}"
    )

    assert fora_do_escopo.status_code == 404
    _assert_fail_envelope(fora_do_escopo.get_json(), code="not_found")
    assert fora_do_escopo.get_json() == inexistente.get_json()


def test_api_projeto_tarefas_etapa_libera_convidado_leitor(
    client_convidado_leitor, seed_data
):
    project_id = seed_data["project_id"]
    etapa_id = seed_data["etapa_id"]
    response = client_convidado_leitor.get(
        f"/api/projetos/{project_id}/tarefas-etapa?etapa_id={etapa_id}"
    )

    assert response.status_code == 200
    _assert_ok_envelope(response.get_json())


# ---------------------------------------------------------------------------
# Par 404/403 nas mutações de etapa do projeto (S5/F4-2)
# ---------------------------------------------------------------------------


def test_api_etapa_mutacao_rank_zero_e_404(client_outsider, seed_data):
    """Rank 0 não distingue "projeto invisível" de "projeto inexistente"."""
    etapa_id = seed_data["etapa_id"]
    fora_do_escopo = client_outsider.post(
        f"/api/etapas/{etapa_id}/update-field",
        json={"field": "descricao", "value": "Bloqueado"},
    )
    inexistente = client_outsider.post(
        "/api/etapas/999999/update-field",
        json={"field": "descricao", "value": "Bloqueado"},
    )

    assert fora_do_escopo.status_code == 404
    _assert_fail_envelope(fora_do_escopo.get_json(), code="not_found")
    assert fora_do_escopo.get_json() == inexistente.get_json()


def test_api_etapa_mutacao_de_convidado_leitor_e_403(
    client_convidado_leitor, seed_data
):
    """Leitor VÊ a etapa mas a mutação exige editor => 403 `forbidden`."""
    response = client_convidado_leitor.post(
        f"/api/etapas/{seed_data['etapa_id']}/update-field",
        json={"field": "descricao", "value": "Bloqueado"},
    )

    assert response.status_code == 403
    _assert_fail_envelope(response.get_json(), code="forbidden")
