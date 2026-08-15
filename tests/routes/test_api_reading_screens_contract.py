"""Testes de contrato dos endpoints JSON das telas de leitura (Fase 2).

Afirmam o shape ``{"ok": true, "data": ...}`` / ``{"ok": false, "error":
{"code", "message"}}`` de ``/api/projetos-pendentes``,
``/api/projetos/<id>/historico`` e ``/api/busca``, o 401 JSON do guard
``api_login_required`` quando não há sessão e, para o histórico, o 404 canônico
da S5 (projeto inexistente e projeto invisível respondem o MESMO envelope).

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
    from models import Etapa, EtapaResponsavel, db

    with app.app_context():
        etapa_a = Etapa(
            descricao="Etapa dedup A",
            project_id=seed_data["project_id"],
            ordem=90,
        )
        etapa_a.responsaveis = [EtapaResponsavel(area_id=None, label="Equipe Dedup")]
        etapa_b = Etapa(
            descricao="Etapa dedup B",
            project_id=seed_data["project_id"],
            ordem=91,
        )
        etapa_b.responsaveis = [EtapaResponsavel(area_id=None, label="Equipe Dedup ")]
        db.session.add_all([etapa_a, etapa_b])
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


def test_api_projeto_historico_returns_404_envelope_for_rank_zero(
    client_outsider, seed_data
):
    """``user_vpd`` tem rank 0 no projeto da Auditoria => 404 igual ao inexistente."""
    project_id = seed_data["project_id"]
    fora_do_escopo = client_outsider.get(f"/api/projetos/{project_id}/historico")
    inexistente = client_outsider.get("/api/projetos/999999/historico")

    assert fora_do_escopo.status_code == 404
    _assert_fail_envelope(fora_do_escopo.get_json(), code="not_found")
    assert fora_do_escopo.get_json() == inexistente.get_json()


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


# ---------------------------------------------------------------------------
# /api/busca — modo paginado (?page=)
# ---------------------------------------------------------------------------


def _seed_busca_paginada(app, seed_data) -> None:
    """Semeia 3 projetos + 3 etapas que casam com o termo "BuscaPaginada"."""
    from models import Etapa, Project, db
    from tests._orgao_helpers import ensure_orgao

    with app.app_context():
        orgao_id = ensure_orgao("Auditoria").id
        for index in range(3):
            db.session.add(
                Project(
                    titulo=f"BuscaPaginada Projeto {index}",
                    orgao_id=orgao_id,
                    orgao="Orgao BuscaPaginada",
                    prioridade="media",
                    status="Vigente",
                    objetivo_id=1,
                    resultado_esperado_id=1,
                )
            )
            db.session.add(
                Etapa(
                    descricao=f"BuscaPaginada Etapa {index}",
                    project_id=seed_data["project_id"],
                    ordem=70 + index,
                )
            )
        db.session.commit()


def test_api_busca_paginated_returns_pagination_meta(app, client_user, seed_data):
    _seed_busca_paginada(app, seed_data)

    data = _assert_ok_envelope(
        client_user.get("/api/busca?q=BuscaPaginada&page=1").get_json()
    )

    assert data["meta"]["pagination"] == {
        "page": 1,
        "per_page": 40,
        "total_pages": 1,
        "total": 6,
    }
    assert data["meta"]["type_counts"] == {
        "projects": 3,
        "stages": 3,
        "tasks": 0,
        "events": 0,
    }
    assert data["meta"]["selected_types"] == ["projects", "stages", "tasks", "events"]
    assert data["meta"]["limit_per_type"] is None
    assert data["meta"]["has_more"]["any"] is False
    total_items = sum(len(items) for items in data["results"].values())
    assert total_items == 6
    assert data["counts"]["total"] == 6


def test_api_busca_paginated_page_crosses_type_boundary(app, client_user, seed_data):
    """A lista plana projetos → etapas corta no meio: página 1 leva a cauda de
    projetos + o início de etapas; página 2 leva o restante das etapas."""
    _seed_busca_paginada(app, seed_data)

    page_one = _assert_ok_envelope(
        client_user.get("/api/busca?q=BuscaPaginada&page=1&per_page=4").get_json()
    )
    assert len(page_one["results"]["projects"]) == 3
    assert len(page_one["results"]["stages"]) == 1
    assert page_one["meta"]["pagination"]["total_pages"] == 2

    page_two = _assert_ok_envelope(
        client_user.get("/api/busca?q=BuscaPaginada&page=2&per_page=4").get_json()
    )
    assert page_two["results"]["projects"] == []
    assert len(page_two["results"]["stages"]) == 2
    assert page_two["meta"]["pagination"]["page"] == 2

    page_one_titles = {item["title"] for item in page_one["results"]["stages"]}
    page_two_titles = {item["title"] for item in page_two["results"]["stages"]}
    assert not page_one_titles & page_two_titles


def test_api_busca_paginated_types_filter_combines_selected_types(
    app, client_user, seed_data
):
    _seed_busca_paginada(app, seed_data)

    data = _assert_ok_envelope(
        client_user.get(
            "/api/busca?q=BuscaPaginada&page=1&types=projects,events"
        ).get_json()
    )

    assert data["meta"]["selected_types"] == ["projects", "events"]
    assert data["results"]["stages"] == []
    assert data["results"]["tasks"] == []
    assert len(data["results"]["projects"]) == 3
    assert data["meta"]["pagination"]["total"] == 3
    assert data["counts"] == {
        "projects": 3,
        "stages": 0,
        "tasks": 0,
        "events": 0,
        "total": 3,
    }
    assert data["meta"]["type_counts"]["stages"] == 3


def test_api_busca_paginated_types_only_stages(app, client_user, seed_data):
    _seed_busca_paginada(app, seed_data)

    data = _assert_ok_envelope(
        client_user.get("/api/busca?q=BuscaPaginada&page=1&types=stages").get_json()
    )

    assert data["meta"]["selected_types"] == ["stages"]
    assert data["results"]["projects"] == []
    assert len(data["results"]["stages"]) == 3
    assert data["counts"]["total"] == 3
    assert data["meta"]["type_counts"]["projects"] == 3


def test_api_busca_paginated_invalid_params_fall_back_and_clamp(
    app, client_user, seed_data
):
    _seed_busca_paginada(app, seed_data)

    invalid_types = _assert_ok_envelope(
        client_user.get("/api/busca?q=BuscaPaginada&page=1&types=banana,").get_json()
    )
    assert invalid_types["meta"]["selected_types"] == [
        "projects",
        "stages",
        "tasks",
        "events",
    ]

    clamped_per_page = _assert_ok_envelope(
        client_user.get("/api/busca?q=BuscaPaginada&page=1&per_page=999").get_json()
    )
    assert clamped_per_page["meta"]["pagination"]["per_page"] == 100

    clamped_page = _assert_ok_envelope(
        client_user.get("/api/busca?q=BuscaPaginada&page=999&per_page=4").get_json()
    )
    assert clamped_page["meta"]["pagination"]["page"] == 2
    assert len(clamped_page["results"]["stages"]) == 2


def test_api_busca_paginated_short_term_returns_empty_paginated_payload(client_user):
    data = _assert_ok_envelope(client_user.get("/api/busca?q=a&page=3").get_json())

    assert data["counts"]["total"] == 0
    assert data["results"]["projects"] == []
    assert data["meta"]["pagination"] == {
        "page": 1,
        "per_page": 40,
        "total_pages": 0,
        "total": 0,
    }
    assert data["meta"]["type_counts"] == {
        "projects": 0,
        "stages": 0,
        "tasks": 0,
        "events": 0,
    }
    assert data["meta"]["selected_types"] == ["projects", "stages", "tasks", "events"]


def test_api_busca_dropdown_mode_has_no_pagination_keys(app, client_user, seed_data):
    """Regressão: sem ``page`` o payload do dropdown fica bit-a-bit igual ao
    atual (cap por tipo + has_more, sem chaves de paginação)."""
    _seed_busca_paginada(app, seed_data)

    data = _assert_ok_envelope(
        client_user.get("/api/busca?q=BuscaPaginada&limit=2").get_json()
    )

    assert len(data["results"]["projects"]) == 2
    assert data["meta"]["has_more"]["projects"] is True
    assert data["meta"]["limit_per_type"] == 2
    assert "pagination" not in data["meta"]
    assert "type_counts" not in data["meta"]
    assert "selected_types" not in data["meta"]


def test_api_projetos_pendentes_responsaveis_options_um_item_por_area(
    app, client_user, seed_data
):
    """Etapa com N áreas gera N opções — nunca a string concatenada.

    Regressão: o filtro lia o espelho legado ``Etapa.responsavel``
    ("SUBEXE, COODADOS, COOACES"), então três áreas viravam UMA opção só e o
    usuário não conseguia filtrar por uma delas isoladamente.
    """
    from models import Etapa, db
    from services.etapa_responsaveis import replace_etapa_responsaveis
    from tests._orgao_helpers import ensure_orgao

    with app.app_context():
        areas = [ensure_orgao(sigla) for sigla in ("SUBEXE", "COODADOS", "COOACES")]
        etapa = Etapa(
            descricao="Etapa multi-area",
            project_id=seed_data["project_id"],
            ordem=95,
        )
        db.session.add(etapa)
        db.session.flush()
        replace_etapa_responsaveis(etapa, [{"area_id": a.id} for a in areas])
        db.session.commit()
        mirror = etapa.responsavel

    assert "," in mirror  # o espelho legado continua concatenado

    data = _assert_ok_envelope(client_user.get("/api/projetos-pendentes").get_json())
    options = data["responsaveis_options"]
    assert {"SUBEXE", "COODADOS", "COOACES"} <= set(options)
    assert mirror not in options
    assert not [opt for opt in options if "," in opt]


def test_api_projetos_pendentes_filtro_responsavel_casa_area_isolada(
    app, client_user, seed_data
):
    """Filtrar por uma das áreas traz a etapa; prefixo de sigla não casa."""
    import datetime

    from models import Etapa, db
    from services.etapa_responsaveis import replace_etapa_responsaveis
    from tests._orgao_helpers import ensure_orgao

    ontem = datetime.date.today() - datetime.timedelta(days=1)
    with app.app_context():
        areas = [ensure_orgao(sigla) for sigla in ("SUBEXE", "COODADOS")]
        # data_fim no passado => bucket "atrasada", visível no período default.
        etapa = Etapa(
            descricao="Etapa filtro area",
            project_id=seed_data["project_id"],
            ordem=96,
            data_inicio=ontem,
            data_fim=ontem,
        )
        db.session.add(etapa)
        db.session.flush()
        replace_etapa_responsaveis(etapa, [{"area_id": a.id} for a in areas])
        db.session.commit()
        etapa_id = etapa.id

    def _etapa_ids(responsavel: str) -> set[int]:
        payload = client_user.get(
            f"/api/projetos-pendentes?responsavel={responsavel}"
        ).get_json()
        data = _assert_ok_envelope(payload)
        return {
            etapa["id"] for row in data["projetos"] for etapa in row["etapas_visiveis"]
        }

    assert etapa_id in _etapa_ids("COODADOS")
    assert etapa_id in _etapa_ids("SUBEXE")
    # "COO" é prefixo de COODADOS: substring casaria, rótulo exato não.
    assert etapa_id not in _etapa_ids("COO")
