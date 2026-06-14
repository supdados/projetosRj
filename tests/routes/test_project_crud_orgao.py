from models import OrgaoUnidade, Project, db


def _login(client, user_id):
    with client.session_transaction() as session:
        session["user_id"] = user_id


def test_add_project_rejects_orgao_outside_user_subtree(app, seed_data):
    client = app.test_client()
    _login(client, seed_data["user_id"])

    with app.app_context():
        outside = OrgaoUnidade.query.filter_by(sigla="VPD").first()

    response = client.post(
        "/add_project",
        data={
            "project_titulo": "Projeto Fora Do Escopo",
            "project_orgao_id": str(outside.id),
            "project_orgao": "Livre",
            "project_prioridade": "media",
            "project_objetivo": "1",
            "project_resultado": "1",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        assert Project.query.filter_by(titulo="Projeto Fora Do Escopo").first() is None


def test_add_project_sets_orgao_id_and_mirrors_area(app, seed_data):
    client = app.test_client()
    _login(client, seed_data["user_id"])

    response = client.post(
        "/add_project",
        data={
            "project_titulo": "Projeto No Escopo",
            "project_orgao_id": str(seed_data["auditoria_orgao_id"]),
            "project_orgao": "Livre",
            "project_prioridade": "media",
            "project_objetivo": "1",
            "project_resultado": "1",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        project = Project.query.filter_by(titulo="Projeto No Escopo").first()
        assert project is not None
        assert project.orgao_id == seed_data["auditoria_orgao_id"]
        assert project.orgao_ref.sigla == "Auditoria"


def test_admin_can_create_project_in_any_orgao(app, seed_data):
    client = app.test_client()
    _login(client, seed_data["admin_id"])

    with app.app_context():
        far_away = OrgaoUnidade.query.filter_by(sigla="VPD").first()

    response = client.post(
        "/add_project",
        data={
            "project_titulo": "Projeto Admin Qualquer Orgao",
            "project_orgao_id": str(far_away.id),
            "project_orgao": "Livre",
            "project_prioridade": "alta",
            "project_objetivo": "1",
            "project_resultado": "1",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        project = Project.query.filter_by(titulo="Projeto Admin Qualquer Orgao").first()
        assert project is not None
        assert project.orgao_id == far_away.id
        assert project.orgao_ref.sigla == "VPD"


def test_add_project_rejects_missing_orgao(app, seed_data):
    client = app.test_client()
    _login(client, seed_data["user_id"])

    response = client.post(
        "/add_project",
        data={
            "project_titulo": "Projeto Sem Orgao",
            "project_orgao": "Livre",
            "project_prioridade": "baixa",
            "project_objetivo": "1",
            "project_resultado": "1",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        assert Project.query.filter_by(titulo="Projeto Sem Orgao").first() is None
