import datetime
import re

from models import CalendarEvent, Etapa, ProjectStageMeeting, UserCalendarConnection, db


def test_project_detail_template_contains_stage_table_hooks(client_user, seed_data):
    response = client_user.get(f"/project/{seed_data['project_id']}")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    required_hooks = [
        'id="etapas-tbody"',
        'etapa-draggable-row',
        'etapa-drag-handle',
        'editable-field',
        'toggle-iniciada',
        'toggle-done',
        'btn-comment-data',
        'data-etapa-delete-form',
        'data-etapa-delete-btn',
        "form[data-etapa-delete-form]",
        'data-etapa-id="',
        'data-field="',
        'data-original-value="',
        'data-empty-display="Sem data"',
        'id="date-context-menu"',
    ]

    for hook in required_hooks:
        assert hook in html


def test_project_detail_template_contains_inline_add_stage_contract(client_user, seed_data):
    response = client_user.get(f"/project/{seed_data['project_id']}")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    inline_hooks = [
        'id="btnImportModel"',
        'id="btnOpenInlineEtapaAdd"',
        'id="etapaInlineAddEntryRow"',
        'id="etapaInlineAddFormRow"',
        'id="etapaInlineAddForm"',
        'id="btnSubmitInlineEtapaAdd"',
        'id="btnCancelInlineEtapaAdd"',
        'id="reactivate-project-confirm-modal"',
        'id="reactivate-project-confirm-btn"',
        'id="reactivate-project-cancel-btn"',
        'etapa-inline-cell etapa-inline-cell-actions',
        'etapa-inline-date-wrap',
        'id="etapa_inline_iniciada"',
        'id="etapa_inline_done"',
        'inline-status-toggle',
        'etapa-status-toggle',
        'etapa-inline-form-row',
    ]

    for hook in inline_hooks:
        assert hook in html

    assert 'id="etapa_inline_comentarios"' not in html

    inline_row_match = re.search(
        r'<tr id="etapaInlineAddFormRow"[\s\S]*?</tr>',
        html,
    )
    assert inline_row_match is not None
    assert inline_row_match.group(0).count('<td') == 9
    assert 'type="checkbox"' in inline_row_match.group(0)
    assert 'role="switch"' not in inline_row_match.group(0)


def test_project_detail_without_stages_shows_only_inline_add_entry(app, client_user, seed_data):
    with app.app_context():
        Etapa.query.filter_by(project_id=seed_data['project_id']).delete()
        db.session.commit()

    response = client_user.get(f"/project/{seed_data['project_id']}")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'Nenhuma etapa adicionada ainda.' not in html
    assert 'id="etapaInlineEmptyRow"' not in html
    assert 'id="etapaInlineAddEntryRow"' in html


def test_project_detail_with_google_identity_shows_split_inline_add_actions(app, client_user, seed_data):
    with app.app_context():
        db.session.add(
            UserCalendarConnection(
                user_id=seed_data['user_id'],
                provider='google',
                calendar_id='primary',
                refresh_token='refresh-token',
                google_account_id='google-shared-1',
                google_account_email='user@example.com',
            )
        )
        db.session.commit()

    response = client_user.get(f"/project/{seed_data['project_id']}")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'id="btnOpenInlineMeetingAdd"' in html
    assert 'etapa-inline-entry-actions has-meeting-action' in html
    assert 'id="projectMeetingModal"' in html
    assert f'action="/project/{seed_data["project_id"]}/meeting/add"' in html


def test_project_detail_renders_google_meeting_row_as_informational_item(app, client_user, seed_data):
    with app.app_context():
        db.session.add(
            UserCalendarConnection(
                user_id=seed_data['user_id'],
                provider='google',
                calendar_id='primary',
                refresh_token='refresh-token',
                google_account_id='google-shared-1',
                google_account_email='user@example.com',
            )
        )
        calendar_event = CalendarEvent(
            user_id=seed_data['user_id'],
            title='Reunião de alinhamento',
            starts_at=datetime.datetime(2026, 3, 20, 13, 0),
            ends_at=datetime.datetime(2026, 3, 20, 14, 0),
            google_event_id='google-meeting-template-contract',
            google_calendar_id='primary',
            sync_status='ok',
            source='app',
        )
        etapa = Etapa(
            descricao='Reunião de alinhamento',
            data_inicio=datetime.date(2026, 3, 20),
            data_fim=datetime.date(2026, 3, 20),
            responsavel='user@example.com',
            project_id=seed_data['project_id'],
            ordem=99,
            entry_type='google_meeting',
        )
        db.session.add_all([calendar_event, etapa])
        db.session.flush()
        db.session.add(
            ProjectStageMeeting(
                etapa_id=etapa.id,
                project_id=seed_data['project_id'],
                calendar_event_id=calendar_event.id,
                creator_user_id=seed_data['user_id'],
                google_owner_account_id='google-shared-1',
                google_owner_email='user@example.com',
                google_event_id='google-meeting-template-contract',
                google_calendar_id='primary',
                starts_at=calendar_event.starts_at,
                ends_at=calendar_event.ends_at,
                timezone='America/Sao_Paulo',
                sync_status='ok',
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

    assert 'Reunião Google' in meeting_row
    assert '10:00 - 11:00' in meeting_row
    assert 'etapa-meeting-status-pill' in meeting_row
    assert 'toggle-iniciada' not in meeting_row
    assert 'toggle-done' not in meeting_row
    assert 'data-field="descricao"' not in meeting_row
    assert 'data-field="responsavel"' not in meeting_row
