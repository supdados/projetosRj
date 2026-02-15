import datetime

from flask import flash, g, jsonify, redirect, render_template, request, url_for
from sqlalchemy.orm import joinedload

from models import Project, Task, TaskItem, TaskItemComment, User, UserArea, db

from .blueprint import main_bp
from .decorators import login_required
from .shared import format_local_time
@main_bp.route('/tarefas', methods=['GET'])
@login_required
def list_tasks():
    """Lista tarefas do usuário com filtros e paginação"""
    # Filtros
    project_filter = request.args.get('project', '')
    search_query = request.args.get('search', '')
    
    # Query base
    query = Task.query.options(joinedload(Task.items), joinedload(Task.project))
    
    # Aplicar permissões
    if not g.user.is_admin:
        # Usuário vê: tarefas de projetos de suas áreas + tarefas sem projeto criadas por ele
        user_areas = g.user.get_areas()
        query = query.outerjoin(Project).filter(
            db.or_(
                db.and_(Task.project_id.isnot(None), Project.area_responsavel.in_(user_areas)),
                db.and_(Task.project_id.is_(None), Task.created_by_id == g.user.id)
            )
        )
    
    # Aplicar filtros
    if project_filter:
        if project_filter == 'sem_projeto':
            query = query.filter(Task.project_id.is_(None))
        else:
            query = query.filter(Task.project_id == project_filter)
    
    if search_query:
        query = query.filter(Task.titulo.ilike(f'%{search_query}%'))
    
    # Ordenar por data de criação (mais recentes primeiro)
    query = query.order_by(Task.created_at.desc())
    
    # Paginação
    page = request.args.get('page', 1, type=int)
    per_page = 40
    tasks_pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    tasks = tasks_pagination.items
    
    # Obter lista de projetos do usuário para o filtro
    if g.user.is_admin:
        projects_for_filter = Project.query.order_by(Project.titulo).all()
    else:
        user_areas = g.user.get_areas()
        projects_for_filter = Project.query.filter(Project.area_responsavel.in_(user_areas)).order_by(Project.titulo).all()
    
    return render_template('task_list.html', 
                         tasks=tasks,
                         pagination=tasks_pagination,
                         projects=projects_for_filter,
                         project_filter=project_filter,
                         search_query=search_query)


@main_bp.route('/tarefas/add', methods=['POST'])
@login_required
def add_task():
    """Adiciona nova tarefa"""
    titulo = request.form.get('titulo', '').strip()
    project_id = request.form.get('project_id', '').strip()
    
    # Validações
    if not titulo:
        flash('Título é obrigatório.', 'danger')
        return redirect(url_for('main.list_tasks'))
    
    # Validar project_id se fornecido
    project = None
    if project_id:
        try:
            project_id = int(project_id)
            project = Project.query.get(project_id)
            if not project:
                flash('Projeto não encontrado.', 'danger')
                return redirect(url_for('main.list_tasks'))
            
            # Verificar permissão de acesso ao projeto
            if not g.user.is_admin and not g.user.has_access_to_area(project.area_responsavel):
                flash('Você não tem permissão para associar tarefas a este projeto.', 'danger')
                return redirect(url_for('main.list_tasks'))
        except (ValueError, TypeError):
            project_id = None
    else:
        project_id = None
    
    # Criar tarefa
    task = Task(
        titulo=titulo,
        project_id=project_id,
        created_by_id=g.user.id
    )
    
    try:
        db.session.add(task)
        db.session.commit()
        flash('Tarefa criada com sucesso!', 'success')
        # Redirecionar para a página de detalhes da tarefa
        return redirect(url_for('main.task_detail', task_id=task.id))
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao criar tarefa: {str(e)}', 'danger')
    
    return redirect(url_for('main.list_tasks'))


@main_bp.route('/tarefas/<int:task_id>', methods=['GET'])
@login_required
def task_detail(task_id):
    """Detalhes da tarefa com seus itens e comentários"""
    task = Task.query.options(
        joinedload(Task.items).joinedload(TaskItem.comments).joinedload(TaskItemComment.author),
        joinedload(Task.project)
    ).get_or_404(task_id)
    
    # Verificar permissão
    can_view = (
        g.user.is_admin or 
        task.created_by_id == g.user.id or
        (task.project_id and task.project.area_responsavel in g.user.get_areas())
    )
    
    if not can_view:
        flash('Você não tem permissão para acessar esta tarefa.', 'danger')
        return redirect(url_for('main.list_tasks'))
    
    # Projetos para dropdown de edição (mesma regra de list_tasks)
    if g.user.is_admin:
        projects = Project.query.order_by(Project.titulo).all()
    else:
        user_areas = g.user.get_areas()
        projects = Project.query.filter(Project.area_responsavel.in_(user_areas)).order_by(Project.titulo).all()
    
    return render_template('task_detail.html', task=task, projects=projects)


@main_bp.route('/tarefas/<int:task_id>/edit', methods=['POST'])
@login_required
def edit_task(task_id):
    """Edita tarefa existente (título e projeto)"""
    task = Task.query.get_or_404(task_id)
    
    # Verificar permissão
    can_edit = (
        g.user.is_admin or 
        task.created_by_id == g.user.id or
        (task.project_id and task.project.area_responsavel in g.user.get_areas())
    )
    
    if not can_edit:
        return jsonify({'success': False, 'message': 'Sem permissão'}), 403
    
    titulo = request.form.get('titulo', '').strip()
    project_id = request.form.get('project_id', '').strip()
    
    # Validações
    if not titulo:
        return jsonify({'success': False, 'message': 'Título é obrigatório'}), 400
    
    # Validar project_id se fornecido
    if project_id:
        try:
            project_id = int(project_id)
            project = Project.query.get(project_id)
            if not project:
                return jsonify({'success': False, 'message': 'Projeto não encontrado'}), 404
            
            # Verificar permissão de acesso ao projeto
            if not g.user.is_admin and not g.user.has_access_to_area(project.area_responsavel):
                return jsonify({'success': False, 'message': 'Sem permissão para este projeto'}), 403
        except (ValueError, TypeError):
            project_id = None
    else:
        project_id = None
    
    # Atualizar tarefa
    task.titulo = titulo
    task.project_id = project_id
    
    try:
        db.session.commit()
        project_titulo = task.project.titulo if task.project else None
        return jsonify({
            'success': True,
            'message': 'Tarefa atualizada',
            'task': {
                'titulo': task.titulo,
                'project_id': task.project_id,
                'project_titulo': project_titulo
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@main_bp.route('/tarefas/<int:task_id>/delete', methods=['POST'])
@login_required
def delete_task(task_id):
    """Exclui tarefa"""
    task = Task.query.get_or_404(task_id)
    
    # Verificar permissão
    can_delete = (
        g.user.is_admin or 
        task.created_by_id == g.user.id or
        (task.project_id and task.project.area_responsavel in g.user.get_areas())
    )
    
    if not can_delete:
        flash('Você não tem permissão para excluir esta tarefa.', 'danger')
        return redirect(url_for('main.list_tasks'))
    
    try:
        db.session.delete(task)
        db.session.commit()
        flash('Tarefa excluída com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao excluir tarefa: {str(e)}', 'danger')
    
    return redirect(url_for('main.list_tasks'))


# ===================================
# ROTAS DE ITENS DE TAREFA (TASK ITEMS)
# ===================================

@main_bp.route('/tarefas/<int:task_id>/itens/add', methods=['POST'])
@login_required
def add_task_item(task_id):
    """Adiciona item à tarefa"""
    task = Task.query.get_or_404(task_id)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.best == 'application/json'
    
    # Verificar permissão
    can_edit = (
        g.user.is_admin or 
        task.created_by_id == g.user.id or
        (task.project_id and task.project.area_responsavel in g.user.get_areas())
    )
    
    if not can_edit:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Sem permissão para adicionar itens.'}), 403
        flash('Você não tem permissão para adicionar itens a esta tarefa.', 'danger')
        return redirect(url_for('main.task_detail', task_id=task_id))
    
    descricao = request.form.get('descricao', '').strip()
    status = request.form.get('status', 'programado')
    responsavel = request.form.get('responsavel', '').strip()
    
    # Validações
    if not descricao:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Descrição é obrigatória.'}), 400
        flash('Descrição é obrigatória.', 'danger')
        return redirect(url_for('main.task_detail', task_id=task_id))
    
    # Calcular ordem
    max_ordem = db.session.query(db.func.max(TaskItem.ordem)).filter_by(task_id=task_id).scalar() or 0
    
    # Criar item
    item = TaskItem(
        descricao=descricao,
        status=status,
        responsavel=responsavel if responsavel else None,
        task_id=task_id,
        ordem=max_ordem + 1
    )
    
    try:
        db.session.add(item)
        db.session.commit()
        if is_ajax:
            return jsonify({
                'success': True,
                'item': {
                    'id': item.id,
                    'descricao': item.descricao,
                    'status': item.status,
                    'responsavel': item.responsavel or '',
                    'comments_count': 0
                }
            })
        flash('Item adicionado com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        if is_ajax:
            return jsonify({'success': False, 'message': str(e)}), 500
        flash(f'Erro ao adicionar item: {str(e)}', 'danger')
    
    return redirect(url_for('main.task_detail', task_id=task_id))


@main_bp.route('/tarefas/itens/<int:item_id>/edit', methods=['POST'])
@login_required
def edit_task_item(item_id):
    """Edita item da tarefa"""
    item = TaskItem.query.get_or_404(item_id)
    task = item.task
    
    # Verificar permissão
    can_edit = (
        g.user.is_admin or 
        task.created_by_id == g.user.id or
        (task.project_id and task.project.area_responsavel in g.user.get_areas())
    )
    
    if not can_edit:
        return jsonify({'success': False, 'message': 'Sem permissão'}), 403
    
    descricao = request.form.get('descricao', '').strip()
    status = request.form.get('status', item.status)
    responsavel = request.form.get('responsavel', '').strip()
    
    # Validações
    if not descricao:
        return jsonify({'success': False, 'message': 'Descrição é obrigatória'}), 400
    
    # Atualizar item
    item.descricao = descricao
    item.status = status
    item.responsavel = responsavel if responsavel else None
    
    try:
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Item atualizado',
            'item': {
                'id': item.id,
                'descricao': item.descricao,
                'status': item.status,
                'responsavel': item.responsavel or ''
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@main_bp.route('/tarefas/itens/<int:item_id>/delete', methods=['POST'])
@login_required
def delete_task_item(item_id):
    """Exclui item da tarefa"""
    item = TaskItem.query.get_or_404(item_id)
    task = item.task
    task_id = task.id
    
    # Verificar permissão
    can_delete = (
        g.user.is_admin or 
        task.created_by_id == g.user.id or
        (task.project_id and task.project.area_responsavel in g.user.get_areas())
    )
    
    if not can_delete:
        flash('Você não tem permissão para excluir este item.', 'danger')
        return redirect(url_for('main.task_detail', task_id=task_id))
    
    try:
        db.session.delete(item)
        db.session.commit()
        flash('Item excluído com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao excluir item: {str(e)}', 'danger')
    
    return redirect(url_for('main.task_detail', task_id=task_id))


@main_bp.route('/tarefas/itens/<int:item_id>/update_status', methods=['POST'])
@login_required
def update_task_item_status(item_id):
    """Atualiza status do item via AJAX"""
    item = TaskItem.query.get_or_404(item_id)
    task = item.task
    
    # Verificar permissão
    can_edit = (
        g.user.is_admin or 
        task.created_by_id == g.user.id or
        (task.project_id and task.project.area_responsavel in g.user.get_areas())
    )
    
    if not can_edit:
        return jsonify({'success': False, 'message': 'Sem permissão'}), 403
    
    status = request.json.get('status')
    if status not in ['programado', 'em_andamento', 'validacao', 'finalizado']:
        return jsonify({'success': False, 'message': 'Status inválido'}), 400
    
    item.status = status
    
    try:
        db.session.commit()
        return jsonify({'success': True, 'message': 'Status atualizado'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@main_bp.route('/tarefas/<int:task_id>/itens/reordenar', methods=['POST'])
@login_required
def reorder_task_items(task_id):
    """Reordena itens da tarefa"""
    task = Task.query.get_or_404(task_id)
    
    # Verificar permissão
    can_edit = (
        g.user.is_admin or 
        task.created_by_id == g.user.id or
        (task.project_id and task.project.area_responsavel in g.user.get_areas())
    )
    
    if not can_edit:
        return jsonify({'success': False, 'message': 'Sem permissão'}), 403
    
    try:
        ordem_items = request.json.get('ordem', [])
        
        for index, item_id in enumerate(ordem_items, start=1):
            item = TaskItem.query.get(item_id)
            if item and item.task_id == task_id:
                item.ordem = index
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'Ordem atualizada'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


# ===================================
# COMENTÁRIOS EM ITENS DE TAREFA
# ===================================

def _can_comment_on_task(task):
    """Verifica se o usuário pode comentar na tarefa (e portanto nos itens)."""
    return (
        g.user.is_admin or
        task.created_by_id == g.user.id or
        (task.project_id and task.project.area_responsavel in g.user.get_areas())
    )


@main_bp.route('/tarefas/itens/<int:item_id>/comentarios/add', methods=['POST'])
@login_required
def add_task_item_comment(item_id):
    """Adiciona comentário a um item (apenas após o item existir)."""
    item = TaskItem.query.get_or_404(item_id)
    task = item.task
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.best == 'application/json'
    
    if not _can_comment_on_task(task):
        if is_ajax:
            return jsonify({'success': False, 'message': 'Sem permissão para comentar.'}), 403
        flash('Você não tem permissão para comentar neste item.', 'danger')
        return redirect(url_for('main.task_detail', task_id=task.id))
    
    content = request.form.get('content', '').strip()
    if not content:
        if is_ajax:
            return jsonify({'success': False, 'message': 'O comentário não pode estar vazio.'}), 400
        flash('O comentário não pode estar vazio.', 'warning')
        return redirect(url_for('main.task_detail', task_id=task.id))
    
    comment = TaskItemComment(
        content=content,
        user_id=g.user.id,
        task_item_id=item_id
    )
    try:
        db.session.add(comment)
        db.session.commit()
        if is_ajax:
            return jsonify({
                'success': True,
                'comment': {
                    'id': comment.id,
                    'content': comment.content,
                    'author_name': g.user.name,
                    'user_id': g.user.id,
                    'created_at': format_local_time(comment.created_at),
                    'is_own': True
                }
            })
        flash('Comentário adicionado.', 'success')
    except Exception as e:
        db.session.rollback()
        if is_ajax:
            return jsonify({'success': False, 'message': str(e)}), 500
        flash(f'Erro ao adicionar comentário: {str(e)}', 'danger')
    
    return redirect(url_for('main.task_detail', task_id=task.id))


@main_bp.route('/tarefas/comentarios/<int:comment_id>/edit', methods=['POST'])
@login_required
def edit_task_item_comment(comment_id):
    """Edita comentário (apenas o próprio autor)."""
    comment = TaskItemComment.query.get_or_404(comment_id)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.best == 'application/json'
    
    if comment.user_id != g.user.id:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Você só pode editar seus próprios comentários.'}), 403
        flash('Você só pode editar seus próprios comentários.', 'danger')
        return redirect(url_for('main.task_detail', task_id=comment.task_item.task_id))
    
    content = request.form.get('content', '').strip()
    if not content:
        if is_ajax:
            return jsonify({'success': False, 'message': 'O comentário não pode estar vazio.'}), 400
        flash('O comentário não pode estar vazio.', 'warning')
        return redirect(url_for('main.task_detail', task_id=comment.task_item.task_id))
    
    comment.content = content
    comment.updated_at = datetime.datetime.utcnow()
    try:
        db.session.commit()
        if is_ajax:
            return jsonify({
                'success': True,
                'comment': {
                    'id': comment.id,
                    'content': comment.content,
                    'updated_at': format_local_time(comment.updated_at) if comment.updated_at else None
                }
            })
        flash('Comentário atualizado.', 'success')
    except Exception as e:
        db.session.rollback()
        if is_ajax:
            return jsonify({'success': False, 'message': str(e)}), 500
        flash(f'Erro ao atualizar comentário: {str(e)}', 'danger')
    
    return redirect(url_for('main.task_detail', task_id=comment.task_item.task_id))


@main_bp.route('/tarefas/comentarios/<int:comment_id>/delete', methods=['POST'])
@login_required
def delete_task_item_comment(comment_id):
    """Exclui comentário (apenas o próprio autor)."""
    comment = TaskItemComment.query.get_or_404(comment_id)
    task_id = comment.task_item.task_id
    
    if comment.user_id != g.user.id:
        flash('Você só pode excluir seus próprios comentários.', 'danger')
        return redirect(url_for('main.task_detail', task_id=task_id))
    
    try:
        db.session.delete(comment)
        db.session.commit()
        flash('Comentário excluído.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao excluir comentário: {str(e)}', 'danger')
    
    return redirect(url_for('main.task_detail', task_id=task_id))


@main_bp.route('/projeto/<int:project_id>/tarefas', methods=['GET'])
@login_required
def project_tasks(project_id):
    """Lista tarefas de um projeto específico"""
    project = Project.query.get_or_404(project_id)
    
    # Verificar permissão de acesso ao projeto
    if not g.user.is_admin and not g.user.has_access_to_area(project.area_responsavel):
        flash('Você não tem permissão para acessar este projeto.', 'danger')
        return redirect(url_for('main.list_projects'))
    
    # Buscar tarefas do projeto
    tasks = Task.query.options(joinedload(Task.items)).filter_by(project_id=project_id).order_by(Task.created_at.desc()).all()
    
    return render_template('project_tasks.html', project=project, tasks=tasks)

@main_bp.route('/tarefas/<int:task_id>/sugestoes-responsavel', methods=['GET'])
@login_required
def get_task_assignable_users(task_id):
    """API: usuários que podem ser marcados como responsável no item (pessoas do projeto). Se a tarefa não tem projeto, retorna lista vazia."""
    task = Task.query.get_or_404(task_id)
    if not task.project_id or not task.project:
        return jsonify({'users': []})
    area = task.project.area_responsavel
    if not area:
        return jsonify({'users': []})
    # Usuários que têm essa área (UserArea ou area_responsavel legado)
    user_ids_area = [ua.user_id for ua in UserArea.query.filter_by(area=area).all()]
    if user_ids_area:
        users_q = User.query.filter(User.id.in_(user_ids_area)).order_by(User.name)
    else:
        users_q = User.query.filter(User.area_responsavel == area).order_by(User.name)
    users = [{'id': u.id, 'name': u.name} for u in users_q.all()]
    q = (request.args.get('q') or '').strip().lower()
    if q:
        users = [u for u in users if q in (u['name'] or '').lower()]
    return jsonify({'users': users})
