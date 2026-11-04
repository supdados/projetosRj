import re

from flask import url_for
from sqlalchemy import func

from models import (
    Project,
    ProjectCollection,
    ProjectHistory,
    Task,
    TaskComment,
    User,
    UserOrgao,
    UserNotification,
    db,
)

IGNORED_PROJECT_ACTION_TYPES = {
    "reorder_etapas",
    "cascade_update",
    "relacionar_projeto",
    "desrelacionar_projeto",
}

# Mesmos rótulos da SPA (routes/(app)/colecoes/[id]/+page.svelte::PAPEL_LABEL).
ROTULO_PAPEL_SHARE = {"viewer": "leitor", "editor": "editor"}


def _normalize_person_name(name):
    return " ".join((name or "").strip().split())


def _split_responsavel_names(raw_value):
    raw_value = (raw_value or "").replace("\r", "\n").strip()
    if not raw_value:
        return []

    names = []
    seen = set()

    for part in re.split(r"[,\n;]+", raw_value):
        normalized = _normalize_person_name(part.strip().lstrip("@"))
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        names.append(normalized)

    return names


def _resolve_user_ids_from_names(names):
    normalized_keys = {
        _normalize_person_name(name).casefold()
        for name in names
        if _normalize_person_name(name)
    }
    if not normalized_keys:
        return set()

    users = User.query.filter(func.lower(User.name).in_(list(normalized_keys))).all()
    return {user.id for user in users}


def _truncate_text(value, max_length=140):
    text_value = " ".join((value or "").split())
    if len(text_value) <= max_length:
        return text_value
    return text_value[: max_length - 3].rstrip() + "..."


def create_user_notifications(
    recipient_user_ids, actor_user_id, event_type, title, message, target_url
):
    unique_ids = {int(user_id) for user_id in recipient_user_ids if user_id}
    if actor_user_id:
        unique_ids.discard(int(actor_user_id))
    if not unique_ids:
        return 0

    existing_ids = {
        user_id
        for (user_id,) in User.query.with_entities(User.id)
        .filter(User.id.in_(unique_ids))
        .all()
    }
    if not existing_ids:
        return 0

    notifications = [
        UserNotification(
            recipient_user_id=recipient_user_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            title=title,
            message=message,
            target_url=target_url,
        )
        for recipient_user_id in sorted(existing_ids)
    ]
    db.session.add_all(notifications)
    return len(notifications)


def _resolve_admin_ids_for_orgao(orgao_id):
    """Admins com escopo ao orgao (via UserOrgao + ancestrais). Fallback: todos admins."""
    admin_ids = {
        user_id
        for (user_id,) in User.query.with_entities(User.id)
        .filter(User.is_admin.is_(True))
        .all()
    }
    if not admin_ids:
        return set()
    if not orgao_id:
        return admin_ids

    from routes.orgao_tree import get_orgao_ancestors

    scope_ids = {orgao_id, *get_orgao_ancestors(orgao_id)}
    orgao_user_ids = {
        user_id
        for (user_id,) in (
            UserOrgao.query.with_entities(UserOrgao.user_id)
            .filter(UserOrgao.orgao_id.in_(scope_ids))
            .all()
        )
    }
    scoped_admin_ids = admin_ids.intersection(orgao_user_ids)
    if scoped_admin_ids:
        return scoped_admin_ids
    return admin_ids


def _filter_project_accessible_user_ids(project, user_ids):
    if not project or not user_ids:
        return set()

    from routes.orgao_scope import user_can_access_project

    users = User.query.filter(User.id.in_({int(user_id) for user_id in user_ids})).all()
    return {user.id for user in users if user_can_access_project(user, project)}


def resolve_project_owner_user_ids(project):
    if not project:
        return set()

    creator_entry = (
        ProjectHistory.query.filter(ProjectHistory.project_id == project.id)
        .filter(ProjectHistory.action_type.in_(("create", "seed_create")))
        .order_by(ProjectHistory.timestamp.asc(), ProjectHistory.id.asc())
        .first()
    )
    if creator_entry and creator_entry.user_id:
        owner_ids = _filter_project_accessible_user_ids(
            project, {creator_entry.user_id}
        )
        return owner_ids or _resolve_admin_ids_for_orgao(project.orgao_id)

    first_history_entry = (
        ProjectHistory.query.filter(ProjectHistory.project_id == project.id)
        .order_by(ProjectHistory.timestamp.asc(), ProjectHistory.id.asc())
        .first()
    )
    if first_history_entry and first_history_entry.user_id:
        total_history_count = ProjectHistory.query.filter(
            ProjectHistory.project_id == project.id
        ).count()
        if total_history_count == 1 and first_history_entry.action_type not in {
            "create",
            "seed_create",
        }:
            return _resolve_admin_ids_for_orgao(project.orgao_id)
        owner_ids = _filter_project_accessible_user_ids(
            project, {first_history_entry.user_id}
        )
        return owner_ids or _resolve_admin_ids_for_orgao(project.orgao_id)

    return _resolve_admin_ids_for_orgao(project.orgao_id)


def _get_task_responsavel_user_ids(task_id):
    responsavel_value = (
        Task.query.with_entities(Task.responsavel)
        .filter(Task.id == task_id, Task.responsavel.isnot(None))
        .scalar()
    )
    return _resolve_user_ids_from_names(_split_responsavel_names(responsavel_value))


def _get_task_comment_author_ids(task_id):
    return {
        user_id
        for (user_id,) in (
            TaskComment.query.with_entities(TaskComment.user_id)
            .filter(TaskComment.task_id == task_id)
            .distinct()
            .all()
        )
        if user_id
    }


def resolve_task_collaborator_user_ids(task):
    if not task:
        return set()

    recipient_ids = set()
    if task.created_by_id:
        recipient_ids.add(task.created_by_id)
    recipient_ids.update(_get_task_responsavel_user_ids(task.id))
    recipient_ids.update(_get_task_comment_author_ids(task.id))
    return recipient_ids


def notify_project_history_action(
    project_id,
    actor_user_id,
    action_type,
    action_description,
    old_value=None,
    new_value=None,
):
    if action_type in IGNORED_PROJECT_ACTION_TYPES:
        return 0

    project = db.session.get(Project, project_id)
    if not project:
        return 0

    owner_ids = resolve_project_owner_user_ids(project)
    if not owner_ids:
        return 0

    title = f'Atualização no projeto "{_truncate_text(project.titulo, 80)}"'
    message_parts = [_truncate_text(action_description, 220)]
    if old_value is not None or new_value is not None:
        old_text = _truncate_text(old_value or "vazio", 80)
        new_text = _truncate_text(new_value or "vazio", 80)
        message_parts.append(f'Antes: "{old_text}" | Depois: "{new_text}"')

    return create_user_notifications(
        owner_ids,
        actor_user_id=actor_user_id,
        event_type=f"project_{action_type}",
        title=title,
        message=" ".join([part for part in message_parts if part]).strip(),
        target_url=url_for("main.project_detail", project_id=project.id),
    )


def notify_project_invite(project, recipient_user_id, actor_user_id, papel):
    """Avisa o convidado do acesso concedido (S4/F3-17): sem e-mail, sem aceite.

    Ex.: `notify_project_invite(projeto, convidado.id, g.user.id, "leitor")`.
    """
    if not project or not recipient_user_id:
        return 0

    return create_user_notifications(
        [recipient_user_id],
        actor_user_id=actor_user_id,
        event_type="projeto_convite",
        title=f'Você foi convidado para o projeto "{_truncate_text(project.titulo, 80)}"',
        message=f"Seu acesso é de {papel}: você verá todo o conteúdo deste projeto.",
        target_url=url_for("main.project_detail", project_id=project.id),
    )


def _orgao_active_user_ids(orgao_id: int) -> set[int]:
    """Ativos com vínculo DIRETO no órgão — sem subárvore, como o share da coleção."""
    rows = (
        User.query.with_entities(User.id)
        .join(UserOrgao, UserOrgao.user_id == User.id)
        .filter(UserOrgao.orgao_id == orgao_id, User.deleted_at.is_(None))
        .all()
    )
    return {user_id for (user_id,) in rows}


def collection_share_recipient_ids(
    *, user_id: int | None = None, orgao_id: int | None = None
) -> set[int]:
    """Quem um share alcança: a pessoa, ou os ativos do órgão EXATO de lotação."""
    if user_id is not None:
        return {int(user_id)}
    if orgao_id is None:
        return set()
    return _orgao_active_user_ids(orgao_id)


EVENTO_COLECAO_CONVITE = "colecao_convite"
EVENTO_COLECAO_CONVITE_ACEITO = "colecao_convite_aceito"
EVENTO_COLECAO_CONVITE_RECUSADO = "colecao_convite_recusado"
EVENTO_COLECAO_PARTICIPANTE_SAIU = "colecao_participante_saiu"


def _colecao_target_url(colecao: ProjectCollection) -> str:
    # A página da coleção trata o estado "convite pendente" (Aceitar/Recusar).
    return f"/colecoes/{colecao.id}"


def notify_collection_invite(
    colecao: ProjectCollection,
    actor_user_id: int,
    papel: str,
    *,
    recipient_ids: set[int],
) -> int:
    """Convida para a coleção: o acesso só vale depois do aceite (sem e-mail).

    Disparo: share NOVO (pessoa ou membros ativos do órgão exato, um aviso por
    pessoa) e "reenviar". Upsert de papel e revogação não notificam. O antigo
    ``colecao_compartilhada`` fica só como histórico. Ex.:
    `notify_collection_invite(colecao, g.user.id, "viewer", recipient_ids={7})`.
    """
    if colecao is None or not recipient_ids:
        return 0
    rotulo = ROTULO_PAPEL_SHARE.get(papel, papel)
    return create_user_notifications(
        recipient_ids,
        actor_user_id=actor_user_id,
        event_type=EVENTO_COLECAO_CONVITE,
        title=f'Convite para a coleção "{_truncate_text(colecao.nome, 80)}"',
        message=(
            f"Você foi convidado como {rotulo}. Abra a coleção para aceitar ou "
            "recusar; os projetos só aparecem depois do aceite."
        ),
        target_url=_colecao_target_url(colecao),
    )


def _notify_collection_owner(
    colecao: ProjectCollection,
    ator: User,
    event_type: str,
    *,
    titulo: str,
    mensagem: str,
) -> int:
    """``titulo``/``mensagem`` são a frase INTEIRA de cada evento (``{nome}`` e
    ``{colecao}`` substituídos aqui): montar o verbo + "a coleção" num molde
    comum deu "saiu de a coleção" — a contração muda com a preposição."""
    nome = _truncate_text(getattr(ator, "name", "") or "Alguém", 80)
    nome_colecao = _truncate_text(colecao.nome, 80)
    return create_user_notifications(
        [colecao.owner_user_id],
        actor_user_id=ator.id,
        event_type=event_type,
        title=titulo.format(nome=nome, colecao=nome_colecao),
        message=mensagem.format(nome=nome, colecao=nome_colecao),
        target_url=_colecao_target_url(colecao),
    )


def notify_collection_invite_accepted(colecao: ProjectCollection, ator: User) -> int:
    """Avisa o DONO que ``ator`` aceitou o convite da coleção.

    Ex.: `notify_collection_invite_accepted(colecao, g.user)`.
    """
    return _notify_collection_owner(
        colecao,
        ator,
        EVENTO_COLECAO_CONVITE_ACEITO,
        titulo='{nome} aceitou o convite para a coleção "{colecao}"',
        mensagem="{nome} aceitou o convite para a sua coleção compartilhada.",
    )


def notify_collection_invite_declined(colecao: ProjectCollection, ator: User) -> int:
    """Avisa o DONO que ``ator`` recusou o convite da coleção."""
    return _notify_collection_owner(
        colecao,
        ator,
        EVENTO_COLECAO_CONVITE_RECUSADO,
        titulo='{nome} recusou o convite para a coleção "{colecao}"',
        mensagem="{nome} recusou o convite para a sua coleção compartilhada.",
    )


def notify_collection_member_left(colecao: ProjectCollection, ator: User) -> int:
    """Avisa o DONO que ``ator`` saiu da coleção (itens dele já foram podados)."""
    return _notify_collection_owner(
        colecao,
        ator,
        EVENTO_COLECAO_PARTICIPANTE_SAIU,
        titulo='{nome} saiu da coleção "{colecao}"',
        mensagem="{nome} saiu da sua coleção compartilhada.",
    )


def notify_task_event(
    task, actor_user_id, event_type, title, message, item_id=None, target_url=None
):
    if not task:
        return 0

    del item_id  # Mantido por compatibilidade de assinatura.
    recipient_ids = resolve_task_collaborator_user_ids(task)
    default_target_url = url_for("main.task_detail", task_id=task.id)

    return create_user_notifications(
        recipient_ids,
        actor_user_id=actor_user_id,
        event_type=event_type,
        title=title,
        message=_truncate_text(message, 260),
        target_url=target_url or default_target_url,
    )


def notify_task_assignment_change(
    task, item, actor_user_id, old_responsavel, new_responsavel
):
    if not task:
        return 0

    task_obj = item or task
    recipient_ids = resolve_task_collaborator_user_ids(task)
    recipient_ids.update(
        _resolve_user_ids_from_names(_split_responsavel_names(new_responsavel))
    )

    old_text = _truncate_text(old_responsavel or "Sem responsável", 70)
    new_text = _truncate_text(new_responsavel or "Sem responsável", 70)
    task_desc = _truncate_text(task_obj.descricao or f"Tarefa #{task_obj.id}", 90)

    return create_user_notifications(
        recipient_ids,
        actor_user_id=actor_user_id,
        event_type="task_assignment",
        title="Responsável atualizado na tarefa",
        message=f'A tarefa "{task_desc}" mudou de "{old_text}" para "{new_text}".',
        target_url=url_for("main.task_detail", task_id=task.id),
    )
