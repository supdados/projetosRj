from flask import flash, g, jsonify, request, url_for

from models import Task, db

from routes.blueprint import main_bp
from routes.decorators import login_required
from routes.tasks.constants import VALID_PRIORIDADES, VALID_STATUSES, VALID_TIPOS
from routes.tasks.helpers import (
    _audit_denied_task_action,
    _build_visible_tasks_query,
    _can_manage_task_restricted_actions,
    _can_transition_task_to_status,
    _can_view_task,
    _create_task_common,
    _format_invalid_responsavel_message,
    _get_assignable_users_for_area,
    _get_assignable_users_for_project,
    _merge_task_filter_values,
    _normalize_responsavel_value,
    _read_task_filter_values,
    _redirect_back_or,
    _resolve_project_token,
    _resolve_responsavel_for_edit,
    _serialize_task_payload,
)
from routes.tasks.notifications import (
    notify_prioridade_change,
    notify_status_change,
    notify_task_archived_in_batch,
    notify_task_deleted,
    notify_task_edited,
    notify_task_finalized,
    notify_task_unarchived,
    notify_tipo_change,
)
from routes.tasks.validators import extract_edit_inputs
from services.task_mutation import (
    apply_task_edits,
    apply_task_order,
    archive_task as mutate_archive_task,
    bulk_archive_finalized,
    parse_unique_task_order_ids,
    unarchive_task as mutate_unarchive_task,
)


FINALIZE_DENIED_MESSAGE = 'Apenas o criador da tarefa pode movê-la para Finalizada.'
DELETE_DENIED_MESSAGE = 'Somente o autor da tarefa ou um administrador pode excluí-la.'
EDIT_RESTRICTED_FIELDS_DENIED_MESSAGE = (
    'Somente o autor da tarefa ou um administrador pode editar descrição, prioridade e responsável.'
)


# ── Helpers locais ────────────────────────────────────────────────────────────


def _wants_json() -> bool:
    return (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.accept_mimetypes.best == 'application/json'
    )


def _task_hub_reorder_scope_key(task):
    if task.project_id is not None:
        return ('project', task.project_id)
    if g.user.is_admin:
        return ('orphan', None)
    return ('orphan', task.created_by_id)


def _build_task_hub_reorder_scope_query(scope_key):
    scope_type, scope_value = scope_key
    base = _build_visible_tasks_query(include_relations=False).order_by(None)

    if scope_type == 'project':
        scoped = base.filter(Task.project_id == scope_value)
    elif scope_type == 'orphan':
        scoped = base.filter(Task.project_id.is_(None))
        if scope_value is not None:
            scoped = scoped.filter(Task.created_by_id == scope_value)
    else:
        scoped = base.filter(db.false())

    return scoped.order_by(Task.ordem.asc(), Task.id.asc())


def _check_restricted_fields_permission(task, inputs):
    """Retorna resposta 403 se o usuário mexeu em campo restrito sem permissão."""
    descricao_changed = inputs.descricao != (task.descricao or '').strip()
    prioridade_changed = (inputs.prioridade or '') != (task.prioridade or '')
    responsavel_changed = (
        _normalize_responsavel_value(inputs.responsavel_raw)
        != _normalize_responsavel_value(task.responsavel or '')
    )
    if not (descricao_changed or prioridade_changed or responsavel_changed):
        return None
    if _can_manage_task_restricted_actions(g.user, task):
        return None

    _audit_denied_task_action(task, 'forbidden_edit_restricted')
    return jsonify({'success': False, 'message': EDIT_RESTRICTED_FIELDS_DENIED_MESSAGE}), 403


def _resolve_project_for_edit(project_raw, task):
    if project_raw is None:
        return task.project, None
    project, error, status_code = _resolve_project_token(project_raw, allow_empty=True)
    if error:
        return None, (jsonify({'success': False, 'message': error}), status_code)
    return project, None


def _group_ids_by_reorder_scope(ordem_ids):
    visible_tasks = (
        _build_visible_tasks_query(include_relations=False)
        .order_by(None)
        .filter(Task.id.in_(ordem_ids))
        .all()
    )
    tasks_by_id = {task.id: task for task in visible_tasks}

    scope_orders: dict = {}
    scope_sequence: list = []
    for task_id in ordem_ids:
        task = tasks_by_id.get(task_id)
        if task is None:
            continue
        scope_key = _task_hub_reorder_scope_key(task)
        if scope_key not in scope_orders:
            scope_orders[scope_key] = []
            scope_sequence.append(scope_key)
        scope_orders[scope_key].append(task.id)
    return scope_sequence, scope_orders


def _on_db_error(e: Exception) -> tuple:
    """Rollback e retorna JSON 500. Para rotas que só respondem JSON."""
    db.session.rollback()
    return jsonify({'success': False, 'message': str(e)}), 500


def _on_db_error_redirect(
    e: Exception, *, is_ajax: bool, error_prefix: str, endpoint: str, **extra_json
) -> tuple:
    """Rollback e retorna JSON 500 ou flash+redirect para rotas híbridas (AJAX e form)."""
    db.session.rollback()
    if is_ajax:
        return jsonify({'success': False, 'message': str(e), **extra_json}), 500
    flash(f'{error_prefix}: {str(e)}', 'danger')
    return _redirect_back_or(endpoint)


# ── Rotas ─────────────────────────────────────────────────────────────────────


@main_bp.route('/tarefas/add', methods=['POST'])
@login_required
def add_task():
    return _create_task_common()


@main_bp.route('/tarefas/reordenar', methods=['POST'])
@login_required
def reorder_tasks_hub():
    payload = request.get_json(silent=True) or {}
    ordem_ids = parse_unique_task_order_ids(payload.get('ordem', []))
    if not ordem_ids:
        return jsonify({'success': True, 'message': 'Nenhuma alteração de ordem enviada'})

    scope_sequence, scope_orders = _group_ids_by_reorder_scope(ordem_ids)

    try:
        for scope_key in scope_sequence:
            apply_task_order(
                _build_task_hub_reorder_scope_query(scope_key),
                scope_orders[scope_key],
            )
        db.session.commit()
        return jsonify({'success': True, 'message': 'Ordem atualizada'})
    except Exception as e:
        return _on_db_error(e)


@main_bp.route('/tarefas/<int:task_id>/edit', methods=['POST'])
@login_required
def edit_task(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        return jsonify({'success': False, 'message': 'Tarefa não encontrada'}), 404
    if not _can_view_task(g.user, task):
        return jsonify({'success': False, 'message': 'Sem permissão'}), 403

    payload = request.get_json(silent=True) or {}
    inputs = extract_edit_inputs(task, request.form, payload)

    project, project_error_response = _resolve_project_for_edit(inputs.project_raw, task)
    if project_error_response:
        return project_error_response

    restricted_denied = _check_restricted_fields_permission(task, inputs)
    if restricted_denied:
        return restricted_denied

    if not inputs.descricao:
        return jsonify({'success': False, 'message': 'Descrição é obrigatória'}), 400

    is_valid, responsavel, invalid_names = _resolve_responsavel_for_edit(
        task, inputs.responsavel_raw, project,
    )
    if not is_valid:
        return jsonify({'success': False, 'message': _format_invalid_responsavel_message(invalid_names)}), 400

    if not _can_transition_task_to_status(g.user, task, inputs.status, previous_status=task.status):
        _audit_denied_task_action(task, 'forbidden_finalize', attempted_status=inputs.status)
        return jsonify({'success': False, 'message': FINALIZE_DENIED_MESSAGE}), 403

    diff = apply_task_edits(
        task,
        descricao=inputs.descricao,
        status=inputs.status,
        responsavel=responsavel,
        prioridade=inputs.prioridade,
        tipo_pedido=inputs.tipo_pedido,
        project=project,
    )

    try:
        notify_task_edited(task, diff)
        db.session.commit()
    except Exception as e:
        return _on_db_error(e)

    serialized = _serialize_task_payload(task)
    return jsonify({
        'success': True,
        'message': 'Tarefa atualizada',
        'task': serialized,
        'item': serialized,
    })


@main_bp.route('/tarefas/<int:task_id>/delete', methods=['POST'])
@login_required
def delete_task(task_id):
    task = db.session.get(Task, task_id)
    is_ajax = _wants_json()

    if not task:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Tarefa não encontrada.', 'item_id': task_id}), 404
        flash('Tarefa não encontrada.', 'warning')
        return _redirect_back_or('main.list_tasks')

    if not _can_view_task(g.user, task):
        if is_ajax:
            return jsonify({'success': False, 'message': 'Sem permissão para excluir esta tarefa.', 'item_id': task_id}), 403
        flash('Você não tem permissão para excluir esta tarefa.', 'danger')
        return _redirect_back_or('main.list_tasks')

    if not _can_manage_task_restricted_actions(g.user, task):
        _audit_denied_task_action(task, 'forbidden_delete')
        if is_ajax:
            return jsonify({'success': False, 'message': DELETE_DENIED_MESSAGE, 'item_id': task_id}), 403
        flash(DELETE_DENIED_MESSAGE, 'danger')
        return _redirect_back_or('main.list_tasks')

    try:
        notify_task_deleted(task)
        db.session.delete(task)
        db.session.commit()
    except Exception as e:
        return _on_db_error_redirect(
            e, is_ajax=is_ajax, error_prefix='Erro ao excluir tarefa',
            endpoint='main.list_tasks', item_id=task_id,
        )

    if is_ajax:
        return jsonify({'success': True, 'message': 'Tarefa excluída com sucesso!', 'item_id': task_id})
    flash('Tarefa excluída com sucesso!', 'success')
    return _redirect_back_or('main.list_tasks')


@main_bp.route('/tarefas/<int:task_id>/update_status', methods=['POST'])
@login_required
def update_task_status(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        return jsonify({'success': False, 'message': 'Tarefa não encontrada'}), 404
    if not _can_view_task(g.user, task):
        return jsonify({'success': False, 'message': 'Sem permissão'}), 403

    payload = request.get_json(silent=True) or {}
    status = payload.get('status')
    if status not in VALID_STATUSES:
        return jsonify({'success': False, 'message': 'Status inválido'}), 400

    if not _can_transition_task_to_status(g.user, task, status, previous_status=task.status):
        _audit_denied_task_action(task, 'forbidden_finalize', attempted_status=status)
        return jsonify({'success': False, 'message': FINALIZE_DENIED_MESSAGE}), 403

    old_status = task.status
    task.status = status

    try:
        notify_status_change(task, old_status)
        db.session.commit()
    except Exception as e:
        return _on_db_error(e)

    return jsonify({'success': True, 'message': 'Status atualizado'})


@main_bp.route('/tarefas/<int:task_id>/update_prioridade', methods=['POST'])
@login_required
def update_task_prioridade(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        return jsonify({'success': False, 'message': 'Tarefa não encontrada'}), 404
    if not _can_view_task(g.user, task):
        return jsonify({'success': False, 'message': 'Sem permissão'}), 403

    payload = request.get_json(silent=True) or {}
    prioridade = payload.get('prioridade', '') or None
    if prioridade and prioridade not in VALID_PRIORIDADES:
        return jsonify({'success': False, 'message': 'Prioridade inválida'}), 400

    if not _can_manage_task_restricted_actions(g.user, task):
        _audit_denied_task_action(task, 'forbidden_edit_restricted')
        return jsonify({'success': False, 'message': EDIT_RESTRICTED_FIELDS_DENIED_MESSAGE}), 403

    old_prioridade = task.prioridade
    task.prioridade = prioridade

    try:
        notify_prioridade_change(task, old_prioridade)
        db.session.commit()
    except Exception as e:
        return _on_db_error(e)

    return jsonify({'success': True, 'prioridade': task.prioridade or ''})


@main_bp.route('/tarefas/<int:task_id>/update_tipo', methods=['POST'])
@login_required
def update_task_tipo(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        return jsonify({'success': False, 'message': 'Tarefa não encontrada'}), 404
    if not _can_view_task(g.user, task):
        return jsonify({'success': False, 'message': 'Sem permissão'}), 403

    payload = request.get_json(silent=True) or {}
    tipo = payload.get('tipo_pedido', '') or None
    if tipo and tipo not in VALID_TIPOS:
        return jsonify({'success': False, 'message': 'Tipo inválido'}), 400

    old_tipo = task.tipo_pedido
    task.tipo_pedido = tipo

    try:
        notify_tipo_change(task, old_tipo)
        db.session.commit()
    except Exception as e:
        return _on_db_error(e)

    return jsonify({'success': True, 'tipo_pedido': task.tipo_pedido or ''})


@main_bp.route('/tarefas/<int:task_id>/finalizar', methods=['POST'])
@login_required
def finalize_task(task_id):
    is_ajax = _wants_json()
    task = db.session.get(Task, task_id)
    if not task or not _can_view_task(g.user, task):
        if is_ajax:
            return jsonify({'success': False, 'message': 'Você não tem permissão para finalizar esta tarefa.'}), 403
        flash('Você não tem permissão para finalizar esta tarefa.', 'danger')
        return _redirect_back_or('main.list_tasks')

    if not _can_manage_task_restricted_actions(g.user, task):
        _audit_denied_task_action(task, 'forbidden_finalize', attempted_status='finalizada')
        if is_ajax:
            return jsonify({'success': False, 'message': FINALIZE_DENIED_MESSAGE}), 403
        flash(FINALIZE_DENIED_MESSAGE, 'danger')
        return _redirect_back_or('main.list_tasks')

    if task.is_archived:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Esta tarefa já está arquivada.'}), 400
        flash('Esta tarefa já está arquivada.', 'info')
        return _redirect_back_or('main.list_tasks_archived')

    old_status = task.status
    task.status = 'finalizada'

    try:
        if old_status != task.status:
            notify_task_finalized(task)
        db.session.commit()
    except Exception as e:
        return _on_db_error_redirect(
            e, is_ajax=is_ajax, error_prefix='Erro ao finalizar tarefa', endpoint='main.list_tasks',
        )

    if is_ajax:
        serialized = _serialize_task_payload(task)
        return jsonify({'success': True, 'task': serialized, 'item': serialized})
    flash('Tarefa finalizada com sucesso!', 'success')
    return _redirect_back_or('main.list_tasks')


@main_bp.route('/tarefas/<int:task_id>/desarquivar', methods=['POST'])
@login_required
def unarchive_task(task_id):
    task = db.session.get(Task, task_id)
    is_ajax = _wants_json()
    if not task or not _can_view_task(g.user, task):
        return jsonify({'success': False, 'message': 'Sem permissão'}), 403

    mutate_unarchive_task(task)

    try:
        notify_task_unarchived(task)
        db.session.commit()
    except Exception as e:
        return _on_db_error_redirect(
            e, is_ajax=is_ajax, error_prefix='Erro ao desarquivar tarefa', endpoint='main.list_tasks_archived',
        )

    if is_ajax:
        serialized = _serialize_task_payload(task)
        return jsonify({'success': True, 'task': serialized, 'item': serialized})
    flash('Tarefa desarquivada com sucesso!', 'success')
    return _redirect_back_or('main.list_tasks')


@main_bp.route('/tarefas/<int:task_id>/reativar', methods=['POST'])
@login_required
def reactivate_task(task_id):
    return unarchive_task(task_id)


@main_bp.route('/tarefas/arquivar-finalizadas', methods=['POST'])
@login_required
def archive_finalized_tasks():
    is_ajax = _wants_json()

    payload = request.get_json(silent=True) or {}
    filter_values = _merge_task_filter_values(
        _read_task_filter_values(payload),
        _read_task_filter_values(request.form),
    )

    finalized_tasks = (
        _build_visible_tasks_query(
            include_archived=False,
            project_filter=filter_values['project_filter'],
            prioridade_filter=filter_values['prioridade_filter'],
            tipo_filter=filter_values['tipo_filter'],
            status_filter=filter_values['status_filter'],
            responsavel_filter=filter_values['responsavel_filter'],
            include_relations=False,
        )
        .filter(Task.status == 'finalizada')
        .all()
    )

    try:
        archived_ids = bulk_archive_finalized(finalized_tasks)
        for task in finalized_tasks:
            notify_task_archived_in_batch(task)
        db.session.commit()
    except Exception as e:
        return _on_db_error_redirect(
            e, is_ajax=is_ajax, error_prefix='Erro ao arquivar tarefas', endpoint='main.list_tasks',
        )

    archived_count = len(archived_ids)
    message = (
        f'{archived_count} tarefa(s) arquivada(s).'
        if archived_count
        else 'Nenhuma tarefa finalizada para arquivar no escopo atual.'
    )

    if is_ajax:
        return jsonify({
            'success': True,
            'archived_count': archived_count,
            'archived_task_ids': [str(tid) for tid in archived_ids],
            'message': message,
        })

    flash(message, 'success' if archived_count else 'info')
    return _redirect_back_or('main.list_tasks')


@main_bp.route('/tarefas/sugestoes-responsavel', methods=['GET'])
@login_required
def get_hub_assignable_users():
    project_raw = (request.args.get('project') or '').strip()
    area_raw = (request.args.get('area') or '').strip()

    if project_raw:
        project, project_error, status_code = _resolve_project_token(project_raw, allow_empty=False)
        if project_error:
            return jsonify({'success': False, 'message': project_error}), status_code
        users = _get_assignable_users_for_project(project)
    elif area_raw:
        users = _get_assignable_users_for_area(area_raw)
    else:
        return jsonify({'success': False, 'message': 'Informe um projeto ou área.'}), 400

    return jsonify({'users': _filter_users_by_query(users, request.args.get('q'))})


@main_bp.route('/tarefas/<int:task_id>/sugestoes-responsavel', methods=['GET'])
@login_required
def get_task_assignable_users(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        return jsonify({'success': False, 'message': 'Tarefa não encontrada'}), 404
    if not _can_view_task(g.user, task):
        return jsonify({'success': False, 'message': 'Sem permissão'}), 403

    users = _get_assignable_users_for_project(task.project)
    return jsonify({'users': _filter_users_by_query(users, request.args.get('q'))})


def _filter_users_by_query(users, raw_query):
    payload = [{'id': user.id, 'name': user.name} for user in users]
    query = (raw_query or '').strip().lower()
    if not query:
        return payload
    return [user for user in payload if query in (user['name'] or '').lower()]
