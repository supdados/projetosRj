"""Endpoints JSON do CRUD de usuários (Admin) consumidos pela SPA SvelteKit.

Fase 4 — Admin. Espelha o CRUD Jinja de ``routes/admin_users.py`` em endpoints
``/api/admin/usuarios*`` no envelope canônico, protegidos por
``api_admin_required`` (401 sem sessão, 403 para não-admin). Sucessor das rotas
Jinja ``/admin/users*`` (``list_users``/``add_user``/``edit_user``/``remove_cpf``/
``delete_user``), que foram CORTADAS na migração SPA — restaram só os helpers de
parse em ``routes/admin_users.py``.

Reaproveita os helpers de validação já existentes em ``routes/admin_users.py``
(``_parse_selected_orgaos``, ``_parse_cpf_govbr``, ``_list_orgaos_with_depth``),
preservando o comportamento das rotas Jinja. As regras de negócio (CPF gov.br,
unicidade de username/CPF, proteção do último admin, vínculos a órgãos inativos)
são mantidas; erros de validação resultam em ``fail(..., 422, "validation")`` em
vez do ``flash`` + re-render do fluxo Jinja.

Anexa ao ``main_bp`` ÚNICO (``routes/blueprint.py``); NÃO cria blueprint novo e
NUNCA serializa ``password_hash`` nem ``govbr_sub``.
"""

from __future__ import annotations

from typing import Any

from flask import Response, g, request

from models import OrgaoUnidade, User, UserOrgao, db
from services.password_policy import validate_password_strength
from time_utils import utc_now

from ..admin_users import (
    _list_orgaos_with_depth,
    _parse_cpf_govbr,
    _parse_selected_orgaos,
)
from ..blueprint import main_bp
from .envelope import fail, ok
from .negotiation import api_admin_required
from .serializers import serialize_admin_user

_PER_PAGE = 20


def _serialize_orgao_depth_option(row: tuple[int, str, str, int]) -> dict[str, Any]:
    """Serializa uma linha de ``_list_orgaos_with_depth`` como opção de form.

    Args:
        row: Tupla ``(orgao_id, sigla, nome, depth)`` produzida por
            ``_list_orgaos_with_depth`` (já ordenada por profundidade/sigla).

    Returns:
        ``dict`` JSON-safe ``{id, sigla, nome, depth}`` para indentação de árvore
        no seletor de órgãos da tela.
    """
    orgao_id, sigla, nome, depth = row
    return {"id": orgao_id, "sigla": sigla, "nome": nome, "depth": depth}


def _orgao_options() -> list[dict[str, Any]]:
    """Opções de órgãos (ativos) com profundidade para o form de usuário."""
    return [_serialize_orgao_depth_option(row) for row in _list_orgaos_with_depth()]


@main_bp.route("/api/admin/usuarios", methods=["GET"])
@api_admin_required
def api_admin_usuarios_list() -> Response | tuple[Response, int]:
    """Lista paginada de usuários para o painel admin (envelope canônico).

    Sucessor da extinta rota Jinja ``list_users`` (``/admin/users``): ordena por
    ``name`` e pagina em blocos de 10. Cada usuário é serializado por
    ``serialize_admin_user`` (sem segredos) com os órgãos vinculados.

    Returns:
        Envelope ``{"ok": true, "data": {"usuarios": [...]}, "meta": {...}}`` com
        HTTP 200. ``api_admin_required`` devolve 401/403 JSON conforme a sessão.
    """
    page = request.args.get("page", 1, type=int)
    search = (request.args.get("q") or "").strip()
    area_id = request.args.get("area_id", type=int)
    # Soft-delete C4: a listagem admin mostra apenas usuários ATIVOS; removidos
    # (deleted_at não nulo) somem da gestão mas continuam no histórico.
    query = User.query.filter(User.deleted_at.is_(None))
    if search:
        like = f"%{search}%"
        query = query.filter(
            db.or_(
                User.name.ilike(like),
                User.username.ilike(like),
            )
        )
    if area_id:
        query = query.filter(User.orgaos.any(UserOrgao.orgao_id == area_id))
    pagination = query.order_by(User.name).paginate(
        page=page, per_page=_PER_PAGE, error_out=False
    )
    return ok(
        {"usuarios": [serialize_admin_user(user) for user in pagination.items]},
        meta={
            "page": pagination.page,
            "per_page": _PER_PAGE,
            "total": pagination.total,
            "total_pages": pagination.pages,
        },
    )


@main_bp.route("/api/admin/usuarios/<int:user_id>", methods=["GET"])
@api_admin_required
def api_admin_usuarios_detail(user_id: int) -> Response | tuple[Response, int]:
    """Dados de um usuário + opções de órgãos para o form de edição.

    Espelha o GET de ``edit_user``: devolve o usuário serializado, os ids dos
    órgãos vinculados e o catálogo de órgãos (com profundidade) para o seletor.

    Args:
        user_id: ID do usuário a carregar.

    Returns:
        Envelope ``{"ok": true, "data": {"usuario", "orgao_ids",
        "orgaos_options"}}`` com HTTP 200; ``fail(..., 404, "not_found")`` quando
        o usuário não existe.
    """
    user = db.session.get(User, user_id)
    if user is None:
        return fail("Usuário não encontrado.", status=404, code="not_found")
    return ok(
        {
            "usuario": serialize_admin_user(user),
            "orgao_ids": [uo.orgao_id for uo in user.orgaos],
            "orgaos_options": _orgao_options(),
        }
    )


@main_bp.route("/api/admin/usuarios", methods=["POST"])
@api_admin_required
def api_admin_usuarios_create() -> Response | tuple[Response, int]:
    """Cria um usuário (envelope canônico), espelhando o POST de ``add_user``.

    Reaproveita ``_parse_selected_orgaos`` e ``_parse_cpf_govbr`` e preserva as
    validações: campos obrigatórios, CPF gov.br válido, órgãos válidos e
    unicidade de ``username``/``cpf_govbr``. Aceita JSON ou form. Falhas de
    validação => ``fail(..., 422, "validation")``.

    Returns:
        Envelope ``{"ok": true, "data": {"usuario": {...}}}`` com HTTP 200 ao
        criar; ``fail(..., 422)`` em erro de validação.
    """
    payload = request.get_json(silent=True) or request.form
    selected_orgao_ids, invalid_orgaos = _parse_selected_orgaos(_get_orgao_ids(payload))
    username = (payload.get("username") or "").strip()
    name = (payload.get("name") or "").strip()
    password = payload.get("password") or ""
    orgao = (payload.get("orgao") or "").strip()
    is_admin_flag = _parse_bool(payload.get("is_admin"))
    cpf_govbr, cpf_error = _parse_cpf_govbr(payload.get("cpf_govbr"))

    if not username or not name or not password:
        return fail(
            "Username, Nome Completo e Senha são obrigatórios.",
            status=422,
            code="validation",
        )
    password_error = validate_password_strength(password)
    if password_error:
        return fail(password_error, status=422, code="validation")
    if cpf_error:
        return fail(f"CPF gov.br inválido: {cpf_error}", status=422, code="validation")
    if invalid_orgaos:
        return fail(
            f'Órgão(s) inválido(s): {", ".join(invalid_orgaos)}.',
            status=422,
            code="validation",
        )
    if User.query.filter_by(username=username).first():
        return fail(
            "Este nome de usuário já está em uso. Escolha outro.",
            status=422,
            code="validation",
        )
    if cpf_govbr and User.query.filter_by(cpf_govbr=cpf_govbr).first():
        return fail(
            "Já existe um usuário vinculado a este CPF gov.br.",
            status=422,
            code="validation",
        )

    new_user = User(
        username=username,
        name=name,
        orgao=orgao or None,
        is_admin=is_admin_flag,
        cpf_govbr=cpf_govbr,
    )
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.flush()
    new_user.set_orgaos(selected_orgao_ids)
    db.session.commit()
    return ok({"usuario": serialize_admin_user(new_user)})


@main_bp.route("/api/admin/usuarios/<int:user_id>", methods=["PUT"])
@api_admin_required
def api_admin_usuarios_update(user_id: int) -> Response | tuple[Response, int]:
    """Edita um usuário (envelope canônico), espelhando o POST de ``edit_user``.

    Preserva o comportamento do Jinja: ``username`` não é editável; órgãos
    inativos pré-vinculados são mantidos; o CPF só é alterado quando o vínculo
    Gov.br não está travado (``govbr_sub`` presente); o último administrador não
    pode ser despromovido; a senha só muda se uma nova for fornecida.

    Args:
        user_id: ID do usuário a editar.

    Returns:
        Envelope ``{"ok": true, "data": {"usuario": {...}}}`` com HTTP 200; ou
        ``fail(..., 422)`` em erro de validação; ``fail(..., 404)`` se não existe.
    """
    user = db.session.get(User, user_id)
    if user is None:
        return fail("Usuário não encontrado.", status=404, code="not_found")

    payload = request.get_json(silent=True) or request.form
    hide_govbr_link_fields = bool(user.cpf_govbr and user.govbr_sub)

    name = (payload.get("name") or "").strip()
    orgao = (payload.get("orgao") or "").strip()
    is_admin_flag = _parse_bool(payload.get("is_admin"))

    selected_orgao_ids, invalid_orgaos = _resolve_update_orgao_ids(user, payload)

    should_update_cpf = not hide_govbr_link_fields and "cpf_govbr" in payload
    cpf_govbr = user.cpf_govbr
    cpf_error = None
    if should_update_cpf:
        cpf_govbr, cpf_error = _parse_cpf_govbr(payload.get("cpf_govbr"))

    # Soft-delete C4: conta apenas administradores ATIVOS ao proteger o último.
    if (
        user.is_admin
        and not is_admin_flag
        and User.query.filter(
            User.is_admin.is_(True), User.deleted_at.is_(None)
        ).count()
        <= 1
    ):
        return fail(
            "Não é possível remover o status de administrador do único "
            "administrador existente.",
            status=422,
            code="validation",
        )
    if invalid_orgaos:
        return fail(
            f'Órgão(s) inválido(s): {", ".join(invalid_orgaos)}.',
            status=422,
            code="validation",
        )
    if cpf_error:
        return fail(f"CPF gov.br inválido: {cpf_error}", status=422, code="validation")
    if (
        should_update_cpf
        and cpf_govbr
        and User.query.filter(User.cpf_govbr == cpf_govbr, User.id != user.id).first()
    ):
        return fail(
            "Já existe um usuário vinculado a este CPF gov.br.",
            status=422,
            code="validation",
        )

    user.name = name
    user.orgao = orgao or None
    user.is_admin = is_admin_flag
    if should_update_cpf:
        old_cpf = user.cpf_govbr
        user.cpf_govbr = cpf_govbr
        if not cpf_govbr or (old_cpf and old_cpf != cpf_govbr):
            user.govbr_sub = None
    user.set_orgaos(selected_orgao_ids)

    new_password = payload.get("password")
    if new_password:
        password_error = validate_password_strength(new_password)
        if password_error:
            return fail(password_error, status=422, code="validation")
        user.set_password(new_password)

    db.session.commit()
    return ok({"usuario": serialize_admin_user(user)})


@main_bp.route("/api/admin/usuarios/<int:user_id>/remover-cpf", methods=["POST"])
@api_admin_required
def api_admin_usuarios_remove_cpf(user_id: int) -> Response | tuple[Response, int]:
    """Remove CPF e vínculo gov.br de um usuário, espelhando ``remove_cpf``.

    Args:
        user_id: ID do usuário cujo vínculo gov.br será removido.

    Returns:
        Envelope ``{"ok": true, "data": {"usuario": {...}}}`` com HTTP 200;
        ``fail(..., 404)`` quando o usuário não existe.
    """
    user = db.session.get(User, user_id)
    if user is None:
        return fail("Usuário não encontrado.", status=404, code="not_found")
    user.cpf_govbr = None
    user.govbr_sub = None
    db.session.commit()
    return ok({"usuario": serialize_admin_user(user)})


@main_bp.route("/api/admin/usuarios/<int:user_id>", methods=["DELETE"])
@api_admin_required
def api_admin_usuarios_delete(user_id: int) -> Response | tuple[Response, int]:
    """Remove (soft-delete) um usuário, preservando TODO o histórico (C4).

    SOFT-DELETE: marca ``user.deleted_at`` em vez de apagar a linha. Eventos,
    etapas, tarefas, comentários, anexos e ``project_history`` permanecem intactos
    e atribuídos ao usuário, que passa a aparecer como "(removido)". NUNCA
    cascateia/apaga dados — por isso não há mais try/except de IntegrityError de FK.

    Preserva as proteções: o admin não pode se auto-excluir e o único
    administrador ATIVO do sistema não pode ser removido.

    Args:
        user_id: ID do usuário a remover.

    Returns:
        Envelope ``{"ok": true, "data": {"deleted_id": <id>}}`` com HTTP 200; ou
        ``fail(..., 422, "validation")`` quando a remoção é proibida;
        ``fail(..., 404)`` quando o usuário não existe.
    """
    user = db.session.get(User, user_id)
    if user is None:
        return fail("Usuário não encontrado.", status=404, code="not_found")

    if user.id == g.user.id:
        return fail(
            "Você não pode excluir sua própria conta de administrador.",
            status=422,
            code="validation",
        )
    # O guard do "único admin" conta apenas administradores ATIVOS (deleted_at
    # is None) — admins já removidos não contam como existentes.
    active_admins = User.query.filter(
        User.is_admin.is_(True), User.deleted_at.is_(None)
    ).count()
    if user.is_admin and user.deleted_at is None and active_admins == 1:
        return fail(
            "Não é possível excluir o único administrador do sistema.",
            status=422,
            code="validation",
        )

    user.deleted_at = utc_now()
    db.session.commit()
    return ok({"deleted_id": user_id})


def _get_orgao_ids(payload: Any) -> list[Any]:
    """Extrai a lista de ids de órgãos do payload (JSON list ou form getlist)."""
    if hasattr(payload, "getlist"):
        return payload.getlist("orgaos_responsavel")
    raw = payload.get("orgaos_responsavel")
    if raw is None:
        return []
    return raw if isinstance(raw, list) else [raw]


def _parse_bool(value: Any) -> bool:
    """Normaliza flags admin (``on``/``true``/``1``/bool) para ``bool``."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"on", "true", "1", "yes"}


def _resolve_update_orgao_ids(user: User, payload: Any) -> tuple[list[int], list[str]]:
    """Resolve os órgãos a vincular na edição, preservando inativos pré-vinculados.

    Espelha a lógica do POST de ``edit_user``: vínculos a órgãos inativos (que não
    aparecem como checkbox em ``_list_orgaos_with_depth``) são preservados para
    não serem apagados silenciosamente. Sempre substitui o conjunto de vínculos
    (o form admin sempre envia o estado completo dos órgãos).

    Args:
        user: Usuário sendo editado.
        payload: Payload da requisição (JSON ou form).

    Returns:
        Tupla ``(selected_orgao_ids, invalid_orgaos)``.
    """
    selected_orgao_ids, invalid_orgaos = _parse_selected_orgaos(_get_orgao_ids(payload))
    current_orgao_ids = [uo.orgao_id for uo in user.orgaos]
    inactive_current_ids = {
        oid
        for oid in current_orgao_ids
        if (o := db.session.get(OrgaoUnidade, oid)) is not None and not o.ativo
    }
    for oid in inactive_current_ids:
        if oid not in selected_orgao_ids:
            selected_orgao_ids.append(oid)
    return selected_orgao_ids, invalid_orgaos
