from models import Etapa, Project, db

AJAX_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json",
}


def test_add_etapa_inline_ajax_success_returns_json_payload(
    app, client_user, seed_data
):
    response = client_user.post(
        f"/project/{seed_data['project_id']}/etapa/add",
        data={
            "etapa_descricao": "Nova etapa inline",
            "etapa_data_inicio": "2026-03-10",
            "etapa_data_fim": "2026-03-15",
            "etapa_responsavel": "Usuario Auditoria",
            "etapa_iniciada": "on",
        },
        headers=AJAX_HEADERS,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["etapa"]["descricao"] == "Nova etapa inline"
    assert payload["etapa"]["data_inicio"] == "2026-03-10"
    assert payload["etapa"]["data_inicio_display"] == "10/03/2026"
    assert payload["etapa"]["ordem"] == 2

    with app.app_context():
        etapa = db.session.get(Etapa, payload["etapa"]["id"])
        assert etapa is not None
        assert etapa.project_id == seed_data["project_id"]
        assert etapa.descricao == "Nova etapa inline"


def test_add_etapa_inline_ajax_requires_descricao(client_user, seed_data):
    response = client_user.post(
        f"/project/{seed_data['project_id']}/etapa/add",
        data={"etapa_descricao": "   "},
        headers=AJAX_HEADERS,
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert "descrição" in payload["message"].lower()


def test_add_etapa_inline_ajax_forbidden_without_area_access(
    client_outsider, seed_data
):
    response = client_outsider.post(
        f"/project/{seed_data['project_id']}/etapa/add",
        data={"etapa_descricao": "Tentativa sem permissão"},
        headers=AJAX_HEADERS,
    )

    assert response.status_code == 403
    payload = response.get_json()
    assert payload["success"] is False


def test_add_etapa_inline_ajax_normalizes_done_when_not_started(client_user, seed_data):
    response = client_user.post(
        f"/project/{seed_data['project_id']}/etapa/add",
        data={
            "etapa_descricao": "Etapa com done inválido",
            "etapa_done": "on",
        },
        headers=AJAX_HEADERS,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["etapa"]["iniciada"] is False
    assert payload["etapa"]["done"] is False
    assert payload["warning"]


def test_add_etapa_inline_ajax_requires_confirmation_for_finalized_project(
    app, client_user, seed_data
):
    with app.app_context():
        project = db.session.get(Project, seed_data["project_complete_id"])
        project.status = "Finalizado"
        db.session.commit()

    response = client_user.post(
        f"/project/{seed_data['project_complete_id']}/etapa/add",
        data={"etapa_descricao": "Nova etapa sem confirmar"},
        headers=AJAX_HEADERS,
    )

    assert response.status_code == 409
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["confirmation_required"] is True

    with app.app_context():
        project = db.session.get(Project, seed_data["project_complete_id"])
        assert project.status == "Finalizado"
        etapa = Etapa.query.filter_by(
            project_id=seed_data["project_complete_id"],
            descricao="Nova etapa sem confirmar",
        ).first()
        assert etapa is None


def test_add_etapa_inline_ajax_reactivates_project_when_confirmation_is_sent(
    app, client_user, seed_data
):
    with app.app_context():
        project = db.session.get(Project, seed_data["project_complete_id"])
        project.status = "Finalizado"
        db.session.commit()

    response = client_user.post(
        f"/project/{seed_data['project_complete_id']}/etapa/add",
        data={
            "etapa_descricao": "Nova etapa reativada",
            "reactivate_project": "1",
        },
        headers=AJAX_HEADERS,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["project_reactivated"] is True
    assert payload["project_status"] == "Vigente"
    assert payload["reload_page"] is True

    with app.app_context():
        project = db.session.get(Project, seed_data["project_complete_id"])
        assert project.status == "Vigente"
        etapa = Etapa.query.filter_by(
            project_id=seed_data["project_complete_id"],
            descricao="Nova etapa reativada",
        ).first()
        assert etapa is not None
