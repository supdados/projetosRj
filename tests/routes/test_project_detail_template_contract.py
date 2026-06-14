from pathlib import Path

from models import Task, TaskItemComment, db


def test_project_detail_stage_task_quick_add_defaults_closed_and_keeps_add_row_visible_on_growth():
    root = Path(__file__).resolve().parents[2]
    quick_add_js = (
        root
        / "static"
        / "js"
        / "pages"
        / "projects"
        / "detail"
        / "11-stage-task-quick-add.js"
    ).read_text(encoding="utf-8")
    row_factory_js = (
        root
        / "static"
        / "js"
        / "pages"
        / "projects"
        / "detail"
        / "11-stage-task-quick-add-row-factory.js"
    ).read_text(encoding="utf-8")

    assert "loadPanel({ focusAdd: false, resetScroll: true });" in quick_add_js
    assert "function ensureFormVisible(contentHost)" in row_factory_js
    assert "scrollIntoView({ block: 'end', inline: 'nearest' });" in row_factory_js


def test_project_stage_tasks_panel_renders_hub_markup_csrf_and_legacy_bucket(
    app, client_user, seed_data
):
    with app.app_context():
        task = Task(
            descricao="Tarefa renderizada na etapa",
            status="nao_iniciada",
            responsavel="Usuario Auditoria",
            ordem=2,
            project_id=seed_data["project_id"],
            etapa_id=seed_data["etapa_started_id"],
            created_by_id=seed_data["user_id"],
        )
        db.session.add(task)
        db.session.flush()
        db.session.add(
            TaskItemComment(
                content="Comentario renderizado",
                user_id=seed_data["user_id"],
                task_id=task.id,
            )
        )
        db.session.commit()
        task_id = task.id

    response = client_user.get(
        f"/project/{seed_data['project_id']}/etapa/{seed_data['etapa_started_id']}/tasks"
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    html = payload["html"]

    required_hooks = [
        "task-detail-v2-items task-hub-items",
        "task-items-list task-hub-items-list",
        "task-hub-group stage-task-quick-add__stage-panel",
        "task-item-header-row task-hub-group-columns",
        "Tarefa renderizada na etapa",
        "Comentario renderizado",
        f'id="deleteItemModal-{task_id}"',
        f'action="/tarefas/{task_id}/delete"',
        f'action="/tarefas/{task_id}/comentarios/add"',
        'name="csrf_token"',
        "task-item-add-row task-hub-add-row stage-task-quick-add__row",
        'data-role="submit-add"',
    ]

    for hook in required_hooks:
        assert hook in html

    # Tarefas legadas (etapa_id NULL) NÃO devem aparecer no modal de uma etapa
    # específica — vivem em endpoint próprio para evitar duplicação.
    assert "Item Auditoria" not in html
    assert "Sem etapa" not in html


def test_project_legacy_tasks_panel_lists_orphan_tasks(client_user, seed_data):
    response = client_user.get(f"/project/{seed_data['project_id']}/tarefas-sem-etapa")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    html = payload["html"]
    assert "Item Auditoria" in html
    assert "data-legacy-task-list" in html


def test_project_stage_tasks_panel_limits_results_and_links_full_task_list(
    app, client_user, seed_data
):
    with app.app_context():
        db.session.add_all(
            [
                Task(
                    descricao="Tarefa paginada A",
                    status="nao_iniciada",
                    ordem=10,
                    project_id=seed_data["project_id"],
                    etapa_id=seed_data["etapa_started_id"],
                    created_by_id=seed_data["user_id"],
                ),
                Task(
                    descricao="Tarefa paginada B",
                    status="nao_iniciada",
                    ordem=11,
                    project_id=seed_data["project_id"],
                    etapa_id=seed_data["etapa_started_id"],
                    created_by_id=seed_data["user_id"],
                ),
            ]
        )
        db.session.commit()

    response = client_user.get(
        f"/project/{seed_data['project_id']}/etapa/{seed_data['etapa_started_id']}/tasks",
        query_string={"limit": 1},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["stage_has_more"] is True
    assert "Ver mais na lista completa" in payload["html"]
    assert f'/projeto/{seed_data["project_id"]}/tarefas' in payload["html"]
