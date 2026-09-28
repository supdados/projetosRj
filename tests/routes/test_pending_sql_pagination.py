"""P2-18: preservar buckets/ordem/escopo sem carregar a carteira inteira."""

from datetime import date, timedelta

import pytest

from models import Etapa, EtapaResponsavel, Project, ProjectMember, Task, db
from tests.model_load_counter import ModelLoadCounter

TODAY = date(2026, 9, 28)


class PendingClock:
    def __call__(self) -> date:
        return TODAY


@pytest.fixture(autouse=True)
def fixed_pending_clock(monkeypatch) -> None:
    monkeypatch.setattr("routes.projects.views.hoje_utc", PendingClock())


def add_pending_project(
    orgao_id: int, title: str, ends: list[int | None], responsible: str = "PERF"
) -> Project:
    project = Project(titulo=title, orgao_id=orgao_id, prioridade="alta")
    db.session.add(project)
    db.session.flush()
    for order, days in enumerate(ends):
        stage = Etapa(
            descricao=f"Etapa {order}",
            project_id=project.id,
            ordem=order,
            data_inicio=TODAY - timedelta(days=30),
            data_fim=TODAY + timedelta(days=days) if days is not None else None,
        )
        stage.responsaveis = [
            EtapaResponsavel(area_id=None, label=responsible, ordem=0)
        ]
        db.session.add(stage)
    db.session.flush()
    return project


@pytest.fixture
def pending_windows(app, seed_data) -> dict[str, int]:
    with app.app_context():
        alpha = add_pending_project(
            seed_data["auditoria_orgao_id"],
            "P2 Janela Alfa",
            [-2, 0, 7, 14, 21, 22, None],
        )
        beta = add_pending_project(
            seed_data["auditoria_orgao_id"], "P2 Janela Beta", [14], "OUTRO"
        )
        add_pending_project(seed_data["auditoria_orgao_id"], "P2 Janela Futuro", [22])
        stage = Etapa.query.filter_by(project_id=alpha.id, ordem=0).one()
        stage.responsaveis.append(
            EtapaResponsavel(
                area_id=seed_data["auditoria_orgao_id"], label="DUAL", ordem=1
            )
        )
        db.session.add_all(
            [
                Task(
                    descricao="aberta",
                    project_id=alpha.id,
                    etapa_id=stage.id,
                    created_by_id=seed_data["user_id"],
                ),
                Task(
                    descricao="concluída",
                    project_id=alpha.id,
                    etapa_id=stage.id,
                    created_by_id=seed_data["user_id"],
                    status="finalizada",
                ),
                Task(
                    descricao="arquivada",
                    project_id=alpha.id,
                    etapa_id=stage.id,
                    created_by_id=seed_data["user_id"],
                    status="finalizada",
                    is_archived=True,
                ),
                Etapa(
                    descricao="Concluída",
                    project_id=alpha.id,
                    ordem=8,
                    done=True,
                    iniciada=True,
                    data_fim=TODAY - timedelta(days=99),
                ),
                Etapa(
                    descricao="Reunião",
                    project_id=alpha.id,
                    ordem=9,
                    entry_type="google_meeting",
                    data_fim=TODAY - timedelta(days=200),
                ),
            ]
        )
        db.session.commit()
        return {"alpha": alpha.id, "beta": beta.id, "stage": stage.id}


@pytest.mark.parametrize(
    "period,visible,total",
    [("atrasados", 1, 1), ("7dias", 3, 1), ("14dias", 4, 2), ("21dias", 5, 2)],
)
def test_windows_boundaries_global_counts_and_progress(
    client_user, pending_windows, period, visible, total
) -> None:
    response = client_user.get(
        "/api/projetos-pendentes",
        query_string={"search": "P2 Janela", "periodo": period},
    )
    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["summary_counts"] == {
        "total_projects": total,
        "atrasada": 1,
        "7dias": 2,
        "14dias": 2,
        "21dias": 1,
        "sem_data": 1,
    }
    alpha = payload["projetos"][0]
    assert alpha["project"]["id"] == pending_windows["alpha"]
    assert alpha["qtd_visiveis"] == visible
    assert alpha["qtd_outras"] == 7 - visible
    assert [alpha["qtd_7dias"], alpha["qtd_14dias"], alpha["qtd_21dias"]] == [2, 3, 4]
    assert payload["etapa_task_progress"][str(pending_windows["stage"])] == {
        "total": 2,
        "done": 1,
    }
    assert (
        len(payload["etapa_bucket_map"]) == 9
    )  # Inclui também as etapas fora do período.


def test_responsavel_matches_nn_exactly_without_narrowing_options(
    client_user, pending_windows
) -> None:
    response = client_user.get(
        "/api/projetos-pendentes",
        query_string={
            "search": "P2 Janela",
            "periodo": "21dias",
            "responsavel": "dual",
        },
    )
    payload = response.get_json()["data"]
    assert payload["responsaveis_options"] == ["DUAL", "OUTRO", "PERF"]
    assert payload["summary_counts"]["atrasada"] == 1
    assert payload["summary_counts"]["7dias"] == 0
    assert payload["projetos"][0]["qtd_visiveis"] == 1
    empty = client_user.get("/api/projetos-pendentes?search=P2+Janela&responsavel=DU")
    assert empty.get_json()["data"]["pagination"] == {
        "page": 1,
        "per_page": 15,
        "total_pages": 0,
        "total": 0,
    }


def test_sql_page_keeps_unicode_ties_and_materializes_only_its_models(
    app, client_user, seed_data
) -> None:
    with app.app_context():
        heavy = [
            add_pending_project(
                seed_data["auditoria_orgao_id"], f"P2 Página pesada {i:02}", [-5, -5]
            ).id
            for i in range(16)
        ]
        titles = ["Água", "água", "Straße", "STRASSE", "Zeta", "Alfa"]
        light = [
            (
                title,
                add_pending_project(
                    seed_data["auditoria_orgao_id"], f"P2 Página {title}", [-5]
                ).id,
            )
            for title in titles
            for _ in range(3)
        ]
        db.session.commit()
    # Casefold é o contrato existente; empate final mantém a ordem por ID.
    expected = heavy + [
        project_id
        for _, project_id in sorted(
            light, key=lambda item: (item[0].casefold(), item[1])
        )
    ]
    with ModelLoadCounter() as loaded:
        response = client_user.get("/api/projetos-pendentes?search=P2+Página&page=2")
    payload = response.get_json()["data"]
    assert [row["project"]["id"] for row in payload["projetos"]] == expected[15:30]
    assert payload["pagination"]["total"] == 34
    assert loaded.counts["Project"] == 15
    assert loaded.counts["Etapa"] == 16
    assert len(payload["etapa_bucket_map"]) == 50  # Contrato global preservado.
    last = client_user.get(
        "/api/projetos-pendentes?search=P2+Página&page=999"
    ).get_json()["data"]
    assert last["pagination"]["page"] == 3
    assert [row["project"]["id"] for row in last["projetos"]] == expected[30:]


def test_pending_scope_includes_invitation_but_not_unshared_project(
    app, client_user, seed_data
) -> None:
    with app.app_context():
        invited = add_pending_project(
            seed_data["vpd_orgao_id"], "P2 Escopo convidado", [-3]
        )
        hidden = add_pending_project(
            seed_data["vpd_orgao_id"], "P2 Escopo oculto", [-4]
        )
        db.session.add(
            ProjectMember(
                project_id=invited.id,
                user_id=seed_data["user_id"],
                papel="leitor",
                granted_by_id=seed_data["admin_id"],
            )
        )
        db.session.commit()
        invited_id, hidden_id = invited.id, hidden.id
    payload = client_user.get("/api/projetos-pendentes?search=P2+Escopo").get_json()[
        "data"
    ]
    assert [row["project"]["id"] for row in payload["projetos"]] == [invited_id]
    assert payload["summary_counts"]["total_projects"] == 1
    assert hidden_id != invited_id
