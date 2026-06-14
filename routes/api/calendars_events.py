"""Endpoints JSON dedicados do CRUD de evento de calendário + reuniões Google.

Issue #20 (autorização do usuário): cria ``/api/calendarios/eventos/*`` no
envelope canônico reusando EXATAMENTE os helpers de ``routes/calendars/helpers``
e ``routes/calendars/events`` (parse/sync/guards) — SEM tocar
``oauth``/``webhook``/``sync``. Cobre:

    - ``POST /api/calendarios/eventos``                   — criar evento.
    - ``POST /api/calendarios/eventos/<id>/editar``       — editar evento.
    - ``POST /api/calendarios/eventos/<id>/excluir``      — excluir evento.
    - ``POST /api/calendarios/eventos/<id>/gerar-meet``   — gerar link do Meet.

E as reuniões de etapa (Detalhe do Projeto), reusando ``services.project_meetings``:

    - ``POST /api/projetos/<id>/reunioes``                — criar reunião de etapa.
    - ``POST /api/etapas/<id>/reuniao``                   — editar reunião de etapa.

A falha de SYNC com o Google NÃO é erro HTTP (o evento persiste): devolvemos
``ok`` com ``sync_outcome``/``sync_message``/``warning`` para a SPA exibir o
toast equivalente ao flash legado. NUNCA serializa tokens OAuth.
"""

from __future__ import annotations

from typing import Any

from flask import Response, current_app, g, request
from werkzeug.exceptions import NotFound

from models import CalendarEvent, Etapa, Project, db
from services.calendar_core import parse_event_form
from services.calendar_sync import delete_remote_event
from services.etapas_mutation import delete_meeting_etapa
from services.project_meetings import (
    can_manage_project_meeting,
    create_stage_meeting,
    find_project_meeting_for_calendar_event,
    is_google_meeting_stage,
    update_stage_meeting,
)

from ..blueprint import main_bp
import routes.calendars.helpers as _cal_helpers
from ..calendars.helpers import (
    _connection_for_current_user,
    _delete_project_meeting,
    _get_user_event_or_404,
    _sync_project_meeting_from_calendar_event,
    _user_can_edit_meeting_project,
)
from ..etapas.helpers import _serialize_etapa_payload
from ..orgao_scope import user_can_access_project
from ..shared import get_or_404, log_project_action
from .envelope import fail, fail_internal, ok
from .negotiation import api_login_required
from .serializers import serialize_calendar_event


def _event_payload_from_json() -> tuple[dict[str, Any] | None, Any]:
    """Lê o corpo JSON e adapta para ``parse_event_form`` (form-like).

    ``parse_event_form`` espera ``form.get(...)`` com ``all_day``/
    ``create_conference`` como checkbox-truthy. Convertemos os booleanos JSON
    (``is_all_day``/``create_conference``) para esse formato e devolvemos o dict
    de payload já validado, ou um ``fail`` (422) em corpo/validação inválidos.

    Returns:
        ``(payload, None)`` em sucesso; ``(None, fail_response)`` (422) em erro.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, fail("Corpo JSON inválido.", status=422, code="validation")
    form_like = {
        "title": data.get("title"),
        "description": data.get("description"),
        "location": data.get("location"),
        "starts_at": data.get("starts_at"),
        "ends_at": data.get("ends_at"),
        "all_day": "1" if data.get("is_all_day") else "",
        "create_conference": "1" if data.get("create_conference") else "",
    }
    try:
        return parse_event_form(form_like), None
    except ValueError as exc:
        return None, fail(str(exc), status=422, code="validation")


def _sync_outcome(connection: Any, sync_warning: str | None) -> tuple[str, str]:
    """Deriva ``(sync_outcome, sync_message)`` espelhando os flashes legados.

    - sem conexão       => ("local_only", mensagem de salvar localmente).
    - falha de sync     => ("sync_error", a mensagem de erro).
    - sucesso pleno     => ("synced", mensagem de sincronizado).
    """
    if sync_warning:
        return "sync_error", sync_warning
    if connection is None:
        return (
            "local_only",
            "Evento salvo localmente. Conecte o Google Calendar para sincronizar.",
        )
    return "synced", "Evento salvo e sincronizado com Google Calendar."


# ── CRUD de evento ──────────────────────────────────────────────────────────


@main_bp.route("/api/calendarios/eventos", methods=["POST"])
@api_login_required
def api_calendar_event_create() -> Response | tuple[Response, int]:
    """Cria um evento de calendário (envelope), reusando a lógica de ``create_calendar_event``.

    A falha de sync com o Google NÃO é erro HTTP (o evento persiste): devolve
    ``ok`` com ``sync_outcome='sync_error'``.

    Returns:
        ``ok({event, sync_outcome, sync_message})`` (200); 422 validação; 500 commit.
    """
    payload, error = _event_payload_from_json()
    if error is not None:
        return error

    event = CalendarEvent(
        user_id=g.user.id,
        title=payload["title"],
        description=payload["description"],
        location=payload["location"],
        starts_at=payload["starts_at"],
        ends_at=payload["ends_at"],
        is_all_day=payload["is_all_day"],
        timezone="America/Sao_Paulo",
        source="app",
    )
    db.session.add(event)

    connection = _connection_for_current_user()
    sync_warning = None
    if connection is not None:
        try:
            _cal_helpers._sync_local_event_to_google(
                event, connection, create_conference=payload["create_conference"]
            )
        except Exception as exc:
            event.sync_status = "error"
            event.sync_error = str(exc)
            sync_warning = str(exc)
    else:
        event.sync_status = "pending"
        event.sync_error = (
            "Evento salvo localmente. Conecte o Google Calendar para sincronizar."
        )

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return fail_internal(exc, "salvar evento")

    outcome, message = _sync_outcome(connection, sync_warning)
    return ok(
        {
            "event": serialize_calendar_event(event),
            "sync_outcome": outcome,
            "sync_message": message,
        }
    )


def _guard_linked_meeting(event: CalendarEvent, connection: Any) -> Any | None:
    """Aplica os guards de reunião vinculada (mesma regra do legado).

    Returns:
        ``None`` quando autorizado; um ``fail`` (403 ``forbidden``) caso a conta
        Google ou o acesso ao projeto não permitam a operação.
    """
    linked = find_project_meeting_for_calendar_event(event, connection=connection)
    if linked is None:
        return None
    if not can_manage_project_meeting(connection, linked):
        return fail(
            "Somente quem estiver com a mesma conta Google conectada pode "
            "editar esta reunião.",
            status=403,
            code="forbidden",
        )
    if not _user_can_edit_meeting_project(g.user, linked):
        return fail("Permissão negada.", status=403, code="forbidden")
    return None


def _load_event_or_404(event_id: int) -> tuple[CalendarEvent | None, Any]:
    """Carrega o evento do usuário; converte o ``abort(404)`` legado em ``fail``."""
    try:
        return _get_user_event_or_404(event_id), None
    except NotFound:
        return None, fail("Evento não encontrado.", status=404, code="not_found")


@main_bp.route("/api/calendarios/eventos/<int:event_id>/editar", methods=["POST"])
@api_login_required
def api_calendar_event_edit(event_id: int) -> Response | tuple[Response, int]:
    """Edita um evento (envelope), reusando os guards/sync de ``edit_calendar_event``.

    Returns:
        ``ok({event, sync_outcome, sync_message})`` (200); 403 guards; 404; 422; 500.
    """
    event, load_error = _load_event_or_404(event_id)
    if load_error is not None:
        return load_error
    connection = _connection_for_current_user()

    guard_error = _guard_linked_meeting(event, connection)
    if guard_error is not None:
        return guard_error
    linked_meeting = find_project_meeting_for_calendar_event(
        event, connection=connection
    )

    payload, parse_error = _event_payload_from_json()
    if parse_error is not None:
        return parse_error

    event.title = payload["title"]
    event.description = payload["description"]
    event.location = payload["location"]
    event.starts_at = payload["starts_at"]
    event.ends_at = payload["ends_at"]
    event.is_all_day = payload["is_all_day"]
    event.source = "app"

    sync_warning = None
    if connection is not None:
        try:
            _cal_helpers._sync_local_event_to_google(
                event, connection, create_conference=payload["create_conference"]
            )
        except Exception as exc:
            event.sync_status = "error"
            event.sync_error = str(exc)
            sync_warning = str(exc)
    else:
        event.sync_status = "pending"
        event.sync_error = (
            "Evento editado localmente. Conecte o Google Calendar para sincronizar."
        )

    if linked_meeting is not None:
        _sync_project_meeting_from_calendar_event(
            event, connection=connection, user=g.user
        )

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return fail_internal(exc, "atualizar evento")

    if sync_warning:
        outcome, message = "sync_error", sync_warning
    elif connection is None:
        outcome, message = "local_only", "Evento atualizado localmente."
    else:
        outcome, message = (
            "synced",
            "Evento atualizado e sincronizado com Google Calendar.",
        )
    return ok(
        {
            "event": serialize_calendar_event(event),
            "sync_outcome": outcome,
            "sync_message": message,
        }
    )


@main_bp.route("/api/calendarios/eventos/<int:event_id>/gerar-meet", methods=["POST"])
@api_login_required
def api_calendar_event_generate_meet(
    event_id: int,
) -> Response | tuple[Response, int]:
    """Gera o link do Google Meet (envelope), reusando ``generate_meet_link``.

    Returns:
        ``ok({event})`` com ``meet_link`` preenchido (200); 409 sem conexão; 403
        guards; 404; 502 falha de geração.
    """
    event, load_error = _load_event_or_404(event_id)
    if load_error is not None:
        return load_error
    connection = _connection_for_current_user()
    if connection is None:
        return fail(
            "Conecte o Google Calendar para gerar um link do Meet.",
            status=409,
            code="validation",
        )

    guard_error = _guard_linked_meeting(event, connection)
    if guard_error is not None:
        return guard_error
    linked_meeting = find_project_meeting_for_calendar_event(
        event, connection=connection
    )

    try:
        _cal_helpers._sync_local_event_to_google(
            event, connection, create_conference=True
        )
        if linked_meeting is not None:
            _sync_project_meeting_from_calendar_event(
                event, connection=connection, user=g.user
            )
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return fail_internal(
            exc,
            "gerar link do Meet",
            status=502,
            public_message="Não foi possível gerar o link do Meet. Tente novamente.",
        )

    return ok({"event": serialize_calendar_event(event)})


@main_bp.route("/api/calendarios/eventos/<int:event_id>/excluir", methods=["POST"])
@api_login_required
def api_calendar_event_delete(event_id: int) -> Response | tuple[Response, int]:
    """Exclui um evento (envelope), reusando os guards/remote-delete de ``delete_calendar_event``.

    Reunião vinculada com falha remota ABORTA (502, não exclui local). Evento
    simples com falha remota é removido localmente com ``remote_warning``.

    Returns:
        ``ok({deleted: true, remote_warning?})`` (200); 403 guards; 404; 502 quando
        a reunião vinculada falha no Google; 500 commit.
    """
    event, load_error = _load_event_or_404(event_id)
    if load_error is not None:
        return load_error
    connection = _connection_for_current_user()

    guard_error = _guard_linked_meeting(event, connection)
    if guard_error is not None:
        return guard_error
    linked_meeting = find_project_meeting_for_calendar_event(
        event, connection=connection
    )

    remote_warning = None
    if connection is not None and event.google_event_id:
        try:
            delete_remote_event(
                current_app.config,
                connection,
                google_event_id=event.google_event_id,
                google_calendar_id=event.google_calendar_id,
            )
        except Exception as exc:
            remote_warning = str(exc)

    if linked_meeting is not None:
        if remote_warning:
            return fail(
                "Não foi possível remover a reunião no Google Calendar.",
                status=502,
                code="server",
            )
        _delete_project_meeting(linked_meeting)
    else:
        db.session.delete(event)

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return fail_internal(exc, "excluir evento")

    if remote_warning:
        return ok({"deleted": True, "remote_warning": remote_warning})
    return ok({"deleted": True})


# ── Reuniões de etapa (Detalhe do Projeto) ────────────────────────────────────


def _meeting_response(
    etapa: Etapa, connection: Any, sync_warning: str | None, *, message: str
):
    """Monta o envelope de sucesso de criar/editar reunião (etapa + warning)."""
    return ok(
        {
            "etapa": _serialize_etapa_payload(etapa, connection=connection),
            "warning": sync_warning,
            "message": message,
        }
    )


@main_bp.route("/api/projetos/<int:project_id>/reunioes", methods=["POST"])
@api_login_required
def api_project_meeting_create(
    project_id: int,
) -> Response | tuple[Response, int]:
    """Cria uma reunião Google de etapa (envelope), reusando ``create_stage_meeting``.

    Mesmas validações de ``add_project_meeting``: permissão de edição (403),
    conexão Google ativa (400), parse do evento (422). A falha de sync devolve
    ``warning`` (o evento/etapa persistem).

    Returns:
        ``ok({etapa, warning, message})`` (200); 403/400/422; 404 projeto; 500.
    """
    project = db.session.get(Project, project_id)
    if project is None:
        return fail("Projeto não encontrado.", status=404, code="not_found")
    if not user_can_access_project(g.user, project):
        return fail(
            "Você não tem permissão para adicionar reuniões a este projeto.",
            status=403,
            code="forbidden",
        )

    connection = _connection_for_current_user()
    if connection is None or not (connection.google_account_id or "").strip():
        return fail(
            "Conecte novamente sua conta Google antes de adicionar reuniões ao "
            "projeto.",
            status=400,
            code="validation",
        )

    payload, parse_error = _event_payload_from_json()
    if parse_error is not None:
        return parse_error

    etapa, sync_warning = create_stage_meeting(
        current_app.config, project, connection, payload, actor_user_id=g.user.id
    )

    try:
        log_project_action(
            project_id=project.id,
            action_type="add_google_meeting",
            description=f'Adicionou a reunião "{etapa.descricao}"',
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        return fail("Erro ao adicionar reunião ao projeto.", status=500, code="server")

    message = "Reunião adicionada ao projeto com sucesso!"
    if sync_warning:
        message = (
            "Reunião adicionada ao projeto, mas houve falha na sincronização com "
            "o Google Calendar."
        )
    return _meeting_response(etapa, connection, sync_warning, message=message)


@main_bp.route("/api/etapas/<int:etapa_id>/reuniao", methods=["POST"])
@api_login_required
def api_project_meeting_edit(etapa_id: int) -> Response | tuple[Response, int]:
    """Edita uma reunião Google de etapa (envelope), reusando ``update_stage_meeting``.

    Mesmas validações de ``edit_project_meeting``: a etapa precisa ser reunião
    editável (400), a conta Google precisa ser a dona (403), reunião em erro de
    sync é somente-leitura (409) e o parse do evento (422).

    Returns:
        ``ok({etapa, warning, message})`` (200); 400/403/409/422; 404 etapa; 500.
    """
    etapa = db.session.get(Etapa, etapa_id)
    if etapa is None:
        return fail("Etapa não encontrada.", status=404, code="not_found")
    project = etapa.project
    if not user_can_access_project(g.user, project):
        return fail(
            "Você não tem permissão para editar esta reunião.",
            status=403,
            code="forbidden",
        )

    if not is_google_meeting_stage(etapa) or etapa.meeting is None:
        return fail(
            "Esta etapa não é uma reunião Google editável.",
            status=400,
            code="validation",
        )

    meeting = etapa.meeting
    connection = _connection_for_current_user()
    if not can_manage_project_meeting(connection, meeting):
        return fail(
            "Somente quem estiver com a mesma conta Google conectada pode editar "
            "esta reunião.",
            status=403,
            code="forbidden",
        )
    if meeting.sync_status == "error":
        return fail(
            "Esta reunião está somente leitura porque o evento não está mais "
            "disponível no Google Calendar.",
            status=409,
            code="validation",
        )

    payload, parse_error = _event_payload_from_json()
    if parse_error is not None:
        return parse_error

    etapa, sync_warning = update_stage_meeting(
        current_app.config, etapa, connection, payload
    )

    try:
        log_project_action(
            project_id=project.id,
            action_type="edit_google_meeting",
            description=f'Editou a reunião "{etapa.descricao}"',
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        return fail("Erro ao salvar a reunião.", status=500, code="server")

    message = "Reunião atualizada com sucesso!"
    if sync_warning:
        message = (
            "Reunião atualizada, mas houve falha na sincronização com o Google "
            "Calendar."
        )
    return _meeting_response(etapa, connection, sync_warning, message=message)


@main_bp.route("/api/etapas/<int:etapa_id>/reuniao/excluir", methods=["POST"])
@api_login_required
def api_project_meeting_delete(etapa_id: int) -> Response | tuple[Response, int]:
    """Exclui uma reunião Google de etapa (envelope), reusando ``delete_meeting_etapa``.

    Mesmos guards/efeitos de ``delete_etapa`` para reuniões (routes/etapas/
    crud.py): só a conta Google dona pode excluir (403); a falha remota ABORTA
    (502, não exclui). Em sucesso remove a etapa-reunião e devolve o total de
    etapas para a página recalcular o botão "Concluir". NÃO serializa tokens.

    Returns:
        ``ok({deleted_id, project_id, total_etapas, message})`` (200); 403/404/422;
        502 quando a remoção remota falha; 500 commit.
    """
    etapa = db.session.get(Etapa, etapa_id)
    if etapa is None:
        return fail("Etapa não encontrada.", status=404, code="not_found")
    project = etapa.project
    if not user_can_access_project(g.user, project):
        return fail(
            "Você não tem permissão para excluir esta reunião.",
            status=403,
            code="forbidden",
        )
    if not is_google_meeting_stage(etapa) or etapa.meeting is None:
        return fail(
            "Esta etapa não é uma reunião Google.", status=422, code="validation"
        )

    connection = _connection_for_current_user()
    if not can_manage_project_meeting(connection, etapa.meeting):
        return fail(
            "Somente quem estiver com a mesma conta Google conectada pode excluir "
            "esta reunião.",
            status=403,
            code="forbidden",
        )

    project_id = etapa.project_id
    try:
        remote_warning = delete_meeting_etapa(etapa, connection)
        if remote_warning:
            db.session.rollback()
            return fail(remote_warning, status=502, code="server")
        db.session.commit()
    except Exception:
        db.session.rollback()
        return fail("Erro ao excluir reunião.", status=500, code="server")

    project = db.session.get(Project, project_id)
    total = project.total_workflow_etapas if project is not None else 0
    return ok(
        {
            "deleted_id": etapa_id,
            "project_id": project_id,
            "total_etapas": total,
            "message": "Reunião excluída com sucesso.",
        }
    )
