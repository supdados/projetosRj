"""P2-20: falha de persistência não é validação; rollback e um log com causa."""

import logging

import pytest
from services.google_calendar import GoogleCalendarError

from models import (
    Etapa,
    Project,
    ProjectHistory,
    Task,
    TaskComment,
    UserNotification,
    db,
)


class RejectedCommit:
    def __call__(self) -> None:
        db.session.flush()
        raise RuntimeError("SQL interno / credencial-sintetica-nao-expor")


class FailedCatalogRead:
    def __call__(self, _objective_id: int) -> None:
        raise RuntimeError("SQL interno / credencial-sintetica-nao-expor")


def persisted_state(app) -> dict[str, object]:
    with app.app_context():
        return {
            "comments": [
                (row.id, row.content)
                for row in TaskComment.query.order_by(TaskComment.id)
            ],
            "stages": [
                (row.id, row.descricao, row.iniciada, row.done)
                for row in Etapa.query.order_by(Etapa.id)
            ],
            "tasks": [
                (row.id, row.descricao, row.status, row.is_archived)
                for row in Task.query.order_by(Task.id)
            ],
            "projects": [
                (row.id, row.titulo, row.status)
                for row in Project.query.order_by(Project.id)
            ],
            "history": ProjectHistory.query.count(),
            "notifications": UserNotification.query.count(),
        }


@pytest.mark.parametrize(
    "action",
    [
        "comment_add",
        "comment_edit",
        "comment_delete",
        "stage_add",
        "stage_field",
        "stage_reorder",
        "task_fields",
        "task_status",
        "project_inline",
    ],
)
def test_commit_failure_is_500_logged_once_and_rolled_back(
    app, client_user, seed_data, monkeypatch, caplog, action
) -> None:
    cases = {
        "comment_add": (
            f"/api/tarefas/{seed_data['task_id']}/comentarios",
            {"content": "novo"},
        ),
        "comment_edit": (
            f"/api/comentarios/{seed_data['comment_id']}",
            {"content": "alterado"},
        ),
        "comment_delete": (f"/api/comentarios/{seed_data['comment_id']}/delete", {}),
        "stage_add": (
            f"/api/projetos/{seed_data['project_id']}/etapas",
            {
                "descricao": "nova",
                "responsaveis": [{"area_id": seed_data["auditoria_orgao_id"]}],
            },
        ),
        "stage_field": (
            f"/api/etapas/{seed_data['etapa_id']}/update-field",
            {"field": "descricao", "value": "alterada"},
        ),
        "stage_reorder": (
            f"/api/projetos/{seed_data['project_id']}/etapas/reordenar",
            {"etapa_ids": [seed_data["etapa_started_id"], seed_data["etapa_id"]]},
        ),
        "task_fields": (
            f"/api/tarefas/{seed_data['task_id']}/campos",
            {"descricao": "alterada"},
        ),
        "task_status": (
            f"/api/tarefas/{seed_data['task_id']}/status",
            {"status": "em_andamento"},
        ),
        "project_inline": (
            f"/api/projetos/{seed_data['project_id']}/inline",
            {"titulo": "alterado"},
        ),
    }
    before = persisted_state(app)
    monkeypatch.setattr(db.session, "commit", RejectedCommit())
    with caplog.at_level(logging.ERROR):
        response = client_user.post(cases[action][0], json=cases[action][1])
    assert response.status_code == 500
    assert response.get_json()["error"]["code"] == "server"
    assert "credencial-sintetica" not in response.get_data(as_text=True)
    assert persisted_state(app) == before
    failures = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "api_internal_error"
    ]
    assert len(failures) == 1
    assert failures[0].exc_info is not None
    assert failures[0].path == cases[action][0]


def test_global_handler_records_unhandled_cause(
    client_user, monkeypatch, caplog
) -> None:
    monkeypatch.setattr(
        "routes.api.legacy.get_resultados_for_objetivo", FailedCatalogRead()
    )
    with caplog.at_level(logging.ERROR):
        response = client_user.get("/api/resultados/1")
    assert response.status_code == 500
    assert "credencial-sintetica" not in response.get_data(as_text=True)
    failures = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "api_internal_error"
    ]
    assert len(failures) == 1
    assert failures[0].exc_info is not None


def test_domain_validation_remains_422_without_internal_error(
    client_user, seed_data, caplog
) -> None:
    response = client_user.post(
        f"/api/tarefas/{seed_data['task_id']}/comentarios", json={"content": ""}
    )
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "validation"
    assert not [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "api_internal_error"
    ]


class ConnectedCalendar:
    def __call__(self) -> object:
        return object()


class FailedRemoteSync:
    def __call__(self, *_args: object, **_kwargs: object) -> None:
        raise RuntimeError("credencial-sintetica-nao-expor")


class RemoteMeeting:
    google_event_id = "remote-id"
    google_calendar_id = "primary"
    sync_status = "ok"


class MeetingStage:
    meeting = RemoteMeeting()


def test_meeting_service_does_not_return_raw_remote_exception(
    app, monkeypatch, caplog
) -> None:
    from services.etapas_mutation import delete_meeting_etapa

    monkeypatch.setattr(
        "services.etapas_mutation.delete_remote_event", FailedRemoteSync()
    )
    with app.test_request_context("/api/etapas/1/reuniao"), caplog.at_level(
        logging.ERROR
    ):
        warning = delete_meeting_etapa(MeetingStage(), object())
    assert warning
    assert "credencial-sintetica" not in warning
    assert (
        len(
            [
                r
                for r in caplog.records
                if getattr(r, "event", None) == "api_internal_error"
            ]
        )
        == 1
    )


class ExpiredCalendarToken:
    def __call__(self, _connection: object) -> None:
        raise GoogleCalendarError("invalid_grant")


class CalendarDisconnect:
    def __init__(self) -> None:
        self.called = False

    def __call__(self, _connection: object) -> None:
        self.called = True


@pytest.mark.parametrize("commit_fails", [False, True])
def test_expired_token_is_401_only_when_disconnection_is_persisted(
    client_user, monkeypatch, caplog, commit_fails
) -> None:
    disconnect = CalendarDisconnect()
    monkeypatch.setattr(
        "routes.api.calendars._connection_for_current_user", ConnectedCalendar()
    )
    monkeypatch.setattr(
        "routes.api.calendars._sync_events_from_google", ExpiredCalendarToken()
    )
    monkeypatch.setattr("routes.api.calendars._auto_disconnect", disconnect)
    if commit_fails:
        monkeypatch.setattr(db.session, "commit", RejectedCommit())
    with caplog.at_level(logging.ERROR):
        response = client_user.post("/api/calendarios/google/sync")
    assert disconnect.called
    assert response.status_code == (500 if commit_fails else 401)
    assert response.get_json()["error"]["code"] == (
        "server" if commit_fails else "unauthenticated"
    )
    assert len(
        [r for r in caplog.records if getattr(r, "event", None) == "api_internal_error"]
    ) == int(commit_fails)


def test_unexpected_calendar_failure_is_not_exposed(
    client_user, monkeypatch, caplog
) -> None:
    monkeypatch.setattr(
        "routes.api.calendars._connection_for_current_user", ConnectedCalendar()
    )
    monkeypatch.setattr(
        "routes.api.calendars._sync_events_from_google", FailedRemoteSync()
    )
    with caplog.at_level(logging.ERROR):
        response = client_user.post("/api/calendarios/google/sync")
    assert response.status_code == 500
    assert "credencial-sintetica" not in response.get_data(as_text=True)
    assert (
        len(
            [
                r
                for r in caplog.records
                if getattr(r, "event", None) == "api_internal_error"
            ]
        )
        == 1
    )


def test_missing_stage_description_is_known_validation(
    client_user, seed_data, caplog
) -> None:
    response = client_user.post(f"/api/etapas/{seed_data['etapa_id']}", json={})
    assert response.status_code == 422
    assert not [
        r for r in caplog.records if getattr(r, "event", None) == "api_internal_error"
    ]


def test_nonfatal_sync_failure_keeps_local_event_without_exposing_exception(
    client_user, monkeypatch, caplog
) -> None:
    monkeypatch.setattr(
        "routes.api.calendars_events._connection_for_current_user", ConnectedCalendar()
    )
    monkeypatch.setattr(
        "routes.api.calendars_events._cal_helpers._sync_local_event_to_google",
        FailedRemoteSync(),
    )
    with caplog.at_level(logging.ERROR):
        response = client_user.post(
            "/api/calendarios/eventos",
            json={
                "title": "Evento local",
                "starts_at": "2026-09-28T10:00",
                "ends_at": "2026-09-28T11:00",
            },
        )
    assert response.status_code == 200
    assert response.get_json()["data"]["sync_outcome"] == "sync_error"
    assert "credencial-sintetica" not in response.get_data(as_text=True)
    assert (
        len(
            [
                r
                for r in caplog.records
                if getattr(r, "event", None) == "api_internal_error"
            ]
        )
        == 1
    )
