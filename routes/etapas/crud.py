import datetime

from flask import current_app, flash, g, jsonify, redirect, render_template, request, url_for

from models import Etapa, Project, db
from services.calendar_core import to_local_datetime
from services.calendar_sync import delete_remote_event, sync_local_event_to_google
from services.project_meetings import (
    MEETING_ENTRY_TYPE,
    can_manage_project_meeting,
    delete_local_calendar_event_mirrors,
    is_google_meeting_stage,
    sync_etapa_from_meeting,
    sync_local_calendar_event_mirrors,
    update_meeting_from_calendar_event,
)

from routes.blueprint import main_bp
from routes.decorators import login_required
from routes.shared import get_or_404, log_project_action
from routes.etapas.helpers import (
    _add_business_days,
    _business_days_between,
    _connection_for_current_user,
    _current_user_can_edit_project,
    _is_ajax_request,
    _next_etapa_order,
    _normalize_to_business_day,
    _serialize_etapa_payload,
)


@main_bp.route('/project/<int:project_id>/etapa/add', methods=['POST'])
@login_required
def add_etapa(project_id):
    ajax_request = _is_ajax_request()
    project = get_or_404(Project, project_id)
    if not _current_user_can_edit_project(project):
        if ajax_request:
            return jsonify({'success': False, 'message': 'Você não tem permissão para adicionar etapas a este projeto.'}), 403
        flash('Você não tem permissão para adicionar etapas a este projeto.', 'danger')
        return redirect(url_for('main.project_detail', project_id=project_id)) # Ou para list_projects

    descricao = (request.form.get('etapa_descricao') or '').strip()
    if not descricao:
        if ajax_request:
            return jsonify({'success': False, 'message': 'A descrição da etapa é obrigatória.'}), 400
        flash('A descrição da etapa é obrigatória.', 'warning')
        return redirect(url_for('main.project_detail', project_id=project_id))

    reactivate_project = (request.form.get('reactivate_project') or '').strip().lower() in {'1', 'true', 'on', 'sim'}
    if project.status == 'Finalizado' and not reactivate_project:
        message = 'Ao adicionar uma nova etapa, o projeto voltará para o status Vigente. Deseja continuar?'
        if ajax_request:
            return jsonify({
                'success': False,
                'message': message,
                'confirmation_required': True,
                'project_status': project.status,
            }), 409
        flash(message, 'warning')
        return redirect(url_for('main.project_detail', project_id=project_id))

    data_inicio_str = request.form.get('etapa_data_inicio')
    data_fim_str = request.form.get('etapa_data_fim')
    responsavel = (request.form.get('etapa_responsavel') or '').strip() or None
    comentarios = (request.form.get('etapa_comentarios') or '').strip() or None
    etapa_iniciada = request.form.get('etapa_iniciada') == 'on'
    etapa_concluida = request.form.get('etapa_done') == 'on'
    validation_warning = None
    project_was_reactivated = False

    if not etapa_iniciada and etapa_concluida:
        validation_warning = 'Uma etapa não pode ser marcada como concluída sem ser iniciada.'
        if not ajax_request:
            flash(validation_warning, 'warning')
        etapa_concluida = False # Força para não concluída

    try:
        data_inicio = datetime.datetime.strptime(data_inicio_str, '%Y-%m-%d').date() if data_inicio_str else None
        data_fim = datetime.datetime.strptime(data_fim_str, '%Y-%m-%d').date() if data_fim_str else None
    except ValueError:
        if ajax_request:
            return jsonify({'success': False, 'message': 'Formato de data inválido.'}), 400
        flash('Formato de data inválido.', 'warning')
        return redirect(url_for('main.project_detail', project_id=project_id))

    # Calcular a ordem da nova etapa
    nova_ordem = _next_etapa_order(project.id)

    new_etapa = Etapa(
        descricao=descricao, data_inicio=data_inicio, data_fim=data_fim,
        responsavel=responsavel, iniciada=etapa_iniciada, done=etapa_concluida,
        comentarios=comentarios, project_id=project.id, ordem=nova_ordem  # Adicionado ordem
    )
    db.session.add(new_etapa)

    try:
        if project.status == 'Finalizado':
            project.status = 'Vigente'
            project_was_reactivated = True

            log_project_action(
                project_id=project.id,
                action_type='reactivate',
                description=f'Reativou o projeto ao adicionar a etapa "{descricao}"'
            )

        # Registrar no histórico
        log_project_action(
            project_id=project.id,
            action_type='add_etapa',
            description=f'Adicionou a etapa "{descricao}"'
        )

        db.session.commit()

        success_message = 'Etapa adicionada com sucesso!'
        if project_was_reactivated:
            success_message = 'Etapa adicionada com sucesso! O projeto voltou para Vigente.'

        if ajax_request:
            return jsonify(
                {
                    'success': True,
                    'message': success_message,
                    'warning': validation_warning,
                    'project_status': project.status,
                    'project_reactivated': project_was_reactivated,
                    'reload_page': project_was_reactivated,
                    'etapa': _serialize_etapa_payload(new_etapa, connection=_connection_for_current_user()),
                }
            )
    except Exception:
        db.session.rollback()
        if ajax_request:
            return jsonify({'success': False, 'message': 'Erro ao adicionar etapa.'}), 500
        flash('Erro ao adicionar etapa.', 'danger')
        return redirect(url_for('main.project_detail', project_id=project_id))

    flash(success_message, 'success')
    return redirect(url_for('main.project_detail', project_id=project_id))


@main_bp.route('/etapa/<int:etapa_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_etapa(etapa_id):
    etapa = get_or_404(Etapa, etapa_id)
    project_of_etapa = etapa.project # Projeto pai da etapa
    if not _current_user_can_edit_project(project_of_etapa):
        flash('Você não tem permissão para editar etapas deste projeto.', 'danger')
        return redirect(url_for('main.project_detail', project_id=project_of_etapa.id))

    if is_google_meeting_stage(etapa):
        flash('Reuniões do Google devem ser editadas pelo fluxo de calendário ou pelo ajuste rápido de datas.', 'warning')
        return redirect(url_for('main.project_detail', project_id=project_of_etapa.id))

    if request.method == 'POST':
        old_descricao = etapa.descricao
        etapa.descricao = request.form.get('etapa_descricao')
        etapa.responsavel = request.form.get('etapa_responsavel')
        etapa.comentarios = request.form.get('etapa_comentarios')
        etapa.iniciada = request.form.get('etapa_iniciada') == 'on'
        etapa_done_form = request.form.get('etapa_done') == 'on'

        if not etapa.iniciada and etapa_done_form:
            flash('A etapa não pode ser marcada como concluída pois não foi iniciada.', 'warning')
            etapa.done = False
        else:
            etapa.done = etapa_done_form

        data_inicio_str = request.form.get('etapa_data_inicio')
        etapa.data_inicio = datetime.datetime.strptime(data_inicio_str, '%Y-%m-%d').date() if data_inicio_str else None
        data_fim_str = request.form.get('etapa_data_fim')
        etapa.data_fim = datetime.datetime.strptime(data_fim_str, '%Y-%m-%d').date() if data_fim_str else None

        # Registrar no histórico
        log_project_action(
            project_id=etapa.project_id,
            action_type='edit_etapa',
            description=f'Editou a etapa "{old_descricao}"'
        )

        db.session.commit()
        flash('Etapa atualizada com sucesso!', 'success')
        return redirect(url_for('main.project_detail', project_id=etapa.project_id))

    data_inicio_f = etapa.data_inicio.strftime('%Y-%m-%d') if etapa.data_inicio else ''
    data_fim_f = etapa.data_fim.strftime('%Y-%m-%d') if etapa.data_fim else ''
    return render_template('etapas/form.html', etapa=etapa, action=url_for('main.edit_etapa', etapa_id=etapa_id), data_inicio_form=data_inicio_f, data_fim_form=data_fim_f)

@main_bp.route('/etapa/<int:etapa_id>/delete', methods=['POST'])
@login_required
def delete_etapa(etapa_id):
    ajax_request = _is_ajax_request()
    etapa_to_delete = get_or_404(Etapa, etapa_id)
    project_of_etapa = etapa_to_delete.project
    project_id_for_redirect = etapa_to_delete.project_id

    if not _current_user_can_edit_project(project_of_etapa):
        message = 'Você não tem permissão para excluir etapas deste projeto.'
        if ajax_request:
            return jsonify({
                'success': False,
                'message': message,
                'etapa_id': etapa_id,
                'project_id': project_id_for_redirect,
            }), 403
        flash('Você não tem permissão para excluir etapas deste projeto.', 'danger')
        return redirect(url_for('main.project_detail', project_id=project_of_etapa.id))

    meeting = etapa_to_delete.meeting if is_google_meeting_stage(etapa_to_delete) else None
    if meeting is not None:
        connection = _connection_for_current_user()
        if not can_manage_project_meeting(connection, meeting):
            message = 'Somente quem estiver com a mesma conta Google conectada pode excluir esta reunião.'
            if ajax_request:
                return jsonify({'success': False, 'message': message, 'etapa_id': etapa_id}), 403
            flash(message, 'warning')
            return redirect(url_for('main.project_detail', project_id=project_id_for_redirect))

        remote_warning = None
        if meeting.google_event_id and meeting.sync_status != 'error':
            try:
                delete_remote_event(
                    current_app.config,
                    connection,
                    google_event_id=meeting.google_event_id,
                    google_calendar_id=meeting.google_calendar_id,
                )
            except Exception as exc:
                remote_warning = str(exc)

        if remote_warning:
            if ajax_request:
                return jsonify({'success': False, 'message': remote_warning, 'etapa_id': etapa_id}), 502
            flash(remote_warning, 'warning')
            return redirect(url_for('main.project_detail', project_id=project_id_for_redirect))

        etapa_descricao = etapa_to_delete.descricao
        try:
            log_project_action(
                project_id=project_id_for_redirect,
                action_type='delete_google_meeting',
                description=f'Excluiu a reunião "{etapa_descricao}"',
            )
            delete_local_calendar_event_mirrors(meeting)
            db.session.delete(etapa_to_delete)
            db.session.commit()
        except Exception:
            db.session.rollback()
            if ajax_request:
                return jsonify({'success': False, 'message': 'Erro ao excluir reunião.', 'etapa_id': etapa_id}), 500
            flash('Erro ao excluir reunião.', 'danger')
            return redirect(url_for('main.project_detail', project_id=project_id_for_redirect))

        if ajax_request:
            project = db.session.get(Project, project_id_for_redirect)
            total_etapas = project.total_workflow_etapas if project is not None else 0
            return jsonify({
                'success': True,
                'message': 'Reunião excluída com sucesso.',
                'etapa_id': etapa_id,
                'project_id': project_id_for_redirect,
                'total_etapas': total_etapas,
            })

        flash('Reunião excluída com sucesso.', 'success')
        return redirect(url_for('main.project_detail', project_id=project_id_for_redirect))

    etapa_descricao = etapa_to_delete.descricao

    try:
        # Registrar no histórico
        log_project_action(
            project_id=project_id_for_redirect,
            action_type='delete_etapa',
            description=f'Excluiu a etapa "{etapa_descricao}"'
        )

        db.session.delete(etapa_to_delete)
        db.session.commit()
    except Exception:
        db.session.rollback()
        if ajax_request:
            return jsonify({
                'success': False,
                'message': 'Erro ao excluir etapa.',
                'etapa_id': etapa_id,
                'project_id': project_id_for_redirect,
            }), 500
        flash('Erro ao excluir etapa.', 'danger')
        return redirect(url_for('main.project_detail', project_id=project_id_for_redirect))

    if ajax_request:
        project = db.session.get(Project, project_id_for_redirect)
        total_etapas = project.total_workflow_etapas if project is not None else 0
        return jsonify({
            'success': True,
            'message': 'Etapa excluída com sucesso.',
            'etapa_id': etapa_id,
            'project_id': project_id_for_redirect,
            'total_etapas': total_etapas,
        })

    flash('Etapa excluída com sucesso.', 'success')
    return redirect(url_for('main.project_detail', project_id=project_id_for_redirect))

@main_bp.route('/project/<int:project_id>/etapas/reordenar', methods=['POST'])
@login_required
def reorder_etapas(project_id):
    project = get_or_404(Project, project_id)
    if not g.user.is_admin and not g.user.has_access_to_area(project.area_responsavel):
        return jsonify({'success': False, 'message': 'Você não tem permissão para reordenar etapas deste projeto.'}), 403

    data = request.get_json() or {}
    etapa_ids_ordenadas = data.get('etapa_ids')

    if not etapa_ids_ordenadas or not isinstance(etapa_ids_ordenadas, list):
        return jsonify({'success': False, 'message': 'Lista de IDs de etapas inválida.'}), 400

    try:
        for index, etapa_id in enumerate(etapa_ids_ordenadas):
            etapa = Etapa.query.filter_by(id=etapa_id, project_id=project.id).first()
            if etapa:
                etapa.ordem = index
            else:
                # Tratar caso onde um ID de etapa não pertence ao projeto ou não existe
                # Pode ser um erro, ou apenas ignorar silenciosamente dependendo da política
                # Por segurança, vamos logar e retornar um erro se um ID for inválido.
                print(f"Tentativa de reordenar etapa inválida (ID: {etapa_id}) para o projeto {project.id}")
                # Poderia lançar uma exceção ou retornar um erro específico

        db.session.commit()
        # flash('Ordem das etapas atualizada com sucesso!', 'success') # Flash não funciona bem com AJAX
        return jsonify({'success': True, 'message': 'Ordem das etapas atualizada.'})
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao reordenar etapas: {e}")
        return jsonify({'success': False, 'message': 'Erro ao atualizar a ordem das etapas.'}), 500

@main_bp.route('/etapa/<int:etapa_id>/toggle_iniciada', methods=['POST'])
@login_required
def toggle_iniciada_etapa(etapa_id):
    etapa = get_or_404(Etapa, etapa_id)
    project_of_etapa = etapa.project
    if not _current_user_can_edit_project(project_of_etapa):
        return jsonify({'success': False, 'message': 'Permissão negada para alterar esta etapa.'}), 403
    if is_google_meeting_stage(etapa):
        return jsonify({'success': False, 'message': 'Reuniões Google não participam do fluxo de início/conclusão.'}), 400

    etapa.iniciada = not etapa.iniciada
    ajax_flash_message = None

    # Registrar no histórico
    status_text = 'iniciada' if etapa.iniciada else 'não iniciada'
    log_project_action(
        project_id=etapa.project_id,
        action_type='toggle_iniciada',
        description=f'Marcou a etapa "{etapa.descricao}" como {status_text}'
    )

    if not etapa.iniciada and etapa.done: # Se desmarcou iniciada e estava concluída
        etapa.done = False
        ajax_flash_message = 'Etapa marcada como não iniciada e, consequentemente, como não concluída.'
    db.session.commit()
    return jsonify({
        'success': True, 'etapa_id': etapa.id, 'iniciada': etapa.iniciada,
        'done': etapa.done, 'message': ajax_flash_message
    })

@main_bp.route('/etapa/<int:etapa_id>/toggle', methods=['POST']) # Rota para toggle 'done'
@login_required
def toggle_etapa(etapa_id): # Renomeada para evitar conflito, mas a URL é a mesma
    etapa = get_or_404(Etapa, etapa_id)
    project_of_etapa = etapa.project
    if not _current_user_can_edit_project(project_of_etapa):
        return jsonify({'success': False, 'message': 'Permissão negada para alterar esta etapa.'}), 403
    if is_google_meeting_stage(etapa):
        return jsonify({'success': False, 'message': 'Reuniões Google não participam do fluxo de início/conclusão.'}), 400

    if not etapa.iniciada and not etapa.done: # Tentando marcar como 'done' sem estar 'iniciada'
        return jsonify({
            'success': False, 'etapa_id': etapa.id, 'iniciada': etapa.iniciada,
            'done': etapa.done, 'message': 'Não é possível concluir uma etapa que não foi iniciada.'
        })

    etapa.done = not etapa.done

    # Registrar no histórico
    status_text = 'concluída' if etapa.done else 'não concluída'
    log_project_action(
        project_id=etapa.project_id,
        action_type='toggle_done',
        description=f'Marcou a etapa "{etapa.descricao}" como {status_text}'
    )

    db.session.commit()
    return jsonify({
        'success': True, 'etapa_id': etapa.id, 'iniciada': etapa.iniciada,
        'done': etapa.done, 'message': None # Nenhuma mensagem específica aqui a menos que haja um caso
    })

@main_bp.route('/etapa/<int:etapa_id>/update_field', methods=['POST'])
@login_required
def update_etapa_field(etapa_id):
    etapa = get_or_404(Etapa, etapa_id)
    project_of_etapa = etapa.project

    if not _current_user_can_edit_project(project_of_etapa):
        return jsonify({'success': False, 'message': 'Permissão negada.'}), 403

    data = request.get_json()
    field = data.get('field')
    value = data.get('value')

    if is_google_meeting_stage(etapa):
        meeting = etapa.meeting
        connection = _connection_for_current_user()
        if field not in ['data_inicio', 'data_fim']:
            return jsonify({'success': False, 'message': 'Nesta reunião só é permitido ajustar as datas.'}), 400
        if meeting is None or not can_manage_project_meeting(connection, meeting):
            return jsonify({'success': False, 'message': 'Somente a mesma conta Google conectada pode editar esta reunião.'}), 403
        if meeting.sync_status == 'error':
            return jsonify({
                'success': False,
                'message': 'Esta reunião está somente leitura porque o evento não está mais disponível no Google Calendar.',
            }), 409

        try:
            new_date = datetime.datetime.strptime(value, '%Y-%m-%d').date() if value else None
        except ValueError:
            return jsonify({'success': False, 'message': 'Formato de data inválido.'}), 400

        if new_date is None:
            return jsonify({'success': False, 'message': 'A data da reunião é obrigatória.'}), 400

        start_local = to_local_datetime(meeting.starts_at)
        end_local = to_local_datetime(meeting.ends_at)
        if start_local is None or end_local is None:
            return jsonify({'success': False, 'message': 'A reunião não possui horário válido para ajuste.'}), 400

        if field == 'data_inicio':
            duration = meeting.ends_at - meeting.starts_at
            new_start_local = datetime.datetime.combine(new_date, start_local.timetz())
            new_start_utc = new_start_local.astimezone(datetime.timezone.utc).replace(tzinfo=None)
            new_end_utc = new_start_utc + duration
            old_value_str = start_local.strftime('%d/%m/%Y')
            new_value_str = new_start_local.strftime('%d/%m/%Y')
            meeting.starts_at = new_start_utc
            meeting.ends_at = new_end_utc
        else:
            new_end_local = datetime.datetime.combine(new_date, end_local.timetz())
            new_end_utc = new_end_local.astimezone(datetime.timezone.utc).replace(tzinfo=None)
            if new_end_utc <= meeting.starts_at:
                return jsonify({'success': False, 'message': 'A data final precisa ser posterior ao início da reunião.'}), 400
            old_value_str = end_local.strftime('%d/%m/%Y')
            new_value_str = new_end_local.strftime('%d/%m/%Y')
            meeting.ends_at = new_end_utc

        event = meeting.calendar_event
        if event is not None:
            event.starts_at = meeting.starts_at
            event.ends_at = meeting.ends_at
            event.is_all_day = meeting.is_all_day
            event.timezone = meeting.timezone
            try:
                sync_local_event_to_google(
                    current_app.config,
                    event,
                    connection,
                    create_conference=False,
                )
            except Exception as exc:
                event.sync_status = 'error'
                event.sync_error = str(exc)
            update_meeting_from_calendar_event(meeting, event)
        sync_etapa_from_meeting(etapa, meeting, title=etapa.descricao)
        sync_local_calendar_event_mirrors(meeting, title=etapa.descricao)

        log_project_action(
            project_id=etapa.project_id,
            action_type='reschedule_google_meeting',
            description=f'Reagendou a reunião "{etapa.descricao}"',
            old_value=old_value_str,
            new_value=new_value_str,
        )

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            return jsonify({'success': False, 'message': 'Erro ao salvar a alteração da reunião.'}), 500

        response_data = {
            'success': True,
            'newValue': (
                etapa.data_inicio.strftime('%Y-%m-%d')
                if field == 'data_inicio' and etapa.data_inicio
                else (etapa.data_fim.strftime('%Y-%m-%d') if etapa.data_fim else '')
            ),
            'displayValue': (
                etapa.data_inicio.strftime('%d/%m/%Y')
                if field == 'data_inicio' and etapa.data_inicio
                else (etapa.data_fim.strftime('%d/%m/%Y') if etapa.data_fim else 'Sem data')
            ),
            'isMeeting': True,
            'message': 'Data da reunião atualizada com sucesso.',
        }
        if field == 'data_inicio' and etapa.data_fim:
            response_data['updatedEndDate'] = etapa.data_fim.strftime('%Y-%m-%d')
            response_data['updatedEndDateDisplay'] = etapa.data_fim.strftime('%d/%m/%Y')
        return jsonify(response_data)

    if field not in ['descricao', 'data_inicio', 'data_fim', 'responsavel']:
        return jsonify({'success': False, 'message': 'Campo inválido.'}), 400

    try:
        response_data = {'success': True}

        # Mapeamento de nomes de campos para exibição
        field_names = {
            'descricao': 'descrição',
            'data_inicio': 'data de início',
            'data_fim': 'data de fim',
            'responsavel': 'responsável'
        }
        field_display = field_names.get(field, field)

        if field == 'data_inicio':
            old_date = etapa.data_inicio
            raw_new_date = datetime.datetime.strptime(value, '%Y-%m-%d').date() if value else None
            new_date = _normalize_to_business_day(raw_new_date, forward=True) if raw_new_date else None

            # Registrar no histórico
            old_value_str = old_date.strftime('%d/%m/%Y') if old_date else 'vazio'
            new_value_str = new_date.strftime('%d/%m/%Y') if new_date else 'vazio'
            log_project_action(
                project_id=etapa.project_id,
                action_type='edit_etapa_inline',
                description=f'Alterou {field_display} da etapa "{etapa.descricao}"',
                old_value=old_value_str,
                new_value=new_value_str
            )

            etapa.data_inicio = new_date
            response_data['newValue'] = new_date.strftime('%Y-%m-%d') if new_date else ''
            response_data['displayValue'] = new_date.strftime('%d/%m/%Y') if new_date else 'Sem data'

            if old_date and new_date:
                days_diff = _business_days_between(old_date, new_date)
                if etapa.data_fim:
                    etapa.data_fim = _add_business_days(etapa.data_fim, days_diff)
                    etapa.data_fim = _normalize_to_business_day(etapa.data_fim, forward=True)
                    response_data['updatedEndDate'] = etapa.data_fim.strftime('%Y-%m-%d')
                    response_data['updatedEndDateDisplay'] = etapa.data_fim.strftime('%d/%m/%Y')
                response_data['daysDiff'] = days_diff

        elif field == 'data_fim':
            old_date = etapa.data_fim
            raw_new_date = datetime.datetime.strptime(value, '%Y-%m-%d').date() if value else None
            new_date = _normalize_to_business_day(raw_new_date, forward=True) if raw_new_date else None

            # Registrar no histórico
            old_value_str = old_date.strftime('%d/%m/%Y') if old_date else 'vazio'
            new_value_str = new_date.strftime('%d/%m/%Y') if new_date else 'vazio'
            log_project_action(
                project_id=etapa.project_id,
                action_type='edit_etapa_inline',
                description=f'Alterou {field_display} da etapa "{etapa.descricao}"',
                old_value=old_value_str,
                new_value=new_value_str
            )

            etapa.data_fim = new_date
            response_data['newValue'] = new_date.strftime('%Y-%m-%d') if new_date else ''
            response_data['displayValue'] = new_date.strftime('%d/%m/%Y') if new_date else 'Sem data'

        elif field == 'descricao':
            old_value = etapa.descricao
            new_value = value

            # Registrar no histórico
            log_project_action(
                project_id=etapa.project_id,
                action_type='edit_etapa_inline',
                description=f'Alterou {field_display} da etapa',
                old_value=old_value or 'vazio',
                new_value=new_value or 'vazio'
            )

            etapa.descricao = new_value
            response_data['newValue'] = new_value
            response_data['displayValue'] = new_value if new_value else '-'

        elif field == 'responsavel':
            old_value = etapa.responsavel
            new_value = value

            # Registrar no histórico
            log_project_action(
                project_id=etapa.project_id,
                action_type='edit_etapa_inline',
                description=f'Alterou {field_display} da etapa "{etapa.descricao}"',
                old_value=old_value or 'vazio',
                new_value=new_value or 'vazio'
            )

            etapa.responsavel = new_value
            response_data['newValue'] = new_value
            response_data['displayValue'] = new_value if new_value else 'Sem responsável'

        db.session.commit()
        return jsonify(response_data)

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Erro ao salvar a alteração.'}), 500

@main_bp.route('/etapa/<int:etapa_id>/comentario', methods=['POST'])
@login_required
def update_etapa_comentario(etapa_id):
    """Endpoint para adicionar/editar/remover comentário de uma etapa via modal."""
    etapa = get_or_404(Etapa, etapa_id)
    project_of_etapa = etapa.project

    if not _current_user_can_edit_project(project_of_etapa):
        return jsonify({'success': False, 'message': 'Permissão negada.'}), 403
    if is_google_meeting_stage(etapa):
        return jsonify({'success': False, 'message': 'Reuniões Google não aceitam comentários de etapa.'}), 400

    if etapa.done:
        return jsonify({'success': False, 'message': 'Não é possível editar comentários de uma etapa concluída.'}), 403

    data = request.get_json()
    comentario = data.get('comentario', '').strip()

    try:
        old_comentario = etapa.comentarios or 'vazio'
        new_comentario = comentario if comentario else 'vazio'

        # Atualizar o comentário
        etapa.comentarios = comentario if comentario else None

        # Registrar no histórico
        action_description = 'Adicionou comentário' if comentario and old_comentario == 'vazio' else \
                             'Removeu comentário' if not comentario and old_comentario != 'vazio' else \
                             'Editou comentário'

        log_project_action(
            project_id=etapa.project_id,
            action_type='edit_etapa_comentario',
            description=f'{action_description} da etapa "{etapa.descricao}"',
            old_value=old_comentario,
            new_value=new_comentario
        )

        db.session.commit()

        message = 'Comentário salvo com sucesso!' if comentario else 'Comentário removido com sucesso!'
        return jsonify({'success': True, 'message': message})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Erro ao salvar comentário.'}), 500

@main_bp.route('/project/<int:project_id>/cascade_update', methods=['POST'])
@login_required
def cascade_date_update(project_id):
    project = get_or_404(Project, project_id)
    if not _current_user_can_edit_project(project):
        return jsonify({'success': False, 'message': 'Permissão negada.'}), 403

    data = request.get_json() or {}
    base_etapa_id = data.get('etapa_id')
    days_to_add = data.get('days_diff')

    if not all([base_etapa_id, days_to_add is not None]):
         return jsonify({'success': False, 'message': 'Parâmetros inválidos.'}), 400

    try:
        days_to_add = int(days_to_add)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Parâmetro de dias inválido.'}), 400

    try:
        base_etapa = db.session.get(Etapa, base_etapa_id)
        if not base_etapa or base_etapa.project_id != project_id:
            return jsonify({'success': False, 'message': 'Etapa base não encontrada.'}), 404
        if is_google_meeting_stage(base_etapa):
            return jsonify({'success': False, 'message': 'Reuniões Google não participam da cascata de datas.'}), 400

        subsequent_etapas = Etapa.query.filter(
            Etapa.project_id == project_id,
            Etapa.ordem > base_etapa.ordem,
            Etapa.entry_type != MEETING_ENTRY_TYPE,
        ).order_by(Etapa.ordem.asc(), Etapa.id.asc()).all()

        for etapa in subsequent_etapas:
            if etapa.data_inicio:
                etapa.data_inicio = _add_business_days(etapa.data_inicio, days_to_add)
                etapa.data_inicio = _normalize_to_business_day(etapa.data_inicio, forward=True)
            if etapa.data_fim:
                etapa.data_fim = _add_business_days(etapa.data_fim, days_to_add)
                etapa.data_fim = _normalize_to_business_day(etapa.data_fim, forward=True)

        db.session.commit()
        return jsonify({'success': True, 'message': 'Datas subsequentes atualizadas com sucesso.'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Erro ao atualizar datas subsequentes.'}), 500
