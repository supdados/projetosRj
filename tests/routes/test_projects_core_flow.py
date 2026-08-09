"""Fluxos remanescentes de /projects após a migração SPA.

A LISTA Jinja /projects virou redirect 302 -> /projetos e o CRUD migrou para
/api/projetos* (criação/edição inline/conclusão/exclusão), coberto em
tests/routes/test_api_*_contract.py. Sobram aqui: o export CSV (/projects/download,
vivo) e o fail-closed por órgão nas telas de leitura (dashboard SPA + busca).
"""

import csv
import io
import time

from models import Project, ProjectSeiProcess, User, db


def _create_no_orgao_user(app, username="user_sem_orgao"):
    with app.app_context():
        user = User(
            username=username,
            name="Usuario Sem Orgao",
            orgao="Auditoria",
            is_admin=False,
        )
        user.set_password("senha123")
        db.session.add(user)
        db.session.commit()
        return user.id


def _login_user(client, user_id):
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["login_at"] = time.time()


def test_no_orgao_user_metadata_routes_fail_closed(app, client, seed_data):
    user_id = _create_no_orgao_user(app, username="user_sem_orgao_metadata")
    _login_user(client, user_id)

    dashboard_response = client.get("/dashboard")
    assert dashboard_response.status_code == 200
    dashboard_html = dashboard_response.get_data(as_text=True)
    assert "Projeto Auditoria" not in dashboard_html
    assert "Projeto VPD" not in dashboard_html

    search_response = client.get("/api/busca-global", query_string={"q": "Projeto"})
    assert search_response.status_code == 200
    search_payload = search_response.get_json()
    assert search_payload["results"]["projects"] == []
    assert "Projeto Auditoria" not in search_response.get_data(as_text=True)
    assert "Projeto VPD" not in search_response.get_data(as_text=True)


def test_project_detail_redirect_preserves_focus_etapa_query(client_user, seed_data):
    """KEEP-ENDPOINT /project/<id> deve carregar o query string ao redirecionar.

    Regressão do bug 2.15: o deep-link ?focus_etapa=<id> vindo da busca global era
    descartado, então a SPA nunca recebia a etapa-alvo.
    """
    project_id = seed_data["project_id"]

    response = client_user.get(
        f"/project/{project_id}?focus_etapa=12", follow_redirects=False
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        f"/projetos/{project_id}?focus_etapa=12"
    )


def test_project_detail_redirect_without_query_has_no_dangling_question_mark(
    client_user, seed_data
):
    project_id = seed_data["project_id"]

    response = client_user.get(f"/project/{project_id}", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/projetos/{project_id}")
    assert "?" not in response.headers["Location"]


def test_projects_csv_export_neutralizes_formula_text_cells(app, client_admin):
    with app.app_context():
        project = Project(
            titulo='=HYPERLINK("https://attacker.example","click")',
            short_description=" +SUM(1,2)",
            orgao="-Orgao Legado",
            prioridade="alta",
            status="Vigente",
            objetivo_id=1,
            resultado_esperado_id=1,
        )
        project.sei_processes = [
            ProjectSeiProcess(numero="@cmd", ordem=0),
            ProjectSeiProcess(numero="SEI-380001/000664/2026", ordem=1),
        ]
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
    assert "SEI-380001/000664/2026" in row[header.index("Processo SEI-RJ")]
    assert row[header.index("Órgão Responsável")].startswith("'-")
