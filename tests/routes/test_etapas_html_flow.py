from html import unescape

from models import Etapa, Project, db


def _follow_redirect_and_get_html(client, response):
    location = response.headers["Location"]
    followed = client.get(location)
    assert followed.status_code == 200
    return unescape(followed.get_data(as_text=True))


def test_add_etapa_html_redirects_back_with_success_flash_and_persists_stage(
    app, client_user, seed_data
):
    response = client_user.post(
        f"/project/{seed_data['project_id']}/etapa/add",
        data={
            "etapa_descricao": "Nova etapa HTML",
            "etapa_data_inicio": "2026-03-10",
            "etapa_data_fim": "2026-03-12",
            "etapa_responsavel": "Usuario Auditoria",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/project/{seed_data['project_id']}")

    html = _follow_redirect_and_get_html(client_user, response)
    assert "Etapa adicionada com sucesso!" in html

    with app.app_context():
        etapa = (
            Etapa.query.filter_by(
                project_id=seed_data["project_id"], descricao="Nova etapa HTML"
            )
            .order_by(Etapa.id.desc())
            .first()
        )
        assert etapa is not None
        assert etapa.ordem == 2
        assert etapa.data_inicio.isoformat() == "2026-03-10"
        assert etapa.data_fim.isoformat() == "2026-03-12"


def test_add_etapa_html_requires_confirmation_for_finalized_project(
    app, client_user, seed_data
):
    with app.app_context():
        project = db.session.get(Project, seed_data["project_complete_id"])
        assert project is not None
        project.status = "Finalizado"
        db.session.commit()

    response = client_user.post(
        f"/project/{seed_data['project_complete_id']}/etapa/add",
        data={"etapa_descricao": "Etapa HTML sem confirmar"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        f"/project/{seed_data['project_complete_id']}"
    )

    html = _follow_redirect_and_get_html(client_user, response)
    assert (
        "Ao adicionar uma nova etapa, o projeto voltará para o status Vigente. Deseja continuar?"
        in html
    )

    with app.app_context():
        project = db.session.get(Project, seed_data["project_complete_id"])
        assert project is not None
        assert project.status == "Finalizado"

        etapa = Etapa.query.filter_by(
            project_id=seed_data["project_complete_id"],
            descricao="Etapa HTML sem confirmar",
        ).first()
        assert etapa is None
