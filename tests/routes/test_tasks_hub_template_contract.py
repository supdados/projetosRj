from pathlib import Path
import re

from models import Task, db
from time_utils import utc_now


def _read_kanban_js(*relative_paths):
    modules_root = Path(__file__).resolve().parents[2] / 'static' / 'js' / 'modules'
    paths = relative_paths or (
        'kanban-manager.js',
        'kanban/board-render.js',
        'kanban/drawer-comments.js',
        'kanban/drawer-anexos.js',
        'kanban/drawer-core.js',
        'kanban/board-dnd.js',
        'kanban/composer.js',
        'kanban/view-toggle.js',
    )
    return '\n'.join((modules_root / path).read_text(encoding='utf-8') for path in paths)


def test_tasks_hub_template_contains_view_toggle_and_project_filter(client_user):
    response = client_user.get('/tarefas')
    assert response.status_code == 200

    html = response.get_data(as_text=True)

    required_hooks = [
        'id="taskItemsViewToggle"',
        'id="taskHubCreateButton"',
        'data-view="list"',
        'data-view="kanban"',
        'id="taskItemsListView"',
        'id="taskItemsKanbanView"',
        'id="taskItemsKanbanBoard"',
        'id="filter_project_input"',
        'id="filterProjectDropdown"',
        'id="filter_prioridade"',
        'id="filter_tipo"',
        'id="filter_status"',
        'id="filter_responsavel"',
        'class="task-hub-group"',
        'task-hub-add-row',
    ]
    for hook in required_hooks:
        assert hook in html

    assert '>Filtrar<' not in html
    assert 'id="archiveFinalizedTasksForm"' in html
    assert 'items-header-clean' not in html
    assert html.index('id="taskItemsViewToggle"') < html.index('id="filterTasksForm"')
    assert 'Gerenciamento de tarefas' in html
    assert 'title="Tarefas arquivadas"' in html
    assert 'aria-label="Tarefas arquivadas"' in html
    assert 'data-reorder-url="/tarefas/reordenar"' in html


def test_tasks_hub_header_orders_archive_then_toggle_then_create(client_user):
    response = client_user.get('/tarefas')
    assert response.status_code == 200

    html = response.get_data(as_text=True)
    archive_form_index = html.index('id="archiveFinalizedTasksForm"')
    archived_link_index = html.index('aria-label="Tarefas arquivadas"')
    toggle_index = html.index('id="taskItemsViewToggle"')
    create_button_index = html.index('id="taskHubCreateButton"')

    assert archive_form_index < archived_link_index < toggle_index < create_button_index


def test_tasks_hub_kanban_composer_requires_project_when_no_filter(client_user):
    response = client_user.get('/tarefas')
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'task-items-kanban-add-project-input' in html
    assert 'task-hub-kanban-project-dropdown' in html
    assert 'task-hub-kanban-project-caret' in html
    assert 'placeholder="Selecione o projeto"' in html
    assert 'placeholder="Selecione o projeto..."' not in html
    assert html.index('id="taskItemDrawerAutosaveStatus"') < html.index('id="taskItemDrawerPrioridade"')


def test_tasks_hub_drawer_contains_permission_banner_hook(client_user):
    response = client_user.get('/tarefas')
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'id="taskItemDrawerPermissionBanner"' in html
    assert 'class="task-item-drawer-permission-banner"' in html


def test_tasks_hub_kanban_composer_uses_filtered_project_without_project_input(client_user, seed_data):
    response = client_user.get(f'/tarefas?project={seed_data["project_id"]}')
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'task-items-kanban-add-project-input' not in html
    assert 'task-items-kanban-add-project-value' in html


def test_tasks_hub_admin_renders_project_filter_before_area_filter(client_admin):
    response = client_admin.get('/tarefas')
    assert response.status_code == 200

    html = response.get_data(as_text=True)
    assert 'id="filter_project_input"' in html
    assert 'id="filter_area"' in html
    assert html.index('id="filter_project_input"') < html.index('id="filter_area"')


def test_tasks_hub_uses_project_links_and_not_duplicate_task_detail_link(client_user, seed_data):
    response = client_user.get('/tarefas')
    assert response.status_code == 200

    html = response.get_data(as_text=True)
    assert f'href="/project/{seed_data["project_id"]}"' in html
    assert f'href="/tarefas/{seed_data["task_id"]}"' not in html


def test_tasks_hub_project_filter_lists_visible_projects_without_active_items(client_user, seed_data):
    response = client_user.get('/tarefas')
    assert response.status_code == 200

    html = response.get_data(as_text=True)
    assert f'data-value="{seed_data["project_complete_id"]}"' in html
    assert 'Projeto Concluivel' in html


def test_tasks_hub_hides_finalize_and_delete_controls_for_non_author(client_editable, seed_data):
    response = client_editable.get('/tarefas')
    assert response.status_code == 200

    html = response.get_data(as_text=True)
    row_match = re.search(
        rf'<div\s+class="task-item-row"[^>]*data-item-id="{seed_data["task_id"]}"[\s\S]*?<select class="task-item-status[\s\S]*?</select>',
        html,
    )

    assert row_match is not None
    row_html = row_match.group(0)
    assert 'data-can-delete="0"' in row_html
    assert 'data-can-finalize="0"' in row_html
    assert 'value="finalizada"' not in row_html
    assert f'data-bs-target="#deleteItemModal-{seed_data["task_id"]}"' not in html
    assert f'id="deleteItemModal-{seed_data["task_id"]}"' not in html


def test_tasks_hub_project_filter_js_allows_enter_to_clear_empty_selection():
    file_path = Path(__file__).resolve().parents[2] / 'static' / 'js' / 'modules' / 'inline-editors.js'
    content = file_path.read_text(encoding='utf-8')

    assert 'function clearProjectFilter(shouldSubmit)' in content
    assert "if (!(input.value || '').trim()) {" in content
    assert 'clearProjectFilter(true);' in content


def test_tasks_hub_global_placeholder_project_picker_scopes_projects_by_selected_area():
    file_path = Path(__file__).resolve().parents[2] / 'static' / 'js' / 'modules' / 'add-item-inline.js'
    content = file_path.read_text(encoding='utf-8')

    assert 'function getProjectOptionsForPicker()' in content
    assert 'if (!selectedArea) {' in content
    assert 'optionArea === selectedAreaKey' in content
    assert "input.addEventListener('focus', showDropdown);" not in content
    assert "input.addEventListener('click', showDropdown);" in content
    assert "if (typeof opts.containsTarget === 'function' && opts.containsTarget(event.target)) return;" in content


def test_tasks_hub_inline_add_js_reuses_existing_group_and_skips_focus_jump():
    file_path = Path(__file__).resolve().parents[2] / 'static' / 'js' / 'modules' / 'add-item-inline.js'
    content = file_path.read_text(encoding='utf-8')

    assert 'return sourceGroup;' in content
    assert 'if (opts.focusInserted !== false) {' in content
    assert 'focusInserted: !!opts.isGlobalPlaceholder' in content


def test_tasks_hub_global_placeholder_css_keeps_extra_spacing_before_area_line():
    file_path = Path(__file__).resolve().parents[2] / 'static' / 'css' / 'tasks' / 'hub.css'
    content = file_path.read_text(encoding='utf-8')

    assert '.task-hub-page .task-hub-group-global-placeholder .task-hub-group-project-wrap {' in content
    assert 'margin-bottom: 0.58rem;' in content


def test_tasks_hub_kanban_js_persists_visual_order_per_url():
    content = _read_kanban_js('kanban-manager.js', 'kanban/board-render.js')

    assert 'function buildKanbanOrderStorageKey()' in content
    assert "return 'task-hub-kanban-order:' + window.location.pathname + window.location.search;" in content
    assert 'function readStoredKanbanOrder()' in content
    assert 'function sortItemsForKanban(items)' in content
    assert 'writeStoredKanbanOrder(serializeKanbanOrder());' in content


def test_tasks_hub_kanban_js_blocks_restricted_drawer_fields_and_shows_banner():
    content = _read_kanban_js('kanban-manager.js', 'kanban/drawer-core.js')

    assert "var DRAWER_RESTRICTED_EDIT_MESSAGE = 'Somente o autor da tarefa ou um administrador pode editar descrição, prioridade e responsável.';" in content
    assert "drawerPermissionBanner: document.getElementById('taskItemDrawerPermissionBanner')," in content
    assert 'function setDrawerRestrictedFieldLocks(canEditRestricted)' in content
    assert 'function handleDrawerRestrictedInteraction(event)' in content
    assert "drawerPrioridade.addEventListener('pointerdown'" in content


def test_tasks_hub_drawer_css_marks_locked_controls_as_not_allowed():
    drawer_css_path = Path(__file__).resolve().parents[2] / 'static' / 'css' / 'tasks' / 'detail' / 'drawer.css'
    drawer_css_content = drawer_css_path.read_text(encoding='utf-8')
    dark_css_path = Path(__file__).resolve().parents[2] / 'static' / 'css' / 'tasks' / 'detail' / 'dark.css'
    dark_css_content = dark_css_path.read_text(encoding='utf-8')

    assert '.task-detail-v2 .task-item-drawer-permission-banner {' in drawer_css_content
    assert '.task-detail-v2 .task-item-drawer-select.is-locked,' in drawer_css_content
    assert 'cursor: not-allowed;' in drawer_css_content
    assert '.task-item-drawer-permission-banner {' in dark_css_content
    assert '.task-item-drawer-select.is-locked,' in dark_css_content


def test_tasks_hub_kanban_js_keeps_grouped_list_rows_inside_project_sections():
    content = _read_kanban_js('kanban-manager.js', 'kanban/board-render.js')

    assert 'function syncGroupedListOrder(orderIds)' in content
    assert "var groups = refs.listEl.querySelectorAll('.task-hub-group');" in content
    assert "var row = group.querySelector('.task-item-row[data-item-id=\"' + id + '\"]');" in content
    assert "if (ctx.isTaskHubGroupedList()) {" in content
    assert 'syncGroupedListOrder(orderIds);' in content


def test_tasks_hub_kanban_project_link_disables_native_link_drag():
    js_content = _read_kanban_js('kanban-manager.js', 'kanban/board-render.js')
    css_path = Path(__file__).resolve().parents[2] / 'static' / 'css' / 'tasks' / 'hub.css'
    css_content = css_path.read_text(encoding='utf-8')

    assert "link.setAttribute('draggable', 'false');" in js_content
    assert '-webkit-user-drag: none;' in css_content


def test_tasks_hub_kanban_project_link_keeps_drag_cursor_on_hold():
    tarefas_css_path = Path(__file__).resolve().parents[2] / 'static' / 'css' / 'tasks' / 'hub.css'
    tarefas_css_content = tarefas_css_path.read_text(encoding='utf-8')
    kanban_css_path = Path(__file__).resolve().parents[2] / 'static' / 'css' / 'tasks' / 'detail' / 'kanban.css'
    kanban_css_content = kanban_css_path.read_text(encoding='utf-8')

    assert 'cursor: pointer;' in tarefas_css_content
    assert '.task-detail-v2 .task-items-kanban-card:active .task-hub-kanban-context a,' in kanban_css_content
    assert 'cursor: grabbing;' in kanban_css_content


def test_tasks_hub_view_toggle_hover_only_affects_hovered_button():
    pages_root = Path(__file__).resolve().parents[2] / 'static' / 'css' / 'tasks' / 'detail'
    light_css = (pages_root / 'view-toggle.css').read_text(encoding='utf-8')
    dark_css = (pages_root / 'dark.css').read_text(encoding='utf-8')

    assert '.task-detail-v2 .task-items-view-btn:hover .task-items-view-label:not(.is-active),' in light_css
    assert '.task-detail-v2 .task-items-view-toggle:hover .task-items-view-label:not(.is-active)' not in light_css
    assert 'html[data-theme="dark"] body.is-authenticated .task-detail-v2 .task-items-view-btn:hover .task-items-view-label:not(.is-active),' in dark_css
    assert 'html[data-theme="dark"] body.is-authenticated .task-detail-v2 .task-items-view-toggle:hover .task-items-view-label:not(.is-active)' not in dark_css


def test_tasks_hub_kanban_light_mode_uses_distinct_validation_and_adjustments_colors():
    kanban_css_path = Path(__file__).resolve().parents[2] / 'static' / 'css' / 'tasks' / 'detail' / 'kanban.css'
    kanban_css_content = kanban_css_path.read_text(encoding='utf-8')
    list_css_path = Path(__file__).resolve().parents[2] / 'static' / 'css' / 'tasks' / 'detail' / 'list.css'
    list_css_content = list_css_path.read_text(encoding='utf-8')

    assert '.task-detail-v2 .task-items-kanban-badge.status-para_validacao {\n    background: #fff2c2;' in kanban_css_content
    assert 'border-color: #eac35b;' in kanban_css_content
    assert 'color: #7a4b00;' in kanban_css_content

    assert '.task-detail-v2 .task-items-kanban-badge.status-para_ajustes {\n    background: #fde7eb;' in kanban_css_content
    assert 'border-color: #efb2bf;' in kanban_css_content
    assert 'color: #9f1f3a;' in kanban_css_content

    assert '.task-detail-v2 .task-item-status.status-para_validacao,\n.task-detail-v2 .task-item-status-readonly.status-para_validacao {\n    background: #fff2c2;' in list_css_content
    assert 'border-color: #eac35b;' in list_css_content
    assert 'color: #7a4b00;' in list_css_content
    assert '.task-detail-v2 .task-item-bar.status-para_validacao {\n    background: #7a4b00;' in list_css_content

    assert '.task-detail-v2 .task-item-status.status-para_ajustes,\n.task-detail-v2 .task-item-status-readonly.status-para_ajustes {\n    background: #fde7eb;' in list_css_content
    assert 'border-color: #efb2bf;' in list_css_content
    assert 'color: #9f1f3a;' in list_css_content
    assert '.task-detail-v2 .task-item-bar.status-para_ajustes {\n    background: #9f1f3a;' in list_css_content


def test_tasks_hub_dark_mode_uses_neutral_text_tokens_for_structural_copy():
    tarefas_css_path = Path(__file__).resolve().parents[2] / 'static' / 'css' / 'tasks' / 'hub.css'
    tarefas_css_content = tarefas_css_path.read_text(encoding='utf-8')

    assert 'html[data-theme="dark"] body.is-authenticated .task-hub-page .task-hub-group-title {\n    color: var(--app-color-text-primary);' in tarefas_css_content
    assert 'html[data-theme="dark"] body.is-authenticated .task-hub-page .task-hub-group-meta {\n    color: var(--app-color-text-muted);' in tarefas_css_content
    assert 'html[data-theme="dark"] body.is-authenticated .task-hub-page .task-hub-kanban-context {\n    color: var(--app-color-text-muted);' in tarefas_css_content


def test_tasks_hub_inline_add_action_buttons_use_square_corners():
    list_css_path = Path(__file__).resolve().parents[2] / 'static' / 'css' / 'tasks' / 'detail' / 'list.css'
    list_css_content = list_css_path.read_text(encoding='utf-8')

    assert '.task-detail-v2 .task-hub-add-cancel {\n    color: #6b7280;\n    width: 26px;\n    height: 26px;\n    min-width: 26px;\n    border-radius: 8px;' in list_css_content
    assert '.task-detail-v2 .task-item-btn-confirm {\n    color: #16a34a;\n    width: 26px;\n    height: 26px;\n    min-width: 26px;\n    border-radius: 8px;' in list_css_content


def test_tasks_archived_template_reuses_active_list_structure_in_readonly_mode(app, client_user, seed_data):
    with app.app_context():
        archived_task = Task(
            descricao='Tarefa arquivada readonly',
            status='finalizada',
            responsavel='Usuario Editavel',
            prioridade='alta',
            tipo_pedido='bug',
            ordem=99,
            project_id=seed_data['project_id'],
            created_by_id=seed_data['user_id'],
            is_archived=True,
            archived_at=utc_now(),
        )
        db.session.add(archived_task)
        db.session.commit()

    response = client_user.get('/tarefas/arquivadas')
    assert response.status_code == 200

    html = response.get_data(as_text=True)
    required_hooks = [
        'id="taskItemsListView"',
        'class="task-hub-group"',
        'task-item-col-desc',
        'task-item-col-prioridade',
        'task-item-col-tipo',
        'task-item-col-status',
        'task-item-col-responsavel',
        'task-item-status-readonly',
        'task-item-unarchive-form',
        'task-item-comments-btn',
        'comments-body-',
        'title="Desarquivar"',
        'Apagar',
        '>Ativas<',
    ]
    for hook in required_hooks:
        assert hook in html

    assert 'id="taskItemsViewToggle"' not in html
    assert 'id="taskItemsKanbanView"' not in html
    assert 'task-hub-add-row' not in html
    assert 'task-item-desc-edit-btn' not in html
    assert 'class="task-comment-form"' not in html
    assert 'btn-edit-comment' not in html
