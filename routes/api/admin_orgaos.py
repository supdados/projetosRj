"""Endpoints JSON do CRUD de Órgãos (árvore) e Tipos (Admin) para a SPA.

Fase 4 — Admin. Espelha o CRUD Jinja de ``routes/admin_orgaos.py`` em endpoints
``/api/admin/orgaos*`` e ``/api/admin/orgaos/tipos*`` no envelope canônico,
protegidos por ``api_admin_required`` (401 sem sessão, 403 para não-admin). É
ADITIVO: as rotas Jinja (``list_orgaos``/``add_orgao``/``edit_orgao``/...) e os
endpoints JSON legados consumidos pelo admin JS (``move``/``reorder``/
``toggle-ativo`` sob ``/admin/orgaos/*``) permanecem intactos (strangler).

Reaproveita TODOS os helpers de validação/contexto já existentes em
``routes/admin_orgaos.py`` (``_candidate_pais``, ``_prepare_orgao_catalogs``,
``_normalize_tipo_form``, ``_invalid_orgao_type_level_changes``) e em
``routes/orgao_tree.py`` (``normalize_orgao_form``, ``validate_orgao_move``,
``is_valid_parent_tipo``, ``compute_orgao_depth``, ``rebuild_orgao_closure``,
etc.), preservando o comportamento das rotas Jinja. As regras de negócio
(hierarquia de tipos, níveis, profundidade máxima) são mantidas; erros de
validação => ``fail(..., 422, "validation")`` e conflitos => ``fail(..., 409,
"validation")`` em vez do ``flash`` + redirect do fluxo Jinja.

Anexa ao ``main_bp`` ÚNICO (``routes/blueprint.py``); NÃO cria blueprint novo.
RESTificação (PUT/DELETE) marcada como cleanup futuro — aqui usamos POST,
espelhando as rotas Flask existentes (o cliente usa ``client.post`` com
``X-CSRFToken``).
"""

from __future__ import annotations

from typing import Any

from flask import Response, request

from models import OrgaoTipo, OrgaoUnidade, db
from models.orgao import MAX_DEPTH

from ..admin_orgaos import (
    _candidate_pais,
    _invalid_orgao_type_level_changes,
    _normalize_tipo_form,
    _prepare_orgao_catalogs,
)
from ..blueprint import main_bp
from ..orgao_tree import (
    compute_orgao_depth,
    get_orgao_tipo_options,
    get_tipo_rank_map,
    is_valid_parent_tipo,
    normalize_orgao_form,
    rebuild_orgao_closure,
    validate_orgao_move,
)
from .envelope import fail, ok
from .negotiation import api_admin_required
from .serializers import (
    serialize_orgao_form,
    serialize_orgao_node,
    serialize_orgao_tipo,
)


def _orgao_catalogs() -> dict[str, Any]:
    """Catálogos auxiliares para os forms da árvore (tipos + ranks).

    Returns:
        ``{"tipos": [...], "tipo_rank": {nome: nivel}, "max_depth": int}``.
    """
    return {
        "tipos": [
            serialize_orgao_tipo(tipo)
            for tipo in get_orgao_tipo_options(include_inactive=True)
        ],
        "tipo_rank": get_tipo_rank_map(),
        "max_depth": MAX_DEPTH,
    }


def _candidate_pais_payload(orgao: OrgaoUnidade | None) -> list[dict[str, Any]]:
    """Serializa os candidatos a pai (id/sigla/nome) para o seletor do form."""
    return [
        {"id": pai.id, "sigla": pai.sigla, "nome": pai.nome}
        for pai in _candidate_pais(orgao)
    ]


# ---------------------------------------------------------------------------
# Árvore de órgãos
# ---------------------------------------------------------------------------


@main_bp.route("/api/admin/orgaos", methods=["GET"])
@api_admin_required
def api_admin_orgaos_tree() -> Response | tuple[Response, int]:
    """Árvore completa de órgãos + catálogos (envelope canônico).

    Espelha ``list_orgaos`` (``/admin/orgaos``): prepara os catálogos
    (``_prepare_orgao_catalogs`` — tipos-padrão + backfill de ``tipo_id``) e
    serializa as raízes recursivamente (``serialize_orgao_node`` inclui
    ``filhos``). Acompanha os catálogos (tipos, candidatos a pai, ``tipo_rank``,
    ``max_depth``) usados pelos forms.

    Returns:
        Envelope ``{"ok": true, "data": {"arvore", "tipos", "candidatos_pai",
        "tipo_rank", "max_depth", "total"}}`` com HTTP 200.
    """
    _prepare_orgao_catalogs()
    raizes = (
        OrgaoUnidade.query.filter(OrgaoUnidade.pai_id.is_(None))
        .order_by(OrgaoUnidade.ordem, OrgaoUnidade.sigla)
        .all()
    )
    total = OrgaoUnidade.query.count()
    catalogs = _orgao_catalogs()
    return ok(
        {
            "arvore": [serialize_orgao_node(raiz) for raiz in raizes],
            "candidatos_pai": _candidate_pais_payload(None),
            "total": total,
            **catalogs,
        }
    )


@main_bp.route("/api/admin/orgaos/<int:orgao_id>", methods=["GET"])
@api_admin_required
def api_admin_orgaos_detail(orgao_id: int) -> Response | tuple[Response, int]:
    """Dados de um órgão para o form de edição + candidatos a pai.

    Espelha o GET de ``edit_orgao``: devolve o órgão serializado
    (``serialize_orgao_form``), os candidatos a pai (excluindo ele e seus
    descendentes) e os catálogos de tipos.

    Args:
        orgao_id: ID do órgão a carregar.

    Returns:
        Envelope com ``{"orgao", "is_root", "candidatos_pai", ...catalogos}``;
        ``fail(..., 404, "not_found")`` quando não existe.
    """
    _prepare_orgao_catalogs()
    orgao = db.session.get(OrgaoUnidade, orgao_id)
    if orgao is None:
        return fail("Órgão não encontrado.", status=404, code="not_found")
    return ok(
        {
            "orgao": serialize_orgao_form(orgao),
            "is_root": orgao.pai_id is None,
            "candidatos_pai": _candidate_pais_payload(orgao),
            **_orgao_catalogs(),
        }
    )


@main_bp.route("/api/admin/orgaos", methods=["POST"])
@api_admin_required
def api_admin_orgaos_create() -> Response | tuple[Response, int]:
    """Cria um órgão (envelope canônico), espelhando o POST de ``add_orgao``.

    Reaproveita ``normalize_orgao_form`` (que já valida tipo/pai/hierarquia) e
    preserva a regra de profundidade máxima (``MAX_DEPTH``) e a determinação de
    ``is_root`` (primeiro órgão sem pai). Erros de validação =>
    ``fail(..., 422)``; profundidade excedida => ``fail(..., 409)``.

    Returns:
        Envelope ``{"ok": true, "data": {"orgao": {...}}}`` com HTTP 200 ao
        criar.
    """
    _prepare_orgao_catalogs()
    payload = request.get_json(silent=True) or request.form
    has_root = (
        OrgaoUnidade.query.filter(OrgaoUnidade.pai_id.is_(None)).first() is not None
    )
    is_root = not has_root

    data, error = normalize_orgao_form(payload, is_root=is_root)
    if error:
        return fail(error, status=422, code="validation")

    if not is_root and data["pai_id"] is not None:
        pai = db.session.get(OrgaoUnidade, data["pai_id"])
        if pai is None:
            return fail("Órgão pai não encontrado.", status=422, code="validation")
        if compute_orgao_depth(pai) + 1 > MAX_DEPTH:
            return fail(
                f"Profundidade máxima de {MAX_DEPTH} níveis excedida.",
                status=409,
                code="validation",
            )

    try:
        novo = OrgaoUnidade(**data)
        db.session.add(novo)
        db.session.flush()
        rebuild_orgao_closure()
        db.session.commit()
    except Exception as exc:  # noqa: BLE001 — espelha o except do Jinja
        db.session.rollback()
        return fail(f"Erro ao criar órgão: {exc}", status=409, code="validation")

    return ok({"orgao": serialize_orgao_form(novo)})


@main_bp.route("/api/admin/orgaos/<int:orgao_id>", methods=["POST"])
@api_admin_required
def api_admin_orgaos_update(orgao_id: int) -> Response | tuple[Response, int]:
    """Edita um órgão (envelope canônico), espelhando o POST de ``edit_orgao``.

    Reaproveita ``normalize_orgao_form``, ``validate_orgao_move`` (ao trocar de
    pai) e ``is_valid_parent_tipo`` (ao trocar o tipo, validando contra os
    filhos). Preserva ``is_root`` (órgão sem pai não muda de pai).

    Args:
        orgao_id: ID do órgão a editar.

    Returns:
        Envelope ``{"ok": true, "data": {"orgao": {...}}}``; ``fail(..., 422)``
        em validação; ``fail(..., 404)`` se não existe; ``fail(..., 409)`` em
        conflito de movimentação/persistência.
    """
    _prepare_orgao_catalogs()
    orgao = db.session.get(OrgaoUnidade, orgao_id)
    if orgao is None:
        return fail("Órgão não encontrado.", status=404, code="not_found")
    is_root = orgao.pai_id is None

    payload = request.get_json(silent=True) or request.form
    data, error = normalize_orgao_form(payload, is_root=is_root)
    if error:
        return fail(error, status=422, code="validation")

    if not is_root and data["pai_id"] != orgao.pai_id:
        move_error = validate_orgao_move(orgao, data["pai_id"], child_tipo=data["tipo"])
        if move_error:
            return fail(move_error, status=409, code="validation")

    if data["tipo"] != orgao.tipo:
        for filho in orgao.filhos:
            if not is_valid_parent_tipo(data["tipo"], filho.tipo):
                return fail(
                    f'Tipo "{data["tipo"]}" inválido: o filho "{filho.sigla}" '
                    f'é do tipo "{filho.tipo}".',
                    status=409,
                    code="validation",
                )

    try:
        orgao.nome = data["nome"]
        orgao.sigla = data["sigla"]
        orgao.tipo = data["tipo"]
        orgao.tipo_id = data["tipo_id"]
        if not is_root:
            orgao.pai_id = data["pai_id"]
        orgao.ordem = data["ordem"]
        orgao.ativo = data["ativo"]
        orgao.codigo_externo = data["codigo_externo"]
        orgao.data_inicio_vigencia = data["data_inicio_vigencia"]
        orgao.data_fim_vigencia = data["data_fim_vigencia"]
        rebuild_orgao_closure()
        db.session.commit()
    except Exception as exc:  # noqa: BLE001 — espelha o except do Jinja
        db.session.rollback()
        return fail(f"Erro ao atualizar órgão: {exc}", status=409, code="validation")

    return ok({"orgao": serialize_orgao_form(orgao)})


@main_bp.route("/api/admin/orgaos/<int:orgao_id>/delete", methods=["POST"])
@api_admin_required
def api_admin_orgaos_delete(orgao_id: int) -> Response | tuple[Response, int]:
    """Exclui um órgão (envelope canônico), espelhando ``delete_orgao``.

    Preserva as proteções: órgão com filhos não pode ser excluído (mova as
    subunidades antes) e o órgão raiz não pode ser excluído.

    Args:
        orgao_id: ID do órgão a excluir.

    Returns:
        Envelope ``{"ok": true, "data": {"deleted_id": <id>}}``; ``fail(..., 409)``
        quando há filhos ou é raiz; ``fail(..., 404)`` se não existe.
    """
    orgao = db.session.get(OrgaoUnidade, orgao_id)
    if orgao is None:
        return fail("Órgão não encontrado.", status=404, code="not_found")
    if orgao.filhos:
        return fail(
            "Mova as subunidades antes de excluir.", status=409, code="validation"
        )
    if orgao.pai_id is None:
        return fail(
            "Não é possível excluir o órgão raiz.", status=409, code="validation"
        )

    try:
        db.session.delete(orgao)
        db.session.flush()
        rebuild_orgao_closure()
        db.session.commit()
    except Exception as exc:  # noqa: BLE001 — espelha o except do Jinja
        db.session.rollback()
        return fail(f"Erro ao excluir órgão: {exc}", status=409, code="validation")

    return ok({"deleted_id": orgao_id})


def _parse_pai_id(payload: Any) -> tuple[int | None, str | None]:
    """Normaliza ``pai_id`` (None/string/int) do payload de movimentação."""
    raw = payload.get("pai_id")
    if raw in (None, "", "None", "null"):
        return None, None
    try:
        return int(raw), None
    except (TypeError, ValueError):
        return None, "Órgão pai inválido."


@main_bp.route("/api/admin/orgaos/<int:orgao_id>/move", methods=["POST"])
@api_admin_required
def api_admin_orgaos_move(orgao_id: int) -> Response | tuple[Response, int]:
    """Move um órgão para um novo pai, espelhando ``move_orgao``.

    Reaproveita ``validate_orgao_move`` (ciclo, hierarquia de tipos,
    profundidade) e recalcula ``ordem`` ao final da lista de irmãos. Aceita JSON
    ou form (``pai_id``).

    Args:
        orgao_id: ID do órgão a mover.

    Returns:
        Envelope ``{"ok": true, "data": {"orgao": {...}}}``; ``fail(..., 422/409)``
        em validação; ``fail(..., 404)`` se não existe.
    """
    orgao = db.session.get(OrgaoUnidade, orgao_id)
    if orgao is None:
        return fail("Órgão não encontrado.", status=404, code="not_found")

    payload = request.get_json(silent=True) or request.form
    new_pai_id, parse_error = _parse_pai_id(payload)
    if parse_error:
        return fail(parse_error, status=422, code="validation")

    move_error = validate_orgao_move(orgao, new_pai_id)
    if move_error:
        return fail(move_error, status=409, code="validation")

    try:
        orgao.pai_id = new_pai_id
        if new_pai_id is not None:
            siblings_count = (
                OrgaoUnidade.query.filter(OrgaoUnidade.pai_id == new_pai_id)
                .filter(OrgaoUnidade.id != orgao.id)
                .count()
            )
            orgao.ordem = siblings_count
        rebuild_orgao_closure()
        db.session.commit()
    except Exception as exc:  # noqa: BLE001 — espelha o except do Jinja
        db.session.rollback()
        return fail(f"Erro ao mover órgão: {exc}", status=409, code="validation")

    return ok({"orgao": serialize_orgao_form(orgao)})


@main_bp.route("/api/admin/orgaos/<int:orgao_id>/reorder", methods=["POST"])
@api_admin_required
def api_admin_orgaos_reorder(orgao_id: int) -> Response | tuple[Response, int]:
    """Reordena um órgão entre os irmãos, espelhando ``reorder_orgao``.

    Aceita ``direction`` ("up"/"down") via JSON ou form, espelhando a troca de
    ``ordem`` com o irmão adjacente. No-op (idempotente) quando já está no
    extremo da lista.

    Args:
        orgao_id: ID do órgão a reordenar.

    Returns:
        Envelope ``{"ok": true, "data": {"orgao": {...}}}``; ``fail(..., 422)``
        quando a direção é inválida; ``fail(..., 404)`` se não existe.
    """
    orgao = db.session.get(OrgaoUnidade, orgao_id)
    if orgao is None:
        return fail("Órgão não encontrado.", status=404, code="not_found")

    payload = request.get_json(silent=True) or request.form
    direction = (payload.get("direction") or "").lower()
    if direction not in ("up", "down"):
        return fail("Direção inválida.", status=422, code="validation")

    siblings = (
        OrgaoUnidade.query.filter(OrgaoUnidade.pai_id == orgao.pai_id)
        .order_by(OrgaoUnidade.ordem, OrgaoUnidade.sigla)
        .all()
    )
    indices = {s.id: i for i, s in enumerate(siblings)}
    idx = indices.get(orgao.id)
    if idx is None:
        return ok({"orgao": serialize_orgao_form(orgao)})

    target_idx = idx - 1 if direction == "up" else idx + 1
    if target_idx < 0 or target_idx >= len(siblings):
        return ok({"orgao": serialize_orgao_form(orgao)})

    other = siblings[target_idx]
    try:
        orgao.ordem, other.ordem = other.ordem, orgao.ordem
        if orgao.ordem == other.ordem:
            orgao.ordem = target_idx
            other.ordem = idx
        db.session.commit()
    except Exception as exc:  # noqa: BLE001 — espelha o except do Jinja
        db.session.rollback()
        return fail(f"Erro ao reordenar: {exc}", status=409, code="validation")

    return ok({"orgao": serialize_orgao_form(orgao)})


@main_bp.route("/api/admin/orgaos/<int:orgao_id>/toggle-ativo", methods=["POST"])
@api_admin_required
def api_admin_orgaos_toggle_ativo(orgao_id: int) -> Response | tuple[Response, int]:
    """Alterna o status ativo/inativo de um órgão, espelhando ``toggle_orgao_ativo``.

    Args:
        orgao_id: ID do órgão a alternar.

    Returns:
        Envelope ``{"ok": true, "data": {"orgao": {...}}}``; ``fail(..., 404)``
        se não existe; ``fail(..., 409)`` em erro de persistência.
    """
    orgao = db.session.get(OrgaoUnidade, orgao_id)
    if orgao is None:
        return fail("Órgão não encontrado.", status=404, code="not_found")
    try:
        orgao.ativo = not orgao.ativo
        db.session.commit()
    except Exception as exc:  # noqa: BLE001 — espelha o except do Jinja
        db.session.rollback()
        return fail(f"Erro ao alterar status: {exc}", status=409, code="validation")
    return ok({"orgao": serialize_orgao_form(orgao)})


# ---------------------------------------------------------------------------
# Tipos de órgão
# ---------------------------------------------------------------------------


@main_bp.route("/api/admin/orgaos/tipos", methods=["GET"])
@api_admin_required
def api_admin_orgao_tipos_list() -> Response | tuple[Response, int]:
    """Lista de tipos de órgão + uso (envelope), espelhando ``list_orgao_tipos``.

    Prepara catálogos (``_prepare_orgao_catalogs``) e devolve todos os tipos
    (inclusive inativos) com o contador de uso (quantos órgãos referenciam cada
    ``tipo_id``).

    Returns:
        Envelope ``{"ok": true, "data": {"tipos": [...], "usage_counts": {...}}}``
        com HTTP 200.
    """
    _prepare_orgao_catalogs()
    tipos = get_orgao_tipo_options(include_inactive=True)
    usage_counts = {
        tipo_id: count
        for tipo_id, count in db.session.query(
            OrgaoUnidade.tipo_id, db.func.count(OrgaoUnidade.id)
        )
        .group_by(OrgaoUnidade.tipo_id)
        .all()
    }
    return ok(
        {
            "tipos": [serialize_orgao_tipo(tipo) for tipo in tipos],
            "usage_counts": {str(k): v for k, v in usage_counts.items() if k},
        }
    )


@main_bp.route("/api/admin/orgaos/tipos/<int:tipo_id>", methods=["GET"])
@api_admin_required
def api_admin_orgao_tipos_detail(tipo_id: int) -> Response | tuple[Response, int]:
    """Dados de um tipo para o form de edição, espelhando o GET de ``edit_orgao_tipo``.

    Args:
        tipo_id: ID do tipo a carregar.

    Returns:
        Envelope ``{"ok": true, "data": {"tipo": {...}}}``; ``fail(..., 404)``
        quando não existe.
    """
    _prepare_orgao_catalogs()
    tipo = db.session.get(OrgaoTipo, tipo_id)
    if tipo is None:
        return fail("Tipo de órgão não encontrado.", status=404, code="not_found")
    return ok({"tipo": serialize_orgao_tipo(tipo)})


@main_bp.route("/api/admin/orgaos/tipos", methods=["POST"])
@api_admin_required
def api_admin_orgao_tipos_create() -> Response | tuple[Response, int]:
    """Cria um tipo de órgão (envelope), espelhando o POST de ``add_orgao_tipo``.

    Reaproveita ``_normalize_tipo_form`` (valida nome/slug/nível e unicidade).
    Erros de validação => ``fail(..., 422)``; tipos novos são ``is_system=False``.

    Returns:
        Envelope ``{"ok": true, "data": {"tipo": {...}}}`` com HTTP 200 ao criar.
    """
    _prepare_orgao_catalogs()
    payload = request.get_json(silent=True) or request.form
    data, error = _normalize_tipo_form(payload)
    if error:
        return fail(error, status=422, code="validation")
    tipo = OrgaoTipo(**data, is_system=False)
    db.session.add(tipo)
    db.session.commit()
    return ok({"tipo": serialize_orgao_tipo(tipo)})


@main_bp.route("/api/admin/orgaos/tipos/<int:tipo_id>", methods=["POST"])
@api_admin_required
def api_admin_orgao_tipos_update(tipo_id: int) -> Response | tuple[Response, int]:
    """Edita um tipo de órgão (envelope), espelhando o POST de ``edit_orgao_tipo``.

    Reaproveita ``_normalize_tipo_form`` e ``_invalid_orgao_type_level_changes``
    para preservar as regras de hierarquia/níveis. Bloqueia: desativar tipo em
    uso e mudanças de nível/raiz que deixem órgãos fora da regra hierárquica.
    Sincroniza ``OrgaoUnidade.tipo`` (string) dos órgãos vinculados.

    Args:
        tipo_id: ID do tipo a editar.

    Returns:
        Envelope ``{"ok": true, "data": {"tipo": {...}}}``; ``fail(..., 422)``
        em validação; ``fail(..., 409)`` em conflito de regra; ``fail(..., 404)``
        se não existe.
    """
    _prepare_orgao_catalogs()
    tipo = db.session.get(OrgaoTipo, tipo_id)
    if tipo is None:
        return fail("Tipo de órgão não encontrado.", status=404, code="not_found")

    payload = request.get_json(silent=True) or request.form
    data, error = _normalize_tipo_form(payload, tipo)
    if error:
        return fail(error, status=422, code="validation")

    if (
        tipo.ativo
        and not data["ativo"]
        and OrgaoUnidade.query.filter_by(tipo_id=tipo.id).first() is not None
    ):
        return fail(
            "Não é possível desativar tipo em uso por órgãos.",
            status=409,
            code="validation",
        )

    affected = _invalid_orgao_type_level_changes(
        tipo, data["nivel"], data["permite_raiz"]
    )
    if affected:
        labels = ", ".join(o.sigla for o in affected[:8])
        if len(affected) > 8:
            labels += f" e mais {len(affected) - 8}"
        return fail(
            "Alteração bloqueada: existem órgãos que ficariam fora da regra "
            f"hierárquica ({labels}).",
            status=409,
            code="validation",
        )

    tipo.nome = data["nome"]
    tipo.slug = data["slug"]
    tipo.nivel = data["nivel"]
    tipo.descricao = data["descricao"]
    tipo.ativo = data["ativo"]
    tipo.permite_raiz = data["permite_raiz"]
    for orgao in OrgaoUnidade.query.filter_by(tipo_id=tipo.id).all():
        orgao.tipo = tipo.nome
    db.session.commit()
    return ok({"tipo": serialize_orgao_tipo(tipo)})


@main_bp.route("/api/admin/orgaos/tipos/<int:tipo_id>/toggle-ativo", methods=["POST"])
@api_admin_required
def api_admin_orgao_tipos_toggle_ativo(
    tipo_id: int,
) -> Response | tuple[Response, int]:
    """Alterna ativo/inativo de um tipo, espelhando ``toggle_orgao_tipo``.

    Preserva as proteções: não desativa tipo raiz ativo nem tipo em uso por
    órgãos.

    Args:
        tipo_id: ID do tipo a alternar.

    Returns:
        Envelope ``{"ok": true, "data": {"tipo": {...}}}``; ``fail(..., 409)``
        quando a desativação é proibida; ``fail(..., 404)`` se não existe.
    """
    _prepare_orgao_catalogs()
    tipo = db.session.get(OrgaoTipo, tipo_id)
    if tipo is None:
        return fail("Tipo de órgão não encontrado.", status=404, code="not_found")
    if tipo.permite_raiz and tipo.ativo:
        return fail(
            "Não é possível desativar o tipo raiz ativo.",
            status=409,
            code="validation",
        )
    if tipo.ativo and OrgaoUnidade.query.filter_by(tipo_id=tipo.id).first() is not None:
        return fail(
            "Não é possível desativar tipo em uso por órgãos.",
            status=409,
            code="validation",
        )
    tipo.ativo = not tipo.ativo
    db.session.commit()
    return ok({"tipo": serialize_orgao_tipo(tipo)})


@main_bp.route("/api/admin/orgaos/tipos/<int:tipo_id>/delete", methods=["POST"])
@api_admin_required
def api_admin_orgao_tipos_delete(tipo_id: int) -> Response | tuple[Response, int]:
    """Exclui um tipo de órgão (envelope), espelhando ``delete_orgao_tipo``.

    Preserva as proteções: não exclui tipo em uso por órgãos nem tipo permitido
    para raiz.

    Args:
        tipo_id: ID do tipo a excluir.

    Returns:
        Envelope ``{"ok": true, "data": {"deleted_id": <id>}}``; ``fail(..., 409)``
        quando a exclusão é proibida; ``fail(..., 404)`` se não existe.
    """
    _prepare_orgao_catalogs()
    tipo = db.session.get(OrgaoTipo, tipo_id)
    if tipo is None:
        return fail("Tipo de órgão não encontrado.", status=404, code="not_found")
    if OrgaoUnidade.query.filter_by(tipo_id=tipo.id).first() is not None:
        return fail(
            "Não é possível excluir tipo em uso por órgãos.",
            status=409,
            code="validation",
        )
    if tipo.permite_raiz:
        return fail(
            "Não é possível excluir tipo permitido para raiz.",
            status=409,
            code="validation",
        )
    db.session.delete(tipo)
    db.session.commit()
    return ok({"deleted_id": tipo_id})
