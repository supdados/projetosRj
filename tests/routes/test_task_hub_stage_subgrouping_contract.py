"""Garante que o hub renderiza a sub-hierarquia Projeto > Etapa > Tarefa.

O DnD do front depende de atributos ``data-stage-*`` nas rows e dos sub-cabeçalhos
``[data-stage-drop-zone]``.
"""

from models import Task, db


def test_tasks_hub_renders_stage_sub_headers_and_row_metadata(
    app, client_user, seed_data
):
    project_id = seed_data["project_id"]
    etapa_id = seed_data["etapa_id"]
    user_id = seed_data["user_id"]

    with app.app_context():
        # Tarefa legada (sem etapa) + tarefa com etapa no mesmo projeto.
        legacy = Task(
            descricao="Legado sem etapa",
            project_id=project_id,
            etapa_id=None,
            created_by_id=user_id,
            ordem=10,
        )
        in_stage = Task(
            descricao="Nova com etapa",
            project_id=project_id,
            etapa_id=etapa_id,
            created_by_id=user_id,
            ordem=11,
        )
        db.session.add_all([legacy, in_stage])
        db.session.commit()
        legacy_id = legacy.id
        in_stage_id = in_stage.id

    response = client_user.get("/tarefas")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    # Sub-cabeçalhos por etapa devem aparecer.
    assert 'data-stage-drop-zone' in html
    assert 'data-stage-value="sem_etapa"' in html
    assert f'data-stage-value="{etapa_id}"' in html
    assert ">Sem etapa<" in html
    assert "is-legacy" in html

    # As rows precisam carregar data-stage-* e data-project-id para o DnD.
    assert f'data-item-id="{legacy_id}"' in html
    assert f'data-item-id="{in_stage_id}"' in html
    assert f'data-project-id="{project_id}"' in html


def test_tasks_hub_exposes_move_etapa_url_template(client_user):
    response = client_user.get("/tarefas")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "moveTaskEtapaUrlTemplate" in html
    assert "/mover-etapa" in html
