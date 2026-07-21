"""Endpoints JSON do CRUD de Modelos de Etapas (Admin) para a SPA SvelteKit.

Fase 4 — Admin. Espelha o CRUD Jinja de ``routes/admin_templates.py`` em
endpoints ``/api/admin/templates*`` no envelope canônico, protegidos por
``api_admin_required`` (401 sem sessão, 403 para não-admin). É ADITIVO: as rotas
Jinja (``list_templates``/``create_template``/``edit_template``/
``duplicate_template``/``delete_template``) permanecem intactas (strangler).

Reaproveita os helpers de listagem/métricas já existentes em
``routes/admin_templates.py`` (``_build_template_rows``, ``_apply_order``,
``ORDER_OPTIONS``, ``PAGE_SIZE``), preservando o comportamento das rotas Jinja.
As regras (nome + ao menos uma etapa obrigatórios) são mantidas; erros de
validação resultam em ``fail(..., 422, "validation")`` em vez do ``flash`` +
re-render do fluxo Jinja.

Anexa ao ``main_bp`` ÚNICO (``routes/blueprint.py``); NÃO cria blueprint novo.
CRUD de recurso RESTificado: editar -> ``PUT /api/admin/templates/<id>`` e
excluir -> ``DELETE /api/admin/templates/<id>``. A ação ``duplicate`` permanece
``POST`` (comando, não CRUD de recurso). O cliente usa ``client.put``/
``client.del`` com ``X-CSRFToken``.
"""

from __future__ import annotations

from typing import Any

from flask import Response, g, request
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from models import StageTemplate, StageTemplateItem, StageTemplateUsage, db
from time_utils import utc_now

from ..admin_templates import (
    ORDER_OPTIONS,
    PAGE_SIZE,
    _apply_order,
    _build_template_rows,
)
from ..blueprint import main_bp
from .envelope import fail, ok
from .negotiation import api_admin_required
from .serializers import serialize_template_detail, serialize_template_row


def _usage_count_for(template_id: int) -> int:
    """Conta projetos distintos que usaram um modelo (espelha a lista Jinja)."""
    return (
        db.session.query(func.count(func.distinct(StageTemplateUsage.project_id)))
        .filter(StageTemplateUsage.template_id == template_id)
        .scalar()
        or 0
    )


def _parse_stages(payload: Any) -> tuple[list[dict[str, Any]], str | None]:
    """Normaliza as etapas do payload (JSON list ou form ``stage_name``).

    Aceita dois formatos, espelhando o que o form Jinja envia e o que a SPA
    enviará via JSON:

    - JSON: ``{"stages": [{"name": str, "duration_days": int}, ...]}``.
    - Form: listas paralelas ``stage_name[]`` / ``stage_duration[]`` (mesmo
      contrato de ``create_template``/``edit_template``).

    Etapas com nome vazio são ignoradas (igual ao Jinja). A duração default é 1
    quando ausente/ inválida. Retorna ``(stages, error)``; ``error`` não-nulo
    indica que nenhuma etapa válida foi informada.

    Args:
        payload: Payload da requisição (JSON ou ``request.form``).

    Returns:
        Tupla ``(stages, error)`` — ``stages`` é lista de
        ``{"name", "duration_days"}`` na ordem recebida.
    """
    names, durations = _extract_stage_inputs(payload)
    stages: list[dict[str, Any]] = []
    for index, raw_name in enumerate(names):
        name = (raw_name or "").strip()
        if not name:
            continue
        stages.append(
            {"name": name, "duration_days": _stage_duration(durations, index)}
        )
    if not stages:
        return [], "Informe pelo menos uma etapa."
    return stages, None


def _extract_stage_inputs(payload: Any) -> tuple[list[Any], list[Any]]:
    """Extrai nomes/durações brutos do payload (JSON list ou form getlist)."""
    raw_stages = payload.get("stages") if hasattr(payload, "get") else None
    if isinstance(raw_stages, list):
        names = [s.get("name") if isinstance(s, dict) else s for s in raw_stages]
        durations = [
            s.get("duration_days") if isinstance(s, dict) else None for s in raw_stages
        ]
        return names, durations
    if hasattr(payload, "getlist"):
        return payload.getlist("stage_name"), payload.getlist("stage_duration")
    return [], []


def _stage_duration(durations: list[Any], index: int) -> int:
    """Resolve a duração (>=1) de uma etapa pelo índice, default 1."""
    if index >= len(durations):
        return 1
    try:
        value = int(durations[index])
    except (TypeError, ValueError):
        return 1
    return value if value >= 1 else 1


@main_bp.route("/api/admin/templates", methods=["GET"])
@api_admin_required
def api_admin_templates_list() -> Response | tuple[Response, int]:
    """Lista de modelos de etapas + métricas (envelope), espelhando ``list_templates``.

    Reaproveita ``_apply_order`` (ordenação via ``?order=``) e
    ``_build_template_rows`` (métricas ``usage_count``/``stage_count``/
    ``total_duration`` + derivados de apresentação). Suporta busca ``?q=`` e
    paginação ``?page=`` (mesmo ``PAGE_SIZE`` do Jinja).

    Returns:
        Envelope ``{"ok": true, "data": {"templates": [...], "order_options"},
        "meta": {...}}`` com HTTP 200.
    """
    q = (request.args.get("q") or "").strip()
    order = request.args.get("order") or "mais_usados"
    if order not in ORDER_OPTIONS:
        order = "mais_usados"
    page = max(1, request.args.get("page", 1, type=int) or 1)

    usage_subq = (
        db.session.query(
            StageTemplateUsage.template_id.label("template_id"),
            func.count(func.distinct(StageTemplateUsage.project_id)).label(
                "usage_count"
            ),
        )
        .group_by(StageTemplateUsage.template_id)
        .subquery()
    )
    stage_count_subq = (
        db.session.query(
            StageTemplateItem.templateId.label("template_id"),
            func.count(StageTemplateItem.id).label("stage_count"),
            func.coalesce(func.sum(StageTemplateItem.duration_days), 0).label(
                "total_duration"
            ),
        )
        .group_by(StageTemplateItem.templateId)
        .subquery()
    )

    usage_count_expr = func.coalesce(usage_subq.c.usage_count, 0)
    stage_count_expr = func.coalesce(stage_count_subq.c.stage_count, 0)
    total_duration_expr = func.coalesce(stage_count_subq.c.total_duration, 0)

    query = (
        db.session.query(StageTemplate)
        .outerjoin(usage_subq, usage_subq.c.template_id == StageTemplate.id)
        .outerjoin(stage_count_subq, stage_count_subq.c.template_id == StageTemplate.id)
        .options(joinedload(StageTemplate.items))
    )
    if q:
        like = f"%{q}%"
        query = query.filter(
            (StageTemplate.name.ilike(like)) | (StageTemplate.description.ilike(like))
        )

    total = (
        query.with_entities(func.count(func.distinct(StageTemplate.id))).scalar() or 0
    )
    query = _apply_order(
        query, order, usage_count_expr, stage_count_expr, total_duration_expr
    )
    templates = query.offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE).all()

    template_ids = [t.id for t in templates]
    usage_map: dict[int, int] = {}
    if template_ids:
        usage_rows = (
            db.session.query(
                StageTemplateUsage.template_id,
                func.count(func.distinct(StageTemplateUsage.project_id)),
            )
            .filter(StageTemplateUsage.template_id.in_(template_ids))
            .group_by(StageTemplateUsage.template_id)
            .all()
        )
        usage_map = {tid: count for tid, count in usage_rows}

    rows = _build_template_rows(templates, usage_map, utc_now())
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    return ok(
        {
            "templates": [serialize_template_row(row) for row in rows],
            "order_options": list(ORDER_OPTIONS),
        },
        meta={
            "page": page,
            "per_page": PAGE_SIZE,
            "total": total,
            "total_pages": total_pages,
            "order": order,
            "q": q,
        },
    )


@main_bp.route("/api/admin/templates/<int:template_id>", methods=["GET"])
@api_admin_required
def api_admin_templates_detail(
    template_id: int,
) -> Response | tuple[Response, int]:
    """Dados de um modelo + etapas para o form de edição (envelope).

    Espelha o GET de ``edit_template``: devolve o modelo serializado com as
    etapas ordenadas (``serialize_template_detail``) e o ``usage_count``.

    Args:
        template_id: ID do modelo a carregar.

    Returns:
        Envelope ``{"ok": true, "data": {"template": {...}, "usage_count"}}``;
        ``fail(..., 404, "not_found")`` quando não existe.
    """
    template = db.session.get(StageTemplate, template_id)
    if template is None:
        return fail("Modelo de etapas não encontrado.", status=404, code="not_found")
    return ok(
        {
            "template": serialize_template_detail(template),
            "usage_count": _usage_count_for(template.id),
        }
    )


@main_bp.route("/api/admin/templates", methods=["POST"])
@api_admin_required
def api_admin_templates_create() -> Response | tuple[Response, int]:
    """Cria um modelo de etapas (envelope), espelhando o POST de ``create_template``.

    Preserva a validação: nome e ao menos uma etapa são obrigatórios
    (``_parse_stages``). Registra ``created_by``/``updated_by`` (``g.user``).
    Erros de validação => ``fail(..., 422, "validation")``.

    Returns:
        Envelope ``{"ok": true, "data": {"template": {...}}}`` com HTTP 200 ao
        criar.
    """
    payload = request.get_json(silent=True) or request.form
    name = (payload.get("name") or "").strip()
    description = (payload.get("description") or "").strip() or None
    stages, stage_error = _parse_stages(payload)

    if not name:
        return fail("O nome do modelo é obrigatório.", status=422, code="validation")
    if stage_error:
        return fail(stage_error, status=422, code="validation")

    user_id = g.user.id if g.user else None
    template = StageTemplate(
        name=name,
        description=description,
        created_by_id=user_id,
        updated_by_id=user_id,
    )
    db.session.add(template)
    db.session.flush()
    _replace_stages(template.id, stages)
    db.session.commit()
    return ok({"template": serialize_template_detail(template)})


@main_bp.route("/api/admin/templates/<int:template_id>", methods=["PUT"])
@api_admin_required
def api_admin_templates_update(
    template_id: int,
) -> Response | tuple[Response, int]:
    """Edita um modelo de etapas (envelope), espelhando o POST de ``edit_template``.

    Preserva a validação (nome + ao menos uma etapa) e substitui o conjunto de
    etapas por completo (igual ao Jinja: apaga as antigas e recria na ordem
    recebida). Atualiza ``updated_by`` (``g.user``).

    Args:
        template_id: ID do modelo a editar.

    Returns:
        Envelope ``{"ok": true, "data": {"template": {...}}}``; ``fail(..., 422)``
        em validação; ``fail(..., 404)`` se não existe.
    """
    template = db.session.get(StageTemplate, template_id)
    if template is None:
        return fail("Modelo de etapas não encontrado.", status=404, code="not_found")

    payload = request.get_json(silent=True) or request.form
    name = (payload.get("name") or "").strip()
    description = (payload.get("description") or "").strip() or None
    stages, stage_error = _parse_stages(payload)

    if not name:
        return fail("O nome do modelo é obrigatório.", status=422, code="validation")
    if stage_error:
        return fail(stage_error, status=422, code="validation")

    template.name = name
    template.description = description
    template.updated_by_id = g.user.id if g.user else None
    _replace_stages(template.id, stages)
    db.session.commit()
    return ok({"template": serialize_template_detail(template)})


@main_bp.route("/api/admin/templates/<int:template_id>/duplicate", methods=["POST"])
@api_admin_required
def api_admin_templates_duplicate(
    template_id: int,
) -> Response | tuple[Response, int]:
    """Duplica um modelo (envelope), espelhando ``duplicate_template``.

    Cria uma cópia com sufixo "(cópia)" no nome, replicando as etapas (nome,
    duração, ordem) e registrando o autor (``g.user``).

    Args:
        template_id: ID do modelo a duplicar.

    Returns:
        Envelope ``{"ok": true, "data": {"template": {...}}}``; ``fail(..., 404)``
        se não existe.
    """
    original = db.session.get(StageTemplate, template_id)
    if original is None:
        return fail("Modelo de etapas não encontrado.", status=404, code="not_found")

    user_id = g.user.id if g.user else None
    copy = StageTemplate(
        name=f"{original.name} (cópia)",
        description=original.description,
        created_by_id=user_id,
        updated_by_id=user_id,
    )
    db.session.add(copy)
    db.session.flush()
    for item in original.items:
        db.session.add(
            StageTemplateItem(
                name=item.name,
                duration_days=item.duration_days,
                order=item.order,
                templateId=copy.id,
            )
        )
    db.session.commit()
    return ok({"template": serialize_template_detail(copy)})


@main_bp.route("/api/admin/templates/<int:template_id>", methods=["DELETE"])
@api_admin_required
def api_admin_templates_delete(
    template_id: int,
) -> Response | tuple[Response, int]:
    """Exclui um modelo de etapas (envelope), espelhando ``delete_template``.

    As etapas e usos são removidos em cascata (``cascade="all, delete-orphan"``).

    Args:
        template_id: ID do modelo a excluir.

    Returns:
        Envelope ``{"ok": true, "data": {"deleted_id": <id>}}``; ``fail(..., 404)``
        se não existe.
    """
    template = db.session.get(StageTemplate, template_id)
    if template is None:
        return fail("Modelo de etapas não encontrado.", status=404, code="not_found")
    db.session.delete(template)
    db.session.commit()
    return ok({"deleted_id": template_id})


def _replace_stages(template_id: int, stages: list[dict[str, Any]]) -> None:
    """Substitui todas as etapas de um modelo na ordem recebida.

    Espelha ``create_template``/``edit_template``: apaga as etapas antigas e
    recria com ``order`` sequencial (0-based).

    Args:
        template_id: ID do modelo dono das etapas.
        stages: Lista de ``{"name", "duration_days"}`` já normalizada.
    """
    StageTemplateItem.query.filter_by(templateId=template_id).delete()
    for index, stage in enumerate(stages):
        db.session.add(
            StageTemplateItem(
                name=stage["name"],
                duration_days=stage["duration_days"],
                order=index,
                templateId=template_id,
            )
        )
