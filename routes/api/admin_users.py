"""Endpoints JSON do CRUD de usuários (Admin) consumidos pela SPA SvelteKit.

Fase 4 — Admin. Espelha o CRUD Jinja de ``routes/admin_users.py`` em endpoints
``/api/admin/usuarios*`` no envelope canônico, protegidos por
``api_admin_required`` (401 sem sessão, 403 para não-admin). Sucessor das rotas
Jinja ``/admin/users*`` (``list_users``/``add_user``/``edit_user``/``remove_cpf``/
``delete_user``), que foram CORTADAS na migração SPA — restaram só os helpers de
parse em ``routes/admin_users.py``.

Reaproveita os helpers de validação já existentes em ``routes/admin_users.py``
(``_parse_selected_orgaos``, ``_parse_cpf_govbr``, ``_list_orgaos_with_parent``),
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
from services.authorization import PAPEL_GESTOR, PAPEL_RANK
from services.password_policy import validate_password_strength
from time_utils import utc_now

from ..admin_users import (
    _list_orgaos_with_parent,
    _parse_cpf_govbr,
    _parse_selected_orgaos,
)
from ..blueprint import main_bp
from ..pagination import clamp_page
from .envelope import fail, ok
from .negotiation import api_admin_required
from .serializers import serialize_admin_user

_PER_PAGE = 20


def _serialize_orgao_option_row(
    row: tuple[int, str, str, int | None],
) -> dict[str, Any]:
    """Serializa uma linha de ``_list_orgaos_with_parent`` como opção de form.

    Args:
        row: Tupla ``(orgao_id, sigla, nome, pai_id)`` produzida por
            ``_list_orgaos_with_parent`` (ordenada por sigla).

    Returns:
        ``dict`` JSON-safe ``{id, sigla, nome, pai_id}`` — a árvore do seletor
        de órgãos é montada por ``pai_id`` no client.
    """
    orgao_id, sigla, nome, pai_id = row
    return {"id": orgao_id, "sigla": sigla, "nome": nome, "pai_id": pai_id}


def _orgao_options() -> list[dict[str, Any]]:
    """Opções de órgãos (ativos) com hierarquia para o form de usuário."""
    return [_serialize_orgao_option_row(row) for row in _list_orgaos_with_parent()]


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
    ordered = query.order_by(User.name)
    # `error_out=False` devolveria items=[] ecoando a página pedida; a UI não
    # distingue isso de "o filtro não achou ninguém".
    safe_page, total_pages = clamp_page(page, ordered.count(), _PER_PAGE)
    pagination = ordered.paginate(page=safe_page, per_page=_PER_PAGE, error_out=False)
    return ok(
        {"usuarios": [serialize_admin_user(user) for user in pagination.items]},
        meta={
            "page": safe_page,
            "per_page": _PER_PAGE,
            "total": pagination.total,
            "total_pages": total_pages,
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

    Vínculos de área: formato novo ``orgaos: [{"orgao_id", "papel"}]`` ou o antigo
    ``orgaos_responsavel: [id]`` (interpretado como ``gestor``) — ver
    ``_parse_orgao_papel_pairs``.

    Returns:
        Envelope ``{"ok": true, "data": {"usuario": {...}}}`` com HTTP 200 ao
        criar; ``fail(..., 422)`` em erro de validação.
    """
    payload = request.get_json(silent=True) or request.form
    orgao_pairs, invalid_orgaos, papel_error = _parse_orgao_papel_pairs(payload)
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
    if papel_error:
        return fail(papel_error, status=422, code="validation")
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
    new_user.set_orgaos_com_papeis(orgao_pairs)
    db.session.commit()
    return ok({"usuario": serialize_admin_user(new_user)})


@main_bp.route("/api/admin/usuarios/<int:user_id>", methods=["PUT"])
@api_admin_required
def api_admin_usuarios_update(user_id: int) -> Response | tuple[Response, int]:
    """Edita um usuário (envelope canônico), espelhando o POST de ``edit_user``.

    Preserva o comportamento do Jinja: ``username`` não é editável; órgãos
    inativos pré-vinculados são mantidos; o CPF só é alterado quando o vínculo
    Gov.br não está travado (``govbr_sub`` presente); o último administrador não
    pode ser despromovido; a senha só muda se uma nova for fornecida. Os vínculos
    aceitam os dois formatos de ``_parse_orgao_papel_pairs`` (novo com papel e
    ``orgaos_responsavel[]`` legado como ``gestor``).

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

    orgao_pairs, invalid_orgaos, papel_error = _resolve_update_orgao_pairs(
        user, payload
    )

    should_update_cpf = not hide_govbr_link_fields and "cpf_govbr" in payload
    cpf_govbr = user.cpf_govbr
    cpf_error = None
    if should_update_cpf:
        cpf_govbr, cpf_error = _parse_cpf_govbr(payload.get("cpf_govbr"))

    # Soft-delete C4: conta apenas administradores ATIVOS ao proteger o último.
    # Lock pessimista (bug 2.22): evita que dois requests concorrentes
    # despromovam ambos os 2 últimos admins antes de qualquer commit.
    if user.is_admin and not is_admin_flag and _lock_and_count_active_admins() <= 1:
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
    if papel_error:
        return fail(papel_error, status=422, code="validation")
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
    user.set_orgaos_com_papeis(orgao_pairs)

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
    # is None) — admins já removidos não contam como existentes. Lock
    # pessimista (bug 2.22): evita TOCTOU entre duas exclusões concorrentes.
    active_admins = _lock_and_count_active_admins()
    if user.is_admin and user.deleted_at is None and active_admins == 1:
        return fail(
            "Não é possível excluir o único administrador do sistema.",
            status=422,
            code="validation",
        )

    user.deleted_at = utc_now()
    db.session.commit()
    return ok({"deleted_id": user_id})


def _lock_and_count_active_admins() -> int:
    """Conta admins ativos com lock pessimista (evita TOCTOU concorrente).

    ``with_for_update()`` emite ``SELECT ... FOR UPDATE``, travando as linhas
    até o commit da transação corrente — dois requests despromovendo/excluindo
    os 2 últimos admins em paralelo deixam de passar ambos pela checagem
    (bug 2.22). No SQLite dos testes ``with_for_update`` é no-op; o lock real
    só existe em Postgres/produção.
    """
    admins = (
        User.query.filter(User.is_admin.is_(True), User.deleted_at.is_(None))
        .with_for_update()
        .all()
    )
    return len(admins)


def _get_orgao_ids(payload: Any) -> list[Any]:
    """Extrai a lista de ids de órgãos do payload (JSON list ou form getlist)."""
    if hasattr(payload, "getlist"):
        return payload.getlist("orgaos_responsavel")
    raw = payload.get("orgaos_responsavel")
    if raw is None:
        return []
    return raw if isinstance(raw, list) else [raw]


def _get_orgao_papel_entries(payload: Any) -> list[Any] | None:
    """Itens do payload NOVO ``orgaos`` (``[{orgao_id, papel}]``), ou ``None``.

    ``None`` significa "formato novo ausente" — o chamador cai na compat de
    ``orgaos_responsavel[]``. Requisições form-encoded não trafegam objetos, então
    só o formato antigo vale para elas.
    """
    if hasattr(payload, "getlist"):
        return None
    raw = payload.get("orgaos")
    if raw is None:
        return None
    return raw if isinstance(raw, list) else [raw]


def _split_orgao_papel_entry(entry: Any) -> tuple[Any, str]:
    """Extrai ``(orgao_id, papel)`` de um item do payload novo (default gestor)."""
    if not isinstance(entry, dict):
        return entry, PAPEL_GESTOR
    raw_id = entry.get("orgao_id", entry.get("id"))
    papel = str(entry.get("papel") or PAPEL_GESTOR).strip().lower()
    return raw_id, papel


def _first_invalid_papel_error(papeis: list[str]) -> str | None:
    """Mensagem 422 do primeiro papel fora da taxonomia (valor + esperados)."""
    for papel in papeis:
        if papel not in PAPEL_RANK:
            esperados = "|".join(PAPEL_RANK)
            return f"Papel inválido: {papel!r}. Esperado um de {esperados}."
    return None


def _papel_por_orgao_id(raw_pairs: list[tuple[Any, str]]) -> dict[int, str]:
    """Indexa o papel por ``orgao_id``; a primeira ocorrência do id vence."""
    papel_by_id: dict[int, str] = {}
    for raw_id, papel in raw_pairs:
        try:
            papel_by_id.setdefault(int(raw_id), papel)
        except (TypeError, ValueError):
            continue
    return papel_by_id


def _parse_orgao_papel_pairs(
    payload: Any,
) -> tuple[list[tuple[int, str]], list[str], str | None]:
    """Resolve os pares ``(orgao_id, papel)`` do payload, com compat do antigo.

    Formato novo: ``orgaos: [{"orgao_id": 3, "papel": "editor"}]``. Formato antigo
    (mantido para o deploy desacoplado do frontend): ``orgaos_responsavel: [3, 7]``
    — JSON ou form — em que todo vínculo é gravado como ``gestor``.

    Returns:
        Tupla ``(pares, orgaos_invalidos, papel_error)``.
    """
    entries = _get_orgao_papel_entries(payload)
    if entries is None:
        ids, invalid = _parse_selected_orgaos(_get_orgao_ids(payload))
        return [(orgao_id, PAPEL_GESTOR) for orgao_id in ids], invalid, None
    raw_pairs = [_split_orgao_papel_entry(entry) for entry in entries]
    ids, invalid = _parse_selected_orgaos([raw_id for raw_id, _ in raw_pairs])
    papel_by_id = _papel_por_orgao_id(raw_pairs)
    pares = [(orgao_id, papel_by_id[orgao_id]) for orgao_id in ids]
    papel_error = _first_invalid_papel_error([papel for _, papel in raw_pairs])
    return pares, invalid, papel_error


def _parse_bool(value: Any) -> bool:
    """Normaliza flags admin (``on``/``true``/``1``/bool) para ``bool``."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"on", "true", "1", "yes"}


def _inactive_current_pairs(
    user: User, selected_ids: set[int]
) -> list[tuple[int, str]]:
    """Vínculos a órgãos INATIVOS do usuário, com o papel atual preservado.

    Órgãos inativos não aparecem como opção em ``_list_orgaos_with_parent``, logo
    nunca voltam no payload — sem isto seriam apagados silenciosamente na edição.
    """
    return [
        (uo.orgao_id, uo.papel)
        for uo in user.orgaos
        if uo.orgao_id not in selected_ids
        and (orgao := db.session.get(OrgaoUnidade, uo.orgao_id)) is not None
        and not orgao.ativo
    ]


def _resolve_update_orgao_pairs(
    user: User, payload: Any
) -> tuple[list[tuple[int, str]], list[str], str | None]:
    """Resolve os pares (órgão, papel) da edição, preservando inativos vinculados.

    Sempre substitui o conjunto de vínculos (o form admin envia o estado completo
    dos órgãos), acrescido dos inativos pré-existentes.

    Args:
        user: Usuário sendo editado.
        payload: Payload da requisição (JSON ou form).

    Returns:
        Tupla ``(pares, orgaos_invalidos, papel_error)``.
    """
    pares, invalid_orgaos, papel_error = _parse_orgao_papel_pairs(payload)
    selected_ids = {orgao_id for orgao_id, _ in pares}
    pares.extend(_inactive_current_pairs(user, selected_ids))
    return pares, invalid_orgaos, papel_error
