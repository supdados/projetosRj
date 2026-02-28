from flask import flash, redirect, render_template, request, url_for
from sqlalchemy.orm import joinedload

from models import StageTemplate, StageTemplateItem, db

from .blueprint import main_bp
from .decorators import admin_required, login_required
from .shared import get_or_404
@main_bp.route('/admin/templates')
@login_required
@admin_required
def list_templates():
    # Usar joinedload para carregar os 'items' de forma eficiente (Eager Loading)
    # Isso garante que template.items esteja populado sem a necessidade de queries adicionais.
    templates = StageTemplate.query.options(joinedload(StageTemplate.items)).order_by(StageTemplate.name).all()
    return render_template('template_list.html', templates=templates)

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
            return render_template('template_form.html')

        new_template = StageTemplate(name=name, description=description)
        db.session.add(new_template)
        # Flush para obter o ID do novo template antes de criar os itens
        db.session.flush()

        for i, stage_name in enumerate(stage_names):
            if stage_name: # Ignorar campos de etapa vazios
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

    return render_template('template_form.html')

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
            return render_template('template_form.html', template=template)

        # Atualiza os dados do template
        template.name = name
        template.description = description

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

    return render_template('template_form.html', template=template)

@main_bp.route('/admin/templates/<int:template_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_template(template_id):
    template = get_or_404(StageTemplate, template_id)
    db.session.delete(template)
    db.session.commit()
    flash('Modelo de etapas excluído com sucesso.', 'success')
    return redirect(url_for('main.list_templates'))
