"""Garante que o hub renderiza a sub-hierarquia Projeto > Etapa > Tarefa.

O DnD do front depende de atributos ``data-stage-*`` nas rows e dos sub-cabeçalhos
``[data-stage-drop-zone]``.
"""

import re
from pathlib import Path

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
    assert f'<span class="task-hub-entity-id task-hub-project-id">{project_id}</span>' in html
    assert '<span class="task-hub-title-separator" aria-hidden="true">-</span>' in html
    assert f'<span class="task-hub-entity-id task-hub-stage-id">{project_id}.1</span>' in html
    assert f'<span class="task-hub-entity-id task-hub-stage-id">{etapa_id}</span>' not in html
    assert f'<span class="task-hub-entity-id task-hub-stage-id">#{etapa_id}</span>' not in html
    assert 'data-role="stage-progress-count"' in html
    assert ">Sem etapa<" in html
    assert "is-legacy" in html
    assert re.search(
        rf'data-stage-value="{etapa_id}"[\s\S]*?</header>[\s\S]*?'
        rf'class="task-item-header-row task-hub-group-columns"[\s\S]*?'
        rf'data-item-id="{in_stage_id}"',
        html,
    )

    # As rows precisam carregar data-stage-* e data-project-id para o DnD.
    assert f'data-item-id="{legacy_id}"' in html
    assert f'data-item-id="{in_stage_id}"' in html
    assert f'data-project-id="{project_id}"' in html

    # O botão de adicionar fica dentro da etapa e carrega a etapa de destino.
    assert re.search(
        rf'class="task-item-add-row task-hub-add-row"[^>]*'
        rf'data-project-value="{project_id}"[^>]*'
        rf'data-stage-value="{etapa_id}"[^>]*'
        rf'data-stage-id="{etapa_id}"',
        html,
        re.S,
    )

    # A contagem da direita no projeto e o progresso da etapa saíram.
    assert "task-hub-group-count" not in html
    assert "task-hub-stage-stats" not in html
    assert "task-hub-stage-progress" not in html


def test_tasks_hub_exposes_move_etapa_url_template(client_user):
    response = client_user.get("/tarefas")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "moveTaskEtapaUrlTemplate" in html
    assert "/mover-etapa" in html


def test_tasks_hub_inline_stage_add_posts_stage_and_inserts_inside_stage():
    modules_root = Path(__file__).resolve().parents[2] / "static" / "js" / "modules"
    inline_js = (
        modules_root / "add-item-inline" / "inline-form-controller.js"
    ).read_text(encoding="utf-8")
    group_js = (modules_root / "add-item-inline" / "group-manager.js").read_text(
        encoding="utf-8"
    )
    helper_js = (modules_root / "task-item-helpers.js").read_text(encoding="utf-8")
    operations_js = (modules_root / "task-item-operations.js").read_text(
        encoding="utf-8"
    )
    dnd_js = (
        Path(__file__).resolve().parents[2] / "static" / "js" / "pages" / "tasks" / "hub-task-dnd.js"
    ).read_text(encoding="utf-8")

    assert "function getEtapaValue()" in inline_js
    assert "data-stage-id" in inline_js
    assert "etapa: getEtapaValue()" in inline_js
    assert "function resolveTargetAddRow" in group_js
    assert "data-stage-value" in group_js
    assert "function updateTaskHubStageAndProjectProgress(root)" in helper_js
    assert "stage-progress-count" in helper_js
    assert "task-hub-progress-bar > i" in helper_js
    assert "window.updateTaskHubStageAndProjectProgress()" in group_js
    assert "updateTaskHubStageAndProjectProgress();" in operations_js
    assert "window.updateTaskHubStageAndProjectProgress();" in dnd_js


def test_tasks_hub_stage_and_add_styles_are_cleaner():
    css_path = Path(__file__).resolve().parents[2] / "static" / "css" / "tasks" / "hub.css"
    css = css_path.read_text(encoding="utf-8")

    assert ".task-hub-page .task-hub-entity-id" in css
    assert ".task-hub-page .task-hub-project-id" in css
    assert "text-transform: none;" in css
    assert "font-weight: var(--ds-font-weight-regular);" in css
    assert ".task-hub-page .task-hub-add-row {\n    border-top: 0;" in css
    assert "border-top: 1px dashed #d6e4f2;" not in css


def test_tasks_hub_collapse_removes_closed_sections_from_layout():
    root = Path(__file__).resolve().parents[2]
    css = (root / "static" / "css" / "tasks" / "hub.css").read_text(
        encoding="utf-8"
    )
    js = (root / "static" / "js" / "pages" / "tasks" / "hub-collapse.js").read_text(
        encoding="utf-8"
    )

    assert "grid-template-rows" not in css
    assert ".task-hub-page .task-hub-group-body[hidden]," in css
    assert ".task-hub-page .task-hub-stage-body[hidden] {\n    display: none;" in css
    assert "body.hidden = true;" in js
    assert "body.hidden = !open;" in js
    assert "body.style.height = '0px';" in js
    assert "body.scrollHeight + 'px'" in js
    assert "function clampScrollRegion()" in js
    assert "scrollRegion.scrollTop = maxScrollTop;" in js
