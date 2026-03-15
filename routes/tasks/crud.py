from flask import flash, g, jsonify, request, url_for

from models import (
    Task,
    db,
)
from services.notifications import notify_task_assignment_change, notify_task_event
from time_utils import utc_now

from routes.blueprint import main_bp
from routes.decorators import login_required

from routes.tasks.helpers import (
    LEGACY_TIPOS,
    VALID_PRIORIDADES,
    VALID_STATUSES,
    VALID_TIPOS,
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
    _preview_text,
    _read_task_filter_values,
    _redirect_back_or,
    _resolve_project_token,
    _resolve_responsavel_for_edit,
    _serialize_task_payload,
    _task_active_target_url,
    _task_status_label,
)

FINALIZE_DENIED_MESSAGE = 'Apenas o criador da tarefa pode movê-la para Finalizada.'
DELETE_DENIED_MESSAGE = 'Somente o autor da tarefa ou um administrador pode excluí-la.'
EDIT_RESTRICTED_FIELDS_DENIED_MESSAGE = (
    'Somente o autor da tarefa ou um administrador pode editar descrição, prioridade e responsável.'
)


def _parse_unique_task_order_ids(raw_ids):
    if not isinstance(raw_ids, list):
        raw_ids = []

    ordered_ids = []
    seen = set()
    for raw_id in raw_ids:
        try:
            task_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if task_id in seen:
            continue
        seen.add(task_id)
        ordered_ids.append(task_id)

    return ordered_ids


def _task_hub_reorder_scope_key(task):
    if task.project_id is not None:
        return ('project', task.project_id)
    if g.user.is_admin:
        return ('orphan', None)
    return ('orphan', task.created_by_id)


def _build_task_hub_reorder_scope_query(scope_key):
    scope_type, scope_value = scope_key
    query = _build_visible_tasks_query(include_relations=False).order_by(None)

    if scope_type == 'project':
        query = query.filter(Task.project_id == scope_value)
    elif scope_type == 'orphan':
        query = query.filter(Task.project_id.is_(None))
        if scope_value is not None:
            query = query.filter(Task.created_by_id == scope_value)
    else:
        query = query.filter(db.false())

    return query.order_by(Task.ordem.asc(), Task.id.asc())


def _apply_task_order(scope_query, ordered_ids):
    scope_tasks = scope_query.all()
    tasks_by_id = {task.id: task for task in scope_tasks}

    ordered_tasks = [tasks_by_id[task_id] for task_id in ordered_ids if task_id in tasks_by_id]
    ordered_task_ids = {task.id for task in ordered_tasks}
    remaining_tasks = [task for task in scope_tasks if task.id not in ordered_task_ids]

    for index, task in enumerate(ordered_tasks + remaining_tasks, start=1):
        task.ordem = index


def _archive_task(task):
    task.is_archived = True
    task.archived_at = utc_now()


@main_bp.route('/tarefas/add', methods=['POST'])
@login_required
def add_task():
    return _create_task_common()


@main_bp.route('/tarefas/reordenar', methods=['POST'])
@login_required
def reorder_tasks_hub():
    payload = request.get_json(silent=True) or {}
    ordem_ids = _parse_unique_task_order_ids(payload.get('ordem', []))
    if not ordem_ids:
        return jsonify({'success': True, 'message': 'Nenhuma alteração de ordem enviada'})

    visible_tasks = (
        _build_visible_tasks_query(include_relations=False)
        .order_by(None)
        .filter(Task.id.in_(ordem_ids))
        .all()
    )
    tasks_by_id = {task.id: task for task in visible_tasks}

    scope_orders = {}
    scope_sequence = []
    for task_id in ordem_ids:
        task = tasks_by_id.get(task_id)
        if task is None:
            continue
        scope_key = _task_hub_reorder_scope_key(task)
        if scope_key not in scope_orders:
            scope_orders[scope_key] = []
            scope_sequence.append(scope_key)
        scope_orders[scope_key].append(task.id)

    try:
        for scope_key in scope_sequence:
            _apply_task_order(
                _build_task_hub_reorder_scope_query(scope_key),
                scope_orders[scope_key],
            )
        db.session.commit()
        return jsonify({'success': True, 'message': 'Ordem atualizada'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@main_bp.route('/tarefas/<int:task_id>/edit', methods=['POST'])
@login_required
def edit_task(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        return jsonify({'success': False, 'message': 'Tarefa não encontrada'}), 404
    if not _can_view_task(g.user, task):
        return jsonify({'success': False, 'message': 'Sem permissão'}), 403

    payload = request.get_json(silent=True) or {}

    incoming_descricao = request.form.get('descricao')
    if incoming_descricao is None:
        incoming_descricao = payload.get('descricao')
    if incoming_descricao is None:
        incoming_descricao = request.form.get('titulo')
    if incoming_descricao is None:
        incoming_descricao = payload.get('titulo')
    if incoming_descricao is None:
        incoming_descricao = task.descricao
    incoming_descricao = (incoming_descricao or '').strip()

    incoming_status = request.form.get('status')
    if incoming_status is None:
        incoming_status = payload.get('status')
    if incoming_status is None:
        incoming_status = task.status
    incoming_status = (incoming_status or '').strip()
    if incoming_status not in VALID_STATUSES:
        incoming_status = task.status

    project_raw = request.form.get('project')
    if project_raw is None:
        project_raw = request.form.get('project_id')
    if project_raw is None:
        project_raw = payload.get('project')
    if project_raw is None:
        project_raw = payload.get('project_id')

    if project_raw is None:
        project = task.project
    else:
        project, project_error, status_code = _resolve_project_token(project_raw, allow_empty=True)
        if project_error:
            return jsonify({'success': False, 'message': project_error}), status_code

    if 'responsavel' in request.form or 'responsavel' in payload:
        incoming_responsavel = (request.form.get('responsavel') or payload.get('responsavel') or '').strip()
    else:
        incoming_responsavel = task.responsavel or ''

    if 'prioridade' in request.form or 'prioridade' in payload:
        incoming_prioridade = (request.form.get('prioridade') or payload.get('prioridade') or '').strip() or None
        if incoming_prioridade and incoming_prioridade not in VALID_PRIORIDADES:
            incoming_prioridade = None
    else:
        incoming_prioridade = task.prioridade

    if 'tipo_pedido' in request.form or 'tipo_pedido' in payload:
        incoming_tipo = (request.form.get('tipo_pedido') or payload.get('tipo_pedido') or '').strip() or None
        if incoming_tipo is None:
            resolved_tipo = None
        elif incoming_tipo in VALID_TIPOS:
            resolved_tipo = incoming_tipo
        elif incoming_tipo in LEGACY_TIPOS and task.tipo_pedido in LEGACY_TIPOS:
            resolved_tipo = task.tipo_pedido
        else:
            resolved_tipo = None
    else:
        resolved_tipo = task.tipo_pedido

    can_edit_restricted_fields = _can_manage_task_restricted_actions(g.user, task)
    descricao_changed = incoming_descricao != (task.descricao or '').strip()
    prioridade_changed = (incoming_prioridade or '') != (task.prioridade or '')
    responsavel_changed = (
        _normalize_responsavel_value(incoming_responsavel)
        != _normalize_responsavel_value(task.responsavel or '')
    )
    if (descricao_changed or prioridade_changed or responsavel_changed) and not can_edit_restricted_fields:
        _audit_denied_task_action(task, 'forbidden_edit_restricted')
        return jsonify({'success': False, 'message': EDIT_RESTRICTED_FIELDS_DENIED_MESSAGE}), 403

    if not incoming_descricao:
        return jsonify({'success': False, 'message': 'Descrição é obrigatória'}), 400

    is_valid_responsavel, resolved_responsavel, invalid_names = _resolve_responsavel_for_edit(
        task,
        incoming_responsavel,
        project,
    )
    if not is_valid_responsavel:
        return jsonify({'success': False, 'message': _format_invalid_responsavel_message(invalid_names)}), 400

    if not _can_transition_task_to_status(g.user, task, incoming_status, previous_status=task.status):
        _audit_denied_task_action(task, 'forbidden_finalize', attempted_status=incoming_status)
        return jsonify({'success': False, 'message': FINALIZE_DENIED_MESSAGE}), 403

    old_descricao = task.descricao
    old_status = task.status
    old_responsavel = task.responsavel
    old_prioridade = task.prioridade
    old_tipo = task.tipo_pedido
    old_project_id = task.project_id

    task.descricao = incoming_descricao
    task.status = incoming_status
    task.responsavel = resolved_responsavel if resolved_responsavel else None
    task.prioridade = incoming_prioridade
    task.tipo_pedido = resolved_tipo
    task.project_id = project.id if project else None

    try:
        changes = []
        if old_descricao != task.descricao:
            changes.append('descrição')
        if old_status != task.status:
            changes.append(f'status para {_task_status_label(task.status)}')
        if old_prioridade != task.prioridade:
            changes.append(f'prioridade para "{task.prioridade or "vazio"}"')
        if old_tipo != task.tipo_pedido:
            changes.append(f'tipo para "{task.tipo_pedido or "vazio"}"')
        if old_project_id != task.project_id:
            changes.append('projeto')

        if changes:
            notify_task_event(
                task,
                actor_user_id=g.user.id,
                event_type='task_updated',
                title='Tarefa atualizada',
                message=f'{g.user.name} atualizou "{_preview_text(task.descricao, 90)}": {", ".join(changes)}.',
            )

        if (old_responsavel or '') != (task.responsavel or ''):
            notify_task_assignment_change(
                task,
                task,
                g.user.id,
                old_responsavel=old_responsavel,
                new_responsavel=task.responsavel,
            )

        db.session.commit()
        serialized = _serialize_task_payload(task)
        return jsonify({
            'success': True,
            'message': 'Tarefa atualizada',
            'task': serialized,
            'item': serialized,
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@main_bp.route('/tarefas/<int:task_id>/delete', methods=['POST'])
@login_required
def delete_task(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Tarefa não encontrada.', 'item_id': task_id}), 404
        flash('Tarefa não encontrada.', 'warning')
        return _redirect_back_or('main.list_tasks')

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.best == 'application/json'
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
        notify_task_event(
            task,
            actor_user_id=g.user.id,
            event_type='task_deleted',
            title='Tarefa excluída',
            message=f'{g.user.name} excluiu "{_preview_text(task.descricao, 90)}".',
            target_url=url_for('main.list_tasks'),
        )
        db.session.delete(task)
        db.session.commit()
        if is_ajax:
            return jsonify({'success': True, 'message': 'Tarefa excluída com sucesso!', 'item_id': task_id})
        flash('Tarefa excluída com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        if is_ajax:
            return jsonify({'success': False, 'message': str(e), 'item_id': task_id}), 500
        flash(f'Erro ao excluir tarefa: {str(e)}', 'danger')

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
        if old_status != task.status:
            notify_task_event(
                task,
                actor_user_id=g.user.id,
                event_type='task_status_updated',
                title='Status atualizado',
                message=(
                    f'{g.user.name} alterou o status da tarefa "{_preview_text(task.descricao, 90)}" '
                    f'de {_task_status_label(old_status)} para {_task_status_label(task.status)}.'
                ),
            )
        db.session.commit()
        return jsonify({'success': True, 'message': 'Status atualizado'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


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
        if old_prioridade != task.prioridade:
            notify_task_event(
                task,
                actor_user_id=g.user.id,
                event_type='task_priority_updated',
                title='Prioridade atualizada',
                message=(
                    f'{g.user.name} alterou a prioridade da tarefa "{_preview_text(task.descricao, 90)}" '
                    f'de "{old_prioridade or "vazio"}" para "{task.prioridade or "vazio"}".'
                ),
            )
        db.session.commit()
        return jsonify({'success': True, 'prioridade': task.prioridade or ''})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


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
        if old_tipo != task.tipo_pedido:
            notify_task_event(
                task,
                actor_user_id=g.user.id,
                event_type='task_type_updated',
                title='Tipo atualizado',
                message=(
                    f'{g.user.name} alterou o tipo da tarefa "{_preview_text(task.descricao, 90)}" '
                    f'de "{old_tipo or "vazio"}" para "{task.tipo_pedido or "vazio"}".'
                ),
            )
        db.session.commit()
        return jsonify({'success': True, 'tipo_pedido': task.tipo_pedido or ''})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@main_bp.route('/tarefas/<int:task_id>/finalizar', methods=['POST'])
@login_required
def finalize_task(task_id):
    is_ajax = (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.accept_mimetypes.best == 'application/json'
    )
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

    try:
        old_status = task.status
        task.status = 'finalizada'
        if old_status != task.status:
            notify_task_event(
                task,
                actor_user_id=g.user.id,
                event_type='task_finalized',
                title='Tarefa finalizada',
                message=f'{g.user.name} finalizou a tarefa "{_preview_text(task.descricao, 90)}".',
                target_url=_task_active_target_url(task),
            )
        db.session.commit()
        if is_ajax:
            serialized = _serialize_task_payload(task)
            return jsonify({'success': True, 'task': serialized, 'item': serialized})
        flash('Tarefa finalizada com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        if is_ajax:
            return jsonify({'success': False, 'message': str(e)}), 500
        flash(f'Erro ao finalizar tarefa: {str(e)}', 'danger')

    return _redirect_back_or('main.list_tasks')


@main_bp.route('/tarefas/<int:task_id>/desarquivar', methods=['POST'])
@login_required
def unarchive_task(task_id):
    task = db.session.get(Task, task_id)
    if not task or not _can_view_task(g.user, task):
        return jsonify({'success': False, 'message': 'Sem permissão'}), 403

    task.is_archived = False
    task.archived_at = None
    task.status = 'nao_iniciada'

    try:
        notify_task_event(
            task,
            actor_user_id=g.user.id,
            event_type='task_unarchived',
            title='Tarefa desarquivada',
            message=f'{g.user.name} desarquivou "{_preview_text(task.descricao, 90)}".',
            target_url=url_for('main.list_tasks'),
        )
        db.session.commit()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.best == 'application/json':
            serialized = _serialize_task_payload(task)
            return jsonify({'success': True, 'task': serialized, 'item': serialized})
        flash('Tarefa desarquivada com sucesso!', 'success')
        return _redirect_back_or('main.list_tasks')
    except Exception as e:
        db.session.rollback()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.best == 'application/json':
            return jsonify({'success': False, 'message': str(e)}), 500
        flash(f'Erro ao desarquivar tarefa: {str(e)}', 'danger')
        return _redirect_back_or('main.list_tasks_archived')


@main_bp.route('/tarefas/<int:task_id>/reativar', methods=['POST'])
@login_required
def reactivate_task(task_id):
    return unarchive_task(task_id)


@main_bp.route('/tarefas/arquivar-finalizadas', methods=['POST'])
@login_required
def archive_finalized_tasks():
    is_ajax = (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.accept_mimetypes.best == 'application/json'
    )

    payload = request.get_json(silent=True) or {}
    filter_values = _merge_task_filter_values(
        _read_task_filter_values(payload),
        _read_task_filter_values(request.form),
    )
    selected_area = filter_values['selected_area']
    project_filter = filter_values['project_filter']
    prioridade_filter = filter_values['prioridade_filter']
    tipo_filter = filter_values['tipo_filter']
    status_filter = filter_values['status_filter']
    responsavel_filter = filter_values['responsavel_filter']

    query = _build_visible_tasks_query(
        include_archived=False,
        selected_area=selected_area,
        project_filter=project_filter,
        prioridade_filter=prioridade_filter,
        tipo_filter=tipo_filter,
        status_filter=status_filter,
        responsavel_filter=responsavel_filter,
        include_relations=False,
    ).filter(Task.status == 'finalizada')

    tasks = query.all()
    archived_count = 0
    archived_task_ids = []
    now = utc_now()

    try:
        for task in tasks:
            task.is_archived = True
            task.archived_at = now
            archived_count += 1
            archived_task_ids.append(str(task.id))
            notify_task_event(
                task,
                actor_user_id=g.user.id,
                event_type='task_archived',
                title='Tarefa arquivada',
                message=f'{g.user.name} arquivou a tarefa "{_preview_text(task.descricao, 90)}".',
                target_url=url_for('main.list_tasks_archived'),
            )
        db.session.commit()

        if is_ajax:
            return jsonify({
                'success': True,
                'archived_count': archived_count,
                'archived_task_ids': archived_task_ids,
                'message': f'{archived_count} tarefa(s) arquivada(s).' if archived_count else 'Nenhuma tarefa finalizada para arquivar no escopo atual.',
            })

        if archived_count:
            flash(f'{archived_count} tarefa(s) finalizada(s) arquivada(s).', 'success')
        else:
            flash('Nenhuma tarefa finalizada para arquivar no escopo atual.', 'info')
        return _redirect_back_or('main.list_tasks')
    except Exception as e:
        db.session.rollback()
        if is_ajax:
            return jsonify({'success': False, 'message': str(e)}), 500
        flash(f'Erro ao arquivar tarefas: {str(e)}', 'danger')
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

    payload = [{'id': user.id, 'name': user.name} for user in users]

    q = (request.args.get('q') or '').strip().lower()
    if q:
        payload = [user for user in payload if q in (user['name'] or '').lower()]

    return jsonify({'users': payload})


@main_bp.route('/tarefas/<int:task_id>/sugestoes-responsavel', methods=['GET'])
@login_required
def get_task_assignable_users(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        return jsonify({'success': False, 'message': 'Tarefa não encontrada'}), 404
    if not _can_view_task(g.user, task):
        return jsonify({'success': False, 'message': 'Sem permissão'}), 403

    users = _get_assignable_users_for_project(task.project)
    payload = [{'id': user.id, 'name': user.name} for user in users]

    q = (request.args.get('q') or '').strip().lower()
    if q:
        payload = [user for user in payload if q in (user['name'] or '').lower()]

    return jsonify({'users': payload})
