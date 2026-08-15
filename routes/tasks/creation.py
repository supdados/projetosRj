from flask import g, redirect, request, url_for

from routes.safe_redirect import safe_internal_path

from models import (
    Etapa,
    Project,
    User,
    UserOrgao,
    db,
)
from routes.orgao_tree import get_orgao_ancestors
from routes.tasks.constants import (
    _normalize_person_name,
    _normalize_responsavel_value,
    _split_responsavel_names,
)
from routes.tasks.permissions import (
    task_permission_flags,
)
from services.authorization import (
    ACCESS_FORBIDDEN,
    ACCESS_NOT_FOUND,
    PAPEL_EDITOR,
    PAPEL_LEITOR,
    project_access_verdict,
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

    from routes.api.envelope import NOT_FOUND_MESSAGE

    # Anti-enumeração (F4-2b): etapa inexistente e etapa de projeto invisível
    # ou alheio colapsam no mesmo 404 — sem revelar existência do id.
    etapa = db.session.get(Etapa, etapa_id)
    if etapa is None or project is None or etapa.project_id != project.id:
        return None, NOT_FOUND_MESSAGE, 404

    if etapa.done and not allow_done:
        return None, "Etapa concluída não aceita novas tarefas.", 400

    return etapa, None, 200


def _resolve_project_token(raw_project_value, allow_empty=False, *, for_write=False):
    """Resolve o token de projeto de form/JSON para um ``Project``.

    ``for_write=True`` exige rank >= editor no projeto (criar/editar tarefa);
    o padrão exige apenas acesso de leitura (pickers e sugestões).
    Retorna ``(project, error_message, status_code)``. Contrato S5 (F4-2):
    projeto inexistente e projeto invisível (rank 0) devolvem o MESMO 404.
    """
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

    # Import local: `routes.api.envelope` executa `routes/api/__init__`, que
    # importa este módulo de volta — no topo o ciclo estoura no boot.
    from routes.api.envelope import NOT_FOUND_MESSAGE

    project = db.session.get(Project, project_id)
    verdict = project_access_verdict(
        g.user, project, PAPEL_EDITOR if for_write else PAPEL_LEITOR
    )
    if verdict == ACCESS_NOT_FOUND:
        return None, NOT_FOUND_MESSAGE, 404
    if verdict == ACCESS_FORBIDDEN:
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
    # Referer/referrer NÃO entram como fonte: são controláveis pelo atacante e
    # davam open redirect (CWE-601). Só destinos explícitos via 'next', validados.
    raw_next = request.form.get("next") or request.args.get("next")
    return safe_internal_path(raw_next, request.host)


def _redirect_back_or(default_endpoint, **kwargs):
    next_url = _get_safe_next_url()
    if next_url:
        return redirect(next_url)
    return redirect(url_for(default_endpoint, **kwargs))
