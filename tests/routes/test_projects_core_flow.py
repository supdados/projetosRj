import csv
import datetime
import io

from catalogs.abep import ABEP_INDICADORES_OPTIONS
from models import Etapa, Indicador, IndicadorProjeto, Project, ProjectHistory, User, db
from tests._orgao_helpers import ensure_orgao, link_user_to_orgao


def _valid_indicator_ids():
    indicator_ids = [
        item.id
        for item in Indicador.query.filter_by(resultado_esperado_id=1)
        .order_by(Indicador.id.asc())
        .all()
    ]
    assert indicator_ids
    return indicator_ids


def test_projects_list_defaults_to_vigente_and_current_user_area(app, client_user):
    with app.app_context():
        db.session.add(
            Project(
                titulo="Projeto Auditoria Finalizado",
                orgao_id=ensure_orgao("Auditoria").id,
                orgao="Orgao Finalizado",
                prioridade="media",
                status="Finalizado",
                objetivo_id=1,
                resultado_esperado_id=1,
            )
        )
        db.session.commit()

    response = client_user.get("/projects")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert "Projeto Auditoria" in html
    assert "Projeto VPD" not in html
    assert "Projeto Auditoria Finalizado" not in html


def test_projects_list_fails_closed_for_non_admin_without_orgao_links(
    app, client, seed_data
):
    with app.app_context():
        user = User(
            username="user_sem_orgao",
            name="Usuario Sem Orgao",
            orgao="Auditoria",
            is_admin=False,
        )
        user.set_password("senha123")
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    with client.session_transaction() as session:
        session["user_id"] = user_id

    response = client.get("/projects")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Projeto Auditoria" not in html
    assert "Projeto VPD" not in html


def test_projects_list_shows_orgao_filter_for_non_admin_with_multiple_orgaos(
    app, client, seed_data
):
    with app.app_context():
        user = User(
            username="user_multi_orgao",
            name="Usuario Multi Orgao",
            orgao="Orgao Multi",
            is_admin=False,
        )
        user.set_password("senha123")
        db.session.add(user)
        db.session.flush()
        link_user_to_orgao(user.id, "Auditoria")
        link_user_to_orgao(user.id, "VPD")
        db.session.commit()
        user_id = user.id
        vpd_orgao_id = ensure_orgao("VPD").id

    with client.session_transaction() as session:
        session["user_id"] = user_id

    response = client.get("/projects")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'id="filterOrgao"' in html
    assert "Projeto Auditoria" in html
    assert "Projeto VPD" in html

    response = client.get("/projects", query_string={"orgao": str(vpd_orgao_id)})
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'id="filterOrgao"' in html
    assert "Projeto VPD" in html
    assert "Projeto Auditoria" not in html


def test_projects_list_redirects_when_non_admin_forces_foreign_orgao(app, client_user):
    with app.app_context():
        vpd_orgao_id = ensure_orgao("VPD").id

    response = client_user.get(
        "/projects",
        query_string={"orgao": str(vpd_orgao_id), "status": "Vigente"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/projects?status=Vigente")


def test_projects_list_applies_admin_advanced_filters(app, client_admin):
    abep_value = ABEP_INDICADORES_OPTIONS[0]["value"]

    with app.app_context():
        db.session.add_all(
            [
                Project(
                    titulo="Projeto Painel ABEP",
                    orgao_id=ensure_orgao("VPD").id,
                    orgao="Orgao Filtro",
                    prioridade="alta",
                    status="Vigente",
                    objetivo_id=1,
                    resultado_esperado_id=1,
                    delivery_type="Painel",
                    abep_indicator=abep_value,
                ),
                Project(
                    titulo="Projeto Norma ABEP",
                    orgao_id=ensure_orgao("VPD").id,
                    orgao="Orgao Filtro",
                    prioridade="alta",
                    status="Vigente",
                    objetivo_id=1,
                    resultado_esperado_id=1,
                    delivery_type="Norma",
                    abep_indicator=abep_value,
                ),
            ]
        )
        db.session.commit()

    with app.app_context():
        vpd_orgao_id = ensure_orgao("VPD").id

    response = client_admin.get(
        "/projects",
        query_string={
            "orgao": str(vpd_orgao_id),
            "status": "Vigente",
            "delivery_type": "Painel",
            "abep_indicator": abep_value,
            "objetivo": "1",
            "search": "Painel",
        },
    )
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert "Projeto Painel ABEP" in html
    assert "Projeto Norma ABEP" not in html
    assert "Projeto Auditoria" not in html


def test_projects_list_ignores_out_of_range_numeric_search_id(client_user):
    response = client_user.get(
        "/projects", query_string={"search": "9999999999999999999"}
    )

    assert response.status_code == 200
    assert "Projetos" in response.get_data(as_text=True)


def test_projects_csv_export_neutralizes_formula_text_cells(app, client_admin):
    with app.app_context():
        project = Project(
            titulo='=HYPERLINK("https://attacker.example","click")',
            short_description=' +SUM(1,2)',
            sei_process='@cmd',
            orgao="-Orgao Legado",
            prioridade="alta",
            status="Vigente",
            objetivo_id=1,
            resultado_esperado_id=1,
        )
        db.session.add(project)
        db.session.commit()
        project_id = project.id

    response = client_admin.get("/projects/download")

    assert response.status_code == 200
    rows = list(csv.reader(io.StringIO(response.get_data(as_text=True)), delimiter=";"))
    header = rows[0]
    row = next(row for row in rows[1:] if row[0] == str(project_id))

    assert row[header.index("Nome")].startswith("'=")
    assert row[header.index("Descrição")].startswith("' +")
    assert row[header.index("Processo SEI-RJ")].startswith("'@")
    assert row[header.index("Órgão Responsável")].startswith("'-")


def test_add_project_creates_stages_indicators_and_history(app, client_user, seed_data):
    abep_value = ABEP_INDICADORES_OPTIONS[0]["value"]

    response = client_user.post(
        "/add_project",
        data={
            "project_titulo": "Projeto Criado Completo",
            "project_orgao_id": str(seed_data["auditoria_orgao_id"]),
            "project_orgao": "Orgao Novo",
            "project_prioridade": "media",
            "project_objetivo": "1",
            "project_resultado": "1",
            "project_indicadores": ["1"],
            "project_observacao": "Observacao detalhada",
            "project_special_project": "ABEP",
            "project_sei_process": "SEI-123456/654321/2026",
            "project_short_description": "Descricao curta",
            "project_delivery_type": "Sistema",
            "project_abep_indicator": abep_value,
            "project_github_link": "https://github.com/exemplo/projeto",
            "project_documentation_link": "https://docs.example.com/projeto",
            "project_product_link": "https://produto.example.com/projeto",
            "etapa_descricao": ["Etapa 1", "Etapa 2"],
            "etapa_duration": ["2", "3"],
            "project_start_date": "2026-03-10",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302

    with app.app_context():
        project = Project.query.filter_by(titulo="Projeto Criado Completo").first()
        assert project is not None
        assert project.orgao_ref.sigla == "Auditoria"
        assert project.delivery_type == "Sistema"
        assert project.abep_indicator == abep_value
        assert project.special_project == "ABEP"
        assert project.product_link == "https://produto.example.com/projeto"

        etapas = (
            Etapa.query.filter_by(project_id=project.id)
            .order_by(Etapa.ordem.asc())
            .all()
        )
        assert [etapa.descricao for etapa in etapas] == ["Etapa 1", "Etapa 2"]
        assert etapas[0].data_inicio == datetime.date(2026, 3, 10)
        assert etapas[0].data_fim == datetime.date(2026, 3, 11)
        assert etapas[1].data_inicio == datetime.date(2026, 3, 12)
        assert etapas[1].data_fim == datetime.date(2026, 3, 14)

        assert IndicadorProjeto.query.filter_by(project_id=project.id).count() == 1
        history = (
            ProjectHistory.query.filter_by(project_id=project.id, action_type="create")
            .order_by(ProjectHistory.id.desc())
            .first()
        )
        assert history is not None
        assert 'Criou o projeto "Projeto Criado Completo"' in history.action_description


def test_edit_project_updates_fields_and_history(app, client_user, seed_data):
    with app.app_context():
        indicator_ids = _valid_indicator_ids()
        selected_indicator = str(indicator_ids[-1])

    response = client_user.post(
        f"/project/{seed_data['project_id']}/edit",
        data={
            "project_titulo": "Projeto Auditoria Editado",
            "project_orgao": "Orgao Editado",
            "project_orgao_id": str(seed_data["auditoria_orgao_id"]),
            "project_prioridade": "urgente",
            "project_status": "Suspenso",
            "project_special_project": "TCE",
            "project_sei_process": "SEI-123456/654321/2026",
            "project_short_description": "Resumo novo",
            "project_delivery_type": "Painel",
            "project_abep_indicator": ABEP_INDICADORES_OPTIONS[1]["value"],
            "project_github_link": "https://github.com/exemplo/editado",
            "project_documentation_link": "https://docs.example.com/editado",
            "project_product_link": "https://produto.example.com/editado",
            "project_objetivo": "1",
            "project_resultado": "1",
            "project_indicadores": [selected_indicator],
            "project_observacao": "Observacao atualizada",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302

    with app.app_context():
        project = db.session.get(Project, seed_data["project_id"])
        assert project is not None
        assert project.titulo == "Projeto Auditoria Editado"
        assert project.orgao == "Orgao Editado"
        assert project.prioridade == "urgente"
        assert project.status == "Suspenso"
        assert project.special_project == "TCE"
        assert project.delivery_type == "Painel"
        assert project.abep_indicator == ABEP_INDICADORES_OPTIONS[1]["value"]
        assert project.product_link == "https://produto.example.com/editado"

        indicator_ids = [
            row.indicador_id
            for row in IndicadorProjeto.query.filter_by(project_id=project.id)
            .order_by(IndicadorProjeto.id.asc())
            .all()
        ]
        assert indicator_ids == [int(selected_indicator)]

        history = (
            ProjectHistory.query.filter_by(project_id=project.id, action_type="edit")
            .order_by(ProjectHistory.id.desc())
            .first()
        )
        assert history is not None
        assert "Projeto Auditoria Editado" in history.action_description


def test_project_edit_data_returns_goal_payload(client_user, seed_data):
    response = client_user.get(f"/project/{seed_data['project_id']}/edit_data")

    assert response.status_code == 200
    payload = response.get_json()

    assert payload["success"] is True
    assert payload["is_admin"] is False
    assert payload["indicadores_do_projeto"] == [1]
    assert any(item["id"] == 1 for item in payload["objetivos"])


def test_update_project_inline_updates_abep_goal_and_history(
    app, client_user, seed_data
):
    with app.app_context():
        indicator_ids = _valid_indicator_ids()
        selected_indicator = indicator_ids[-1]

    response = client_user.post(
        f"/project/{seed_data['project_id']}/update_inline",
        json={
            "titulo": "Projeto Inline Atualizado",
            "orgao": "Orgao Inline",
            "prioridade": "baixa",
            "abep_indicator": ABEP_INDICADORES_OPTIONS[2]["value"],
            "objetivo_id": 1,
            "resultado_esperado_id": 1,
            "indicadores_ids": [selected_indicator],
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True

    with app.app_context():
        project = db.session.get(Project, seed_data["project_id"])
        assert project is not None
        assert project.titulo == "Projeto Inline Atualizado"
        assert project.orgao == "Orgao Inline"
        assert project.prioridade == "baixa"
        assert project.abep_indicator == ABEP_INDICADORES_OPTIONS[2]["value"]

        indicator_ids = [
            row.indicador_id
            for row in IndicadorProjeto.query.filter_by(project_id=project.id)
            .order_by(IndicadorProjeto.id.asc())
            .all()
        ]
        assert indicator_ids == [selected_indicator]

        history = (
            ProjectHistory.query.filter_by(project_id=project.id, action_type="edit")
            .order_by(ProjectHistory.id.desc())
            .first()
        )
        assert history is not None
        assert "Editou o projeto (inline)" in history.action_description


def test_concluir_project_json_requires_all_stages_completed(client_user, seed_data):
    response = client_user.post(
        f"/project/{seed_data['project_id']}/concluir",
        headers={"Accept": "application/json"},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert "Todas as etapas devem estar iniciadas e concluídas" in payload["message"]


def test_concluir_project_json_finalizes_project_and_logs_history(
    app, client_user, seed_data
):
    response = client_user.post(
        f"/project/{seed_data['project_complete_id']}/concluir",
        headers={"Accept": "application/json"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True

    with app.app_context():
        project = db.session.get(Project, seed_data["project_complete_id"])
        assert project is not None
        assert project.status == "Finalizado"

        history = (
            ProjectHistory.query.filter_by(
                project_id=project.id, action_type="finalize"
            )
            .order_by(ProjectHistory.id.desc())
            .first()
        )
        assert history is not None
        assert "Concluiu o projeto" in history.action_description


def test_concluir_project_json_hides_raw_exception_details(
    client_user, seed_data, monkeypatch
):
    sensitive_error = (
        "(sqlite3.IntegrityError) UNIQUE constraint failed: "
        "project_history.project_id; DB path /srv/projetosRj/instance/projetosrj.db"
    )

    def fail_commit():
        raise RuntimeError(sensitive_error)

    monkeypatch.setattr(db.session, "commit", fail_commit)

    response = client_user.post(
        f"/project/{seed_data['project_complete_id']}/concluir",
        headers={"Accept": "application/json"},
    )

    assert response.status_code == 500
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["message"] == "Erro ao concluir projeto. Tente novamente em instantes."
    assert "sqlite3" not in payload["message"]
    assert "project_history" not in payload["message"]
    assert "/srv/projetosRj" not in payload["message"]


def test_delete_project_ajax_removes_project_from_database(app, client_user):
    with app.app_context():
        project = Project(
            titulo="Projeto Para Excluir",
            orgao_id=ensure_orgao("Auditoria").id,
            orgao="Orgao Delete",
            prioridade="baixa",
            status="Vigente",
            objetivo_id=1,
            resultado_esperado_id=1,
        )
        db.session.add(project)
        db.session.commit()
        project_id = project.id

    response = client_user.post(
        f"/project/{project_id}/delete",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True

    with app.app_context():
        assert db.session.get(Project, project_id) is None
