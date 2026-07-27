"""Fluxo HTML (form, não-AJAX) de ``POST /project/<id>/etapa/add``.

O destino do 302 (``/project/<id>``) virou redirect legado para a SPA, que não
renderiza mais flashes do Jinja — o feedback é lido direto da sessão, que é o
que a rota efetivamente produz.
"""

from models import Etapa, Project, db


def _flashed_messages(client):
    with client.session_transaction() as session:
        return [message for _category, message in session.get("_flashes", [])]


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
    assert "Etapa adicionada com sucesso!" in _flashed_messages(client_user)

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
    assert (
        "Ao adicionar uma nova etapa, o projeto voltará para o status Vigente. Deseja continuar?"
        in _flashed_messages(client_user)
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
