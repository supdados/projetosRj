from urllib.parse import urlparse

from flask import current_app, flash, g, jsonify, redirect, request, url_for

from models import (
    Etapa,
    Project,
    Task,
    User,
    UserOrgao,
    db,
)
from services.notifications import notify_task_assignment_change, notify_task_event
from routes.orgao_tree import get_orgao_ancestors
from routes.tasks.constants import (
    VALID_PRIORIDADES,
    VALID_STATUSES,
    VALID_TIPOS,
    _normalize_person_name,
    _normalize_responsavel_value,
    _preview_text,
    _split_responsavel_names,
    _task_status_label,
)
from routes.tasks.permissions import (
    _can_access_project_in_tasks,
    task_permission_flags,
)


def _format_invalid_responsavel_message(invalid_names):
    invalid_str = ", ".join(invalid_names)
    return f"Responsável inválido: {invalid_str}. Selecione somente usuários com permissão de visualização."


def _resolve_etapa_token(
    raw_etapa_value, project, *, allow_empty=True, allow_done=False
):
    """Resolve um valor cru (vindo de form/JSON) para uma ``Etapa``.

    Retorna ``(etapa, error_message, status_code)``. Quando ``allow_empty`` e o
    valor é vazio/``None``/``"sem_etapa"``, retorna ``(None, None, 200)``.
    Valida que a etapa pertence ao ``project`` informado e que não está
    concluída — etapas concluídas não devem receber tarefas novas.
    """
    if raw_etapa_value is None:
        if allow_empty:
            return None, None, 200
        return None, "Etapa é obrigatória.", 400

    raw = str(raw_etapa_value).strip()
    if not raw or raw == "sem_etapa":
        if allow_empty:
            return None, None, 200
        return None, "Etapa é obrigatória.", 400

    try:
        etapa_id = int(raw)
    except (TypeError, ValueError):
        return None, "Etapa inválida.", 400

    etapa = db.session.get(Etapa, etapa_id)
    if etapa is None:
        return None, "Etapa não encontrada.", 404

    if project is None or etapa.project_id != project.id:
        return None, "Etapa não pertence a este projeto.", 400

    if etapa.done and not allow_done:
        return None, "Etapa concluída não aceita novas tarefas.", 400

    return etapa, None, 200


def _resolve_project_token(raw_project_value, allow_empty=False):
    # Coage para str antes de .strip(): a SPA envia `project_id` como inteiro
    # (JSON number), enquanto o form Jinja envia string. Espelha _resolve_etapa_token.
    project_value = "" if raw_project_value is None else str(raw_project_value).strip()
    if not project_value:
        if allow_empty:
            return None, None, 200
        return None, "Projeto é obrigatório.", 400

    if project_value == "sem_projeto":
        return None, None, 200

    try:
        project_id = int(project_value)
    except (TypeError, ValueError):
        return None, "Projeto inválido.", 400

    project = db.session.get(Project, project_id)
    if not project:
        return None, "Projeto não encontrado.", 404

    if not _can_access_project_in_tasks(project):
        return None, "Sem permissão para este projeto.", 403

    return project, None, 200


def _get_assignable_users_for_orgao(orgao_id):
    candidate_ids = {g.user.id}

    admin_ids = [
        user_id
        for (user_id,) in User.query.with_entities(User.id)
        .filter(User.is_admin.is_(True), User.deleted_at.is_(None))
        .all()
    ]
    candidate_ids.update(admin_ids)

    if orgao_id is not None:
        # Usuário é assignável se está vinculado ao próprio órgão ou a um ancestral
        # (herança descendente: vínculo no pai dá acesso ao filho).
        scope_ids = {orgao_id, *get_orgao_ancestors(orgao_id)}
        orgao_user_ids = [
            user_id
            for (user_id,) in (
                UserOrgao.query.with_entities(UserOrgao.user_id)
                .filter(UserOrgao.orgao_id.in_(scope_ids))
                .all()
            )
        ]
        candidate_ids.update(orgao_user_ids)

    if not candidate_ids:
        return []

    # Soft-delete C4: usuários removidos não podem ser atribuídos como responsável.
    return (
        User.query.filter(User.id.in_(candidate_ids), User.deleted_at.is_(None))
        .order_by(User.name.asc())
        .all()
    )


def _get_assignable_users_for_project(project):
    orgao_id = project.orgao_id if project is not None else None
    return _get_assignable_users_for_orgao(orgao_id)


def _validate_task_responsavel(project, raw_value):
    parsed_names = _split_responsavel_names(raw_value)
    if not parsed_names:
        return True, "", []

    allowed_users = _get_assignable_users_for_project(project)
    allowed_by_key = {}
    for user in allowed_users:
        canonical = _normalize_person_name(user.name)
        if canonical:
            allowed_by_key[canonical.casefold()] = canonical

    canonical_names = []
    invalid_names = []
    seen = set()

    for name in parsed_names:
        canonical = allowed_by_key.get(name.casefold())
        if not canonical:
            invalid_names.append(name)
            continue
        key = canonical.casefold()
        if key in seen:
            continue
        seen.add(key)
        canonical_names.append(canonical)

    return len(invalid_names) == 0, ", ".join(canonical_names), invalid_names


def _resolve_responsavel_for_edit(task, incoming_raw_value, project):
    current_normalized = _normalize_responsavel_value(task.responsavel or "")
    incoming_normalized = _normalize_responsavel_value(incoming_raw_value)
    if incoming_normalized == current_normalized:
        return True, (task.responsavel or ""), []
    return _validate_task_responsavel(project, incoming_raw_value)


def _serialize_task_payload(task):
    project = task.project
    project_id = project.id if project else None
    etapa = task.etapa
    permission_flags = task_permission_flags(task)
    return {
        "id": task.id,
        "descricao": task.descricao,
        "status": task.status,
        "responsavel": task.responsavel or "",
        "prioridade": task.prioridade or "",
        "tipo_pedido": task.tipo_pedido or "",
        "task_id": task.id,
        "task_titulo": task.descricao,
        "project_id": project_id,
        "project_titulo": project.titulo if project else "Sem projeto",
        "project_orgao_sigla": (
            (project.orgao_ref.sigla if project and project.orgao_ref else "")
            if project
            else ""
        ),
        "project_value": str(project_id) if project_id else "sem_projeto",
        "etapa_id": etapa.id if etapa else None,
        "etapa_descricao": etapa.descricao if etapa else "",
        "etapa_value": str(etapa.id) if etapa else "sem_etapa",
        "comments_count": len(task.comments),
        "anexos_count": len(task.anexos),
        "can_delete": permission_flags["can_delete"],
        "can_finalize": permission_flags["can_finalize"],
        "is_author": permission_flags["is_author"],
    }


def _get_safe_next_url():
    raw_next = (
        request.form.get("next")
        or request.args.get("next")
        or request.headers.get("Referer")
        or request.referrer
    )
    if not raw_next:
        return None

    parsed = urlparse(raw_next)

    if not parsed.netloc and parsed.path.startswith("/"):
        target = parsed.path
        if parsed.query:
            target = f"{target}?{parsed.query}"
        return target

    if parsed.netloc and parsed.netloc == request.host:
        target = parsed.path or "/"
        if parsed.query:
            target = f"{target}?{parsed.query}"
        return target

    return None


def _redirect_back_or(default_endpoint, **kwargs):
    next_url = _get_safe_next_url()
    if next_url:
        return redirect(next_url)
    return redirect(url_for(default_endpoint, **kwargs))


def _extract_creation_payload(default_project=None):
    payload = request.get_json(silent=True) or {}

    project_raw = request.form.get("project")
    if project_raw is None:
        project_raw = request.form.get("project_id")
    if project_raw is None:
        project_raw = payload.get("project")
    if project_raw is None:
        project_raw = payload.get("project_id")

    if project_raw is None and default_project is not None:
        project_raw = str(default_project.id)

    etapa_raw = request.form.get("etapa")
    if etapa_raw is None:
        etapa_raw = request.form.get("etapa_id")
    if etapa_raw is None:
        etapa_raw = payload.get("etapa")
    if etapa_raw is None:
        etapa_raw = payload.get("etapa_id")

    descricao = (
        request.form.get("descricao") or payload.get("descricao") or ""
    ).strip()
    if not descricao:
        descricao = (request.form.get("titulo") or payload.get("titulo") or "").strip()

    status = (
        request.form.get("status") or payload.get("status") or "nao_iniciada"
    ).strip()
    responsavel = (
        request.form.get("responsavel") or payload.get("responsavel") or ""
    ).strip()
    prioridade = (
        request.form.get("prioridade") or payload.get("prioridade") or ""
    ).strip() or None
    tipo_pedido = (
        request.form.get("tipo_pedido") or payload.get("tipo_pedido") or ""
    ).strip() or None

    raw_assignee_ids = payload.get("assignee_ids")
    assignee_ids: list[int] = []
    if isinstance(raw_assignee_ids, list):
        for value in raw_assignee_ids:
            try:
                assignee_ids.append(int(value))
            except (TypeError, ValueError):
                continue

    return {
        "project_raw": project_raw,
        "etapa_raw": etapa_raw,
        "descricao": descricao,
        "status": status,
        "responsavel": responsavel,
        "assignee_ids": assignee_ids,
        "prioridade": prioridade,
        "tipo_pedido": tipo_pedido,
    }


def _create_task_common(default_project=None):
    is_ajax = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.accept_mimetypes.best == "application/json"
    )

    payload = _extract_creation_payload(default_project=default_project)

    project, project_error, status_code = _resolve_project_token(
        payload["project_raw"], allow_empty=True
    )
    if project_error:
        if is_ajax:
            return jsonify({"success": False, "message": project_error}), status_code
        flash(project_error, "danger")
        return redirect(url_for("main.list_tasks"))

    etapa, etapa_error, etapa_status = _resolve_etapa_token(
        payload["etapa_raw"], project, allow_empty=True
    )
    if etapa_error:
        if is_ajax:
            return jsonify({"success": False, "message": etapa_error}), etapa_status
        flash(etapa_error, "danger")
        return redirect(url_for("main.list_tasks"))

    status = (
        payload["status"] if payload["status"] in VALID_STATUSES else "nao_iniciada"
    )
    prioridade = (
        payload["prioridade"] if payload["prioridade"] in VALID_PRIORIDADES else None
    )
    tipo_pedido = (
        payload["tipo_pedido"] if payload["tipo_pedido"] in VALID_TIPOS else None
    )

    if not payload["descricao"]:
        message = "Descrição é obrigatória."
        if is_ajax:
            return jsonify({"success": False, "message": message}), 400
        flash(message, "danger")
        return redirect(url_for("main.list_tasks"))

    is_valid_responsavel, canonical_responsavel, invalid_names = (
        _validate_task_responsavel(project, payload["responsavel"])
    )
    if not is_valid_responsavel:
        message = _format_invalid_responsavel_message(invalid_names)
        if is_ajax:
            return jsonify({"success": False, "message": message}), 400
        flash(message, "danger")
        return redirect(url_for("main.list_tasks"))

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
            descricao=payload["descricao"],
            status=status,
            responsavel=canonical_responsavel if canonical_responsavel else None,
            prioridade=prioridade,
            tipo_pedido=tipo_pedido,
            project_id=project.id if project else None,
            etapa_id=etapa.id if etapa else None,
            created_by_id=g.user.id,
            ordem=max_ordem + 1,
        )

        db.session.add(task)
        db.session.flush()

        # Responsáveis múltiplos (novo modelo). Valida cada id contra os
        # candidatos com acesso ao projeto; notifica os adicionados (abaixo).
        from routes.tasks.notifications import notify_assignee_change
        from routes.tasks.queries import set_task_assignees

        allowed_assignee_ids = {
            user.id for user in _get_assignable_users_for_project(project)
        }
        desired_assignees = [
            uid for uid in payload["assignee_ids"] if uid in allowed_assignee_ids
        ]
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

        if is_ajax:
            serialized = _serialize_task_payload(task)
            return jsonify({"success": True, "task": serialized, "item": serialized})

        flash("Tarefa adicionada com sucesso!", "success")
        if project:
            return redirect(url_for("main.project_tasks", project_id=project.id))
        return redirect(url_for("main.list_tasks"))
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Falha ao adicionar tarefa: %s", type(e).__name__)
        if is_ajax:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Não foi possível adicionar a tarefa.",
                    }
                ),
                500,
            )
        flash("Não foi possível adicionar a tarefa.", "danger")
        return redirect(url_for("main.list_tasks"))
