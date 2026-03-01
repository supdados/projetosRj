from flask import flash, redirect, render_template, request, url_for
from sqlalchemy import func

from models import AreaCatalog, Project, UserArea, db

from .blueprint import main_bp
from .decorators import admin_required, login_required
from .shared import get_or_404, validate_area_name


@main_bp.route('/admin/areas')
@login_required
@admin_required
def list_areas():
    areas = AreaCatalog.query.order_by(func.lower(AreaCatalog.name), AreaCatalog.name).all()
    area_names = [item.name for item in areas]
    project_counts = {}
    user_counts = {}

    if area_names:
        project_counts = dict(
            db.session.query(Project.area_responsavel, func.count(Project.id))
            .filter(Project.area_responsavel.in_(area_names))
            .group_by(Project.area_responsavel)
            .all()
        )
        user_counts = dict(
            db.session.query(UserArea.area, func.count(UserArea.id))
            .filter(UserArea.area.in_(area_names))
            .group_by(UserArea.area)
            .all()
        )

    return render_template(
        'area_list.html',
        areas=areas,
        project_counts=project_counts,
        user_counts=user_counts,
    )


@main_bp.route('/admin/areas/new', methods=['GET', 'POST'])
@login_required
@admin_required
def add_area():
    if request.method == 'POST':
        normalized_name, error_message = validate_area_name(request.form.get('name'))
        if error_message:
            flash(error_message, 'danger')
            return render_template(
                'area_form.html',
                area={'name': request.form.get('name', '')},
                action_verb='Adicionar',
            )

        try:
            db.session.add(AreaCatalog(name=normalized_name))
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            flash(f'Erro ao criar área: {exc}', 'danger')
            return render_template(
                'area_form.html',
                area={'name': request.form.get('name', '')},
                action_verb='Adicionar',
            )

        flash(f'Área "{normalized_name}" criada com sucesso.', 'success')
        return redirect(url_for('main.list_areas'))

    return render_template('area_form.html', area=AreaCatalog(), action_verb='Adicionar')


@main_bp.route('/admin/areas/<int:area_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_area(area_id):
    area = get_or_404(AreaCatalog, area_id)

    if request.method == 'POST':
        normalized_name, error_message = validate_area_name(
            request.form.get('name'),
            current_area_id=area.id,
        )
        if error_message:
            flash(error_message, 'danger')
            return render_template(
                'area_form.html',
                area={'id': area.id, 'name': request.form.get('name', '')},
                action_verb='Editar',
            )

        old_name = area.name
        if normalized_name == old_name:
            flash('Nenhuma alteração foi realizada.', 'info')
            return redirect(url_for('main.list_areas'))

        try:
            project_updates = (
                Project.query.filter(Project.area_responsavel == old_name).update(
                    {Project.area_responsavel: normalized_name},
                    synchronize_session=False,
                )
            )
            user_area_updates = (
                UserArea.query.filter(UserArea.area == old_name).update(
                    {UserArea.area: normalized_name},
                    synchronize_session=False,
                )
            )
            area.name = normalized_name
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            flash(f'Erro ao atualizar área: {exc}', 'danger')
            return render_template('area_form.html', area=area, action_verb='Editar')

        flash(
            (
                f'Área renomeada para "{normalized_name}". '
                f'{project_updates} projeto(s) e {user_area_updates} vínculo(s) de usuário foram atualizados.'
            ),
            'success',
        )
        return redirect(url_for('main.list_areas'))

    return render_template('area_form.html', area=area, action_verb='Editar')


@main_bp.route('/admin/areas/<int:area_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_area(area_id):
    area = get_or_404(AreaCatalog, area_id)

    associated_projects_count = Project.query.filter(
        Project.area_responsavel == area.name
    ).count()
    if associated_projects_count > 0:
        flash(
            (
                f'Não é possível excluir a área "{area.name}" '
                f'porque existem {associated_projects_count} projeto(s) associado(s).'
            ),
            'warning',
        )
        return redirect(url_for('main.list_areas'))

    try:
        removed_user_links = UserArea.query.filter(UserArea.area == area.name).delete(
            synchronize_session=False
        )
        db.session.delete(area)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        flash(f'Erro ao excluir área: {exc}', 'danger')
        return redirect(url_for('main.list_areas'))

    flash(
        (
            f'Área "{area.name}" excluída com sucesso. '
            f'{removed_user_links} vínculo(s) de usuário removido(s).'
        ),
        'success',
    )
    return redirect(url_for('main.list_areas'))
