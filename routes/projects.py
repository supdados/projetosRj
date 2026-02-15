import datetime

from flask import flash, g, jsonify, redirect, render_template, request, url_for

from abep_catalog import normalize_abep_indicator
from models import Etapa, IndicadorProjeto, Project, ProjectHistory, db
from objective_catalog import normalize_goal_selection

from .blueprint import main_bp
from .decorators import login_required
from .shared import (
    AREAS_RESPONSAVEIS_CHOICES,
    get_goal_catalog_context,
    log_project_action,
    parse_abep_indicator_filter,
    parse_objetivo_filter,
)
@main_bp.route('/projects')
@login_required
def list_projects():
    selected_priority = request.args.get('prioridade')
    selected_status = request.args.get('status')
    selected_area_filter = request.args.get('area') # Filtro de área do formulário
    selected_atraso = request.args.get('atraso')
    selected_special_project = request.args.get('special_project')  # Novo filtro
    selected_delivery_type = request.args.get('delivery_type')  # Novo filtro
    selected_abep_indicator = request.args.get('abep_indicator')  # Novo filtro
    selected_objetivo = request.args.get('objetivo')  # Novo filtro
    search_query = request.args.get('search', '').strip()  # Busca
    
    # Paginação
    page = request.args.get('page', 1, type=int)
    per_page = 40

    # Se nenhum status for especificado na URL, define 'Vigente' como padrão.
    # A verificação `is None` é importante para permitir que o usuário selecione
    # "Todos os status", que envia uma string vazia ("").
    if selected_status is None:
        selected_status = 'Vigente'

    query = Project.query

    # Filtro de área baseado no perfil do usuário E no filtro do formulário
    if not g.user.is_admin:
        user_areas = g.user.get_areas()
        if user_areas:
            # Usuário não-admin com áreas: filtra pelas suas áreas
            query = query.filter(Project.area_responsavel.in_(user_areas))
            # Se o usuário aplicou um filtro de área e essa área está nas suas áreas, aplica o filtro
            if selected_area_filter and selected_area_filter in user_areas:
                query = query.filter(Project.area_responsavel == selected_area_filter)
            # Se não, mostra todas as suas áreas (já filtrado acima)
    elif selected_area_filter and selected_area_filter != "": # Admin pode filtrar por qualquer área
        query = query.filter(Project.area_responsavel == selected_area_filter)
    # Se for admin e não houver filtro de área, mostra todas as áreas.

    if selected_priority and selected_priority != "":
        query = query.filter(Project.prioridade == selected_priority)
    if selected_status and selected_status != "":
        query = query.filter(Project.status == selected_status)
    if selected_special_project and selected_special_project != "":
        query = query.filter(Project.special_project == selected_special_project)
    if selected_delivery_type and selected_delivery_type != "":
        query = query.filter(Project.delivery_type == selected_delivery_type)
    selected_abep_indicator = parse_abep_indicator_filter(selected_abep_indicator)
    if selected_abep_indicator:
        query = query.filter(Project.abep_indicator == selected_abep_indicator)
    objetivo_filter_id = parse_objetivo_filter(selected_objetivo)
    if selected_objetivo and objetivo_filter_id is None:
        selected_objetivo = ""
    if selected_objetivo and objetivo_filter_id is not None:
        query = query.filter(Project.objetivo_id == objetivo_filter_id)
    
    # Filtro de busca (título, área, órgão, indicador ABEP)
    if search_query:
        search_pattern = f"%{search_query}%"
        query = query.filter(
            db.or_(
                Project.titulo.ilike(search_pattern),
                Project.area_responsavel.ilike(search_pattern),
                Project.orgao.ilike(search_pattern),
                Project.abep_indicator.ilike(search_pattern)
            )
        )
        
    # Aplicar filtros de DB antes de filtrar por atraso (que é feito em Python)
    projects_after_db_filters = query.order_by(Project.id).all()
    
    # Filtro de Atraso (aplicado em Python)
    if selected_atraso and selected_atraso != "":
        data_atual = datetime.date.today()
        filtered_by_delay = []
        for projeto in projects_after_db_filters:
            if projeto.status == 'Vigente': # Apenas projetos vigentes são considerados para "atraso" ou "no prazo"
                etapas_atrasadas_count = Etapa.query.filter(
                    Etapa.project_id == projeto.id,
                    Etapa.done == False,
                    Etapa.data_fim < data_atual
                ).count()
                if selected_atraso == "atrasado" and etapas_atrasadas_count > 0:
                    filtered_by_delay.append(projeto)
                elif selected_atraso == "no_prazo" and etapas_atrasadas_count == 0:
                    filtered_by_delay.append(projeto)
        all_projects_filtered = filtered_by_delay
    else:
        all_projects_filtered = projects_after_db_filters
    
    # Aplicar paginação manualmente (já que alguns filtros são em Python)
    total_projects = len(all_projects_filtered)
    total_pages = (total_projects + per_page - 1) // per_page  # Ceiling division
    
    # Calcular índices para slice
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    
    # Paginar os projetos
    projects_paginated = all_projects_filtered[start_idx:end_idx]
    
    # Opções para os dropdowns de filtro
    # Áreas: se não for admin, suas áreas (se tiver). Se admin, todas as áreas com projetos + áreas padrão.
    if not g.user.is_admin:
        user_areas = g.user.get_areas()
        areas_options_for_dropdown = sorted(user_areas) if user_areas else []
    else:
        project_areas_in_db = set(p.area_responsavel for p in Project.query.all() if p.area_responsavel)
        areas_options_for_dropdown = sorted(list(project_areas_in_db.union(set(AREAS_RESPONSAVEIS_CHOICES))))

    priorities_options = sorted(list(set(p.prioridade for p in Project.query.all() if p.prioridade)))
    statuses_options = sorted(list(set(p.status for p in Project.query.all() if p.status)))
    atrasos_options = [("no_prazo", "No prazo"), ("atrasado", "Atrasado")]
    objetivos, _, _ = get_goal_catalog_context()  # Para o modal de adicionar projeto e filtro
    
    # Novas opções para filtros
    special_projects_options = ['ABEP', 'TCE']
    delivery_types_options = ['Sistema', 'Painel', 'Norma', 'Instrumento de parceria', 'Fluxo Processual', 'Outro']

    # Verificar se há filtros ativos (para mostrar botão "Limpar")
    has_active_filters = False
    if search_query:
        has_active_filters = True
    if selected_priority:
        has_active_filters = True
    if selected_status and selected_status != 'Vigente':  # Vigente é o padrão
        has_active_filters = True
    if selected_atraso:
        has_active_filters = True
    if selected_special_project:
        has_active_filters = True
    if selected_delivery_type:
        has_active_filters = True
    if selected_abep_indicator:
        has_active_filters = True
    if selected_objetivo:
        has_active_filters = True
    # Área só conta como filtro ativo se o usuário for admin
    if g.user.is_admin and selected_area_filter:
        has_active_filters = True

    return render_template(
        'projects_list.html', 
        projects=projects_paginated,
        page=page,
        total_pages=total_pages,
        total_projects=total_projects,
        search_query=search_query,
        selected_priority=selected_priority,
        selected_status=selected_status,
        selected_area=selected_area_filter, 
        selected_atraso=selected_atraso,
        selected_special_project=selected_special_project,
        selected_delivery_type=selected_delivery_type,
        selected_abep_indicator=selected_abep_indicator,
        selected_objetivo=selected_objetivo,
        areas=areas_options_for_dropdown,
        priorities=priorities_options,
        statuses=statuses_options,
        atrasos_options=atrasos_options,
        objetivos=objetivos,
        special_projects_options=special_projects_options,
        delivery_types_options=delivery_types_options,
        has_active_filters=has_active_filters,
        AREAS_RESPONSAVEIS_CHOICES=AREAS_RESPONSAVEIS_CHOICES
    )
@main_bp.route('/projetos_pendentes')
@login_required
def list_projetos_pendentes():
    selected_area_filter = request.args.get('area')
    filtro_periodo = request.args.get('periodo', 'atrasados')  # Novo parâmetro com default 'atrasados'
    data_atual = datetime.date.today()
    projetos_pendentes_com_etapas = []

    query_projetos_base = Project.query.filter(Project.status == 'Vigente')

    # Filtro de área
    if g.user.is_admin:
        if selected_area_filter:
            query_projetos_base = query_projetos_base.filter(Project.area_responsavel == selected_area_filter)
    else: # Se não for admin, filtra pelas suas áreas
        user_areas = g.user.get_areas()
        if user_areas:
            query_projetos_base = query_projetos_base.filter(Project.area_responsavel.in_(user_areas))
        else: # Não-admin sem área não deve ver nenhum projeto
            query_projetos_base = query_projetos_base.filter(Project.id == -1) 

    projetos_vigentes = query_projetos_base.all()

    for projeto in projetos_vigentes:
        # Aplicar filtro de período nas etapas
        if filtro_periodo == 'atrasados':
            etapas_filtradas = Etapa.query.filter(
                Etapa.project_id == projeto.id,
                Etapa.done == False,
                Etapa.data_fim < data_atual
            ).order_by(Etapa.data_fim).all()
        elif filtro_periodo == '7dias':
            # Inclui atrasados + próximos 7 dias
            data_limite = data_atual + datetime.timedelta(days=7)
            etapas_filtradas = Etapa.query.filter(
                Etapa.project_id == projeto.id,
                Etapa.done == False,
                Etapa.data_fim <= data_limite
            ).order_by(Etapa.data_fim).all()
        elif filtro_periodo == '14dias':
            # Inclui atrasados + próximos 14 dias
            data_limite = data_atual + datetime.timedelta(days=14)
            etapas_filtradas = Etapa.query.filter(
                Etapa.project_id == projeto.id,
                Etapa.done == False,
                Etapa.data_fim <= data_limite
            ).order_by(Etapa.data_fim).all()
        else:
            # Fallback para atrasados se o valor for inválido
            etapas_filtradas = Etapa.query.filter(
                Etapa.project_id == projeto.id,
                Etapa.done == False,
                Etapa.data_fim < data_atual
            ).order_by(Etapa.data_fim).all()

        if etapas_filtradas:
            projetos_pendentes_com_etapas.append({
                'projeto': projeto,
                'etapas_atrasadas': etapas_filtradas  # Nome mantido por compatibilidade com o template
            })
    
    # Opções de área para o dropdown (apenas para admin)
    areas_options_for_dropdown = []
    if g.user.is_admin:
        project_areas_in_db = set(p.area_responsavel for p in Project.query.all() if p.area_responsavel)
        areas_options_for_dropdown = sorted(list(project_areas_in_db.union(set(AREAS_RESPONSAVEIS_CHOICES))))

    # Necessário para o formulário de criação de projeto
    # (objetivo -> resultado esperado -> indicadores)
    objetivos, _, _ = get_goal_catalog_context()

    return render_template(
        'projetos_pendentes.html',
        projetos_com_etapas=projetos_pendentes_com_etapas,
        objetivos=objetivos,
        AREAS_RESPONSAVEIS_CHOICES=AREAS_RESPONSAVEIS_CHOICES,
        # Variáveis para os filtros
        areas_options=areas_options_for_dropdown,
        selected_area=selected_area_filter,
        filtro_periodo=filtro_periodo  # Novo parâmetro
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


@main_bp.route('/project/<int:project_id>')
@login_required
def project_detail(project_id):
    project = Project.query.get_or_404(project_id)
    if not g.user.is_admin and not g.user.has_access_to_area(project.area_responsavel):
        flash('Você não tem permissão para visualizar este projeto.', 'danger')
        return redirect(url_for('main.list_projects'))

    # O cálculo do índice de exibição dinâmico foi removido.
    # O ID real do projeto (project.id) será usado diretamente no template.
            
    return render_template('project_detail.html', project=project)


@main_bp.route('/project/<int:project_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_project(project_id):
    project_to_edit = Project.query.get_or_404(project_id)
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
        areas_responsaveis=AREAS_RESPONSAVEIS_CHOICES, # Lista de todas as áreas possíveis para o dropdown
        objetivos=objetivos,
        resultados_por_objetivo=resultados_por_objetivo,
        indicadores_por_resultado=indicadores_por_resultado,
        indicadores_do_projeto=indicadores_do_projeto_ids # Lista de IDs dos indicadores já associados
    )

@main_bp.route('/project/<int:project_id>/edit_data', methods=['GET'])
@login_required
def get_project_edit_data(project_id):
    """Endpoint AJAX para buscar dados necessários para edição"""
    project = Project.query.get_or_404(project_id)
    
    # Verificar permissão
    if not g.user.is_admin and not g.user.has_access_to_area(project.area_responsavel):
        return jsonify({'success': False, 'message': 'Você não tem permissão para editar este projeto.'}), 403
    
    try:
        objetivos, resultados_por_objetivo, indicadores_por_resultado = get_goal_catalog_context()
        
        indicadores_do_projeto_ids = [ip.indicador_id for ip in project.indicadores]
        
        return jsonify({
            'success': True,
            'objetivos': objetivos,
            'resultados_por_objetivo': resultados_por_objetivo,
            'indicadores_por_resultado': indicadores_por_resultado,
            'indicadores_do_projeto': indicadores_do_projeto_ids,
            'areas_responsaveis': AREAS_RESPONSAVEIS_CHOICES,
            'is_admin': g.user.is_admin
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro ao buscar dados: {str(e)}'}), 500

@main_bp.route('/project/<int:project_id>/update_inline', methods=['POST'])
@login_required
def update_project_inline(project_id):
    """Endpoint AJAX para atualizar projeto inline"""
    project_to_edit = Project.query.get_or_404(project_id)
    
    # Verificar permissão
    if not g.user.is_admin and not g.user.has_access_to_area(project_to_edit.area_responsavel):
        return jsonify({'success': False, 'message': 'Você não tem permissão para editar este projeto.'}), 403
    
    try:
        data = request.get_json()
        changes = []
        
        # Atualizar campos básicos
        if 'titulo' in data and data['titulo'] != project_to_edit.titulo:
            changes.append(f'título de "{project_to_edit.titulo}" para "{data["titulo"]}"')
            project_to_edit.titulo = data['titulo']
        
        if 'status' in data and data['status'] != project_to_edit.status:
            changes.append(f'status de "{project_to_edit.status}" para "{data["status"]}"')
            project_to_edit.status = data['status']
        
        if 'prioridade' in data and data['prioridade'] != project_to_edit.prioridade:
            changes.append(f'prioridade de "{project_to_edit.prioridade}" para "{data["prioridade"]}"')
            project_to_edit.prioridade = data['prioridade']
        
        if 'orgao' in data:
            old_orgao = project_to_edit.orgao or ""
            new_orgao = data['orgao'] or ""
            if old_orgao != new_orgao:
                changes.append(f'órgão de "{old_orgao or "vazio"}" para "{new_orgao or "vazio"}"')
            project_to_edit.orgao = data['orgao'] or None
        
        # Admin ou usuário com múltiplas áreas pode alterar área
        if 'area_responsavel' in data:
            new_area = data['area_responsavel']
            if new_area != project_to_edit.area_responsavel:
                user_areas = g.user.get_areas()
                if g.user.is_admin or (len(user_areas) > 1 and new_area in user_areas):
                    changes.append(f'área de "{project_to_edit.area_responsavel}" para "{new_area}"')
                    project_to_edit.area_responsavel = new_area
        
        # Novos campos
        if 'special_project' in data:
            project_to_edit.special_project = data['special_project'] or None
        
        if 'sei_process' in data:
            project_to_edit.sei_process = data['sei_process'] or None
        
        if 'short_description' in data:
            project_to_edit.short_description = data['short_description'] or None
        
        if 'delivery_type' in data:
            project_to_edit.delivery_type = data['delivery_type'] or None

        if 'abep_indicator' in data:
            old_abep = project_to_edit.abep_indicator
            new_abep = normalize_abep_indicator(data['abep_indicator'])
            if old_abep != new_abep:
                changes.append(
                    f'indicador ABEP de "{old_abep or "vazio"}" para "{new_abep or "vazio"}"'
                )
            project_to_edit.abep_indicator = new_abep
        
        if 'github_link' in data:
            project_to_edit.github_link = data['github_link'] or None
        
        if 'documentation_link' in data:
            project_to_edit.documentation_link = data['documentation_link'] or None
        
        if 'observacao' in data:
            project_to_edit.observacao = data['observacao'] or None
        
        # Objetivo, Resultado e Indicadores
        goal_fields_present = any(
            field in data for field in ('objetivo_id', 'resultado_esperado_id', 'indicadores_ids')
        )
        if goal_fields_present:
            objetivo_raw = data.get('objetivo_id', project_to_edit.objetivo_id)
            resultado_raw = data.get('resultado_esperado_id', project_to_edit.resultado_esperado_id)
            indicadores_raw = data.get(
                'indicadores_ids',
                [ip.indicador_id for ip in project_to_edit.indicadores],
            )

            objetivo_norm, resultado_norm, indicadores_norm = normalize_goal_selection(
                objetivo_raw,
                resultado_raw,
                indicadores_raw,
            )

            project_to_edit.objetivo_id = objetivo_norm
            project_to_edit.resultado_esperado_id = resultado_norm

            # Atualizar indicadores
            IndicadorProjeto.query.filter_by(project_id=project_id).delete()
            for indicador_id in indicadores_norm:
                indicador_projeto_novo = IndicadorProjeto(
                    project_id=project_id,
                    indicador_id=indicador_id,
                )
                db.session.add(indicador_projeto_novo)
        
        # Registrar no histórico
        if changes:
            change_desc = ', '.join(changes)
            log_project_action(
                project_id=project_id,
                action_type='edit',
                description=f'Editou o projeto (inline): alterou {change_desc}'
            )
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'Projeto atualizado com sucesso!'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Erro ao atualizar projeto: {str(e)}'}), 500

@main_bp.route('/project/<int:project_id>/delete', methods=['POST'])
@login_required
# @admin_required # Decida se apenas admin pode excluir. Se não, a lógica abaixo se aplica.
def delete_project(project_id):
    project_to_delete = Project.query.get_or_404(project_id)

    # Permissão para excluir: Admin pode excluir qualquer um.
    # Usuário não-admin só pode excluir projetos de suas áreas.
    if not g.user.is_admin and not g.user.has_access_to_area(project_to_delete.area_responsavel):
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
    flash(f'Projeto "{project_titulo}" e suas etapas foram excluídos.', 'success')
    return redirect(url_for('main.list_projects'))

@main_bp.route('/project/<int:project_id>/concluir', methods=['POST'])
@login_required
def concluir_project(project_id):
    project = Project.query.get_or_404(project_id)
    
    # Verificar permissão
    if not g.user.is_admin and not g.user.has_access_to_area(project.area_responsavel):
        flash('Você não tem permissão para concluir este projeto.', 'danger')
        return redirect(url_for('main.project_detail', project_id=project_id))
    
    # Verificar se o projeto está Vigente
    if project.status != 'Vigente':
        flash('Apenas projetos com status "Vigente" podem ser concluídos.', 'warning')
        return redirect(url_for('main.project_detail', project_id=project_id))
    
    # Verificar se todas as etapas estão concluídas
    if not project.todas_etapas_concluidas:
        flash('Todas as etapas devem estar iniciadas e concluídas para finalizar o projeto.', 'warning')
        return redirect(url_for('main.project_detail', project_id=project_id))
    
    # Atualizar status
    project.status = 'Finalizado'
    
    # Registrar no histórico
    log_project_action(
        project_id=project.id,
        action_type='finalize',
        description=f'Concluiu o projeto "{project.titulo}"'
    )
    
    db.session.commit()
    flash(f'Projeto "{project.titulo}" foi concluído com sucesso!', 'success')
    return redirect(url_for('main.project_detail', project_id=project_id))

@main_bp.route('/project/<int:project_id>/history')
@login_required
def project_history(project_id):
    """Visualizar histórico de ações de um projeto"""
    project = Project.query.get_or_404(project_id)
    
    # Verificar permissão
    if not g.user.is_admin and not g.user.has_access_to_area(project.area_responsavel):
        flash('Você não tem permissão para visualizar este projeto.', 'danger')
        return redirect(url_for('main.list_projects'))
    
    # Buscar histórico ordenado por data (mais recente primeiro)
    history_entries = ProjectHistory.query.filter_by(project_id=project_id)\
        .order_by(ProjectHistory.timestamp.desc())\
        .all()
    
    return render_template('project_history.html', project=project, history=history_entries)
