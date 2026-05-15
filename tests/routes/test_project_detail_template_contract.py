import datetime
import re

import routes.projects.views as project_views
from models import (
    CalendarEvent,
    Etapa,
    ProjectStageMeeting,
    Task,
    TaskItemComment,
    UserCalendarConnection,
    db,
)


def test_project_detail_template_contains_stage_table_hooks(client_user, seed_data):
    response = client_user.get(f"/project/{seed_data['project_id']}")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    required_hooks = [
        'id="etapas-tbody"',
        "etapa-draggable-row",
        "etapa-drag-handle",
        "editable-field",
        "toggle-iniciada",
        "toggle-done",
        "btn-comment-data",
        "data-etapa-delete-form",
        "data-etapa-delete-btn",
        "form[data-etapa-delete-form]",
        'data-etapa-id="',
        'data-field="',
        'data-original-value="',
        'data-empty-display="Sem data"',
        'id="date-context-menu"',
    ]

    for hook in required_hooks:
        assert hook in html


def test_project_detail_history_button_opens_modal(client_user, seed_data):
    response = client_user.get(f"/project/{seed_data['project_id']}")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    required_hooks = [
        'class="btn btn-sm btn-history"',
        'data-bs-toggle="modal"',
        'data-bs-target="#projectHistoryModal"',
        'id="projectHistoryModal"',
        'id="projectHistoryModalLabel"',
        'id="historySearch"',
        'id="historyEntriesList"',
        "js/pages/projects/history.js",
    ]

    for hook in required_hooks:
        assert hook in html

    assert f'href="/project/{seed_data["project_id"]}/history" class="btn btn-sm btn-history"' not in html


def test_project_detail_template_contains_inline_add_stage_contract(
    client_user, seed_data
):
    response = client_user.get(f"/project/{seed_data['project_id']}")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    inline_hooks = [
        'id="btnImportModel"',
        'id="btnOpenInlineEtapaAdd"',
        'id="etapaInlineAddEntryRow"',
        'id="etapaInlineAddFormRow"',
        'id="etapaInlineAddForm"',
        'id="etapaInlineOrderPreview"',
        'id="btnSubmitInlineEtapaAdd"',
        'id="btnCancelInlineEtapaAdd"',
        'id="reactivate-project-confirm-modal"',
        'id="reactivate-project-confirm-btn"',
        'id="reactivate-project-cancel-btn"',
        "etapa-inline-cell etapa-inline-cell-actions",
        "etapa-inline-date-wrap",
        'id="etapa_inline_iniciada"',
        'id="etapa_inline_done"',
        "inline-status-toggle",
        "etapa-status-toggle",
        "etapa-inline-form-row",
    ]

    for hook in inline_hooks:
        assert hook in html

    assert 'id="etapa_inline_comentarios"' not in html

    inline_row_match = re.search(
        r'<tr id="etapaInlineAddFormRow"[\s\S]*?</tr>',
        html,
    )
    assert inline_row_match is not None
    assert inline_row_match.group(0).count("<td") == 9
    assert 'type="checkbox"' in inline_row_match.group(0)
    assert 'role="switch"' not in inline_row_match.group(0)
    assert "etapa-inline-new-badge" not in inline_row_match.group(0)
    assert '<th class="etapa-v4-col-number">ID</th>' in html


def test_project_detail_stage_task_quick_add_matches_task_hub_contract(
    client_user, seed_data
):
    response = client_user.get(f"/project/{seed_data['project_id']}")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    required_hooks = [
        "css/tasks/hub.css",
        "css/tasks/detail.css",
        "css/projects/detail/stage-task-modal-scoped.css",
        "css/projects/detail.css",
        'id="stageTaskQuickAdd"',
        "inert",
        "stage-task-quick-add__panel task-detail-v2 task-hub-page",
        'data-stage-task-content',
        'data-stage-task-loading',
        "stageTasksUrlTemplate",
        "/project/",
        "__ETAPA_ID__",
        "legacyTasksUrl",
        "tarefas-sem-etapa",
        "js/modules/responsavel-picker.js",
        "assignableUsersUrl",
        'aria-hidden="true"',
    ]

    for hook in required_hooks:
        assert hook in html

    assert 'data-stage-panel="' not in html
    assert "task-item-row" not in html
    assert "Nenhuma tarefa nesta etapa." not in html


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
    response = client_user.get(
        f"/project/{seed_data['project_id']}/tarefas-sem-etapa"
    )
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


def test_project_detail_without_stages_shows_only_inline_add_entry(
    app, client_user, seed_data
):
    with app.app_context():
        Etapa.query.filter_by(project_id=seed_data["project_id"]).delete()
        db.session.commit()

    response = client_user.get(f"/project/{seed_data['project_id']}")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert "Nenhuma etapa adicionada ainda." not in html
    assert 'id="etapaInlineEmptyRow"' not in html
    assert 'id="etapaInlineAddEntryRow"' in html


def test_project_detail_with_google_identity_shows_split_inline_add_actions(
    app, client_user, seed_data
):
    with app.app_context():
        db.session.add(
            UserCalendarConnection(
                user_id=seed_data["user_id"],
                provider="google",
                calendar_id="primary",
                refresh_token="refresh-token",
                google_account_id="google-shared-1",
                google_account_email="user@example.com",
            )
        )
        db.session.commit()

    response = client_user.get(f"/project/{seed_data['project_id']}")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'id="btnOpenInlineMeetingAdd"' in html
    assert "etapa-inline-entry-actions has-meeting-action" in html
    assert 'id="projectMeetingModal"' in html
    assert "css/partials/calendar-event-modal.css" in html
    assert f'action="/project/{seed_data["project_id"]}/meeting/add"' in html


def test_project_detail_hydrates_legacy_google_connection_and_shows_split_actions(
    app, client_user, seed_data, monkeypatch
):
    with app.app_context():
        db.session.add(
            UserCalendarConnection(
                user_id=seed_data["user_id"],
                provider="google",
                calendar_id="primary",
                refresh_token="refresh-token",
            )
        )
        db.session.commit()

    monkeypatch.setattr(
        project_views, "is_google_calendar_enabled", lambda _config: True
    )
    monkeypatch.setattr(
        project_views,
        "hydrate_google_connection_identity",
        lambda _config, connection: (
            setattr(connection, "google_account_id", "google-shared-legacy"),
            setattr(connection, "google_account_email", "legacy@example.com"),
        ),
    )

    response = client_user.get(f"/project/{seed_data['project_id']}")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'id="btnOpenInlineMeetingAdd"' in html

    with app.app_context():
        connection = UserCalendarConnection.query.filter_by(
            user_id=seed_data["user_id"]
        ).first()
        assert connection is not None
        assert connection.google_account_id == "google-shared-legacy"


def test_project_detail_renders_google_meeting_row_as_informational_item(
    app, client_user, seed_data
):
    with app.app_context():
        db.session.add(
            UserCalendarConnection(
                user_id=seed_data["user_id"],
                provider="google",
                calendar_id="primary",
                refresh_token="refresh-token",
                google_account_id="google-shared-1",
                google_account_email="user@example.com",
            )
        )
        calendar_event = CalendarEvent(
            user_id=seed_data["user_id"],
            title="Reunião de alinhamento",
            description="Descrição da reunião",
            location="Sala 2",
            starts_at=datetime.datetime(2026, 3, 20, 13, 0),
            ends_at=datetime.datetime(2026, 3, 20, 14, 0),
            google_event_id="google-meeting-template-contract",
            google_calendar_id="primary",
            meet_link="https://meet.google.com/test-contract",
            sync_status="ok",
            source="app",
        )
        etapa = Etapa(
            descricao="Reunião de alinhamento",
            data_inicio=datetime.date(2026, 3, 20),
            data_fim=datetime.date(2026, 3, 20),
            responsavel="user@example.com",
            project_id=seed_data["project_id"],
            ordem=99,
            entry_type="google_meeting",
        )
        db.session.add_all([calendar_event, etapa])
        db.session.flush()
        db.session.add(
            ProjectStageMeeting(
                etapa_id=etapa.id,
                project_id=seed_data["project_id"],
                calendar_event_id=calendar_event.id,
                creator_user_id=seed_data["user_id"],
                google_owner_account_id="google-shared-1",
                google_owner_email="user@example.com",
                google_event_id="google-meeting-template-contract",
                google_calendar_id="primary",
                starts_at=calendar_event.starts_at,
                ends_at=calendar_event.ends_at,
                timezone="America/Sao_Paulo",
                description=calendar_event.description,
                location=calendar_event.location,
                meet_link=calendar_event.meet_link,
                sync_status="ok",
            )
        )
        db.session.commit()

    response = client_user.get(f"/project/{seed_data['project_id']}")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    meeting_row_match = re.search(
        r'<tr[^>]*data-entry-type="google_meeting"[\s\S]*?</tr>',
        html,
    )
    assert meeting_row_match is not None
    meeting_row = meeting_row_match.group(0)

    assert "10:00 - 11:00" not in meeting_row
    assert "20/03/2026 10:00" in meeting_row
    assert "20/03/2026 11:00" in meeting_row
    assert "user@example.com" in meeting_row
    assert "far fa-user" in meeting_row
    assert "fa-video" in meeting_row
    assert "data-meeting-event=" in meeting_row
    assert 'colspan="7"' not in meeting_row
    assert "etapa-meeting-owner" in meeting_row
    assert "fab fa-google" in meeting_row
    assert "Reunião Google" not in meeting_row
    assert "etapa-v4-cell-number" in meeting_row
    assert ">Início<" not in meeting_row
    assert ">Fim<" not in meeting_row
    assert "toggle-iniciada" not in meeting_row
    assert "toggle-done" not in meeting_row
    assert 'data-field="descricao"' not in meeting_row
    assert 'data-field="data_inicio"' not in meeting_row
    assert 'data-field="data_fim"' not in meeting_row
    assert 'data-field="responsavel"' not in meeting_row
