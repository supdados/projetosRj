from flask import flash, g, jsonify, redirect, render_template, request, url_for

from catalogs.abep import normalize_abep_indicator
from models import Etapa, IndicadorProjeto, Project, db
from catalogs.objectives import normalize_goal_selection

from routes.blueprint import main_bp
from routes.decorators import login_required
from routes.shared import (
    get_area_catalog_choices,
    is_area_in_catalog,
    resolve_catalog_area_name,
    get_or_404,
    get_goal_catalog_context,
    log_project_action,
)
@main_bp.route('/add_project', methods=['POST'])
@login_required
def add_project():
    try:
        titulo = request.form.get('project_titulo')
        if not titulo:
            flash('O título do projeto é obrigatório.', 'danger')
            # Redirecionar para o painel pode ser uma boa opção de fallback
            return redirect(request.referrer or url_for('main.dashboard'))

        area_responsavel = request.form.get('project_area_responsavel')
        if area_responsavel and not is_area_in_catalog(area_responsavel):
            flash('A área selecionada é inválida ou não está mais disponível.', 'danger')
            return redirect(request.referrer or url_for('main.dashboard'))
        if area_responsavel:
            area_responsavel = resolve_catalog_area_name(area_responsavel)
        
        # Verificação de permissão: usuário pode criar projeto apenas em suas áreas
        if not g.user.is_admin:
            if not area_responsavel:
                flash('Você deve selecionar uma área para o projeto.', 'danger')
                return redirect(request.referrer or url_for('main.dashboard'))
            if not g.user.has_access_to_area(area_responsavel):
                flash('Você não tem permissão para criar projetos nesta área.', 'danger')
                return redirect(request.referrer or url_for('main.dashboard'))
        
        orgao = request.form.get('project_orgao')
        prioridade = request.form.get('project_prioridade')
        objetivo_id_raw = request.form.get('project_objetivo')
        resultado_esperado_id_raw = request.form.get('project_resultado')
        observacao = request.form.get('project_observacao')
        indicador_ids_raw = request.form.getlist('project_indicadores')

        objetivo_id, resultado_esperado_id, indicador_ids = normalize_goal_selection(
            objetivo_id_raw,
            resultado_esperado_id_raw,
            indicador_ids_raw,
        )
        
        # Novos campos
        special_project = request.form.get('project_special_project') or None
        sei_process = request.form.get('project_sei_process') or None
        short_description = request.form.get('project_short_description') or None
        delivery_type = request.form.get('project_delivery_type') or None
        abep_indicator = normalize_abep_indicator(request.form.get('project_abep_indicator'))
        github_link = request.form.get('project_github_link') or None
        documentation_link = request.form.get('project_documentation_link') or None
        
        # Etapas importadas do modelo
        etapa_descricoes = request.form.getlist('etapa_descricao')
        etapa_durations = request.form.getlist('etapa_duration')  # Durações em dias
        project_start_date = request.form.get('project_start_date')  # Data de início do projeto

        new_project = Project(
            titulo=titulo,
            area_responsavel=area_responsavel,
            orgao=orgao,
            prioridade=prioridade,
            objetivo_id=objetivo_id,
            resultado_esperado_id=resultado_esperado_id,
            observacao=observacao,
            status='Vigente',  # Definir status padrão
            special_project=special_project,
            sei_process=sei_process,
            short_description=short_description,
            delivery_type=delivery_type,
            abep_indicator=abep_indicator,
            github_link=github_link,
            documentation_link=documentation_link
        )
        db.session.add(new_project)
        db.session.flush()  # Para obter o new_project.id para as etapas e indicadores

        # Adicionar as etapas ao novo projeto com cálculo automático de datas
        current_date = None
        if project_start_date:
            try:
                from datetime import datetime, timedelta
                current_date = datetime.strptime(project_start_date, '%Y-%m-%d').date()
            except:
                current_date = None
        
        for i, descricao in enumerate(etapa_descricoes):
            if descricao.strip():  # Apenas adiciona se não estiver vazio
                data_inicio = None
                data_fim = None
                
                # Se há data de início e duração, calcular automaticamente
                if current_date and i < len(etapa_durations) and etapa_durations[i]:
                    try:
                        from datetime import timedelta
                        duration = int(etapa_durations[i])
                        data_inicio = current_date
                        data_fim = current_date + timedelta(days=duration - 1)  # -1 porque o início conta como dia 1
                        current_date = data_fim + timedelta(days=1)  # Próxima etapa começa no dia seguinte
                    except:
                        pass
                
                nova_etapa = Etapa(
                    descricao=descricao,
                    project_id=new_project.id,
                    ordem=i,
                    data_inicio=data_inicio,
                    data_fim=data_fim
                )
                db.session.add(nova_etapa)

        # Adicionar os indicadores
        if indicador_ids:
            for ind_id in indicador_ids:
                indicador_projeto = IndicadorProjeto(project_id=new_project.id, indicador_id=ind_id)
                db.session.add(indicador_projeto)

        # Registrar no histórico
        log_project_action(
            project_id=new_project.id,
            action_type='create',
            description=f'Criou o projeto "{titulo}"'
        )
        
        db.session.commit()
        
        flash('Projeto adicionado com sucesso!', 'success')
        return redirect(url_for('main.project_detail', project_id=new_project.id))

    except ValueError as e:
        db.session.rollback()
        flash(str(e), 'warning')
        return redirect(request.referrer or url_for('main.dashboard'))
    except Exception as e:
        db.session.rollback()
        flash(f'Ocorreu um erro ao adicionar o projeto: {e}', 'danger')
        return redirect(request.referrer or url_for('main.dashboard'))

@main_bp.route('/project/<int:project_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_project(project_id):
    project_to_edit = get_or_404(Project, project_id)
    if not g.user.is_admin and not g.user.has_access_to_area(project_to_edit.area_responsavel):
        flash('Você não tem permissão para editar este projeto.', 'danger')
        return redirect(url_for('main.list_projects'))

    objetivos, resultados_por_objetivo, indicadores_por_resultado = get_goal_catalog_context()

    indicadores_do_projeto_ids = [ip.indicador_id for ip in project_to_edit.indicadores]

    if request.method == 'POST':
        # Capturar valores anteriores para o histórico
        changes = []
        old_titulo = project_to_edit.titulo
        
        new_titulo = request.form.get('project_titulo')
        if old_titulo != new_titulo:
            changes.append(f'título de "{old_titulo}" para "{new_titulo}"')
        project_to_edit.titulo = new_titulo
        
        # Atualiza o órgão do projeto com o valor do formulário, independentemente do tipo de usuário.
        old_orgao = project_to_edit.orgao
        new_orgao = request.form.get('project_orgao')
        if old_orgao != new_orgao:
            changes.append(f'órgão de "{old_orgao or "vazio"}" para "{new_orgao or "vazio"}"')
        project_to_edit.orgao = new_orgao

        # Admin ou usuário com múltiplas áreas pode alterar área
        new_area = request.form.get('project_area_responsavel')
        if new_area:
            if not is_area_in_catalog(new_area):
                flash('A área selecionada é inválida ou não está mais disponível.', 'warning')
                return redirect(url_for('main.edit_project', project_id=project_id))
            new_area = resolve_catalog_area_name(new_area)
            old_area = project_to_edit.area_responsavel
            user_areas = g.user.get_areas()
            if g.user.is_admin or (len(user_areas) > 1 and new_area in user_areas):
                if old_area != new_area:
                    changes.append(f'área responsável de "{old_area}" para "{new_area}"')
                project_to_edit.area_responsavel = new_area

        old_prioridade = project_to_edit.prioridade
        new_prioridade = request.form.get('project_prioridade')
        if old_prioridade != new_prioridade:
            changes.append(f'prioridade de "{old_prioridade}" para "{new_prioridade}"')
        project_to_edit.prioridade = new_prioridade
        
        old_status = project_to_edit.status
        new_status = request.form.get('project_status')
        if old_status != new_status:
            changes.append(f'status de "{old_status}" para "{new_status}"')
        project_to_edit.status = new_status
        
        project_to_edit.observacao = request.form.get('project_observacao')
        
        # Processar novos campos
        project_to_edit.special_project = request.form.get('project_special_project') or None
        project_to_edit.sei_process = request.form.get('project_sei_process') or None
        project_to_edit.short_description = request.form.get('project_short_description') or None
        project_to_edit.delivery_type = request.form.get('project_delivery_type') or None
        project_to_edit.github_link = request.form.get('project_github_link') or None
        project_to_edit.documentation_link = request.form.get('project_documentation_link') or None
        
        try:
            old_abep_indicator = project_to_edit.abep_indicator
            new_abep_indicator = normalize_abep_indicator(request.form.get('project_abep_indicator'))
            if old_abep_indicator != new_abep_indicator:
                changes.append(
                    f'indicador ABEP de "{old_abep_indicator or "vazio"}" para "{new_abep_indicator or "vazio"}"'
                )
            project_to_edit.abep_indicator = new_abep_indicator

            objetivo_id_norm, resultado_id_norm, indicadores_ids_norm = normalize_goal_selection(
                request.form.get('project_objetivo'),
                request.form.get('project_resultado'),
                request.form.getlist('project_indicadores'),
            )
        except ValueError as e:
            flash(str(e), 'warning')
            return redirect(url_for('main.edit_project', project_id=project_id))

        project_to_edit.objetivo_id = objetivo_id_norm
        project_to_edit.resultado_esperado_id = resultado_id_norm

        # Atualizar Indicadores
        IndicadorProjeto.query.filter_by(project_id=project_id).delete() # Remove todos os antigos
        for indicador_id in indicadores_ids_norm:
            indicador_projeto_novo = IndicadorProjeto(project_id=project_id, indicador_id=indicador_id)
            db.session.add(indicador_projeto_novo)
        
        # Registrar no histórico
        if changes:
            change_desc = ', '.join(changes)
            log_project_action(
                project_id=project_id,
                action_type='edit',
                description=f'Editou o projeto: alterou {change_desc}'
            )
        
        db.session.commit()
        flash(f'Projeto "{project_to_edit.titulo}" atualizado com sucesso!', 'success')
        return redirect(url_for('main.project_detail', project_id=project_id))
    
    return render_template(
        'project_form.html', 
        project=project_to_edit, 
        areas_responsaveis=get_area_catalog_choices(),
        objetivos=objetivos,
        resultados_por_objetivo=resultados_por_objetivo,
        indicadores_por_resultado=indicadores_por_resultado,
        indicadores_do_projeto=indicadores_do_projeto_ids # Lista de IDs dos indicadores já associados
    )

@main_bp.route('/project/<int:project_id>/delete', methods=['POST'])
@login_required
# @admin_required # Decida se apenas admin pode excluir. Se não, a lógica abaixo se aplica.
def delete_project(project_id):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    project_to_delete = get_or_404(Project, project_id)

    # Permissão para excluir: Admin pode excluir qualquer um.
    # Usuário não-admin só pode excluir projetos de suas áreas.
    if not g.user.is_admin and not g.user.has_access_to_area(project_to_delete.area_responsavel):
        if is_ajax:
            from flask import jsonify
            return jsonify({'ok': False, 'message': 'Você não tem permissão para excluir este projeto.'}), 403
        flash('Você não tem permissão para excluir este projeto.', 'danger')
        return redirect(url_for('main.list_projects'))

    # Registrar no histórico antes de excluir
    project_titulo = project_to_delete.titulo
    log_project_action(
        project_id=project_to_delete.id,
        action_type='delete',
        description=f'Excluiu o projeto "{project_titulo}"'
    )

    db.session.delete(project_to_delete)
    db.session.commit()

    if is_ajax:
        from flask import jsonify
        return jsonify({'ok': True, 'message': f'Projeto "{project_titulo}" excluído.'})
    flash(f'Projeto "{project_titulo}" e suas etapas foram excluídos.', 'success')
    return redirect(url_for('main.list_projects'))

@main_bp.route('/project/<int:project_id>/concluir', methods=['POST'])
@login_required
def concluir_project(project_id):
    project = get_or_404(Project, project_id)
    redirect_url = url_for('main.project_detail', project_id=project_id)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.best == 'application/json'

    def respond_error(message, category='warning', status_code=400):
        if is_ajax:
            return jsonify({
                'success': False,
                'message': message,
                'category': category,
                'redirect_url': redirect_url
            }), status_code
        flash(message, category)
        return redirect(redirect_url)
    
    # Verificar permissão
    if not g.user.is_admin and not g.user.has_access_to_area(project.area_responsavel):
        return respond_error('Você não tem permissão para concluir este projeto.', category='danger', status_code=403)
    
    # Verificar se o projeto está Vigente
    if project.status != 'Vigente':
        return respond_error('Apenas projetos com status "Vigente" podem ser concluídos.', category='warning', status_code=400)
    
    # Verificar se todas as etapas estão concluídas
    if not project.todas_etapas_concluidas:
        return respond_error('Todas as etapas devem estar iniciadas e concluídas para finalizar o projeto.', category='warning', status_code=400)

    try:
        # Atualizar status
        project.status = 'Finalizado'

        # Registrar no histórico
        log_project_action(
            project_id=project.id,
            action_type='finalize',
            description=f'Concluiu o projeto "{project.titulo}"'
        )

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return respond_error(f'Erro ao concluir projeto: {str(e)}', category='danger', status_code=500)

    success_message = f'Projeto "{project.titulo}" foi concluído com sucesso!'
    if is_ajax:
        return jsonify({
            'success': True,
            'message': success_message,
            'redirect_url': redirect_url
        })
    flash(success_message, 'success')
    return redirect(redirect_url)
