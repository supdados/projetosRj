"""Endpoints JSON do DRAWER de Tarefa (Fase 5b-2) consumidos pela SPA SvelteKit.

O drawer abre UMA tarefa (do board Kanban, da lista ou de uma etapa no Detalhe do
Projeto) com edição inline AUTOSAVE dos campos, comentários, anexos e ações de
ciclo de vida (finalizar/arquivar/desarquivar/reativar). Todos os endpoints aqui
respondem no envelope canônico (``ok``/``fail``), exceto o download binário de
anexo — que continua sendo a rota Jinja legada ``view_task_item_anexo``
(``send_file``), referenciada apenas como ``url`` no payload.

Endpoints (anexados ao ``main_bp`` ÚNICO; ADITIVO — NÃO altera as rotas Jinja
legadas em ``routes/tasks/{crud,comments,attachments}.py``):

    - ``GET  /api/tarefas/<id>/detalhe``               — payload completo do drawer.
    - ``POST /api/tarefas/<id>/campos``                — edição inline (AUTOSAVE):
      ``descricao``/``prioridade``/``tipo_pedido``/``responsavel``. O ``status``
      continua em ``POST /api/tarefas/<id>/status`` (Fase 5b-1, ``board.py``).
    - ``POST /api/tarefas/<id>/finalizar``             — move para "finalizada"
      (respeita ``_can_manage_task_restricted_actions`` -> 403).
    - ``POST /api/tarefas/<id>/arquivar``              — arquiva.
    - ``POST /api/tarefas/<id>/desarquivar``           — desarquiva (reseta status).
    - ``POST /api/tarefas/<id>/reativar``              — alias de desarquivar.
    - ``GET  /api/tarefas/<id>/sugestoes-responsavel`` — picker de responsável.

SERVIDOR AUTORITATIVO: as regras de permissão/transição são REUSADAS das mesmas
funções das rotas legadas (``_can_view_task``, ``_can_manage_task_restricted_actions``,
``_can_transition_task_to_status``), sem duplicação. O drawer e a board (Fase 5b-1)
compartilham a MESMA fonte de verdade: a resposta inclui o card atualizado
(``serialize_task_card``) para a store reconciliar.
"""

from __future__ import annotations

from typing import Any

from flask import Response, current_app, g, request, url_for

from models import Task, db

from ..blueprint import main_bp
from ..tasks.creation import (
    _format_invalid_responsavel_message,
    _get_assignable_users_for_project,
    _resolve_responsavel_for_edit,
)
from ..tasks.notifications import (
    notify_assignee_change,
    notify_prioridade_change,
    notify_task_edited,
    notify_task_finalized,
    notify_task_unarchived,
    notify_tipo_change,
)
from ..tasks.queries import serialize_assignee, set_task_assignees
from ..tasks.permissions import (
    FINALIZE_DENIED_MESSAGE,
    _audit_denied_task_action,
    _can_manage_task_restricted_actions,
    _can_view_task,
    task_permission_flags,
)
from .envelope import fail, ok
from .negotiation import api_login_required
from .serializers import serialize_task_card, serialize_task_detail

from services.task_mutation import (
    apply_task_edits,
    archive_task as mutate_archive_task,
    unarchive_task as mutate_unarchive_task,
)

#: Mesma string da rota legada ``update_task_prioridade`` (``crud.py``); a edição
#: de campos restritos (descrição/prioridade/responsável) exige autoria/admin.
EDIT_RESTRICTED_DENIED_MESSAGE = (
    "Somente o autor da tarefa ou um administrador pode editar "
    "descrição, prioridade e responsável."
)

#: Campos válidos do AUTOSAVE inline. ``status`` é deliberadamente EXCLUÍDO — ele
#: continua sendo mudado por ``POST /api/tarefas/<id>/status`` (Fase 5b-1).
_INLINE_FIELDS = frozenset({"descricao", "prioridade", "tipo_pedido", "responsavel"})


def _anexo_download_url(anexo: Any) -> str:
    """Monta a URL do download binário do anexo (rota Jinja legada send_file).

    O drawer abre este link em nova aba / via ``<a download>`` (mesma origin,
    cookie de sessão). NÃO envelopamos o download — é octet-stream.
    """
    return url_for("main.view_task_item_anexo", anexo_id=anexo.id)


def _load_drawer_task(task_id: int) -> tuple[Task | None, Any]:
    """Carrega a tarefa validando existência (404) e escopo de visão (403).

    Reusa ``_can_view_task`` (a MESMA regra das rotas legadas), devolvendo o
    envelope canônico em vez de ``jsonify(success=...)``.

    Args:
        task_id: ID da tarefa.

    Returns:
        ``(task, None)`` quando autorizado; ``(None, fail_response)`` (404/403).
    """
    task = db.session.get(Task, task_id)
    if task is None:
        return None, fail("Tarefa não encontrada.", status=404, code="not_found")
    if not _can_view_task(g.user, task):
        return None, fail(
            "Você não tem permissão para acessar esta tarefa.",
            status=403,
            code="forbidden",
        )
    return task, None


def _drawer_detail_payload(task: Task) -> dict[str, Any]:
    """Monta o payload ``{task, detail}`` reconciliável pela board store + drawer.

    ``task`` é o card canônico (``serialize_task_card``) — a MESMA forma que a
    board store consome (Fase 5b-1), para refletir a mutação no card sem duplicar
    estado. ``detail`` é o payload completo do drawer (contexto + comentários +
    anexos + permissions autoritativos).

    Args:
        task: Tarefa já carregada/validada.

    Returns:
        ``{"task": <card>, "detail": <detalhe completo>}``.
    """
    permissions = task_permission_flags(task)
    permissions = {
        "can_edit": bool(permissions["can_delete"]),
        "can_finalize": bool(permissions["can_finalize"]),
        "can_delete": bool(permissions["can_delete"]),
    }
    detail = serialize_task_detail(
        task, permissions=permissions, anexo_url_for=_anexo_download_url
    )
    return {"task": serialize_task_card(task), "detail": detail}


@main_bp.route("/api/tarefas/<int:task_id>/detalhe", methods=["GET"])
@api_login_required
def api_tarefa_detalhe(task_id: int) -> Response | tuple[Response, int]:
    """Retorna o payload completo do DRAWER de uma tarefa (read-only).

    Inclui campos editáveis, status/prioridade/tipo/responsável, contexto de
    etapa/projeto, comentários, anexos e ``permissions`` ``{can_edit,
    can_finalize, can_delete}`` derivados server-side. 404 (inexistente), 403
    (fora de escopo), 401 JSON sem sessão.

    Args:
        task_id: ID da tarefa.

    Returns:
        Envelope ``{"ok": true, "data": {"task": {...}, "detail": {...}}}`` (200).
    """
    task, error = _load_drawer_task(task_id)
    if error is not None:
        return error
    return ok(_drawer_detail_payload(task))


def _read_inline_payload() -> tuple[dict[str, Any] | None, Any]:
    """Lê e valida o corpo JSON do AUTOSAVE de campos inline.

    Exige um objeto JSON com AO MENOS um campo de ``_INLINE_FIELDS``. Chaves
    desconhecidas são ignoradas (edição parcial robusta para o autosave).

    Returns:
        ``(fields, None)`` com só as chaves válidas presentes; ou
        ``(None, fail_response)`` (422) quando o corpo é inválido/vazio.
    """
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return None, fail("Corpo JSON inválido.", status=422, code="validation")
    fields = {key: payload[key] for key in _INLINE_FIELDS if key in payload}
    if not fields:
        return None, fail(
            "Nenhum campo editável enviado.", status=422, code="validation"
        )
    return fields, None


def _apply_inline_fields(task: Task, fields: dict[str, Any]) -> Any | None:
    """Aplica os campos do AUTOSAVE em ``task`` (sem commit), validando server-side.

    Reusa a MESMA lógica das rotas legadas sem alterá-las:
      - ``descricao``/``prioridade``/``responsavel`` exigem
        ``_can_manage_task_restricted_actions`` (403 ``forbidden`` se negado);
      - ``responsavel`` é resolvido por ``_resolve_responsavel_for_edit`` (422 se
        inválido para o escopo do projeto);
      - ``descricao`` não pode ficar vazia (422).
    Dispara as notificações de domínio existentes (edição/prioridade/tipo).

    Args:
        task: Tarefa carregada/validada.
        fields: Subconjunto de ``_INLINE_FIELDS`` enviado pelo cliente.

    Returns:
        ``None`` em sucesso (mutação em memória); ou um ``fail(...)`` (403/422).
    """
    touches_restricted = bool({"descricao", "prioridade", "responsavel"} & set(fields))
    if touches_restricted and not _can_manage_task_restricted_actions(g.user, task):
        _audit_denied_task_action(task, "forbidden_edit_restricted")
        return fail(EDIT_RESTRICTED_DENIED_MESSAGE, status=403, code="forbidden")

    descricao = task.descricao
    if "descricao" in fields:
        descricao = (fields["descricao"] or "").strip()
        if not descricao:
            return fail("Descrição é obrigatória.", status=422, code="validation")

    prioridade = task.prioridade
    if "prioridade" in fields:
        from ..tasks.constants import VALID_PRIORIDADES

        raw = (fields["prioridade"] or "").strip() or None
        if raw and raw not in VALID_PRIORIDADES:
            return fail("Prioridade inválida.", status=422, code="validation")
        prioridade = raw

    tipo_pedido = task.tipo_pedido
    if "tipo_pedido" in fields:
        from ..tasks.constants import VALID_TIPOS

        raw = (fields["tipo_pedido"] or "").strip() or None
        if raw and raw not in VALID_TIPOS:
            return fail("Tipo inválido.", status=422, code="validation")
        tipo_pedido = raw

    responsavel = task.responsavel
    if "responsavel" in fields:
        is_valid, resolved, invalid_names = _resolve_responsavel_for_edit(
            task, fields["responsavel"] or "", task.project
        )
        if not is_valid:
            return fail(
                _format_invalid_responsavel_message(invalid_names),
                status=422,
                code="validation",
            )
        responsavel = resolved

    old_prioridade = task.prioridade
    old_tipo = task.tipo_pedido
    diff = apply_task_edits(
        task,
        descricao=descricao,
        status=task.status,
        responsavel=responsavel,
        prioridade=prioridade,
        tipo_pedido=tipo_pedido,
        project=task.project,
        apply_etapa=False,
    )
    notify_task_edited(task, diff)
    if "prioridade" in fields and old_prioridade != task.prioridade:
        notify_prioridade_change(task, old_prioridade)
    if "tipo_pedido" in fields and old_tipo != task.tipo_pedido:
        notify_tipo_change(task, old_tipo)
    return None


@main_bp.route("/api/tarefas/<int:task_id>/campos", methods=["POST"])
@api_login_required
def api_tarefa_campos(task_id: int) -> Response | tuple[Response, int]:
    """Edição inline AUTOSAVE de campos da tarefa (descricao/prioridade/tipo/responsavel).

    O ``status`` NÃO é alterado aqui — continua em ``POST /api/tarefas/<id>/status``
    (Fase 5b-1). Reusa a lógica das rotas legadas (sem alterá-las), validando
    permissão de campos restritos (403) e os valores (422). Devolve o card + o
    detalhe atualizados para o drawer e a board store reconciliarem.

    Body JSON: ``{"descricao"?, "prioridade"?, "tipo_pedido"?, "responsavel"?}``.

    Args:
        task_id: ID da tarefa.

    Returns:
        Envelope ``{"ok": true, "data": {"task": {...}, "detail": {...}}}`` (200);
        404/403/422 canônicos; 401 JSON sem sessão.
    """
    task, error = _load_drawer_task(task_id)
    if error is not None:
        return error

    fields, parse_error = _read_inline_payload()
    if parse_error is not None:
        return parse_error

    apply_error = _apply_inline_fields(task, fields)
    if apply_error is not None:
        db.session.rollback()
        return apply_error

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return fail("Erro ao salvar a tarefa.", status=422, code="validation")

    return ok(_drawer_detail_payload(task))


@main_bp.route("/api/tarefas/<int:task_id>/finalizar", methods=["POST"])
@api_login_required
def api_tarefa_finalizar(task_id: int) -> Response | tuple[Response, int]:
    """Finaliza a tarefa (status -> "finalizada"), respeitando a permissão autoritativa.

    Reusa ``_can_manage_task_restricted_actions`` (MESMA regra de
    ``finalize_task`` legada): só o autor/admin finaliza (403 ``forbidden`` +
    ``FINALIZE_DENIED_MESSAGE``). Tarefa já arquivada => 422. Em sucesso devolve o
    card + detalhe para a board store refletir/remover o card conforme o status.

    Args:
        task_id: ID da tarefa.

    Returns:
        Envelope com ``{task, detail}`` (200); 404/403/422; 401 JSON sem sessão.
    """
    task, error = _load_drawer_task(task_id)
    if error is not None:
        return error

    if not _can_manage_task_restricted_actions(g.user, task):
        _audit_denied_task_action(
            task, "forbidden_finalize", attempted_status="finalizada"
        )
        return fail(FINALIZE_DENIED_MESSAGE, status=403, code="forbidden")

    if task.is_archived:
        return fail("Esta tarefa já está arquivada.", status=422, code="validation")

    old_status = task.status
    task.status = "finalizada"

    try:
        if old_status != task.status:
            notify_task_finalized(task)
        db.session.commit()
    except Exception:
        db.session.rollback()
        return fail("Erro ao finalizar a tarefa.", status=422, code="validation")

    return ok(_drawer_detail_payload(task))


@main_bp.route("/api/tarefas/<int:task_id>/arquivar", methods=["POST"])
@api_login_required
def api_tarefa_arquivar(task_id: int) -> Response | tuple[Response, int]:
    """Arquiva a tarefa (``is_archived=True``); a board remove o card.

    Reusa ``archive_task`` (``services/task_mutation.py``); restrito a autor/admin
    (403 ``forbidden``). Idempotente: já arquivada => 422. Devolve card + detalhe.

    Args:
        task_id: ID da tarefa.

    Returns:
        Envelope com ``{task, detail}`` (200); 404/403/422; 401 JSON sem sessão.
    """
    task, error = _load_drawer_task(task_id)
    if error is not None:
        return error

    if not _can_manage_task_restricted_actions(g.user, task):
        _audit_denied_task_action(task, "forbidden_edit_restricted")
        return fail(
            "Somente o autor da tarefa ou um administrador pode arquivá-la.",
            status=403,
            code="forbidden",
        )

    if task.is_archived:
        return fail("Esta tarefa já está arquivada.", status=422, code="validation")

    mutate_archive_task(task)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return fail("Erro ao arquivar a tarefa.", status=422, code="validation")

    return ok(_drawer_detail_payload(task))


def _unarchive_and_respond(task_id: int) -> Response | tuple[Response, int]:
    """Lógica compartilhada de desarquivar/reativar (reusa ``unarchive_task``).

    Reseta ``is_archived``/``archived_at`` e status para "nao_iniciada" (MESMA
    regra de ``unarchive_task`` legada). Dispara ``notify_task_unarchived``.
    Restrito a autor/admin — MESMO guard de ``arquivar``/``finalizar`` (403
    ``forbidden``); ver auditoria 2.5.

    Args:
        task_id: ID da tarefa.

    Returns:
        Envelope com ``{task, detail}`` (200); 404/403/422.
    """
    task, error = _load_drawer_task(task_id)
    if error is not None:
        return error

    if not _can_manage_task_restricted_actions(g.user, task):
        _audit_denied_task_action(task, "forbidden_edit_restricted")
        return fail(
            "Somente o autor da tarefa ou um administrador pode desarquivá-la.",
            status=403,
            code="forbidden",
        )

    mutate_unarchive_task(task)

    try:
        notify_task_unarchived(task)
        db.session.commit()
    except Exception:
        db.session.rollback()
        return fail("Erro ao desarquivar a tarefa.", status=422, code="validation")

    return ok(_drawer_detail_payload(task))


@main_bp.route("/api/tarefas/<int:task_id>/desarquivar", methods=["POST"])
@api_login_required
def api_tarefa_desarquivar(task_id: int) -> Response | tuple[Response, int]:
    """Desarquiva a tarefa (reseta status para "nao_iniciada").

    Args:
        task_id: ID da tarefa.

    Returns:
        Envelope com ``{task, detail}`` (200); 404/403/422; 401 JSON sem sessão.
    """
    return _unarchive_and_respond(task_id)


@main_bp.route("/api/tarefas/<int:task_id>/reativar", methods=["POST"])
@api_login_required
def api_tarefa_reativar(task_id: int) -> Response | tuple[Response, int]:
    """Reativa a tarefa (alias de desarquivar — mesma regra legada ``reactivate_task``).

    Args:
        task_id: ID da tarefa.

    Returns:
        Envelope com ``{task, detail}`` (200); 404/403/422; 401 JSON sem sessão.
    """
    return _unarchive_and_respond(task_id)


@main_bp.route("/api/tarefas/<int:task_id>/sugestoes-responsavel", methods=["GET"])
@api_login_required
def api_tarefa_sugestoes_responsavel(task_id: int) -> Response | tuple[Response, int]:
    """Sugestões de responsável para o picker do drawer.

    Reusa ``_get_assignable_users_for_project`` (MESMA fonte da rota legada
    ``get_task_assignable_users``), filtrando por ``?q=`` (case-insensitive).

    Args:
        task_id: ID da tarefa.

    Returns:
        Envelope ``{"ok": true, "data": {"users": [{id, name}]}}`` (200);
        404/403; 401 JSON sem sessão.
    """
    task, error = _load_drawer_task(task_id)
    if error is not None:
        return error

    users = _get_assignable_users_for_project(task.project)
    query = (request.args.get("q") or "").strip().lower()
    options = [serialize_assignee(user) for user in users]
    if query:
        options = [u for u in options if query in (u["name"] or "").lower()]
    return ok({"users": options})


@main_bp.route("/api/tarefas/<int:task_id>/responsaveis", methods=["POST"])
@api_login_required
def api_tarefa_responsaveis(task_id: int) -> Response | tuple[Response, int]:
    """Define os responsáveis MÚLTIPLOS da tarefa e notifica os adicionados.

    Body JSON: ``{"user_ids": [int, ...]}``. Cada id é validado contra os
    candidatos com acesso ao projeto; ids fora dessa lista são ignorados.
    Notifica (sino) em TODA atribuição — adicionados e removidos. Exige autor
    ou admin (mesma restrição da edição de ``responsavel``).

    Returns:
        Envelope ``{"ok": true, "data": {"task": {...}, "detail": {...}}}`` (200);
        404/403/422 canônicos; 401 JSON sem sessão.
    """
    task, error = _load_drawer_task(task_id)
    if error is not None:
        return error

    if not _can_manage_task_restricted_actions(g.user, task):
        return fail(EDIT_RESTRICTED_DENIED_MESSAGE, status=403, code="forbidden")

    payload = request.get_json(silent=True) or {}
    raw_ids = payload.get("user_ids")
    if not isinstance(raw_ids, list):
        return fail(
            "'user_ids' deve ser uma lista de inteiros.", status=422, code="validation"
        )

    allowed_ids = {user.id for user in _get_assignable_users_for_project(task.project)}
    desired: list[int] = []
    for value in raw_ids:
        try:
            user_id = int(value)
        except (TypeError, ValueError):
            return fail(
                f"user_id inválido: {value!r} (esperado inteiro).",
                status=422,
                code="validation",
            )
        if user_id in allowed_ids:
            desired.append(user_id)

    added, removed = set_task_assignees(task, desired)
    notify_assignee_change(task, added, removed)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Erro ao salvar responsaveis da tarefa %s", task_id
        )
        return fail("Erro ao salvar responsáveis.", status=422, code="validation")

    return ok(_drawer_detail_payload(task))
