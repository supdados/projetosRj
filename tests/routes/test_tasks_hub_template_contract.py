from pathlib import Path

from models import Task, db
from time_utils import utc_now


def _read_kanban_js(*relative_paths):
    modules_root = Path(__file__).resolve().parents[2] / "static" / "js" / "modules"
    paths = relative_paths or (
        "kanban-manager.js",
        "kanban/board-render.js",
        "kanban/drawer-comments.js",
        "kanban/drawer-anexos.js",
        "kanban/drawer-core.js",
        "kanban/board-dnd.js",
        "kanban/composer.js",
        "kanban/view-toggle.js",
    )
    return "\n".join(
        (modules_root / path).read_text(encoding="utf-8") for path in paths
    )


def test_tasks_hub_serves_spa_shell(client_user):
    # Apos o cut-over KEEP-ENDPOINT o hub serve a shell da SPA SvelteKit; a UI
    # (toggle/list/kanban/composer/drawer) vive nos componentes Svelte e a fonte
    # de dados em GET /api/tarefas. Aqui garantimos apenas o shell no path nativo.
    response = client_user.get("/tarefas")
    assert response.status_code == 200
    assert response.mimetype == "text/html"
    body = response.get_data(as_text=True)
    assert "data-sveltekit-preload-data" in body
    assert '<meta name="csrf-token"' in body


def test_tasks_hub_requires_login(client):
    response = client.get("/tarefas", follow_redirects=False)
    assert response.status_code == 302


def test_tasks_hub_project_filter_js_allows_enter_to_clear_empty_selection():
    file_path = (
        Path(__file__).resolve().parents[2]
        / "static"
        / "js"
        / "modules"
        / "inline-editors.js"
    )
    content = file_path.read_text(encoding="utf-8")

    assert "function clearProjectFilter(shouldSubmit)" in content
    assert "if (!(input.value || '').trim()) {" in content
    assert "clearProjectFilter(true);" in content


def test_tasks_hub_global_placeholder_css_keeps_extra_spacing_before_orgao_line():
    file_path = (
        Path(__file__).resolve().parents[2] / "static" / "css" / "tasks" / "hub.css"
    )
    content = file_path.read_text(encoding="utf-8")

    assert (
        ".task-hub-page .task-hub-group-global-placeholder .task-hub-group-project-wrap {"
        in content
    )
    assert "margin-bottom: 0.58rem;" in content


def test_tasks_hub_kanban_js_persists_visual_order_per_url():
    content = _read_kanban_js("kanban-manager.js", "kanban/board-render.js")

    assert "function buildKanbanOrderStorageKey()" in content
    assert (
        "return 'task-hub-kanban-order:' + window.location.pathname + window.location.search;"
        in content
    )
    assert "function readStoredKanbanOrder()" in content
    assert "function sortItemsForKanban(items)" in content
    assert "writeStoredKanbanOrder(serializeKanbanOrder());" in content


def test_tasks_hub_kanban_js_blocks_restricted_drawer_fields_and_shows_banner():
    content = _read_kanban_js("kanban-manager.js", "kanban/drawer-core.js")

    assert (
        "var DRAWER_RESTRICTED_EDIT_MESSAGE = 'Somente o autor da tarefa ou um administrador pode editar descrição, prioridade e responsável.';"
        in content
    )
    assert (
        "drawerPermissionBanner: document.getElementById('taskItemDrawerPermissionBanner'),"
        in content
    )
    assert "function setDrawerRestrictedFieldLocks(canEditRestricted)" in content
    assert "function handleDrawerRestrictedInteraction(event)" in content
    assert "drawerPrioridade.addEventListener('pointerdown'" in content


def test_tasks_hub_drawer_css_marks_locked_controls_as_not_allowed():
    drawer_css_path = (
        Path(__file__).resolve().parents[2]
        / "static"
        / "css"
        / "tasks"
        / "detail"
        / "drawer.css"
    )
    drawer_css_content = drawer_css_path.read_text(encoding="utf-8")
    dark_css_path = (
        Path(__file__).resolve().parents[2]
        / "static"
        / "css"
        / "tasks"
        / "detail"
        / "dark.css"
    )
    dark_css_content = dark_css_path.read_text(encoding="utf-8")

    assert ".task-detail-v2 .task-item-drawer-permission-banner {" in drawer_css_content
    assert ".task-detail-v2 .task-item-drawer-select.is-locked," in drawer_css_content
    assert "cursor: not-allowed;" in drawer_css_content
    assert ".task-item-drawer-permission-banner {" in dark_css_content
    assert ".task-item-drawer-select.is-locked," in dark_css_content


def test_tasks_hub_kanban_js_keeps_grouped_list_rows_inside_project_sections():
    content = _read_kanban_js("kanban-manager.js", "kanban/board-render.js")

    assert "function syncGroupedListOrder(orderIds)" in content
    assert "var groups = refs.listEl.querySelectorAll('.task-hub-group');" in content
    assert (
        "var row = group.querySelector('.task-item-row[data-item-id=\"' + id + '\"]');"
        in content
    )
    assert (
        "function syncListOrderFromKanban() {\n"
        "            if (!ctx.reorderUrl) return;\n" in content
    )
    # Lista agrupada delega para syncGroupedListOrder, mantendo as linhas dentro
    # das seções de projeto (em vez de reordenar a lista plana).
    assert (
        "            if (ctx.isTaskHubGroupedList()) {\n"
        "                syncGroupedListOrder(orderIds);\n"
        "                return;\n"
        "            }" in content
    )


def test_tasks_hub_kanban_project_link_disables_native_link_drag():
    js_content = _read_kanban_js("kanban-manager.js", "kanban/board-render.js")
    css_path = (
        Path(__file__).resolve().parents[2] / "static" / "css" / "tasks" / "hub.css"
    )
    css_content = css_path.read_text(encoding="utf-8")

    assert "link.setAttribute('draggable', 'false');" in js_content
    assert "-webkit-user-drag: none;" in css_content


def test_tasks_hub_kanban_project_link_keeps_drag_cursor_on_hold():
    tarefas_css_path = (
        Path(__file__).resolve().parents[2] / "static" / "css" / "tasks" / "hub.css"
    )
    tarefas_css_content = tarefas_css_path.read_text(encoding="utf-8")
    kanban_css_path = (
        Path(__file__).resolve().parents[2]
        / "static"
        / "css"
        / "tasks"
        / "detail"
        / "kanban.css"
    )
    kanban_css_content = kanban_css_path.read_text(encoding="utf-8")

    assert "cursor: pointer;" in tarefas_css_content
    assert (
        ".task-detail-v2 .task-items-kanban-card:active .task-hub-kanban-context a,"
        in kanban_css_content
    )
    assert "cursor: grabbing;" in kanban_css_content


def test_tasks_hub_view_toggle_hover_only_affects_hovered_button():
    pages_root = (
        Path(__file__).resolve().parents[2] / "static" / "css" / "tasks" / "detail"
    )
    light_css = (pages_root / "view-toggle.css").read_text(encoding="utf-8")
    dark_css = (pages_root / "dark.css").read_text(encoding="utf-8")

    assert (
        ".task-detail-v2 .task-items-view-btn:hover .task-items-view-label:not(.is-active),"
        in light_css
    )
    assert (
        ".task-detail-v2 .task-items-view-toggle:hover .task-items-view-label:not(.is-active)"
        not in light_css
    )
    assert (
        'html[data-theme="dark"] body.is-authenticated .task-detail-v2 .task-items-view-btn:hover .task-items-view-label:not(.is-active),'
        in dark_css
    )
    assert (
        'html[data-theme="dark"] body.is-authenticated .task-detail-v2 .task-items-view-toggle:hover .task-items-view-label:not(.is-active)'
        not in dark_css
    )


def test_tasks_hub_kanban_light_mode_uses_distinct_validation_and_adjustments_colors():
    kanban_css_path = (
        Path(__file__).resolve().parents[2]
        / "static"
        / "css"
        / "tasks"
        / "detail"
        / "kanban.css"
    )
    kanban_css_content = kanban_css_path.read_text(encoding="utf-8")
    list_css_path = (
        Path(__file__).resolve().parents[2]
        / "static"
        / "css"
        / "tasks"
        / "detail"
        / "list.css"
    )
    list_css_content = list_css_path.read_text(encoding="utf-8")

    assert (
        ".task-detail-v2 .task-items-kanban-badge.status-para_validacao {\n    background: #fff2c2;"
        in kanban_css_content
    )
    assert "border-color: #eac35b;" in kanban_css_content
    assert "color: #7a4b00;" in kanban_css_content

    assert (
        ".task-detail-v2 .task-items-kanban-badge.status-para_ajustes {\n    background: #fde7eb;"
        in kanban_css_content
    )
    assert "border-color: #efb2bf;" in kanban_css_content
    assert "color: #9f1f3a;" in kanban_css_content

    assert (
        ".task-detail-v2 .task-item-status.status-para_validacao,\n.task-detail-v2 .task-item-status-readonly.status-para_validacao {\n    background: #fff2c2;"
        in list_css_content
    )
    assert "border-color: #eac35b;" in list_css_content
    assert "color: #7a4b00;" in list_css_content
    assert (
        ".task-detail-v2 .task-item-bar.status-para_validacao {\n    background: #7a4b00;"
        in list_css_content
    )

    assert (
        ".task-detail-v2 .task-item-status.status-para_ajustes,\n.task-detail-v2 .task-item-status-readonly.status-para_ajustes {\n    background: #fde7eb;"
        in list_css_content
    )
    assert "border-color: #efb2bf;" in list_css_content
    assert "color: #9f1f3a;" in list_css_content
    assert (
        ".task-detail-v2 .task-item-bar.status-para_ajustes {\n    background: #9f1f3a;"
        in list_css_content
    )


def test_tasks_hub_dark_mode_uses_neutral_text_tokens_for_structural_copy():
    tarefas_css_path = (
        Path(__file__).resolve().parents[2] / "static" / "css" / "tasks" / "hub.css"
    )
    tarefas_css_content = tarefas_css_path.read_text(encoding="utf-8")

    assert (
        'html[data-theme="dark"] body.is-authenticated .task-hub-page .task-hub-group-title {\n    color: var(--app-color-text-primary);'
        in tarefas_css_content
    )
    assert (
        'html[data-theme="dark"] body.is-authenticated .task-hub-page .task-hub-group-meta {\n    color: var(--app-color-text-muted);'
        in tarefas_css_content
    )
    assert (
        'html[data-theme="dark"] body.is-authenticated .task-hub-page .task-hub-kanban-context {\n    color: var(--app-color-text-muted);'
        in tarefas_css_content
    )


def test_tasks_hub_inline_add_action_buttons_use_square_corners():
    list_css_path = (
        Path(__file__).resolve().parents[2]
        / "static"
        / "css"
        / "tasks"
        / "detail"
        / "list.css"
    )
    list_css_content = list_css_path.read_text(encoding="utf-8")

    assert (
        ".task-detail-v2 .task-hub-add-cancel {\n    color: #6b7280;\n    width: 26px;\n    height: 26px;\n    min-width: 26px;\n    border-radius: 8px;"
        in list_css_content
    )
    assert (
        ".task-detail-v2 .task-item-btn-confirm {\n    color: #16a34a;\n    width: 26px;\n    height: 26px;\n    min-width: 26px;\n    border-radius: 8px;"
        in list_css_content
    )


def test_tasks_archived_redirects_to_hub_with_modo_param(app, client_user, seed_data):
    # A SPA nao tem rota client-side /tarefas/arquivadas: o endpoint vira um
    # redirect resolver 302 -> /tarefas?modo=arquivadas (a pagina /tarefas le o
    # query param no mount); os dados vem de GET /api/tarefas?modo=arquivadas.
    with app.app_context():
        archived_task = Task(
            descricao="Tarefa arquivada readonly",
            status="finalizada",
            responsavel="Usuario Editavel",
            prioridade="alta",
            tipo_pedido="bug",
            ordem=99,
            project_id=seed_data["project_id"],
            created_by_id=seed_data["user_id"],
            is_archived=True,
            archived_at=utc_now(),
        )
        db.session.add(archived_task)
        db.session.commit()

    response = client_user.get("/tarefas/arquivadas", follow_redirects=False)
    assert response.status_code == 302
    location = response.headers["Location"]
    assert "/tarefas" in location
    assert "modo=arquivadas" in location

    # O destino do redirect serve a shell da SPA.
    final_response = client_user.get(location)
    assert final_response.status_code == 200
    assert "data-sveltekit-preload-data" in final_response.get_data(as_text=True)
