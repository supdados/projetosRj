from models import Etapa, ProjectHistory, db


def test_edit_etapa_form_prefills_existing_values(client_user, seed_data):
    response = client_user.get(f"/etapa/{seed_data['etapa_id']}/edit")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert "Editar Etapa" in html
    assert 'Projeto: <a href="/project/1"' in html
    assert "Etapa Planejada" in html
    assert "Sem comentarios" in html
    assert 'value="2026-01-10"' in html
    assert 'value="2026-01-15"' in html
    assert 'value="Usuario Auditoria"' in html
    assert 'id="etapa_iniciada"' in html
    assert 'id="etapa_done"' in html


def test_edit_etapa_form_post_updates_fields_normalizes_done_and_logs_history(
    app, client_user, seed_data
):
    response = client_user.post(
        f"/etapa/{seed_data['etapa_id']}/edit",
        data={
            "etapa_descricao": "Etapa Planejada Ajustada",
            "etapa_responsavel": "Responsavel Ajustado",
            "etapa_comentarios": "Comentario atualizado no form",
            "etapa_data_inicio": "2026-03-05",
            "etapa_data_fim": "2026-03-10",
            "etapa_done": "on",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert f"/project/{seed_data['project_id']}" in response.headers["Location"]

    with app.app_context():
        etapa = db.session.get(Etapa, seed_data["etapa_id"])
        assert etapa is not None
        assert etapa.descricao == "Etapa Planejada Ajustada"
        assert etapa.responsavel == "Responsavel Ajustado"
        assert etapa.comentarios == "Comentario atualizado no form"
        assert etapa.data_inicio.isoformat() == "2026-03-05"
        assert etapa.data_fim.isoformat() == "2026-03-10"
        assert etapa.iniciada is False
        assert etapa.done is False

        history = (
            ProjectHistory.query.filter_by(
                project_id=seed_data["project_id"], action_type="edit_etapa"
            )
            .order_by(ProjectHistory.id.desc())
            .first()
        )
        assert history is not None
        assert 'Editou a etapa "Etapa Planejada"' in history.action_description
