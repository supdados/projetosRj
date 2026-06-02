from datetime import timedelta

from flask import flash, g, jsonify, redirect, render_template, request, url_for
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from models import StageTemplate, StageTemplateItem, StageTemplateUsage, db
from time_utils import format_relative_time_pt, utc_now

from .blueprint import main_bp
from .decorators import admin_required, login_required
from .shared import get_or_404

PAGE_SIZE = 10
NEW_BADGE_DAYS = 14
ORDER_OPTIONS = (
    "mais_usados",
    "nome",
    "mais_etapas",
    "maior_duracao",
    "edicao_recente",
)


def _template_initials(name):
    """Retorna até 2 letras maiúsculas das primeiras palavras do nome."""
    if not name:
        return "?"
    parts = [p for p in name.strip().split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[1][0]).upper()


def _silhouette_bars(items, *, max_bars=14, max_height=28):
    """Gera barras proporcionais para mini gráfico de duração das etapas.

    Retorna lista de tuplas ``(height_px, duration_days)`` — a view renderiza como SVG.
    """
    if not items:
        return []
    durations = [max(1, int(it.duration_days or 1)) for it in items[:max_bars]]
    peak = max(durations)
    return [(max(3, round((d / peak) * max_height)), d) for d in durations]


def _apply_order(query, order, usage_count_expr, stage_count_expr, total_duration_expr):
    """Aplica ordenação configurada na query da lista."""
    if order == "nome":
        return query.order_by(StageTemplate.name.asc())
    if order == "mais_etapas":
        return query.order_by(stage_count_expr.desc(), StageTemplate.name.asc())
    if order == "maior_duracao":
        return query.order_by(total_duration_expr.desc(), StageTemplate.name.asc())
    if order == "edicao_recente":
        return query.order_by(
            StageTemplate.updated_at.desc().nullslast(), StageTemplate.name.asc()
        )
    return query.order_by(usage_count_expr.desc(), StageTemplate.name.asc())


def _build_template_rows(templates, usage_map, now):
    """Transforma cada StageTemplate em dict pronto para a view."""
    new_badge_cutoff = now - timedelta(days=NEW_BADGE_DAYS)
    rows = []
    for tpl in templates:
        items = list(tpl.items)
        total_duration = sum(int(it.duration_days or 0) for it in items)
        editor = tpl.updated_by or tpl.created_by
        is_new = tpl.created_at is not None and tpl.created_at >= new_badge_cutoff
        rows.append(
            {
                "id": tpl.id,
                "name": tpl.name,
                "description": tpl.description,
                "initials": _template_initials(tpl.name),
                "stage_count": len(items),
                "total_duration": total_duration,
                "silhouette": _silhouette_bars(items),
                "usage_count": usage_map.get(tpl.id, 0),
                "updated_at": tpl.updated_at,
                "updated_relative": format_relative_time_pt(tpl.updated_at, now=now),
                "editor_name": (editor.name if editor else None)
                or (editor.username if editor else None),
                "is_new": is_new,
            }
        )
    return rows

