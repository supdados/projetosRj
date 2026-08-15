"""Endpoints JSON de MUTAÇÃO do Hub de Tarefas consumidos pela SPA.

Cobre as ações de paridade que faltavam no envelope canônico:

    - ``POST   /api/tarefas``                       — cria tarefa (composer/quick-add).
    - ``POST   /api/tarefas/<id>/excluir``          — exclui tarefa (card/drawer/modal).
    - ``POST   /api/tarefas/arquivar-finalizadas``  — arquiva finalizadas em lote.
    - ``POST   /api/tarefas/<id>/mover-etapa``      — move tarefa de etapa (DnD).
    - ``GET    /api/tarefas/sugestoes-responsavel`` — picker de responsável do hub.

REUSO PARCIAL: exclusão, arquivamento em lote e mover-etapa chamam as MESMAS
funções das rotas Jinja legadas (``_can_manage_task_restricted_actions``,
``move_task_to_etapa``, ``bulk_archive_finalized``, ``notify_*``) — só trocam a
embalagem de resposta para o envelope ``ok``/``fail``. A criação (``POST
/api/tarefas``) tem corpo próprio e usa os helpers de validação de
``routes/tasks/creation.py`` (o legado ``_create_task_common`` morreu com
``routes/tasks/crud.py`` na sprint 2).

Anexa ao ``main_bp`` ÚNICO; NÃO cria blueprint novo e NÃO altera os legados.
"""

from __future__ import annotations

from typing import Any

from flask import Response, g, request

from models import OrgaoUnidade, Task, db

from ..blueprint import main_bp
from ..orgao_scope import sanitize_orgao_filter_for_current_user
from ..tasks.constants import VALID_PRIORIDADES, VALID_STATUSES, VALID_TIPOS
from ..tasks.creation import (
    _format_invalid_responsavel_message,
    _get_assignable_users_for_orgao,
    _get_assignable_users_for_project,
    _resolve_etapa_token,
    _resolve_project_token,
    _serialize_task_payload,
    _validate_task_responsavel,
)
from ..tasks.notifications import (
    notify_task_archived_in_batch,
    notify_task_deleted,
)
from ..tasks.permissions import (
    _audit_denied_task_action,
    _can_edit_task,
    _can_manage_task_restricted_actions,
    api_task_denial,
)
from ..tasks.queries import _build_visible_tasks_query, _read_task_filter_values
from .envelope import fail, fail_internal, ok
from .negotiation import api_login_required
from .serializers import serialize_task_card
from services.notifications import notify_task_assignment_change, notify_task_event
from services.task_mutation import bulk_archive_finalized, move_task_to_etapa

#: String herdada do legado ``delete_task`` (rota cortada na sprint 2).
DELETE_DENIED_MESSAGE = "Somente o autor da tarefa ou um administrador pode excluí-la."


def _load_task_or_error(
    task_id: int, *, for_write: bool = False
) -> tuple[Task | None, Any]:
    """Carrega a tarefa aplicando o contrato S5 (404 invisível, 403 rank baixo).

    ``for_write=True`` exige rank >= editor (mutação); o padrão exige rank >=
    leitor. Tarefa avulsa segue restrita ao criador (ou admin) nos dois modos.
    Decisão única em ``api_task_denial`` — tarefa inexistente e tarefa invisível
    respondem o MESMO 404 (anti-enumeração F4-2b).
    """
    task = db.session.get(Task, task_id)
    denied = api_task_denial(task, for_write=for_write)
    if denied is not None:
        return None, denied
    return task, None


@main_bp.route("/api/tarefas", methods=["POST"])
@api_login_required
def api_tarefa_criar() -> Response | tuple[Response, int]:
    """Cria uma tarefa (envelope) com corpo próprio.

    Usa os helpers de validação de ``routes/tasks/creation.py``
    (``_resolve_project_token``, ``_resolve_etapa_token``,
    ``_validate_task_responsavel``); a extração para service fica na sprint 3.2.

    Body JSON: ``{project, etapa, descricao, status, responsavel, prioridade,
    tipo_pedido}`` (``project_id``/``etapa_id`` aceitos como alias). Valida
    projeto/etapa/descrição/responsável com as regras legadas. Em sucesso devolve
    o card serializado (mesma forma do drawer/board) para inserção otimista.

    Returns:
        ``ok({task})`` (200); 422 validação (sem descrição/ responsável inválido);
        403/404 de projeto/etapa fora de escopo; 401 sem sessão.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return fail("Corpo JSON inválido.", status=422, code="validation")

    project_raw = data.get("project")
    if project_raw is None:
        project_raw = data.get("project_id")
    etapa_raw = data.get("etapa")
    if etapa_raw is None:
        etapa_raw = data.get("etapa_id")
    descricao = (data.get("descricao") or data.get("titulo") or "").strip()

    project, project_error, status_code = _resolve_project_token(
        project_raw, allow_empty=True, for_write=True
    )
    if project_error:
        code = (
            "forbidden"
            if status_code == 403
            else ("not_found" if status_code == 404 else "validation")
        )
        return fail(project_error, status=status_code, code=code)

    etapa, etapa_error, etapa_status = _resolve_etapa_token(
        etapa_raw, project, allow_empty=True
    )
    if etapa_error:
        code = "not_found" if etapa_status == 404 else "validation"
        return fail(etapa_error, status=etapa_status, code=code)

    if not descricao:
        return fail("Descrição é obrigatória.", status=422, code="validation")

    status = (data.get("status") or "nao_iniciada").strip()
    if status not in VALID_STATUSES:
        status = "nao_iniciada"
    prioridade = (data.get("prioridade") or "").strip() or None
    if prioridade not in VALID_PRIORIDADES:
        prioridade = None
    tipo_pedido = (data.get("tipo_pedido") or "").strip() or None
    if tipo_pedido not in VALID_TIPOS:
        tipo_pedido = None

    raw_assignee_ids = data.get("assignee_ids")
    assignee_ids: list[int] = []
    if isinstance(raw_assignee_ids, list):
        for value in raw_assignee_ids:
            try:
                assignee_ids.append(int(value))
            except (TypeError, ValueError):
                continue

    is_valid, canonical_responsavel, invalid_names = _validate_task_responsavel(
        project, (data.get("responsavel") or "").strip()
    )
    if not is_valid:
        return fail(
            _format_invalid_responsavel_message(invalid_names),
            status=422,
            code="validation",
        )

    try:
        max_ordem = (
            db.session.query(db.func.max(Task.ordem))
            .filter(
                Task.project_id == (project.id if project else None),
                Task.is_archived.is_(False),
            )
            .scalar()
            or 0
        )
        task = Task(
            descricao=descricao,
            status=status,
            responsavel=canonical_responsavel or None,
            prioridade=prioridade,
            tipo_pedido=tipo_pedido,
            project_id=project.id if project else None,
            etapa_id=etapa.id if etapa else None,
            created_by_id=g.user.id,
            ordem=max_ordem + 1,
        )
        db.session.add(task)
        db.session.flush()

        from ..tasks.constants import _preview_text, _task_status_label
        from ..tasks.notifications import notify_assignee_change
        from ..tasks.queries import set_task_assignees

        # Responsáveis múltiplos do quick-add: valida contra os candidatos com
        # acesso ao projeto e notifica os adicionados (abaixo, antes do commit).
        allowed_assignee_ids = {
            user.id for user in _get_assignable_users_for_project(project)
        }
        desired_assignees = [uid for uid in assignee_ids if uid in allowed_assignee_ids]
        added_assignees, removed_assignees = set_task_assignees(task, desired_assignees)

        notify_task_event(
            task,
            actor_user_id=g.user.id,
            event_type="task_created",
            title="Nova tarefa",
            message=(
                f'{g.user.name} criou a tarefa "{_preview_text(task.descricao, 90)}" '
                f"com status {_task_status_label(task.status)}."
            ),
        )
        if task.responsavel:
            notify_task_assignment_change(
                task,
                task,
                g.user.id,
                old_responsavel=None,
                new_responsavel=task.responsavel,
            )
        notify_assignee_change(task, added_assignees, removed_assignees)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return fail_internal(exc, "adicionar tarefa")

    return ok(_stage_card_payload(task))


def _stage_card_payload(task: Task) -> dict[str, Any]:
    """Card canônico + campos legados (``_serialize_task_payload``) num só payload.

    O composer/quick-add precisa do card (``serialize_task_card`` — base da board
    store) e dos campos extras de contexto de projeto/etapa que o
    ``_serialize_task_payload`` legado expõe; mesclamos ambos para o front
    reconciliar sem duas chamadas.
    """
    card = serialize_task_card(task)
    legacy = _serialize_task_payload(task)
    card.update(
        {
            "etapa_descricao": legacy["etapa_descricao"],
            "project_titulo": legacy["project_titulo"],
            "project_orgao_sigla": legacy["project_orgao_sigla"],
            "comments_count": legacy["comments_count"],
            "anexos_count": legacy["anexos_count"],
        }
    )
    card["permissions"]["can_delete"] = legacy["can_delete"]
    card["permissions"]["is_author"] = legacy["is_author"]
    return {"task": card}


@main_bp.route("/api/tarefas/<int:task_id>/excluir", methods=["POST"])
@api_login_required
def api_tarefa_excluir(task_id: int) -> Response | tuple[Response, int]:
    """Exclui uma tarefa (envelope), reusando o guard e ``notify_task_deleted``.

    Replica ``delete_task``: só autor/admin pode excluir
    (``_can_manage_task_restricted_actions`` -> 403 ``DELETE_DENIED_MESSAGE``).
    Em sucesso devolve ``{item_id}`` para o front remover o card/row.

    Returns:
        ``ok({item_id, message})`` (200); 404 inexistente; 403 sem permissão; 401.
    """
    task, error = _load_task_or_error(task_id, for_write=True)
    if error is not None:
        return error

    if not _can_manage_task_restricted_actions(g.user, task):
        _audit_denied_task_action(task, "forbidden_delete")
        return fail(DELETE_DENIED_MESSAGE, status=403, code="forbidden")

    try:
        notify_task_deleted(task)
        db.session.delete(task)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return fail_internal(exc, "excluir tarefa")

    return ok({"item_id": task_id, "message": "Tarefa excluída com sucesso!"})


@main_bp.route("/api/tarefas/<int:task_id>/mover-etapa", methods=["POST"])
@api_login_required
def api_tarefa_mover_etapa(task_id: int) -> Response | tuple[Response, int]:
    """Move uma tarefa para outra etapa (ou desassocia), reusando ``move_task_to_etapa``.

    Replica ``move_task_etapa``: a etapa deve pertencer ao MESMO projeto da
    tarefa (``_resolve_etapa_token`` com ``allow_done=True``); ``"sem_etapa"``
    desassocia. Quando a etapa de destino está concluída, devolve ``warning``
    (paridade com o legado, que o expõe mas o JS atual ignora).

    Body JSON: ``{etapa_id}`` (alias ``etapa``; ``"sem_etapa"`` desassocia).

    Returns:
        ``ok({task_id, etapa_id, previous_etapa_id, warning?})`` (200); 404/403/422.
    """
    task, error = _load_task_or_error(task_id, for_write=True)
    if error is not None:
        return error

    data = request.get_json(silent=True) or {}
    etapa_raw = data.get("etapa")
    if etapa_raw is None:
        etapa_raw = data.get("etapa_id")

    etapa, etapa_error, etapa_status = _resolve_etapa_token(
        etapa_raw, task.project, allow_empty=True, allow_done=True
    )
    if etapa_error:
        code = "not_found" if etapa_status == 404 else "validation"
        return fail(etapa_error, status=etapa_status, code=code)

    previous_etapa_id = move_task_to_etapa(task, etapa)
    warning = None
    if etapa is not None and etapa.done:
        warning = "A etapa está concluída; a tarefa foi movida mesmo assim."

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return fail_internal(exc, "mover tarefa")

    payload = {
        "task_id": task.id,
        "etapa_id": task.etapa_id,
        "previous_etapa_id": previous_etapa_id,
    }
    if warning:
        payload["warning"] = warning
    return ok(payload)


@main_bp.route("/api/tarefas/arquivar-finalizadas", methods=["POST"])
@api_login_required
def api_tarefas_arquivar_finalizadas() -> Response | tuple[Response, int]:
    """Arquiva em lote as tarefas finalizadas do escopo dos filtros (envelope).

    Replica ``archive_finalized_tasks``: monta a query de tarefas visíveis,
    não-arquivadas, ``status == "finalizada"`` no escopo dos filtros do corpo
    (``project``/``orgao``/``prioridade``/``tipo``/``status``/``responsavel``),
    restringe a autor/admin (``_can_manage_task_restricted_actions`` — MESMO
    guard do arquivar individual; auditoria 2.6) e arquiva via
    ``bulk_archive_finalized``, disparando ``notify_task_archived_in_batch``.
    Tarefas alheias no escopo ficam intactas (não é erro do lote). Filtro de
    órgão fora do escopo => 422 (padrão do ``/api/tarefas``).

    Returns:
        ``ok({archived_count, archived_task_ids, message})`` (200); 422 órgão; 401.
    """
    data = request.get_json(silent=True) or {}
    filter_values = _read_task_filter_values(data)

    orgao_filter_raw = filter_values["orgao_filter"]
    orgao_filter_id = None
    if orgao_filter_raw:
        orgao_filter_id, invalid = sanitize_orgao_filter_for_current_user(
            orgao_filter_raw
        )
        if invalid:
            return fail(
                "Filtro de órgão inválido para o usuário.",
                status=422,
                code="validation",
            )

    finalized_tasks = (
        _build_visible_tasks_query(
            include_archived=False,
            orgao_filter_id=orgao_filter_id,
            project_filter=filter_values["project_filter"],
            prioridade_filter=filter_values["prioridade_filter"],
            tipo_filter=filter_values["tipo_filter"],
            status_filter=filter_values["status_filter"],
            responsavel_filter=filter_values["responsavel_filter"],
            include_relations=False,
        )
        .filter(Task.status == "finalizada")
        .all()
    )
    # lote arquiva só as tarefas em que o usuário é autor/admin (auditoria 2.6);
    # as demais ficam intactas, sem erro (não é falha do lote).
    finalized_tasks = [
        task
        for task in finalized_tasks
        if _can_manage_task_restricted_actions(g.user, task)
        and _can_edit_task(g.user, task)
    ]

    try:
        archived_ids = bulk_archive_finalized(finalized_tasks)
        for task in finalized_tasks:
            notify_task_archived_in_batch(task)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return fail_internal(exc, "arquivar tarefas")

    archived_count = len(archived_ids)
    message = (
        f"{archived_count} tarefa(s) arquivada(s)."
        if archived_count
        else "Nenhuma tarefa finalizada para arquivar no escopo atual."
    )
    return ok(
        {
            "archived_count": archived_count,
            "archived_task_ids": [str(tid) for tid in archived_ids],
            "message": message,
        }
    )


@main_bp.route("/api/tarefas/sugestoes-responsavel", methods=["GET"])
@api_login_required
def api_hub_sugestoes_responsavel() -> Response | tuple[Response, int]:
    """Sugestões de responsável do hub por projeto OU órgão (envelope).

    Espelho enveloped de ``get_hub_assignable_users``: aceita ``?project=`` ou
    ``?orgao=``/``?area=`` (sigla ou id) e ``?q=`` para filtrar por nome. Reusa
    ``_get_assignable_users_for_project``/``_get_assignable_users_for_orgao``.

    Returns:
        ``ok({users: [{id, name}]})`` (200); 400/403/404 de projeto/órgão; 401.
    """
    project_raw = (request.args.get("project") or "").strip()
    orgao_raw = (request.args.get("orgao") or request.args.get("area") or "").strip()

    if project_raw:
        project, project_error, status_code = _resolve_project_token(
            project_raw, allow_empty=False
        )
        if project_error:
            code = (
                "forbidden"
                if status_code == 403
                else ("not_found" if status_code == 404 else "validation")
            )
            return fail(project_error, status=status_code, code=code)
        users = _get_assignable_users_for_project(project)
    elif orgao_raw:
        resolved_orgao_raw = orgao_raw
        if not orgao_raw.isdigit():
            orgao = OrgaoUnidade.query.filter(
                db.func.lower(OrgaoUnidade.sigla) == orgao_raw.lower()
            ).first()
            if not orgao:
                return fail("Órgão inválido.", status=400, code="validation")
            resolved_orgao_raw = str(orgao.id)
        orgao_id, invalid = sanitize_orgao_filter_for_current_user(resolved_orgao_raw)
        if invalid:
            return fail("Sem permissão para este órgão.", status=403, code="forbidden")
        users = _get_assignable_users_for_orgao(orgao_id)
    else:
        return fail("Informe um projeto ou órgão.", status=400, code="validation")

    from routes.tasks.queries import serialize_assignee

    query = (request.args.get("q") or "").strip().lower()
    options = [serialize_assignee(user) for user in users]
    if query:
        options = [u for u in options if query in (u["name"] or "").lower()]
    return ok({"users": options})
