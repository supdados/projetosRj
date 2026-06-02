"""Garante a sub-hierarquia Projeto > Etapa > Tarefa exposta pela API do hub.

Apos o cut-over KEEP-ENDPOINT, ``/tarefas`` serve a shell da SPA; a renderizacao
dos sub-cabecalhos/DnD vive nos componentes Svelte. O contrato de DADOS da
sub-hierarquia (etapa por tarefa + ordem dentro do projeto) e validado aqui via
``GET /api/tarefas`` (mesma fonte ``build_task_hub_context``). A logica pura de
agrupamento por etapa continua coberta por ``tests/test_task_hub_grouping_unit``.
"""

from pathlib import Path

from models import Task, db


def test_api_hub_exposes_stage_metadata_per_task(app, client_user, seed_data):
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

    payload = client_user.get("/api/tarefas").get_json()
    assert payload["ok"] is True

    group = next(
        g for g in payload["data"]["groups"] if g["project_id"] == project_id
    )
    cards_by_id = {card["id"]: card for card in group["tasks"]}

    assert legacy_id in cards_by_id
    assert in_stage_id in cards_by_id
    # A tarefa em etapa expoe o titulo da etapa; a legada cai no bucket
    # "Sem etapa" (subgrupo das tarefas sem etapa).
    assert cards_by_id[in_stage_id]["etapa_titulo"] not in (None, "", "Sem etapa")
    assert cards_by_id[legacy_id]["etapa_titulo"] == "Sem etapa"
    # ``is_first_of_stage`` marca a abertura de cada subgrupo de etapa.
    assert any(card["is_first_of_stage"] for card in group["tasks"])


def test_tasks_hub_stage_and_add_styles_are_cleaner():
    css_path = Path(__file__).resolve().parents[2] / "static" / "css" / "tasks" / "hub.css"
    css = css_path.read_text(encoding="utf-8")

    assert ".task-hub-page .task-hub-entity-id" in css
    assert ".task-hub-page .task-hub-project-id" in css
    assert "text-transform: none;" in css
    assert "font-weight: var(--ds-font-weight-regular);" in css
    assert ".task-hub-page .task-hub-add-row {\n    border-top: 0;" in css
    assert "border-top: 1px dashed #d6e4f2;" not in css
