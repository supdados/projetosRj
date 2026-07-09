"""Testes de contrato dos endpoints JSON das telas de leitura (Fase 2).

Afirmam o shape ``{"ok": true, "data": ...}`` / ``{"ok": false, "error":
{"code", "message"}}`` de ``/api/projetos-pendentes``,
``/api/projetos/<id>/historico`` e ``/api/busca``, o 401 JSON do guard
``api_login_required`` quando não há sessão e, para o histórico, os 403/404
estruturados (acesso fora do escopo / projeto inexistente).

Reutiliza as fixtures de ``tests/conftest.py`` (``client`` anônimo,
``client_user`` autenticado como ``user_auditoria``, ``client_outsider`` como
``user_vpd`` e ``seed_data``). Sem mocks de rede: os endpoints operam sobre a
sessão e o banco de teste já semeado.
"""

from __future__ import annotations

from typing import Any


def _assert_ok_envelope(payload: Any) -> dict[str, Any]:
    """Valida o envelope de sucesso e devolve o ``data``."""
    assert isinstance(payload, dict)
    assert payload["ok"] is True
    assert "data" in payload
    assert "error" not in payload
    return payload["data"]


def _assert_fail_envelope(payload: Any, *, code: str) -> None:
    """Valida o envelope de erro e o ``code`` canônico esperado."""
    assert isinstance(payload, dict)
    assert payload["ok"] is False
    assert "data" not in payload
    error = payload["error"]
    assert error["code"] == code
    assert isinstance(error["message"], str)
    assert error["message"]


# ---------------------------------------------------------------------------
# /api/projetos-pendentes
# ---------------------------------------------------------------------------


def test_api_projetos_pendentes_returns_ok_envelope_with_expected_shape(client_user):
    response = client_user.get("/api/projetos-pendentes")

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert isinstance(data["projetos"], list)
    assert "summary_counts" in data
    assert "total_projects" in data["summary_counts"]
    assert "pagination" in data
    assert set(data["pagination"].keys()) == {
        "page",
        "per_page",
        "total_pages",
        "total",
    }
    assert isinstance(data["responsaveis_options"], list)


def test_api_projetos_pendentes_row_reuses_card_serializers(client_user):
    """Cada linha expõe um ``project`` (card) e etapas serializadas (card)."""
    data = _assert_ok_envelope(client_user.get("/api/projetos-pendentes").get_json())
    if not data["projetos"]:
        return
    row = data["projetos"][0]
    assert "id" in row["project"]
    assert "titulo" in row["project"]
    assert "password_hash" not in row["project"]
    assert isinstance(row["etapas_visiveis"], list)
    assert "qtd_atrasadas" in row


def test_api_projetos_pendentes_exposes_etapa_position_map(client_user):
    """A numeração "<projeto>.<posição>" do Detalhe depende deste mapa: cada
    etapa exibida deve ter posição 1-based dentro do próprio projeto."""
    data = _assert_ok_envelope(client_user.get("/api/projetos-pendentes").get_json())
    positions = data["etapa_position_map"]
    assert isinstance(positions, dict)
    for row in data["projetos"]:
        for etapa in row["etapas_visiveis"] + row["etapas_outras"]:
            position = positions[str(etapa["id"])]
            assert isinstance(position, int) and position >= 1


def test_api_projetos_pendentes_responsaveis_options_sem_duplicatas(
    app, client_user, seed_data
):
    """Regressão: responsáveis duplicados após strip quebravam o {#each} da SPA.

    O DISTINCT roda no banco ANTES do strip — "Equipe Dedup" e "Equipe Dedup "
    são linhas distintas no SQL mas idênticas após o trim; a opção deve
    aparecer UMA vez (each_key_duplicate derrubava a tela de pendentes).
    """
    from models import Etapa, db

    with app.app_context():
        db.session.add_all(
            [
                Etapa(
                    descricao="Etapa dedup A",
                    responsavel="Equipe Dedup",
                    project_id=seed_data["project_id"],
                    ordem=90,
                ),
                Etapa(
                    descricao="Etapa dedup B",
                    responsavel="Equipe Dedup ",
                    project_id=seed_data["project_id"],
                    ordem=91,
                ),
            ]
        )
        db.session.commit()

    data = _assert_ok_envelope(client_user.get("/api/projetos-pendentes").get_json())
    options = data["responsaveis_options"]
    assert options.count("Equipe Dedup") == 1
    assert len(options) == len(set(options))


def test_api_projetos_pendentes_returns_401_json_when_unauthenticated(client):
    response = client.get("/api/projetos-pendentes")

    assert response.status_code == 401
    _assert_fail_envelope(response.get_json(), code="unauthenticated")


def test_api_projetos_pendentes_invalid_orgao_filter_returns_422_envelope(client_user):
    """Filtro de órgão fora do escopo => 422 ``validation`` (não 302)."""
    response = client_user.get("/api/projetos-pendentes?orgao=999999")

    assert response.status_code == 422
    _assert_fail_envelope(response.get_json(), code="validation")


# ---------------------------------------------------------------------------
# /api/projetos/<id>/historico
# ---------------------------------------------------------------------------


def test_api_projeto_historico_returns_ok_envelope_with_expected_shape(
    client_user, seed_data
):
    project_id = seed_data["project_id"]
    response = client_user.get(f"/api/projetos/{project_id}/historico")

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data["project"]["id"] == project_id
    assert isinstance(data["history"], list)
    assert data["history"], "seed_data registra ao menos uma entrada de histórico"
    entry = data["history"][0]
    assert set(entry.keys()) == {
        "id",
        "project_id",
        "action_type",
        "action_description",
        "old_value",
        "new_value",
        "timestamp",
        "user",
    }
    assert "password_hash" not in (entry["user"] or {})


def test_api_projeto_historico_returns_401_json_when_unauthenticated(client, seed_data):
    project_id = seed_data["project_id"]
    response = client.get(f"/api/projetos/{project_id}/historico")

    assert response.status_code == 401
    _assert_fail_envelope(response.get_json(), code="unauthenticated")


def test_api_projeto_historico_returns_404_envelope_for_missing_project(client_user):
    response = client_user.get("/api/projetos/999999/historico")

    assert response.status_code == 404
    _assert_fail_envelope(response.get_json(), code="not_found")


def test_api_projeto_historico_returns_403_envelope_out_of_scope(
    client_outsider, seed_data
):
    """``user_vpd`` não acessa o projeto da Auditoria => 403 ``forbidden``."""
    project_id = seed_data["project_id"]
    response = client_outsider.get(f"/api/projetos/{project_id}/historico")

    assert response.status_code == 403
    _assert_fail_envelope(response.get_json(), code="forbidden")


# ---------------------------------------------------------------------------
# /api/busca
# ---------------------------------------------------------------------------


def test_api_busca_returns_ok_envelope_with_expected_shape(client_user):
    response = client_user.get("/api/busca?q=Projeto")

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data["query"] == "Projeto"
    assert set(data["results"].keys()) == {"projects", "stages", "tasks", "events"}
    assert "counts" in data
    assert "total" in data["counts"]
    assert "has_more" in data["meta"]


def test_api_busca_limit_all_returns_every_record_without_cap(
    app, client_user, seed_data
):
    """`limit=all` (tela cheia) traz TODOS os registros — sem cap por tipo nem has_more.

    O dropdown do topo continua mandando `limit=5` (cap + has_more); a página de
    busca manda `limit=all` para não esconder registros.
    """
    from models import Project, db
    from tests._orgao_helpers import ensure_orgao

    with app.app_context():
        orgao_id = ensure_orgao("Auditoria").id
        for index in range(6):
            db.session.add(
                Project(
                    titulo=f"BuscaLimitAll Projeto {index}",
                    orgao_id=orgao_id,
                    orgao="Orgao BuscaLimitAll",
                    prioridade="media",
                    status="Vigente",
                    objetivo_id=1,
                    resultado_esperado_id=1,
                )
            )
        db.session.commit()

    capped = _assert_ok_envelope(
        client_user.get("/api/busca?q=BuscaLimitAll&limit=5").get_json()
    )
    assert len(capped["results"]["projects"]) == 5
    assert capped["meta"]["has_more"]["projects"] is True

    full = _assert_ok_envelope(
        client_user.get("/api/busca?q=BuscaLimitAll&limit=all").get_json()
    )
    assert len(full["results"]["projects"]) == 6
    assert full["meta"]["limit_per_type"] is None
    assert full["meta"]["has_more"]["projects"] is False
    assert full["meta"]["has_more"]["any"] is False


def test_api_busca_short_term_returns_empty_payload_envelope(client_user):
    """Termo com menos de 2 caracteres => payload vazio canônico (sem varredura)."""
    response = client_user.get("/api/busca?q=a")

    assert response.status_code == 200
    data = _assert_ok_envelope(response.get_json())
    assert data["counts"]["total"] == 0
    assert data["results"]["projects"] == []
    assert data["meta"]["limit_per_type"] is None


def test_api_busca_returns_401_json_when_unauthenticated(client):
    response = client.get("/api/busca?q=Projeto")

    assert response.status_code == 401
    _assert_fail_envelope(response.get_json(), code="unauthenticated")
