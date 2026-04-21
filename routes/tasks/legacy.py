from flask import flash, g, jsonify, redirect, request, url_for

from models import Task, db

from routes.blueprint import main_bp
from routes.decorators import login_required

from routes.tasks.helpers import _can_view_task, _create_task_common
from routes.tasks.crud import (
    edit_task,
    delete_task,
    update_task_status,
    update_task_prioridade,
    update_task_tipo,
)
from routes.tasks.comments import add_task_comment
from services.task_mutation import apply_task_order as _apply_task_order, parse_unique_task_order_ids as _parse_unique_task_order_ids
from routes.tasks.attachments import list_task_anexos, add_task_anexo


@main_bp.route('/tarefas/itens/add', methods=['POST'])
@login_required
def add_task_item_global():
    return _create_task_common()


@main_bp.route('/tarefas/<int:task_id>/itens/add', methods=['POST'])
@login_required
def add_task_item(task_id):
    anchor = db.session.get(Task, task_id)
    is_ajax = (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.accept_mimetypes.best == 'application/json'
    )
    if not anchor:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Tarefa não encontrada.'}), 404
        flash('Tarefa não encontrada.', 'warning')
        return redirect(url_for('main.list_tasks'))
    if not _can_view_task(g.user, anchor):
        if is_ajax:
            return jsonify({'success': False, 'message': 'Sem permissão para este projeto.'}), 403
        flash('Sem permissão para este projeto.', 'danger')
        return redirect(url_for('main.list_tasks'))
    default_project = anchor.project
    return _create_task_common(default_project=default_project)


@main_bp.route('/tarefas/itens/<int:item_id>/edit', methods=['POST'])
@login_required
def edit_task_item(item_id):
    return edit_task(item_id)


@main_bp.route('/tarefas/itens/<int:item_id>/delete', methods=['POST'])
@login_required
def delete_task_item(item_id):
    return delete_task(item_id)


@main_bp.route('/tarefas/itens/<int:item_id>/update_status', methods=['POST'])
@login_required
def update_task_item_status(item_id):
    return update_task_status(item_id)


@main_bp.route('/tarefas/itens/<int:item_id>/update_prioridade', methods=['POST'])
@login_required
def update_task_item_prioridade(item_id):
    return update_task_prioridade(item_id)


@main_bp.route('/tarefas/itens/<int:item_id>/update_tipo', methods=['POST'])
@login_required
def update_task_item_tipo(item_id):
    return update_task_tipo(item_id)


@main_bp.route('/tarefas/<int:task_id>/itens/reordenar', methods=['POST'])
@login_required
def reorder_task_items(task_id):
    anchor = db.session.get(Task, task_id)
    if not anchor:
        return jsonify({'success': False, 'message': 'Tarefa não encontrada'}), 404
    if not _can_view_task(g.user, anchor):
        return jsonify({'success': False, 'message': 'Sem permissão'}), 403

    payload = request.get_json(silent=True) or {}
    ordem_ids = _parse_unique_task_order_ids(payload.get('ordem', []))

    scope_query = Task.query.filter(
        Task.project_id == anchor.project_id,
        Task.is_archived.is_(False),
    ).order_by(Task.ordem.asc(), Task.id.asc())

    if anchor.project_id is None and not g.user.is_admin:
        scope_query = scope_query.filter(Task.created_by_id == g.user.id)

    try:
        _apply_task_order(scope_query, ordem_ids)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Ordem atualizada'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@main_bp.route('/tarefas/itens/<int:item_id>/comentarios/add', methods=['POST'])
@login_required
def add_task_item_comment(item_id):
    return add_task_comment(item_id)


@main_bp.route('/tarefas/itens/<int:item_id>/anexos', methods=['GET'])
@login_required
def list_task_item_anexos(item_id):
    return list_task_anexos(item_id)


@main_bp.route('/tarefas/itens/<int:item_id>/anexos/add', methods=['POST'])
@login_required
def add_task_item_anexo(item_id):
    return add_task_anexo(item_id)
