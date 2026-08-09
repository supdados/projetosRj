import datetime
import time

from sqlalchemy import event

import routes.search as search_module
from models import CalendarEvent, Etapa, Project, Task, db
from tests._orgao_helpers import ensure_orgao


class SearchStatementSpy:
    """Coleta os statements SQL do engine — guarda-corpo do custo do typeahead."""

    def __init__(self, engine) -> None:
        self.engine = engine
        self.statements: list[str] = []

    def _on_execute(self, _conn, _cursor, statement, *_rest) -> None:
        self.statements.append(statement)

    def __enter__(self) -> "SearchStatementSpy":
        event.listen(self.engine, "before_cursor_execute", self._on_execute)
        return self

    def __exit__(self, *_exc) -> None:
        event.remove(self.engine, "before_cursor_execute", self._on_execute)

    @property
    def count_statements(self) -> list[str]:
        return [s for s in self.statements if "count(" in s.lower()]


def _seed_matching_projects(app, total: int, prefix: str = "ZetaTeto") -> None:
    with app.app_context():
        orgao_id = ensure_orgao("Auditoria").id
        for index in range(total):
            db.session.add(
                Project(
                    titulo=f"{prefix} Projeto {index}",
                    orgao_id=orgao_id,
                    orgao="Orgao Busca",
                    prioridade="media",
                    status="Vigente",
                    objetivo_id=1,
                    resultado_esperado_id=1,
                )
            )
        db.session.commit()


def _client_for_user(app, user_id):
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["login_at"] = time.time()
    return client


def test_global_search_api_returns_grouped_payload_limits_and_has_more(
    app, client_user, seed_data
):
    with app.app_context():
        for index in range(1, 4):
            project = Project(
                titulo=f"Alvo Projeto {index}",
                orgao_id=ensure_orgao("Auditoria").id,
                orgao="Orgao Busca",
                prioridade="media",
                status="Vigente",
                objetivo_id=1,
                resultado_esperado_id=1,
            )
            db.session.add(project)
            db.session.flush()
            db.session.add(
                Etapa(
                    descricao=f"Alvo Etapa {index}",
                    project_id=project.id,
                    ordem=0,
                )
            )
            db.session.add(
                Task(
                    descricao=f"Alvo Tarefa {index}",
                    status="nao_iniciada",
                    ordem=index,
                    project_id=project.id,
                    created_by_id=seed_data["user_id"],
                )
            )
            db.session.add(
                CalendarEvent(
                    user_id=seed_data["user_id"],
                    title=f"Alvo Evento {index}",
                    description=f"Descricao do evento alvo {index}",
                    location=f"Sala {index}",
                    starts_at=datetime.datetime(2026, 3, 10, 9, 0)
                    + datetime.timedelta(days=index),
                    ends_at=datetime.datetime(2026, 3, 10, 10, 0)
                    + datetime.timedelta(days=index),
                    source="app",
                    sync_status="pending",
                )
            )
        db.session.commit()

    response = client_user.get(
        "/api/busca-global", query_string={"q": "Alvo", "limit": 2}
    )
    assert response.status_code == 200
    payload = response.get_json()

    assert payload["query"] == "Alvo"
    assert payload["meta"]["limit_per_type"] == 2
    assert payload["meta"]["has_more"]["projects"] is True
    assert payload["meta"]["has_more"]["stages"] is True
    assert payload["meta"]["has_more"]["tasks"] is True
    assert payload["meta"]["has_more"]["events"] is True
    assert payload["meta"]["has_more"]["any"] is True

    # `counts` anuncia o TOTAL encontrado (3 por tipo), não a fatia devolvida (2).
    assert payload["counts"] == {
        "projects": 3,
        "stages": 3,
        "tasks": 3,
        "events": 3,
        "total": 12,
    }
    assert all(
        len(payload["results"][key]) == 2
        for key in ("projects", "stages", "tasks", "events")
    )

    assert payload["results"]["projects"][0]["type"] == "project"
    assert (
        payload["results"]["projects"][0]["display_title"]
        == f"{payload['results']['projects'][0]['url'].split('/project/')[1]}-{payload['results']['projects'][0]['title']}"
    )
    assert payload["results"]["stages"][0]["type"] == "stage"
    assert payload["results"]["tasks"][0]["type"] == "task"
    assert payload["results"]["events"][0]["type"] == "event"
    assert payload["results"]["projects"][0]["url"].startswith("/project/")
    assert payload["results"]["tasks"][0]["url"].startswith("/tarefas/")
    assert payload["results"]["events"][0]["url"].startswith("/calendarios")


def test_global_search_api_prefers_prefix_matches_and_respects_area_scope(
    app, seed_data
):
    with app.app_context():
        prefix_project = Project(
            titulo="Busca Especial Prefixo",
            orgao_id=ensure_orgao("Auditoria").id,
            orgao="Orgao Busca",
            prioridade="media",
            status="Vigente",
            objetivo_id=1,
            resultado_esperado_id=1,
        )
        contained_project = Project(
            titulo="Projeto com Busca Especial no meio",
            orgao_id=ensure_orgao("Auditoria").id,
            orgao="Orgao Busca",
            prioridade="media",
            status="Vigente",
            objetivo_id=1,
            resultado_esperado_id=1,
        )
        foreign_project = Project(
            titulo="Busca Especial VPD",
            orgao_id=ensure_orgao("VPD").id,
            orgao="Orgao Busca",
            prioridade="media",
            status="Vigente",
            objetivo_id=1,
            resultado_esperado_id=1,
        )
        db.session.add_all([prefix_project, contained_project, foreign_project])
        db.session.commit()

    user_client = _client_for_user(app, seed_data["user_id"])
    admin_client = _client_for_user(app, seed_data["admin_id"])

    user_response = user_client.get(
        "/api/busca-global", query_string={"q": "Busca Especial"}
    )
    assert user_response.status_code == 200
    user_payload = user_response.get_json()
    user_titles = [item["title"] for item in user_payload["results"]["projects"]]
    assert user_titles[0] == "Busca Especial Prefixo"
    assert "Busca Especial VPD" not in user_titles

    blocked_user_response = user_client.get(
        "/api/busca-global",
        query_string={"q": "Busca Especial", "orgao": seed_data["vpd_orgao_id"]},
    )
    assert blocked_user_response.status_code == 200
    blocked_payload = blocked_user_response.get_json()
    blocked_titles = [item["title"] for item in blocked_payload["results"]["projects"]]
    assert "Busca Especial Prefixo" in blocked_titles
    assert "Busca Especial VPD" not in blocked_titles

    admin_response = admin_client.get(
        "/api/busca-global",
        query_string={"q": "Busca Especial", "orgao": seed_data["vpd_orgao_id"]},
    )
    assert admin_response.status_code == 200
    admin_payload = admin_response.get_json()
    admin_titles = [item["title"] for item in admin_payload["results"]["projects"]]
    assert admin_titles == ["Busca Especial VPD"]


def test_global_search_api_returns_empty_payload_for_short_query(client_user):
    response = client_user.get("/api/busca-global", query_string={"q": "A"})
    assert response.status_code == 200
    payload = response.get_json()

    assert payload == {
        "query": "A",
        "meta": {
            "limit_per_type": None,
            "has_more": {
                "projects": False,
                "stages": False,
                "tasks": False,
                "events": False,
                "any": False,
            },
        },
        "counts": {
            "projects": 0,
            "stages": 0,
            "tasks": 0,
            "events": 0,
            "total": 0,
        },
        "results": {
            "projects": [],
            "stages": [],
            "tasks": [],
            "events": [],
        },
    }


def test_global_search_ignores_out_of_range_numeric_ids(client_user):
    huge_numeric_query = "9999999999999999999"

    api_response = client_user.get(
        "/api/busca-global", query_string={"q": huge_numeric_query}
    )
    assert api_response.status_code == 200
    assert api_response.get_json()["query"] == huge_numeric_query


def test_global_search_api_includes_only_events_of_current_user(app, seed_data):
    with app.app_context():
        db.session.add(
            CalendarEvent(
                user_id=seed_data["user_id"],
                title="Evento Exclusivo Auditoria",
                description="Visivel apenas para o usuario Auditoria",
                location="Sala Auditoria",
                starts_at=datetime.datetime(2026, 4, 10, 9, 0),
                ends_at=datetime.datetime(2026, 4, 10, 10, 0),
                source="app",
                sync_status="pending",
            )
        )
        db.session.add(
            CalendarEvent(
                user_id=seed_data["outsider_id"],
                title="Evento Exclusivo VPD",
                description="Nao deve aparecer para Auditoria",
                location="Sala VPD",
                starts_at=datetime.datetime(2026, 4, 11, 9, 0),
                ends_at=datetime.datetime(2026, 4, 11, 10, 0),
                source="app",
                sync_status="pending",
            )
        )
        db.session.commit()

    user_client = _client_for_user(app, seed_data["user_id"])
    outsider_client = _client_for_user(app, seed_data["outsider_id"])

    user_response = user_client.get(
        "/api/busca-global", query_string={"q": "Evento Exclusivo"}
    )
    assert user_response.status_code == 200
    user_titles = [
        item["title"] for item in user_response.get_json()["results"]["events"]
    ]
    assert "Evento Exclusivo Auditoria" in user_titles
    assert "Evento Exclusivo VPD" not in user_titles

    outsider_response = outsider_client.get(
        "/api/busca-global", query_string={"q": "Evento Exclusivo"}
    )
    assert outsider_response.status_code == 200
    outsider_titles = [
        item["title"] for item in outsider_response.get_json()["results"]["events"]
    ]
    assert "Evento Exclusivo VPD" in outsider_titles
    assert "Evento Exclusivo Auditoria" not in outsider_titles


def test_global_search_api_formats_single_day_all_day_event_without_next_day_suffix(
    app, seed_data
):
    with app.app_context():
        db.session.add(
            CalendarEvent(
                user_id=seed_data["user_id"],
                title="Evento Dia Inteiro Busca",
                description="Evento de um dia inteiro",
                starts_at=datetime.datetime(2026, 3, 11, 3, 0),
                ends_at=datetime.datetime(2026, 3, 12, 2, 59),
                is_all_day=True,
                source="google",
                sync_status="ok",
            )
        )
        db.session.commit()

    response = _client_for_user(app, seed_data["user_id"]).get(
        "/api/busca-global",
        query_string={"q": "Evento Dia Inteiro Busca"},
    )

    assert response.status_code == 200
    event_results = response.get_json()["results"]["events"]
    assert len(event_results) == 1
    assert "Quando: 11/03/2026" in event_results[0]["meta"]
    assert "ate 12/03/2026" not in event_results[0]["meta"]


def test_global_search_api_formats_multi_day_all_day_event_with_inclusive_end_date(
    app, seed_data
):
    with app.app_context():
        db.session.add(
            CalendarEvent(
                user_id=seed_data["user_id"],
                title="Evento Multi Dia Busca",
                description="Evento de varios dias inteiros",
                starts_at=datetime.datetime(2026, 3, 11, 3, 0),
                ends_at=datetime.datetime(2026, 3, 13, 2, 59),
                is_all_day=True,
                source="google",
                sync_status="ok",
            )
        )
        db.session.commit()

    response = _client_for_user(app, seed_data["user_id"]).get(
        "/api/busca-global",
        query_string={"q": "Evento Multi Dia Busca"},
    )

    assert response.status_code == 200
    event_results = response.get_json()["results"]["events"]
    assert len(event_results) == 1
    assert "Quando: 11/03/2026 ate 12/03/2026" in event_results[0]["meta"]


def test_global_search_api_formats_utc_full_day_duration_as_single_local_day(
    app, seed_data
):
    with app.app_context():
        db.session.add(
            CalendarEvent(
                user_id=seed_data["user_id"],
                title="Evento Duracao Dia Local",
                description="Mesmo caso exibido no calendario em um unico dia local",
                starts_at=datetime.datetime(2026, 3, 12, 3, 0),
                ends_at=datetime.datetime(2026, 3, 13, 2, 59),
                is_all_day=False,
                source="google",
                sync_status="ok",
            )
        )
        db.session.commit()

    response = _client_for_user(app, seed_data["user_id"]).get(
        "/api/busca-global",
        query_string={"q": "Evento Duracao Dia Local"},
    )

    assert response.status_code == 200
    event_results = response.get_json()["results"]["events"]
    assert len(event_results) == 1
    assert "Quando: 12/03/2026 00:00 - 23:59" in event_results[0]["meta"]
    assert "13/03/2026" not in event_results[0]["meta"]


# NOTA (corte Grupo B): os testes que renderizavam a pagina Jinja /busca
# (search/results.html) foram removidos — /busca agora serve a SPA via catch-all
# (routes/spa.py). O contrato de dados da busca permanece coberto acima via
# /api/busca-global (mesma fonte build_global_search_results) e em
# tests/routes/test_api_*; o escopo de orgao e o filtro foram preservados ali.


def test_global_search_counts_saturate_at_cap_and_flag_capped(
    app, client_user, seed_data, monkeypatch
):
    """Regressão: o contador do dropdown satura no teto em vez de contar tudo."""
    monkeypatch.setattr(search_module, "GLOBAL_SEARCH_COUNT_CAP", 3)
    _seed_matching_projects(app, total=5)

    response = client_user.get(
        "/api/busca-global", query_string={"q": "ZetaTeto", "limit": 2}
    )
    assert response.status_code == 200
    payload = response.get_json()

    assert payload["meta"]["has_more"]["projects"] is True
    assert payload["counts"]["projects"] == 3
    assert payload["meta"]["counts_capped_at"] == 3
    assert payload["meta"]["counts_capped"]["projects"] is True
    assert payload["meta"]["counts_capped"]["any"] is True
    # Tipos que não estouraram a fatia continuam exatos e sem flag de teto.
    assert payload["counts"]["stages"] == 0
    assert payload["meta"]["counts_capped"]["stages"] is False


def test_global_search_counts_stay_exact_below_cap(
    app, client_user, seed_data, monkeypatch
):
    monkeypatch.setattr(search_module, "GLOBAL_SEARCH_COUNT_CAP", 50)
    _seed_matching_projects(app, total=4)

    payload = client_user.get(
        "/api/busca-global", query_string={"q": "ZetaTeto", "limit": 2}
    ).get_json()

    assert payload["counts"]["projects"] == 4
    assert payload["meta"]["counts_capped_at"] == 50
    assert payload["meta"]["counts_capped"]["projects"] is False
    assert payload["meta"]["counts_capped"]["any"] is False


def test_global_search_count_queries_are_limited_by_cap(app, client_user, seed_data):
    """O COUNT do typeahead roda sobre subquery com LIMIT — nunca varredura cheia."""
    _seed_matching_projects(app, total=8)
    with app.app_context():
        engine = db.engine

    with SearchStatementSpy(engine) as spy:
        payload = client_user.get(
            "/api/busca-global", query_string={"q": "ZetaTeto", "limit": 2}
        ).get_json()

    assert payload["meta"]["has_more"]["projects"] is True
    assert spy.count_statements, "o COUNT deveria rodar quando a fatia estoura"
    assert all("LIMIT" in statement.upper() for statement in spy.count_statements)


def test_paginated_search_keeps_exact_counts_without_cap(app, client_user, seed_data):
    """A tela /busca precisa do total real — paginação não pode ser saturada."""
    _seed_matching_projects(app, total=8)

    payload = client_user.get(
        "/api/busca", query_string={"q": "ZetaTeto", "page": 1, "per_page": 2}
    ).get_json()["data"]

    assert payload["meta"]["type_counts"]["projects"] == 8
    assert payload["meta"]["pagination"]["total"] == 8
    assert payload["meta"]["pagination"]["total_pages"] == 4
    assert payload["meta"].get("counts_capped_at") is None
