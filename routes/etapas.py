import datetime

from flask import flash, g, jsonify, redirect, render_template, request, url_for

from models import Etapa, Project, StageTemplate, db

from .blueprint import main_bp
from .decorators import login_required
from .shared import get_or_404, log_project_action
@main_bp.route('/project/<int:project_id>/etapa/add', methods=['POST'])
@login_required
def add_etapa(project_id):
    def is_ajax_request():
        requested_with = request.headers.get('X-Requested-With', '').lower() == 'xmlhttprequest'
        accepts_json = 'application/json' in request.headers.get('Accept', '').lower()
        return requested_with or accepts_json

    ajax_request = is_ajax_request()
    project = get_or_404(Project, project_id)
    if not g.user.is_admin and not g.user.has_access_to_area(project.area_responsavel):
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
    ultima_etapa = (
        db.session.query(Etapa)
        .filter(Etapa.project_id == project.id)
        .order_by(Etapa.ordem.desc())
        .first()
    )
    nova_ordem = (ultima_etapa.ordem + 1) if ultima_etapa else 0

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
                    'etapa': {
                        'id': new_etapa.id,
                        'descricao': new_etapa.descricao,
                        'comentarios': new_etapa.comentarios or '',
                        'responsavel': new_etapa.responsavel or '',
                        'data_inicio': new_etapa.data_inicio.strftime('%Y-%m-%d') if new_etapa.data_inicio else '',
                        'data_inicio_display': new_etapa.data_inicio.strftime('%d/%m/%Y') if new_etapa.data_inicio else '-',
                        'data_fim': new_etapa.data_fim.strftime('%Y-%m-%d') if new_etapa.data_fim else '',
                        'data_fim_display': new_etapa.data_fim.strftime('%d/%m/%Y') if new_etapa.data_fim else '-',
                        'iniciada': bool(new_etapa.iniciada),
                        'done': bool(new_etapa.done),
                        'ordem': int(new_etapa.ordem or 0),
                    },
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

@main_bp.route('/project/<int:project_id>/import_model', methods=['POST'])
@login_required
def import_model_to_project(project_id):
    """Importa etapas de um modelo para um projeto existente"""
    project = get_or_404(Project, project_id)
    
    # Verificar permissão
    if not g.user.is_admin and not g.user.has_access_to_area(project.area_responsavel):
        flash('Você não tem permissão para importar modelos neste projeto.', 'danger')
        return redirect(url_for('main.project_detail', project_id=project_id))
    
    template_id = request.form.get('template_id')
    start_date_str = request.form.get('start_date')
    
    if not template_id or not start_date_str:
        flash('Selecione um modelo e defina a data de início.', 'warning')
        return redirect(url_for('main.project_detail', project_id=project_id))
    
    # Buscar o modelo
    template = get_or_404(StageTemplate, template_id)
    
    if not template.items:
        flash('Este modelo não possui etapas.', 'warning')
        return redirect(url_for('main.project_detail', project_id=project_id))
    
    try:
        from datetime import datetime, timedelta
        
        # Converter data de início
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        current_date = start_date
        
        # Calcular a próxima ordem disponível
        ultima_etapa = (
            db.session.query(Etapa)
            .filter(Etapa.project_id == project.id)
            .order_by(Etapa.ordem.desc())
            .first()
        )
        ordem_inicial = (ultima_etapa.ordem + 1) if ultima_etapa else 0
        
        # Criar etapas baseadas no modelo
        etapas_criadas = 0
        for index, item in enumerate(template.items):
            # Calcular datas
            data_inicio = current_date
            data_fim = current_date + timedelta(days=item.duration_days - 1)
            
            # Criar etapa
            nova_etapa = Etapa(
                descricao=item.name,
                data_inicio=data_inicio,
                data_fim=data_fim,
                project_id=project.id,
                ordem=ordem_inicial + index,
                iniciada=False,
                done=False
            )
            db.session.add(nova_etapa)
            etapas_criadas += 1
            
            # Próxima etapa começa no dia seguinte ao fim desta
            current_date = data_fim + timedelta(days=1)
        
        # Registrar no histórico
        log_project_action(
            project_id=project.id,
            action_type='import_model',
            description=f'Importou {etapas_criadas} etapa(s) do modelo "{template.name}"'
        )
        
        db.session.commit()
        flash(f'{etapas_criadas} etapa(s) importada(s) com sucesso do modelo "{template.name}"!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao importar modelo: {str(e)}', 'danger')
    
    return redirect(url_for('main.project_detail', project_id=project_id))

@main_bp.route('/etapa/<int:etapa_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_etapa(etapa_id):
    etapa = get_or_404(Etapa, etapa_id)
    project_of_etapa = etapa.project # Projeto pai da etapa
    if not g.user.is_admin and not g.user.has_access_to_area(project_of_etapa.area_responsavel):
        flash('Você não tem permissão para editar etapas deste projeto.', 'danger')
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
    return render_template('etapa_form.html', etapa=etapa, action=url_for('main.edit_etapa', etapa_id=etapa_id), data_inicio_form=data_inicio_f, data_fim_form=data_fim_f)

@main_bp.route('/etapa/<int:etapa_id>/delete', methods=['POST'])
@login_required
def delete_etapa(etapa_id):
    def is_ajax_request():
        requested_with = request.headers.get('X-Requested-With', '').lower() == 'xmlhttprequest'
        accepts_json = 'application/json' in request.headers.get('Accept', '').lower()
        return requested_with or accepts_json

    ajax_request = is_ajax_request()
    etapa_to_delete = get_or_404(Etapa, etapa_id)
    project_of_etapa = etapa_to_delete.project
    project_id_for_redirect = etapa_to_delete.project_id

    if not g.user.is_admin and not g.user.has_access_to_area(project_of_etapa.area_responsavel):
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
        total_etapas = Etapa.query.filter_by(project_id=project_id_for_redirect).count()
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

    data = request.get_json()
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
    if not g.user.is_admin and not g.user.has_access_to_area(project_of_etapa.area_responsavel):
        return jsonify({'success': False, 'message': 'Permissão negada para alterar esta etapa.'}), 403

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
    if not g.user.is_admin and not g.user.has_access_to_area(project_of_etapa.area_responsavel):
        return jsonify({'success': False, 'message': 'Permissão negada para alterar esta etapa.'}), 403

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
    
    if not g.user.is_admin and not g.user.has_access_to_area(project_of_etapa.area_responsavel):
        return jsonify({'success': False, 'message': 'Permissão negada.'}), 403

    data = request.get_json()
    field = data.get('field')
    value = data.get('value')

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
            new_date = datetime.datetime.strptime(value, '%Y-%m-%d').date() if value else None
            
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
            response_data['newValue'] = value
            response_data['displayValue'] = new_date.strftime('%d/%m/%Y') if new_date else '-'

            if old_date and new_date:
                delta = new_date - old_date
                if etapa.data_fim:
                    etapa.data_fim += delta
                    response_data['updatedEndDate'] = etapa.data_fim.strftime('%Y-%m-%d')
                    response_data['updatedEndDateDisplay'] = etapa.data_fim.strftime('%d/%m/%Y')
                response_data['daysDiff'] = delta.days
            
        elif field == 'data_fim':
            old_date = etapa.data_fim
            new_date = datetime.datetime.strptime(value, '%Y-%m-%d').date() if value else None
            
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
            response_data['newValue'] = value
            response_data['displayValue'] = new_date.strftime('%d/%m/%Y') if new_date else '-'
            
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
    
    if not g.user.is_admin and not g.user.has_access_to_area(project_of_etapa.area_responsavel):
        return jsonify({'success': False, 'message': 'Permissão negada.'}), 403

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
    if not g.user.is_admin and not g.user.has_access_to_area(project.area_responsavel):
        return jsonify({'success': False, 'message': 'Permissão negada.'}), 403

    data = request.get_json()
    base_etapa_id = data.get('etapa_id')
    days_to_add = data.get('days_diff')

    if not all([base_etapa_id, days_to_add is not None]):
         return jsonify({'success': False, 'message': 'Parâmetros inválidos.'}), 400

    try:
        days_delta = datetime.timedelta(days=days_to_add)
        base_etapa = db.session.get(Etapa, base_etapa_id)
        if not base_etapa or base_etapa.project_id != project_id:
            return jsonify({'success': False, 'message': 'Etapa base não encontrada.'}), 404
        
        subsequent_etapas = Etapa.query.filter(
            Etapa.project_id == project_id,
            Etapa.ordem > base_etapa.ordem
        ).all()

        for etapa in subsequent_etapas:
            if etapa.data_inicio:
                etapa.data_inicio += days_delta
            if etapa.data_fim:
                etapa.data_fim += days_delta
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'Datas subsequentes atualizadas com sucesso.'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Erro ao atualizar datas subsequentes.'}), 500
