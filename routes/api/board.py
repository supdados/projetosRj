"""Endpoints JSON do Kanban de Tarefas (Fase 5b-1) consumidos pela SPA SvelteKit.

O Kanban exibe as tarefas ATIVAS (não arquivadas) do Hub distribuídas em 5
COLUNAS por status, na ordem canônica ``TASK_STATUS_ORDER``
(``routes/tasks/constants.py``):

    nao_iniciada · em_andamento · para_validacao · para_ajustes · finalizada

Três endpoints, todos no envelope canônico, protegidos por ``api_login_required``
(401 JSON) e com escopo de órgão server-side (reaproveitando a MESMA query de
tarefas visíveis do Hub, ``_build_visible_tasks_query``):

    - ``GET  /api/tarefas/board``                — colunas + cards (read-only + DnD).
    - ``POST /api/tarefas/<id>/status``          — muda o status de UMA tarefa
      (drop entre colunas). A transição é AUTORITATIVA no servidor: reusa
      ``_can_transition_task_to_status`` (a MESMA regra da rota Jinja legada
      ``update_task_status``), respondendo 403 ``forbidden`` com
      ``FINALIZE_DENIED_MESSAGE`` quando finalizar sem permissão.
    - ``POST /api/tarefas/board/reordenar``      — persiste a nova ordem dos cards
      (dentro/entre colunas) e, quando o payload traz ``moved_task_id``, aplica a
      mudança de status SÓ a esse card — sujeita à mesma validação de transição.

ADITIVO: anexa ao ``main_bp`` ÚNICO (``routes/blueprint.py``); NÃO cria blueprint
novo, NÃO altera as rotas Jinja/JSON legadas (``update_task_status``,
``reorder_tasks_hub``, ``mover-etapa`` em ``routes/tasks/crud.py``) nem o JS
legado — elas coexistem (strangler). O estado canônico vive na store Svelte; o
backend é a fonte de verdade para a validação de transição.
"""

from __future__ import annotations

from typing import Any

from flask import Response, g, request
from sqlalchemy.orm import joinedload, selectinload

from models import Task, db

from ..blueprint import main_bp
from ..orgao_scope import sanitize_orgao_filter_for_current_user
from ..tasks.constants import (
    TASK_STATUS_ORDER,
    VALID_STATUSES,
    _task_status_label,
    task_priority_sort_rank,
)
from ..tasks.notifications import notify_status_change
from ..tasks.permissions import (
    FINALIZE_DENIED_MESSAGE,
    _audit_denied_task_action,
    _can_edit_task,
    _can_transition_task_to_status,
)
from ..tasks.queries import _build_visible_tasks_query, _read_task_filter_values
from .envelope import fail, ok
from .negotiation import api_login_required
from .serializers import serialize_task_card


def _load_active_board_tasks(filter_values: dict[str, str], orgao_id: int | None):
    """Carrega as tarefas ATIVAS (não arquivadas) visíveis para o Kanban.

    Reaproveita ``_build_visible_tasks_query`` — a MESMA fonte de verdade do Hub
    Jinja e de ``GET /api/tarefas`` —, garantindo escopo de órgão server-side e os
    mesmos filtros (projeto/órgão/prioridade/tipo/responsável/status). O Kanban
    nunca lista arquivadas: ``include_archived=False`` é fixo.

    Args:
        filter_values: Saída de ``_read_task_filter_values`` (project/prioridade/
            tipo/status/responsável já normalizados).
        orgao_id: ID de órgão já validado para o usuário (ou ``None`` => todos).

    Returns:
        Lista de ``Task`` ativas, ordenadas pela ordem natural do Hub.
    """
    return _build_visible_tasks_query(
        include_archived=False,
        project_filter=filter_values["project_filter"],
        prioridade_filter=filter_values["prioridade_filter"],
        tipo_filter=filter_values["tipo_filter"],
        status_filter=filter_values["status_filter"],
        responsavel_filter=filter_values["responsavel_filter"],
        orgao_filter_id=orgao_id,
    ).all()


def _sort_cards_by_priority(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ordena cards serializados por prioridade (urgente → alta → media → baixa).

    O board já é agrupado por status (uma coluna por status), então dentro de
    cada coluna a ordenação é só por prioridade. ``sorted`` é estável: cards de
    mesma prioridade preservam a ordem de entrada — que é a ordem manual
    (``Task.ordem``) vinda do banco / do drag-and-drop.
    """
    return sorted(cards, key=lambda card: task_priority_sort_rank(card["prioridade"]))


def _group_tasks_into_columns(tasks: list[Any]) -> list[dict[str, Any]]:
    """Agrupa as tarefas nas 5 colunas por status, na ordem ``TASK_STATUS_ORDER``.

    Sempre devolve as 5 colunas (mesmo vazias), para que o cliente monte o board
    sem precisar conhecer a lista de status. Cada tarefa é serializada com
    ``serialize_task_card`` (que já inclui ``permissions.can_finalize``). Dentro
    de cada coluna os cards são ordenados por prioridade (urgente primeiro), com
    a ordem manual (``Task.ordem``, já refletida em ``tasks``) como desempate via
    sort estável.

    Args:
        tasks: Tarefas ativas (de ``_load_active_board_tasks``).

    Returns:
        Lista de ``{status, label, tasks: [card]}`` na ordem canônica.
    """
    by_status: dict[str, list[dict[str, Any]]] = {
        status: [] for status in TASK_STATUS_ORDER
    }
    for task in tasks:
        # Status fora do conjunto canônico (dado legado) cai na primeira coluna,
        # para não sumir silenciosamente do board.
        bucket = task.status if task.status in by_status else TASK_STATUS_ORDER[0]
        by_status[bucket].append(serialize_task_card(task))
    return [
        {
            "status": status,
            "label": _task_status_label(status),
            "tasks": _sort_cards_by_priority(by_status[status]),
        }
        for status in TASK_STATUS_ORDER
    ]


def _load_task_for_mutation(task_id: int) -> tuple[Task | None, Any]:
    """Carrega a tarefa validando existência (404) e rank de escrita (403).

    Espelha o guard das rotas Jinja de mutação de tarefa (``_can_edit_task``,
    rank >= editor; tarefa avulsa segue restrita ao criador/admin), porém
    devolve o envelope canônico em vez de ``jsonify(success=...)``.

    Args:
        task_id: ID da tarefa.

    Returns:
        ``(task, None)`` quando autorizado; ``(None, fail_response)`` com 404/403
        canônico caso contrário.
    """
    task = db.session.get(Task, task_id)
    if task is None:
        return None, fail("Tarefa não encontrada.", status=404, code="not_found")
    if not _can_edit_task(g.user, task):
        return None, fail(
            "Você não tem permissão para acessar esta tarefa.",
            status=403,
            code="forbidden",
        )
    return task, None


def _apply_status_transition(task: Task, new_status: str) -> Any | None:
    """Aplica a mudança de status de ``task`` validando a transição (autoritativo).

    NÃO duplica a regra de negócio: reusa ``_can_transition_task_to_status`` — a
    MESMA usada pela rota Jinja legada ``update_task_status`` —, audita a tentativa
    negada (``_audit_denied_task_action``) e dispara ``notify_status_change``
    quando o status efetivamente muda. NÃO faz commit (o caller decide quando
    persistir, para agrupar reordenação + status numa transação só).

    Args:
        task: Tarefa carregada e já validada para escrita (rank >= editor).
        new_status: Status alvo (deve estar em ``VALID_STATUSES``).

    Returns:
        ``None`` em caso de sucesso (status aplicado em memória); ou um
        ``fail(...)`` (403 ``forbidden``) quando a transição é negada.
    """
    if not _can_transition_task_to_status(
        g.user, task, new_status, previous_status=task.status
    ):
        _audit_denied_task_action(
            task, "forbidden_finalize", attempted_status=new_status
        )
        return fail(FINALIZE_DENIED_MESSAGE, status=403, code="forbidden")

    old_status = task.status
    if old_status != new_status:
        task.status = new_status
        notify_status_change(task, old_status)
    return None


@main_bp.route("/api/tarefas/board", methods=["GET"])
@api_login_required
def api_tarefas_board() -> Response | tuple[Response, int]:
    """Retorna o Kanban de Tarefas (5 colunas por status) no envelope canônico.

    Reaproveita ``_build_visible_tasks_query`` (a MESMA fonte do Hub Jinja e de
    ``GET /api/tarefas``) com ``include_archived=False`` — o Kanban só lista
    tarefas ativas. Respeita o escopo de órgão server-side; ``?orgao=`` inválido
    (fora do escopo) => 422 ``validation``. Suporta os mesmos filtros do Hub:
    ``?project=``, ``?orgao=``, ``?prioridade=``, ``?tipo=``, ``?responsavel=``,
    ``?status=``. Cada card inclui ``permissions.can_finalize`` (UX-only).

    Returns:
        Envelope ``{"ok": true, "data": {"columns": [...], "filters": {...},
        "total": int}}`` (200); ou ``fail(..., 422, "validation")`` quando o
        filtro de órgão é inválido. 401 JSON sem sessão (``api_login_required``).
    """
    filter_values = _read_task_filter_values(request.args)
    selected_orgao_id, invalid_orgao_filter = sanitize_orgao_filter_for_current_user(
        filter_values["orgao_filter"]
    )
    if invalid_orgao_filter:
        return fail(
            "Filtro de órgão inválido para o usuário.",
            status=422,
            code="validation",
        )

    tasks = _load_active_board_tasks(filter_values, selected_orgao_id)
    columns = _group_tasks_into_columns(tasks)
    return ok(
        {
            "columns": columns,
            "filters": {
                "project": filter_values["project_filter"],
                "prioridade": filter_values["prioridade_filter"],
                "tipo": filter_values["tipo_filter"],
                "status": filter_values["status_filter"],
                "responsavel": filter_values["responsavel_filter"],
                "selected_orgao": selected_orgao_id,
            },
            "total": len(tasks),
        }
    )


@main_bp.route("/api/tarefas/<int:task_id>/status", methods=["POST"])
@api_login_required
def api_tarefa_status(task_id: int) -> Response | tuple[Response, int]:
    """Muda o status de UMA tarefa (drop entre colunas do Kanban).

    AUTORITATIVO: reusa ``_can_transition_task_to_status`` (a MESMA regra da rota
    Jinja legada ``update_task_status``), sem duplicar a lógica. Validações:
    404 (tarefa inexistente), 403 ``forbidden`` (sem rank de escrita OU
    finalizar sem permissão, com ``FINALIZE_DENIED_MESSAGE``), 422 ``validation``
    (status ausente/ inválido). Em sucesso devolve o card atualizado — o cliente
    deve confirmar o move com esta resposta e reverter (rollback) se vier erro.

    Body JSON: ``{"status": "<um de VALID_STATUSES>"}``.

    Args:
        task_id: ID da tarefa.

    Returns:
        Envelope ``{"ok": true, "data": {"task": {...}}}`` (200); 404/403/422
        canônicos; 401 JSON sem sessão.
    """
    task, error = _load_task_for_mutation(task_id)
    if error is not None:
        return error

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return fail("Corpo JSON inválido.", status=422, code="validation")
    new_status = (payload.get("status") or "").strip()
    if new_status not in VALID_STATUSES:
        return fail("Status inválido.", status=422, code="validation")

    transition_error = _apply_status_transition(task, new_status)
    if transition_error is not None:
        return transition_error

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return fail(
            "Erro ao atualizar status da tarefa.", status=422, code="validation"
        )

    return ok({"task": serialize_task_card(task)})


def _parse_reorder_columns(payload: Any) -> tuple[list[dict[str, Any]] | None, Any]:
    """Valida e normaliza o corpo de ``/api/tarefas/board/reordenar``.

    Espera ``{"columns": [{"status": <str>, "task_ids": [<int>, ...]}, ...]}``.
    Cada ``status`` deve estar em ``VALID_STATUSES`` e os ``task_ids`` precisam ser
    inteiros. O estado canônico vive na store do cliente, mas o backend valida e
    reconstrói a ordem a partir desta carga.

    Args:
        payload: Corpo JSON cru da requisição.

    Returns:
        ``(columns, None)`` normalizado; ou ``(None, fail_response)`` (422) quando
        o formato é inválido.
    """
    if not isinstance(payload, dict):
        return None, fail("Corpo JSON inválido.", status=422, code="validation")
    raw_columns = payload.get("columns")
    if not isinstance(raw_columns, list):
        return None, fail(
            "Campo 'columns' obrigatório (lista).", status=422, code="validation"
        )

    normalized: list[dict[str, Any]] = []
    for raw_column in raw_columns:
        if not isinstance(raw_column, dict):
            return None, fail("Coluna inválida.", status=422, code="validation")
        status = (raw_column.get("status") or "").strip()
        if status not in VALID_STATUSES:
            return None, fail(
                f"Status de coluna inválido: {status!r}.",
                status=422,
                code="validation",
            )
        raw_ids = raw_column.get("task_ids")
        if not isinstance(raw_ids, list):
            return None, fail(
                "Campo 'task_ids' obrigatório (lista).", status=422, code="validation"
            )
        task_ids: list[int] = []
        for raw_id in raw_ids:
            try:
                task_ids.append(int(raw_id))
            except (TypeError, ValueError):
                return None, fail(
                    f"ID de tarefa inválido: {raw_id!r}.",
                    status=422,
                    code="validation",
                )
        normalized.append({"status": status, "task_ids": task_ids})
    return normalized, None


def _parse_moved_task_id(
    payload: dict[str, Any], columns: list[dict[str, Any]]
) -> tuple[int | None, Any]:
    """Valida o campo opcional ``moved_task_id`` do corpo de reordenação.

    Quando presente, identifica o ÚNICO card que o usuário arrastou entre
    colunas — só ele pode transicionar de status. Deve referenciar um id que
    esteja em alguma ``column.task_ids`` do payload.

    Args:
        payload: Corpo JSON já validado como dict por ``_parse_reorder_columns``.
        columns: Colunas normalizadas.

    Returns:
        ``(moved_task_id, None)`` (``None`` quando ausente); ou
        ``(None, fail_response)`` (422) quando inválido ou fora das colunas.
    """
    raw = payload.get("moved_task_id")
    if raw is None:
        return None, None
    try:
        moved_task_id = int(raw)
    except (TypeError, ValueError):
        return None, fail(
            f"moved_task_id inválido: {raw!r}.", status=422, code="validation"
        )
    if all(moved_task_id not in column["task_ids"] for column in columns):
        return None, fail(
            "moved_task_id fora das colunas enviadas.", status=422, code="validation"
        )
    return moved_task_id, None


def _apply_moved_task_transition(
    columns: list[dict[str, Any]],
    tasks_by_id: dict[int, Task],
    moved_task_id: int | None,
) -> Any | None:
    """Aplica a transição de status APENAS ao card movido (``moved_task_id``).

    Os demais ids do payload NUNCA transicionam: um snapshot obsoleto do cliente
    não pode desfazer a mudança de coluna feita por outro usuário (bug 2.10).
    Mudar status é escrita: exige rank >= editor (MESMO gate de
    ``POST /api/tarefas/<id>/status``), além da validação de transição.

    Returns:
        ``None`` em sucesso/ausência de move; ou ``fail(...)`` (403) negado.
    """
    if moved_task_id is None:
        return None
    task = tasks_by_id[moved_task_id]
    target_status = next(
        (
            column["status"]
            for column in columns
            if moved_task_id in column["task_ids"] and task.status != column["status"]
        ),
        None,
    )
    if target_status is None:
        return None
    if not _can_edit_task(g.user, task):
        return fail(
            "Você não tem permissão para acessar esta tarefa.",
            status=403,
            code="forbidden",
        )
    return _apply_status_transition(task, target_status)


def _drop_stale_task_ids(
    columns: list[dict[str, Any]], tasks_by_id: dict[int, Task]
) -> None:
    """Remove das colunas os ids cujo status atual difere da coluna.

    São snapshot obsoleto (a task já migrou de coluna por ação concorrente):
    ficam de fora da atribuição de ordem e da resposta, preservando o estado
    persistido pelo outro usuário.
    """
    for column in columns:
        column["task_ids"] = [
            task_id
            for task_id in column["task_ids"]
            if tasks_by_id[task_id].status == column["status"]
        ]


def _collect_reorder_tasks(
    columns: list[dict[str, Any]],
) -> tuple[dict[int, Task] | None, Any]:
    """Carrega as tarefas referidas na reordenação validando visão e existência.

    Só considera tarefas ativas e visíveis ao usuário (reusa
    ``_build_visible_tasks_query``); qualquer id desconhecido/fora de escopo =>
    404, pois o cliente não deveria conseguir reordenar o que não enxerga.

    Args:
        columns: Colunas normalizadas por ``_parse_reorder_columns``.

    Returns:
        ``(tasks_by_id, None)`` com todas as tarefas resolvidas; ou
        ``(None, fail_response)`` (404) quando algum id não é visível.
    """
    requested_ids = {tid for column in columns for tid in column["task_ids"]}
    if not requested_ids:
        return {}, None

    # Eager-load do que ``serialize_task_card`` toca ao reserializar as colunas
    # afetadas (projeto + contadores de comentários/anexos): sem isto, cada drop
    # dispararia 3 queries lazy POR card. ``selectinload`` nas coleções evita o
    # produto cartesiano de um joinedload duplo.
    visible = (
        _build_visible_tasks_query(include_archived=False, include_relations=False)
        .options(
            joinedload(Task.project),
            selectinload(Task.comments),
            selectinload(Task.anexos),
        )
        .filter(Task.id.in_(requested_ids))
        .all()
    )
    tasks_by_id = {task.id: task for task in visible}
    missing = requested_ids - set(tasks_by_id)
    if missing:
        return None, fail(
            "Tarefa não encontrada ou fora do escopo.",
            status=404,
            code="not_found",
        )
    return tasks_by_id, None


@main_bp.route("/api/tarefas/board/reordenar", methods=["POST"])
@api_login_required
def api_tarefas_board_reordenar() -> Response | tuple[Response, int]:
    """Persiste a nova ordem dos cards do Kanban (dentro/entre colunas).

    Recebe o estado das colunas afetadas (``{"columns": [{"status", "task_ids"}],
    "moved_task_id"?: int}``) e, numa única transação: (1) aplica a mudança de
    status APENAS ao ``moved_task_id`` — sujeita à MESMA validação de transição
    autoritativa (``_can_transition_task_to_status``), respondendo 403
    ``forbidden`` / ``FINALIZE_DENIED_MESSAGE`` se negada; (2) ignora ids cujo
    status atual difere da coluna (snapshot obsoleto de mudança concorrente) sem
    tocar status nem ordem deles; (3) reescreve ``Task.ordem`` 1..N na ordem
    enviada, por coluna. Devolve as colunas afetadas só com as tasks que de fato
    pertencem a cada coluna, para o cliente reconciliar a store.

    Returns:
        Envelope ``{"ok": true, "data": {"columns": [...]}}`` (200) com as colunas
        afetadas; 422 (formato/status/``moved_task_id`` inválido), 404 (tarefa
        fora de escopo), 403 (transição negada); 401 JSON sem sessão.
    """
    payload = request.get_json(silent=True)
    columns, error = _parse_reorder_columns(payload)
    if error is not None:
        return error
    moved_task_id, moved_error = _parse_moved_task_id(payload, columns)
    if moved_error is not None:
        return moved_error

    tasks_by_id, load_error = _collect_reorder_tasks(columns)
    if load_error is not None:
        return load_error

    # Aplica status (com validação autoritativa) antes da ordem, para abortar a
    # transação inteira se a transição for negada.
    transition_error = _apply_moved_task_transition(columns, tasks_by_id, moved_task_id)
    if transition_error is not None:
        db.session.rollback()
        return transition_error

    _drop_stale_task_ids(columns, tasks_by_id)

    # Ordem é escrita: quem só lê o projeto não reordena as tarefas dele —
    # mesmo skip silencioso do reorder legado (`_group_ids_by_reorder_scope`).
    for column in columns:
        for index, task_id in enumerate(column["task_ids"], start=1):
            if _can_edit_task(g.user, tasks_by_id[task_id]):
                tasks_by_id[task_id].ordem = index

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return fail("Erro ao reordenar tarefas.", status=422, code="validation")

    affected = [
        {
            "status": column["status"],
            "label": _task_status_label(column["status"]),
            # Reaplica a ordenação por prioridade para a resposta refletir o mesmo
            # que ``GET /api/tarefas/board`` devolveria — evita o card "pular" só
            # no próximo reload quando o drop quebra a ordem de prioridade.
            "tasks": _sort_cards_by_priority(
                [
                    serialize_task_card(tasks_by_id[task_id])
                    for task_id in column["task_ids"]
                ]
            ),
        }
        for column in columns
    ]
    return ok({"columns": affected})
