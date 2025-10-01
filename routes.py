from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, g, send_from_directory
import datetime
import os
from functools import wraps
from models import db, User, Project, Etapa, Objetivo, ResultadoEsperado, Indicador, IndicadorProjeto, StageTemplate, StageTemplateItem
from werkzeug.security import generate_password_hash # Para editar senha de usuário
from sqlalchemy.orm import joinedload

main_bp = Blueprint('main', __name__)

# Constante para as opções de áreas (pode ser movida para um config ou detectada do DB no futuro)
AREAS_RESPONSAVEIS_CHOICES = ["CHEGAB", "SUPDADOS", "SUBDGD", "SUPEST", "SUPIM", "SUPPAE", "PRODERJ", "ASSESP", "ECENTRAL", "SUBEDD", "VPD", "VPE", "VPT"]


# Rota específica para servir o favicon
@main_bp.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(main_bp.root_path, 'static'), 'favicon.ico', mimetype='image/vnd.microsoft.icon')


# --- Decorators de Autenticação/Autorização ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session: # Verifica se o user_id está na sessão
            flash('Por favor, faça login para acessar esta página.', 'warning')
            return redirect(url_for('main.login_page', next=request.url))
        # g.user é carregado em app.py via @app.before_request
        if not g.user: # Verifica se o objeto g.user foi carregado (ou seja, usuário existe no DB)
            session.clear() # Limpa sessão inválida
            flash('Sua sessão é inválida ou o usuário não existe. Por favor, faça login novamente.', 'warning')
            return redirect(url_for('main.login_page'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # g.user deve existir por causa do @login_required que geralmente vem antes
        if not g.user or not g.user.is_admin:
            flash('Você não tem permissão para acessar esta página.', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# Processador de contexto para injetar o ano atual e áreas responsáveis (a função em si)
# O registro dela no app é feito em app.py
def inject_current_year():
    return {
        'current_year': datetime.datetime.utcnow().year,
        'AREAS_RESPONSAVEIS_CHOICES': AREAS_RESPONSAVEIS_CHOICES
    }


@main_bp.route('/', methods=['GET'])
def home():
    if 'user_id' in session and g.user: # Se logado e usuário válido
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('main.login_page'))

@main_bp.route('/login', methods=['GET', 'POST'])
def login_page():
    if 'user_id' in session and g.user: # Se já logado e usuário válido
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            flash('Usuário e senha são obrigatórios.', 'warning')
            # Não precisa passar 'error' aqui, o flash já cuida da mensagem
            return render_template('login.html')

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            session.clear() # Limpa qualquer sessão antiga
            session['user_id'] = user.id
            # Outras informações como username, nome, is_admin, area, orgao
            # serão primariamente acessadas via g.user (carregado no @app.before_request)
            # ou pelo context_processor que injeta current_user_obj e is_admin_user.
            # Não é estritamente necessário colocar tudo na session se g.user está disponível.
            
            g.user = user # Garante que g.user esteja populado para este request imediato

            flash(f'Login bem-sucedido, {user.name}!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('main.dashboard'))
        else:
            flash('Credenciais inválidas. Tente novamente.', 'danger')
            # Não precisa passar 'error' aqui, o flash já cuida da mensagem
            return render_template('login.html')
    return render_template('login.html')

@main_bp.route('/logout')
@login_required # Só pode fazer logout se estiver logado
def logout():
    session.clear()
    g.user = None # Limpa g.user também
    flash('Você foi desconectado.', 'info')
    return redirect(url_for('main.login_page'))

@main_bp.route('/profile/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_new_password = request.form.get('confirm_new_password')

        if not current_password or not new_password or not confirm_new_password:
            flash('Todos os campos são obrigatórios.', 'danger')
            return render_template('change_password.html')

        if not g.user.check_password(current_password):
            flash('Senha atual incorreta.', 'danger')
            return render_template('change_password.html')

        if new_password != confirm_new_password:
            flash('A nova senha e a confirmação não correspondem.', 'danger')
            return render_template('change_password.html')
        
        if len(new_password) < 6:
            flash('A nova senha deve ter no mínimo 6 caracteres.', 'danger')
            return render_template('change_password.html')

        g.user.set_password(new_password)
        db.session.commit()
        flash('Senha alterada com sucesso!', 'success')
        return redirect(url_for('main.dashboard'))

    return render_template('change_password.html')

@main_bp.route('/dashboard')
@login_required
def dashboard():
    project_query_base = Project.query
    if not g.user.is_admin and g.user.area_responsavel:
        project_query_base = project_query_base.filter(Project.area_responsavel == g.user.area_responsavel)

    recent_projects = project_query_base.order_by(Project.id.desc()).limit(9).all()
    
    def count_projects_for_user(filter_expression=None):
        query = Project.query
        if not g.user.is_admin and g.user.area_responsavel:
            query = query.filter(Project.area_responsavel == g.user.area_responsavel)
        if filter_expression is not None: # Permite SQLAlchemy filter expressions
            query = query.filter(filter_expression)
        return query.count()

    count_urgente = count_projects_for_user(Project.prioridade == 'urgente')
    count_alta = count_projects_for_user(Project.prioridade == 'alta')
    count_media = count_projects_for_user(Project.prioridade == 'media')
    count_baixa = count_projects_for_user(Project.prioridade == 'baixa')
    count_vigente = count_projects_for_user(Project.status == 'Vigente')
    count_finalizado = count_projects_for_user(Project.status == 'Finalizado')
    count_suspenso = count_projects_for_user(Project.status == 'Suspenso')
    num_projects = count_projects_for_user()

    etapas_query_base = Etapa.query.join(Project, Etapa.project_id == Project.id)
    if not g.user.is_admin and g.user.area_responsavel:
        etapas_query_base = etapas_query_base.filter(Project.area_responsavel == g.user.area_responsavel)
    
    num_etapas = etapas_query_base.count()
    num_etapas_concluidas = etapas_query_base.filter(Etapa.done == True).count()
    
    data_atual = datetime.date.today() # Usar datetime.date.today() é mais simples
    projetos_em_atraso = 0
    
    projetos_vigentes_query = Project.query.filter(Project.status == 'Vigente')
    if not g.user.is_admin and g.user.area_responsavel:
        projetos_vigentes_query = projetos_vigentes_query.filter(Project.area_responsavel == g.user.area_responsavel)
    
    for projeto in projetos_vigentes_query.all():
        if Etapa.query.filter(Etapa.project_id == projeto.id, Etapa.done == False, Etapa.data_fim < data_atual).count() > 0:
            projetos_em_atraso += 1
            
    objetivos = Objetivo.query.all()
    
    return render_template(
        'index.html', 
        recent_projects=recent_projects,
        count_urgente=count_urgente, count_alta=count_alta,
        count_media=count_media, count_baixa=count_baixa,
        count_vigente=count_vigente, count_finalizado=count_finalizado,
        count_suspenso=count_suspenso, num_projects=num_projects,
        num_etapas=num_etapas, num_etapas_concluidas=num_etapas_concluidas,
        projetos_em_atraso=projetos_em_atraso,
        objetivos=objetivos,
        AREAS_RESPONSAVEIS_CHOICES=AREAS_RESPONSAVEIS_CHOICES # Para o modal
    )

@main_bp.route('/projects')
@login_required
def list_projects():
    selected_priority = request.args.get('prioridade')
    selected_status = request.args.get('status')
    selected_area_filter = request.args.get('area') # Filtro de área do formulário
    selected_atraso = request.args.get('atraso')

    # Se nenhum status for especificado na URL, define 'Vigente' como padrão.
    # A verificação `is None` é importante para permitir que o usuário selecione
    # "Todos os status", que envia uma string vazia ("").
    if selected_status is None:
        selected_status = 'Vigente'

    query = Project.query

    # Filtro de área baseado no perfil do usuário E no filtro do formulário
    if not g.user.is_admin and g.user.area_responsavel:
        query = query.filter(Project.area_responsavel == g.user.area_responsavel)
        # Se o usuário não-admin aplicou um filtro de área, e esse filtro é diferente da sua área,
        # o filtro da URL será ignorado, pois a query base já está restrita à área dele.
        # Se o filtro da URL for igual à área dele, é redundante mas inofensivo.
        # Atualizamos selected_area_filter para refletir a área efetivamente filtrada para o usuário.
        selected_area_filter = g.user.area_responsavel
    elif selected_area_filter and selected_area_filter != "": # Admin pode filtrar por qualquer área
        query = query.filter(Project.area_responsavel == selected_area_filter)
    # Se for admin e não houver filtro de área, mostra todas as áreas.

    if selected_priority and selected_priority != "":
        query = query.filter(Project.prioridade == selected_priority)
    if selected_status and selected_status != "":
        query = query.filter(Project.status == selected_status)
        
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
        all_projects_to_display = filtered_by_delay
    else:
        all_projects_to_display = projects_after_db_filters
    
    # Opções para os dropdowns de filtro
    # Áreas: se não for admin, só sua área (se tiver). Se admin, todas as áreas com projetos + áreas padrão.
    if not g.user.is_admin and g.user.area_responsavel:
        areas_options_for_dropdown = [g.user.area_responsavel]
    else:
        project_areas_in_db = set(p.area_responsavel for p in Project.query.all() if p.area_responsavel)
        areas_options_for_dropdown = sorted(list(project_areas_in_db.union(set(AREAS_RESPONSAVEIS_CHOICES))))

    priorities_options = sorted(list(set(p.prioridade for p in Project.query.all() if p.prioridade)))
    statuses_options = sorted(list(set(p.status for p in Project.query.all() if p.status)))
    atrasos_options = [("no_prazo", "No prazo"), ("atrasado", "Atrasado")]
    objetivos = Objetivo.query.all() # Para o modal de adicionar projeto

    return render_template(
        'projects_list.html', 
        projects=all_projects_to_display,
        selected_priority=selected_priority,
        selected_status=selected_status,
        selected_area=selected_area_filter, 
        selected_atraso=selected_atraso, 
        areas=areas_options_for_dropdown,
        priorities=priorities_options,
        statuses=statuses_options,
        atrasos_options=atrasos_options,
        objetivos=objetivos, 
        AREAS_RESPONSAVEIS_CHOICES=AREAS_RESPONSAVEIS_CHOICES
    )

@main_bp.route('/projetos_pendentes')
@login_required
def list_projetos_pendentes():
    selected_area_filter = request.args.get('area')
    data_atual = datetime.date.today()
    projetos_pendentes_com_etapas = []

    query_projetos_base = Project.query.filter(Project.status == 'Vigente')

    # Filtro de área
    if g.user.is_admin:
        if selected_area_filter:
            query_projetos_base = query_projetos_base.filter(Project.area_responsavel == selected_area_filter)
    elif g.user.area_responsavel: # Se não for admin, filtra pela sua própria área
        query_projetos_base = query_projetos_base.filter(Project.area_responsavel == g.user.area_responsavel)
        # Para não-admins, selected_area_filter não é usado, mas a query está correta
    else: # Não-admin sem área não deve ver nenhum projeto
        query_projetos_base = query_projetos_base.filter(Project.id == -1) 

    projetos_vigentes = query_projetos_base.all()

    for projeto in projetos_vigentes:
        etapas_atrasadas = Etapa.query.filter(
            Etapa.project_id == projeto.id,
            Etapa.done == False,
            Etapa.data_fim < data_atual
        ).order_by(Etapa.data_fim).all()

        if etapas_atrasadas:
            projetos_pendentes_com_etapas.append({
                'projeto': projeto,
                'etapas_atrasadas': etapas_atrasadas
            })
    
    # Opções de área para o dropdown (apenas para admin)
    areas_options_for_dropdown = []
    if g.user.is_admin:
        project_areas_in_db = set(p.area_responsavel for p in Project.query.all() if p.area_responsavel)
        areas_options_for_dropdown = sorted(list(project_areas_in_db.union(set(AREAS_RESPONSAVEIS_CHOICES))))
    
    # Manter as variáveis originais para não quebrar o template
    objetivos = Objetivo.query.all()
    AREAS_RESPONSAVEIS_CHOICES_local = AREAS_RESPONSAVEIS_CHOICES

    return render_template(
        'projetos_pendentes.html',
        projetos_com_etapas=projetos_pendentes_com_etapas,
        objetivos=objetivos,
        AREAS_RESPONSAVEIS_CHOICES=AREAS_RESPONSAVEIS_CHOICES_local,
        # Novas variáveis para o filtro
        areas_options=areas_options_for_dropdown,
        selected_area=selected_area_filter
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
        orgao = request.form.get('project_orgao')
        prioridade = request.form.get('project_prioridade')
        objetivo_id = request.form.get('project_objetivo')
        resultado_esperado_id = request.form.get('project_resultado')
        observacao = request.form.get('project_observacao')
        indicador_ids = request.form.getlist('project_indicadores')
        
        # Etapas importadas do modelo
        etapa_descricoes = request.form.getlist('etapa_descricao')

        new_project = Project(
            titulo=titulo,
            area_responsavel=area_responsavel,
            orgao=orgao,
            prioridade=prioridade,
            objetivo_id=int(objetivo_id) if objetivo_id else None,
            resultado_esperado_id=int(resultado_esperado_id) if resultado_esperado_id else None,
            observacao=observacao,
            status='Vigente'  # Definir status padrão
        )
        db.session.add(new_project)
        db.session.flush()  # Para obter o new_project.id para as etapas e indicadores

        # Adicionar as etapas ao novo projeto
        for i, descricao in enumerate(etapa_descricoes):
            if descricao.strip():  # Apenas adiciona se não estiver vazio
                nova_etapa = Etapa(
                    descricao=descricao,
                    project_id=new_project.id,
                    ordem=i
                )
                db.session.add(nova_etapa)

        # Adicionar os indicadores
        if indicador_ids:
            for ind_id in indicador_ids:
                indicador_projeto = IndicadorProjeto(project_id=new_project.id, indicador_id=int(ind_id))
                db.session.add(indicador_projeto)

        db.session.commit()
        
        flash('Projeto adicionado com sucesso!', 'success')
        return redirect(url_for('main.project_detail', project_id=new_project.id))

    except Exception as e:
        db.session.rollback()
        flash(f'Ocorreu um erro ao adicionar o projeto: {e}', 'danger')
        return redirect(request.referrer or url_for('main.dashboard'))


@main_bp.route('/project/<int:project_id>')
@login_required
def project_detail(project_id):
    project = Project.query.get_or_404(project_id)
    if not g.user.is_admin and g.user.area_responsavel and project.area_responsavel != g.user.area_responsavel:
        flash('Você não tem permissão para visualizar este projeto.', 'danger')
        return redirect(url_for('main.list_projects'))

    # O cálculo do índice de exibição dinâmico foi removido.
    # O ID real do projeto (project.id) será usado diretamente no template.
            
    return render_template('project_detail.html', project=project)


@main_bp.route('/project/<int:project_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_project(project_id):
    project_to_edit = Project.query.get_or_404(project_id)
    if not g.user.is_admin and g.user.area_responsavel and project_to_edit.area_responsavel != g.user.area_responsavel:
        flash('Você não tem permissão para editar este projeto.', 'danger')
        return redirect(url_for('main.list_projects'))

    objetivos = Objetivo.query.all()
    # Cria dicionários para fácil acesso nos templates
    resultados_por_objetivo = {obj.id: obj.resultados for obj in objetivos}
    
    indicadores_por_resultado = {}
    todos_resultados_db = ResultadoEsperado.query.all() # Evita N+1 query
    for res in todos_resultados_db:
        indicadores_por_resultado[res.id] = res.indicadores

    indicadores_do_projeto_ids = [ip.indicador_id for ip in project_to_edit.indicadores]

    if request.method == 'POST':
        project_to_edit.titulo = request.form.get('project_titulo')
        
        # Atualiza o órgão do projeto com o valor do formulário, independentemente do tipo de usuário.
        project_to_edit.orgao = request.form.get('project_orgao')

        # Apenas admin pode alterar área diretamente no formulário
        if g.user.is_admin:
            project_to_edit.area_responsavel = request.form.get('project_area_responsavel')
        # Se não for admin, a área não é alterada por este formulário (já viria desabilitada no HTML)
        # O órgão agora é atualizado para todos os usuários com permissão de edição.

        project_to_edit.prioridade = request.form.get('project_prioridade')
        project_to_edit.status = request.form.get('project_status')
        project_to_edit.observacao = request.form.get('project_observacao')
        
        objetivo_id_form = request.form.get('project_objetivo')
        project_to_edit.objetivo_id = int(objetivo_id_form) if objetivo_id_form else None
        
        resultado_id_form = request.form.get('project_resultado')
        project_to_edit.resultado_esperado_id = int(resultado_id_form) if resultado_id_form else None
        
        # Atualizar Indicadores
        IndicadorProjeto.query.filter_by(project_id=project_id).delete() # Remove todos os antigos
        indicadores_ids_form = request.form.getlist('project_indicadores')
        for ind_id_str in indicadores_ids_form[:4]: # Limita a 4
            if ind_id_str: # Garante que não seja string vazia
                indicador_projeto_novo = IndicadorProjeto(project_id=project_id, indicador_id=int(ind_id_str))
                db.session.add(indicador_projeto_novo)
        
        db.session.commit()
        flash(f'Projeto "{project_to_edit.titulo}" atualizado com sucesso!', 'success')
        return redirect(url_for('main.project_detail', project_id=project_id))
    
    return render_template(
        'project_form.html', 
        project=project_to_edit, 
        action_url=url_for('main.edit_project', project_id=project_id), # Nome da var ajustado
        areas_responsaveis=AREAS_RESPONSAVEIS_CHOICES, # Lista de todas as áreas possíveis para o dropdown
        objetivos=objetivos,
        resultados_por_objetivo=resultados_por_objetivo,
        indicadores_por_resultado=indicadores_por_resultado,
        indicadores_do_projeto=indicadores_do_projeto_ids # Lista de IDs dos indicadores já associados
    )

@main_bp.route('/project/<int:project_id>/delete', methods=['POST'])
@login_required
# @admin_required # Decida se apenas admin pode excluir. Se não, a lógica abaixo se aplica.
def delete_project(project_id):
    project_to_delete = Project.query.get_or_404(project_id)

    # Permissão para excluir: Admin pode excluir qualquer um.
    # Usuário não-admin só pode excluir projetos de sua própria área.
    if not g.user.is_admin:
        if not g.user.area_responsavel or project_to_delete.area_responsavel != g.user.area_responsavel:
            flash('Você não tem permissão para excluir este projeto.', 'danger')
            return redirect(url_for('main.list_projects'))
            
    db.session.delete(project_to_delete)
    db.session.commit()
    flash(f'Projeto "{project_to_delete.titulo}" e suas etapas foram excluídos.', 'success')
    return redirect(url_for('main.list_projects'))

# --- Rotas de Etapa (com verificação de permissão no projeto pai) ---
@main_bp.route('/project/<int:project_id>/etapa/add', methods=['POST'])
@login_required
def add_etapa(project_id):
    project = Project.query.get_or_404(project_id)
    if not g.user.is_admin and g.user.area_responsavel and project.area_responsavel != g.user.area_responsavel:
        flash('Você não tem permissão para adicionar etapas a este projeto.', 'danger')
        return redirect(url_for('main.project_detail', project_id=project_id)) # Ou para list_projects

    descricao = request.form.get('etapa_descricao')
    if not descricao:
        flash('A descrição da etapa é obrigatória.', 'warning')
        return redirect(url_for('main.project_detail', project_id=project_id))

    data_inicio_str = request.form.get('etapa_data_inicio')
    data_fim_str = request.form.get('etapa_data_fim')
    responsavel = request.form.get('etapa_responsavel')
    comentarios = request.form.get('etapa_comentarios')
    etapa_iniciada = request.form.get('etapa_iniciada') == 'on'
    etapa_concluida = request.form.get('etapa_done') == 'on'

    if not etapa_iniciada and etapa_concluida:
        flash('Uma etapa não pode ser marcada como concluída sem ser iniciada.', 'warning')
        etapa_concluida = False # Força para não concluída

    data_inicio = datetime.datetime.strptime(data_inicio_str, '%Y-%m-%d').date() if data_inicio_str else None
    data_fim = datetime.datetime.strptime(data_fim_str, '%Y-%m-%d').date() if data_fim_str else None

    # Calcular a ordem da nova etapa
    ultima_etapa = Etapa.query.with_parent(project).order_by(Etapa.ordem.desc()).first()
    nova_ordem = (ultima_etapa.ordem + 1) if ultima_etapa else 0

    new_etapa = Etapa(
        descricao=descricao, data_inicio=data_inicio, data_fim=data_fim,
        responsavel=responsavel, iniciada=etapa_iniciada, done=etapa_concluida,
        comentarios=comentarios, project_id=project.id, ordem=nova_ordem  # Adicionado ordem
    )
    db.session.add(new_etapa)
    db.session.commit()
    flash('Etapa adicionada com sucesso!', 'success')
    return redirect(url_for('main.project_detail', project_id=project_id))

@main_bp.route('/etapa/<int:etapa_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_etapa(etapa_id):
    etapa = Etapa.query.get_or_404(etapa_id)
    project_of_etapa = etapa.project # Projeto pai da etapa
    if not g.user.is_admin and g.user.area_responsavel and project_of_etapa.area_responsavel != g.user.area_responsavel:
        flash('Você não tem permissão para editar etapas deste projeto.', 'danger')
        return redirect(url_for('main.project_detail', project_id=project_of_etapa.id))

    if request.method == 'POST':
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
        
        db.session.commit()
        flash('Etapa atualizada com sucesso!', 'success')
        return redirect(url_for('main.project_detail', project_id=etapa.project_id))

    data_inicio_f = etapa.data_inicio.strftime('%Y-%m-%d') if etapa.data_inicio else ''
    data_fim_f = etapa.data_fim.strftime('%Y-%m-%d') if etapa.data_fim else ''
    return render_template('etapa_form.html', etapa=etapa, action=url_for('main.edit_etapa', etapa_id=etapa_id), data_inicio_form=data_inicio_f, data_fim_form=data_fim_f)

@main_bp.route('/etapa/<int:etapa_id>/delete', methods=['POST'])
@login_required
def delete_etapa(etapa_id):
    etapa_to_delete = Etapa.query.get_or_404(etapa_id)
    project_of_etapa = etapa_to_delete.project
    if not g.user.is_admin and g.user.area_responsavel and project_of_etapa.area_responsavel != g.user.area_responsavel:
        flash('Você não tem permissão para excluir etapas deste projeto.', 'danger')
        return redirect(url_for('main.project_detail', project_id=project_of_etapa.id))

    project_id_for_redirect = etapa_to_delete.project_id
    db.session.delete(etapa_to_delete)
    db.session.commit()
    flash('Etapa excluída com sucesso.', 'success')
    return redirect(url_for('main.project_detail', project_id=project_id_for_redirect))

@main_bp.route('/project/<int:project_id>/etapas/reordenar', methods=['POST'])
@login_required
def reorder_etapas(project_id):
    project = Project.query.get_or_404(project_id)
    if not g.user.is_admin and g.user.area_responsavel and project.area_responsavel != g.user.area_responsavel:
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
    etapa = Etapa.query.get_or_404(etapa_id)
    project_of_etapa = etapa.project
    if not g.user.is_admin and g.user.area_responsavel and project_of_etapa.area_responsavel != g.user.area_responsavel:
        return jsonify({'success': False, 'message': 'Permissão negada para alterar esta etapa.'}), 403

    etapa.iniciada = not etapa.iniciada
    ajax_flash_message = None
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
    etapa = Etapa.query.get_or_404(etapa_id)
    project_of_etapa = etapa.project
    if not g.user.is_admin and g.user.area_responsavel and project_of_etapa.area_responsavel != g.user.area_responsavel:
        return jsonify({'success': False, 'message': 'Permissão negada para alterar esta etapa.'}), 403

    if not etapa.iniciada and not etapa.done: # Tentando marcar como 'done' sem estar 'iniciada'
        return jsonify({
            'success': False, 'etapa_id': etapa.id, 'iniciada': etapa.iniciada,
            'done': etapa.done, 'message': 'Não é possível concluir uma etapa que não foi iniciada.'
        })
    
    etapa.done = not etapa.done
    db.session.commit()
    return jsonify({
        'success': True, 'etapa_id': etapa.id, 'iniciada': etapa.iniciada, 
        'done': etapa.done, 'message': None # Nenhuma mensagem específica aqui a menos que haja um caso
    })

@main_bp.route('/etapa/<int:etapa_id>/update_field', methods=['POST'])
@login_required
def update_etapa_field(etapa_id):
    etapa = Etapa.query.get_or_404(etapa_id)
    project_of_etapa = etapa.project
    
    if not g.user.is_admin and (not g.user.area_responsavel or project_of_etapa.area_responsavel != g.user.area_responsavel):
        return jsonify({'success': False, 'message': 'Permissão negada.'}), 403

    data = request.get_json()
    field = data.get('field')
    value = data.get('value')

    if field not in ['descricao', 'data_inicio', 'data_fim', 'responsavel']:
        return jsonify({'success': False, 'message': 'Campo inválido.'}), 400

    try:
        response_data = {'success': True}
        
        if field == 'data_inicio':
            old_date = etapa.data_inicio
            new_date = datetime.datetime.strptime(value, '%Y-%m-%d').date() if value else None
            
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
            new_date = datetime.datetime.strptime(value, '%Y-%m-%d').date() if value else None
            etapa.data_fim = new_date
            response_data['newValue'] = value
            response_data['displayValue'] = new_date.strftime('%d/%m/%Y') if new_date else '-'
        else:
            setattr(etapa, field, value)
            response_data['newValue'] = value
            response_data['displayValue'] = value if value else '-'
        
        db.session.commit()
        return jsonify(response_data)

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Erro ao salvar a alteração.'}), 500

@main_bp.route('/project/<int:project_id>/cascade_update', methods=['POST'])
@login_required
def cascade_date_update(project_id):
    project = Project.query.get_or_404(project_id)
    if not g.user.is_admin and (not g.user.area_responsavel or project.area_responsavel != g.user.area_responsavel):
        return jsonify({'success': False, 'message': 'Permissão negada.'}), 403

    data = request.get_json()
    base_etapa_id = data.get('etapa_id')
    days_to_add = data.get('days_diff')

    if not all([base_etapa_id, days_to_add is not None]):
         return jsonify({'success': False, 'message': 'Parâmetros inválidos.'}), 400

    try:
        days_delta = datetime.timedelta(days=days_to_add)
        base_etapa = Etapa.query.get(base_etapa_id)
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


# --- Rotas de Gerenciamento de Usuários (Admin) ---
@main_bp.route('/admin/users')
@login_required
@admin_required
def list_users():
    page = request.args.get('page', 1, type=int)
    # Ordenar por nome ou ID, por exemplo
    users_pagination = User.query.order_by(User.name).paginate(page=page, per_page=10)
    return render_template('list_users.html', users=users_pagination, areas_responsaveis_choices=AREAS_RESPONSAVEIS_CHOICES)

@main_bp.route('/admin/users/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_user():
    if request.method == 'POST':
        username = request.form.get('username')
        name = request.form.get('name')
        password = request.form.get('password')
        orgao = request.form.get('orgao')
        area_responsavel_form = request.form.get('area_responsavel') # Pode ser string vazia
        is_admin_form = request.form.get('is_admin') == 'on'

        if not username or not name or not password:
            flash('Username, Nome Completo e Senha são obrigatórios.', 'danger')
        elif User.query.filter_by(username=username).first():
            flash('Este nome de usuário já está em uso. Escolha outro.', 'danger')
        else:
            new_user = User(
                username=username, 
                name=name, 
                orgao=orgao if orgao else None, 
                area_responsavel=area_responsavel_form if area_responsavel_form else None, 
                is_admin=is_admin_form
            )
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            flash(f'Usuário "{name}" ({username}) criado com sucesso!', 'success')
            return redirect(url_for('main.list_users'))
        # Se caiu aqui, houve erro, então renderiza o form novamente com os dados (se o template suportar)
        # ou apenas renderiza o form vazio.
        return render_template('user_form.html', user=request.form, action_verb="Adicionar", areas_responsaveis_choices=AREAS_RESPONSAVEIS_CHOICES)


    # Método GET: exibe o formulário para adicionar novo usuário
    return render_template('user_form.html', user=User(), action_verb="Adicionar", areas_responsaveis_choices=AREAS_RESPONSAVEIS_CHOICES)


@main_bp.route('/admin/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    user_to_edit = User.query.get_or_404(user_id)
    if request.method == 'POST':
        # Username geralmente não é editável ou requer cuidados especiais de unicidade
        user_to_edit.name = request.form.get('name')
        user_to_edit.orgao = request.form.get('orgao') if request.form.get('orgao') else None
        area_form = request.form.get('area_responsavel')
        user_to_edit.area_responsavel = area_form if area_form else None
        
        is_admin_form_val = request.form.get('is_admin') == 'on'

        # Lógica para impedir que o último admin se despromova
        if user_to_edit.is_admin and not is_admin_form_val: # Tentando remover status de admin
            admin_count = User.query.filter_by(is_admin=True).count()
            if admin_count <= 1:
                flash('Não é possível remover o status de administrador do único administrador existente.', 'danger')
                # Não altera user_to_edit.is_admin e recarrega o form
                return render_template('user_form.html', user=user_to_edit, action_verb="Editar", areas_responsaveis_choices=AREAS_RESPONSAVEIS_CHOICES)
        
        user_to_edit.is_admin = is_admin_form_val

        new_password = request.form.get('password')
        if new_password: # Só atualiza a senha se uma nova for fornecida
            user_to_edit.set_password(new_password)
            
        db.session.commit()
        flash(f'Usuário "{user_to_edit.name}" atualizado com sucesso!', 'success')
        return redirect(url_for('main.list_users'))
    
    # Método GET
    return render_template('user_form.html', user=user_to_edit, action_verb="Editar", areas_responsaveis_choices=AREAS_RESPONSAVEIS_CHOICES)

@main_bp.route('/admin/users/delete/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    user_to_delete = User.query.get_or_404(user_id)

    if user_to_delete.id == g.user.id: # Admin não pode se auto-excluir
        flash('Você não pode excluir sua própria conta de administrador.', 'danger')
        return redirect(url_for('main.list_users'))

    if user_to_delete.is_admin and User.query.filter_by(is_admin=True).count() == 1:
        flash('Não é possível excluir o único administrador do sistema.', 'danger')
        return redirect(url_for('main.list_users'))
    
    try:
        db.session.delete(user_to_delete)
        db.session.commit()
        flash(f'Usuário {user_to_delete.username} excluído com sucesso.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao excluir o usuário: {str(e)}', 'danger')

    return redirect(url_for('main.list_users'))


# --- Rotas para Modelos de Etapas (Admin) ---

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

        if not name or not stage_names:
            flash('O nome do modelo e pelo menos uma etapa são obrigatórios.', 'danger')
            return render_template('template_form.html')

        new_template = StageTemplate(name=name, description=description)
        db.session.add(new_template)
        # Flush para obter o ID do novo template antes de criar os itens
        db.session.flush()

        for i, stage_name in enumerate(stage_names):
            if stage_name: # Ignorar campos de etapa vazios
                item = StageTemplateItem(
                    name=stage_name,
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
    template = StageTemplate.query.get_or_404(template_id)

    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        stage_names = request.form.getlist('stage_name')

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
                item = StageTemplateItem(
                    name=stage_name,
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
    template = StageTemplate.query.get_or_404(template_id)
    db.session.delete(template)
    db.session.commit()
    flash('Modelo de etapas excluído com sucesso.', 'success')
    return redirect(url_for('main.list_templates'))


# --- API Endpoints ---

@main_bp.route('/api/resultados/<int:objetivo_id>')
@login_required
def get_resultados(objetivo_id):
    # Validação básica: Objetivo existe?
    objetivo = Objetivo.query.get(objetivo_id)
    if not objetivo:
        return jsonify({"error": "Objetivo não encontrado"}), 404
        
    resultados = ResultadoEsperado.query.filter_by(objetivo_id=objetivo_id).all()
    return jsonify([{'id': res.id, 'descricao': res.descricao} for res in resultados])

@main_bp.route('/api/indicadores/<int:resultado_id>')
@login_required
def get_indicadores(resultado_id):
    # Validação básica: Resultado Esperado existe?
    resultado = ResultadoEsperado.query.get(resultado_id)
    if not resultado:
        return jsonify({"error": "Resultado esperado não encontrado"}), 404

    indicadores = Indicador.query.filter_by(resultado_esperado_id=resultado_id).all()
    return jsonify([{'id': ind.id, 'descricao': ind.descricao} for ind in indicadores])

# --- API para Modelos de Etapas ---

@main_bp.route('/api/templates')
@login_required
def get_templates():
    templates = StageTemplate.query.order_by(StageTemplate.name).all()
    return jsonify([{'id': t.id, 'name': t.name} for t in templates])

@main_bp.route('/api/templates/<int:template_id>')
@login_required
def get_template_stages(template_id):
    template = StageTemplate.query.get_or_404(template_id)
    stages = [{'name': item.name, 'order': item.order} for item in template.items]
    return jsonify(stages)

@main_bp.route('/setup_db')
# @login_required # Opcional: proteger esta rota
# @admin_required # Opcional: proteger esta rota
def setup_db():
    # Lembre-se que a tabela 'user' foi criada manualmente.
    # db.create_all() aqui NÃO vai recriar 'user' se ela já existir.
    # Só criaria outras tabelas dos modelos que ainda não existem.
    from flask import current_app # Importar aqui para evitar import circular no topo se routes for grande
    try:
        from sqlalchemy import inspect # Importar aqui
        inspector = inspect(db.engine)
        
        tabelas_existentes = inspector.get_table_names()
        tabela_project_existe = 'project' in tabelas_existentes
        tabela_user_existe = 'user' in tabelas_existentes
        force_creation = request.args.get('force', 'false').lower() == 'true'
        
        resultado = {
            "status": "success", "mensagem": "",
            "detalhes": {
                "tabelas_existentes": tabelas_existentes,
                "tabela_project_existe": tabela_project_existe,
                "tabela_user_existe": tabela_user_existe,
                "banco_de_dados": current_app.config['SQLALCHEMY_DATABASE_URI'],
                "ambiente": "Google App Engine" if os.getenv('GAE_ENV', '').startswith('standard') else "Desenvolvimento Local"
            }
        }
        
        # Se forçar ou se alguma das tabelas principais (project, user) não existir
        if force_creation or not tabela_project_existe or not tabela_user_existe:
            # CUIDADO: db.drop_all() APAGA TODOS OS DADOS. NÃO use em produção sem backup.
            # if force_creation:
            #     # db.drop_all() # Comentado por segurança
            #     resultado["mensagem"] += " (DROP ALL FOI COMENTADO POR SEGURANÇA) "
            
            db.create_all() # Cria tabelas FALTANTES. Não recria as existentes.
            resultado["mensagem"] += "Banco de dados configurado. Tabelas faltantes (re)criadas."
            resultado["detalhes"]["tabelas_criadas"] = True
        else:
            resultado["mensagem"] = "As tabelas principais já existem. Use ?force=true para tentar recriar tabelas faltantes (sem apagar dados existentes)."
            resultado["detalhes"]["tabelas_criadas"] = False
        
        accept_header = request.headers.get('Accept', '')
        if 'application/json' in accept_header:
            return jsonify(resultado)
        
        html_response = f"""
        <h1>Status do Banco de Dados</h1>
        <p><strong>Status:</strong> {resultado['status']}</p>
        <p><strong>Mensagem:</strong> {resultado['mensagem']}</p>
        <h2>Detalhes</h2><ul>
            <li><strong>Ambiente:</strong> {resultado['detalhes']['ambiente']}</li>
            <li><strong>Banco de Dados:</strong> {resultado['detalhes']['banco_de_dados']}</li>
            <li><strong>Tabela 'project' Existe:</strong> {resultado['detalhes']['tabela_project_existe']}</li>
            <li><strong>Tabela 'user' Existe:</strong> {resultado['detalhes']['tabela_user_existe']}</li>
            <li><strong>Tabelas Existentes:</strong> {', '.join(resultado['detalhes']['tabelas_existentes'])}</li>
        </ul>
        <p><a href="{url_for('main.home')}">Voltar</a> | <a href="{url_for('main.setup_db', force='true')}">Forçar criação de tabelas faltantes</a></p>
        """
        return html_response
            
    except Exception as e:
        error_msg = f"Erro ao configurar banco de dados: {str(e)}"
        current_app.logger.error(f"Erro em /setup_db: {error_msg}", exc_info=True)
        return jsonify({"status": "error", "mensagem": error_msg}) if 'application/json' in request.headers.get('Accept', '') else error_msg
