from datetime import timedelta

from flask import flash, g, redirect, render_template, request, url_for
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from models import StageTemplate, StageTemplateItem, StageTemplateUsage, db
from time_utils import format_relative_time_pt, utc_now

from .blueprint import main_bp
from .decorators import admin_required, login_required
from .shared import get_or_404

PAGE_SIZE = 10
NEW_BADGE_DAYS = 14
ORDER_OPTIONS = ('mais_usados', 'nome', 'mais_etapas', 'maior_duracao', 'edicao_recente')


def _template_initials(name):
    """Retorna até 2 letras maiúsculas das primeiras palavras do nome."""
    if not name:
        return '?'
    parts = [p for p in name.strip().split() if p]
    if not parts:
        return '?'
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
    return [
        (max(3, round((d / peak) * max_height)), d)
        for d in durations
    ]


def _apply_order(query, order, usage_count_expr, stage_count_expr, total_duration_expr):
    """Aplica ordenação configurada na query da lista."""
    if order == 'nome':
        return query.order_by(StageTemplate.name.asc())
    if order == 'mais_etapas':
        return query.order_by(stage_count_expr.desc(), StageTemplate.name.asc())
    if order == 'maior_duracao':
        return query.order_by(total_duration_expr.desc(), StageTemplate.name.asc())
    if order == 'edicao_recente':
        return query.order_by(StageTemplate.updated_at.desc().nullslast(), StageTemplate.name.asc())
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
        rows.append({
            'id': tpl.id,
            'name': tpl.name,
            'description': tpl.description,
            'initials': _template_initials(tpl.name),
            'stage_count': len(items),
            'total_duration': total_duration,
            'silhouette': _silhouette_bars(items),
            'usage_count': usage_map.get(tpl.id, 0),
            'updated_at': tpl.updated_at,
            'updated_relative': format_relative_time_pt(tpl.updated_at, now=now),
            'editor_name': (editor.name if editor else None) or (editor.username if editor else None),
            'is_new': is_new,
        })
    return rows


@main_bp.route('/admin/templates')
@login_required
@admin_required
def list_templates():
    q = (request.args.get('q') or '').strip()
    order = request.args.get('order') or 'mais_usados'
    if order not in ORDER_OPTIONS:
        order = 'mais_usados'
    try:
        page = max(1, int(request.args.get('page') or 1))
    except (TypeError, ValueError):
        page = 1

    usage_subq = (
        db.session.query(
            StageTemplateUsage.template_id.label('template_id'),
            func.count(func.distinct(StageTemplateUsage.project_id)).label('usage_count'),
        )
        .group_by(StageTemplateUsage.template_id)
        .subquery()
    )
    stage_count_subq = (
        db.session.query(
            StageTemplateItem.templateId.label('template_id'),
            func.count(StageTemplateItem.id).label('stage_count'),
            func.coalesce(func.sum(StageTemplateItem.duration_days), 0).label('total_duration'),
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
        like = f'%{q}%'
        query = query.filter(
            (StageTemplate.name.ilike(like)) | (StageTemplate.description.ilike(like))
        )

    total = query.with_entities(func.count(func.distinct(StageTemplate.id))).scalar() or 0
    query = _apply_order(query, order, usage_count_expr, stage_count_expr, total_duration_expr)

    templates = query.offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE).all()

    template_ids = [t.id for t in templates]
    usage_map = {}
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

    now = utc_now()
    rows = _build_template_rows(templates, usage_map, now)

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    total_all = db.session.query(func.count(StageTemplate.id)).scalar() or 0

    return render_template(
        'admin/template_list.html',
        rows=rows,
        total=total,
        total_all=total_all,
        page=page,
        total_pages=total_pages,
        page_size=PAGE_SIZE,
        q=q,
        order=order,
        order_options=ORDER_OPTIONS,
    )


@main_bp.route('/admin/templates/new', methods=['GET', 'POST'])
@login_required
@admin_required
def create_template():
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        stage_names = request.form.getlist('stage_name')
        stage_durations = request.form.getlist('stage_duration')

        if not name or not stage_names:
            flash('O nome do modelo e pelo menos uma etapa são obrigatórios.', 'danger')
            return render_template('admin/template_form.html')

        new_template = StageTemplate(
            name=name,
            description=description,
            created_by_id=g.user.id if g.user else None,
            updated_by_id=g.user.id if g.user else None,
        )
        db.session.add(new_template)
        # Flush para obter o ID do novo template antes de criar os itens
        db.session.flush()

        for i, stage_name in enumerate(stage_names):
            if stage_name:  # Ignorar campos de etapa vazios
                duration = int(stage_durations[i]) if i < len(stage_durations) and stage_durations[i] else 1
                item = StageTemplateItem(
                    name=stage_name,
                    duration_days=duration,
                    order=i,
                    templateId=new_template.id
                )
                db.session.add(item)

        db.session.commit()
        flash('Modelo de etapas criado com sucesso!', 'success')
        return redirect(url_for('main.list_templates'))

    return render_template('admin/template_form.html')


@main_bp.route('/admin/templates/<int:template_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_template(template_id):
    template = get_or_404(StageTemplate, template_id)

    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        stage_names = request.form.getlist('stage_name')
        stage_durations = request.form.getlist('stage_duration')

        if not name or not stage_names:
            flash('O nome do modelo e pelo menos uma etapa são obrigatórios.', 'danger')
            return render_template('admin/template_form.html', template=template)

        # Atualiza os dados do template
        template.name = name
        template.description = description
        template.updated_by_id = g.user.id if g.user else None

        # Remove os itens antigos
        StageTemplateItem.query.filter_by(templateId=template.id).delete()

        # Adiciona os novos itens
        for i, stage_name in enumerate(stage_names):
            if stage_name:
                duration = int(stage_durations[i]) if i < len(stage_durations) and stage_durations[i] else 1
                item = StageTemplateItem(
                    name=stage_name,
                    duration_days=duration,
                    order=i,
                    templateId=template.id
                )
                db.session.add(item)

        db.session.commit()
        flash('Modelo de etapas atualizado com sucesso!', 'success')
        return redirect(url_for('main.list_templates'))

    return render_template('admin/template_form.html', template=template)


@main_bp.route('/admin/templates/<int:template_id>/duplicate', methods=['POST'])
@login_required
@admin_required
def duplicate_template(template_id):
    """Cria cópia do modelo com sufixo "(cópia)" no nome."""
    original = get_or_404(StageTemplate, template_id)

    copy = StageTemplate(
        name=f'{original.name} (cópia)',
        description=original.description,
        created_by_id=g.user.id if g.user else None,
        updated_by_id=g.user.id if g.user else None,
    )
    db.session.add(copy)
    db.session.flush()

    for item in original.items:
        db.session.add(StageTemplateItem(
            name=item.name,
            duration_days=item.duration_days,
            order=item.order,
            templateId=copy.id,
        ))

    db.session.commit()
    flash(f'Modelo "{original.name}" duplicado com sucesso.', 'success')
    return redirect(url_for('main.list_templates'))


@main_bp.route('/admin/templates/<int:template_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_template(template_id):
    template = get_or_404(StageTemplate, template_id)
    db.session.delete(template)
    db.session.commit()
    flash('Modelo de etapas excluído com sucesso.', 'success')
    return redirect(url_for('main.list_templates'))
