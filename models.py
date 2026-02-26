from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import datetime

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False) # Aumentado para acomodar hashes mais longos
    name = db.Column(db.String(120), nullable=False)
    orgao = db.Column(db.String(100), nullable=True)
    area_responsavel = db.Column(db.String(100), nullable=True) # DEPRECATED: mantido para compatibilidade durante migração
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    
    # Relacionamento com múltiplas áreas
    areas = db.relationship('UserArea', backref='user', lazy=True, cascade="all, delete-orphan")

    def set_password(self, password):
        # pbkdf2:sha256 evita dependência de hashlib.scrypt (não disponível em alguns Python/OpenSSL)
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def get_areas(self):
        """Retorna lista de strings com as áreas do usuário"""
        return [ua.area for ua in self.areas]
    
    def has_access_to_area(self, area):
        """Verifica se o usuário tem acesso a uma área específica"""
        if self.is_admin:
            return True
        return area in self.get_areas()
    
    def set_areas(self, area_list):
        """Define as áreas do usuário. Recebe uma lista de strings."""
        # Remove áreas antigas
        UserArea.query.filter_by(user_id=self.id).delete()
        # Adiciona novas áreas
        for area in area_list:
            if area:  # Ignora strings vazias
                user_area = UserArea(user_id=self.id, area=area)
                db.session.add(user_area)

    def __repr__(self):
        return f'<User {self.username}>'

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    area_responsavel = db.Column(db.String(100))
    orgao = db.Column(db.String(100))
    prioridade = db.Column(db.String(20)) # urgente, alta, media, baixa
    status = db.Column(db.String(20), default='Vigente', nullable=False)  # Vigente, Finalizado ou Suspenso
    observacao = db.Column(db.Text)
    objetivo_id = db.Column(db.Integer, db.ForeignKey('objetivo.id'), nullable=True)
    resultado_esperado_id = db.Column(db.Integer, db.ForeignKey('resultado_esperado.id'), nullable=True)
    
    # Novos campos
    special_project = db.Column(db.String(20), nullable=True)  # 'ABEP' ou 'TCE'
    sei_process = db.Column(db.String(50), nullable=True)  # Formato: SEI-000000/000000/0000
    short_description = db.Column(db.Text, nullable=True)  # Descrição curta para Informações Básicas
    delivery_type = db.Column(db.String(50), nullable=True)  # Sistema, Painel, Norma, etc.
    abep_indicator = db.Column(db.String(255), nullable=True)  # Indicador ABEP selecionado
    github_link = db.Column(db.String(500), nullable=True)  # Link do Github
    documentation_link = db.Column(db.String(500), nullable=True)  # Link da Documentação
    
    etapas = db.relationship('Etapa', backref='project', lazy=True, cascade="all, delete-orphan", order_by="Etapa.ordem")
    objetivo = db.relationship('Objetivo', backref='projetos')
    resultado_esperado = db.relationship('ResultadoEsperado', backref='projetos')
    indicadores = db.relationship('IndicadorProjeto', backref='project', lazy=True, cascade="all, delete-orphan")
    # Opcional: adicionar quem criou o projeto
    # created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    # creator = db.relationship('User', backref='created_projects')


    @property
    def data_inicio_projeto(self):
        if not self.etapas:
            return None
        datas_inicio_etapas = [etapa.data_inicio for etapa in self.etapas if etapa.data_inicio]
        return min(datas_inicio_etapas) if datas_inicio_etapas else None

    @property
    def data_fim_projeto(self):
        if not self.etapas:
            return None
        datas_fim_etapas = [etapa.data_fim for etapa in self.etapas if etapa.data_fim]
        return max(datas_fim_etapas) if datas_fim_etapas else None

    @property
    def todas_etapas_concluidas(self):
        """Verifica se todas as etapas do projeto estão iniciadas e concluídas"""
        if not self.etapas:  # Se não há etapas, retorna False
            return False
        return all(etapa.iniciada and etapa.done for etapa in self.etapas)

    def __repr__(self):
        return f'<Project {self.titulo}>'

class Etapa(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.Text, nullable=False)
    data_inicio = db.Column(db.Date)
    data_fim = db.Column(db.Date)
    responsavel = db.Column(db.String(100))
    iniciada = db.Column(db.Boolean, default=False, nullable=False)
    done = db.Column(db.Boolean, default=False, nullable=False)
    comentarios = db.Column(db.Text)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    ordem = db.Column(db.Integer, nullable=False, default=0) # Novo campo para ordenação

    def __repr__(self):
        return f'<Etapa {self.descricao[:50]}>'

class Objetivo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.Text, nullable=False)
    resultados = db.relationship('ResultadoEsperado', backref='objetivo', lazy=True)

    def __repr__(self):
        return f'<Objetivo {self.descricao[:50]}>'

class ResultadoEsperado(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.Text, nullable=False)
    objetivo_id = db.Column(db.Integer, db.ForeignKey('objetivo.id'), nullable=False)
    indicadores = db.relationship('Indicador', backref='resultado_esperado', lazy=True)

    def __repr__(self):
        return f'<ResultadoEsperado {self.descricao[:50]}>'

class Indicador(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.Text, nullable=False)
    resultado_esperado_id = db.Column(db.Integer, db.ForeignKey('resultado_esperado.id'), nullable=False)

    def __repr__(self):
        return f'<Indicador {self.descricao[:50]}>'

class IndicadorProjeto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    indicador_id = db.Column(db.Integer, db.ForeignKey('indicador.id'), nullable=False)
    indicador = db.relationship('Indicador')

    def __repr__(self):
        return f'<IndicadorProjeto {self.id}>'

# Modelos para Templates de Etapas
class StageTemplate(db.Model):
    __tablename__ = 'StageTemplate'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    items = db.relationship('StageTemplateItem', backref='template', lazy=True, cascade="all, delete-orphan", order_by="StageTemplateItem.order")

    def __repr__(self):
        return f'<StageTemplate {self.name}>'

class StageTemplateItem(db.Model):
    __tablename__ = 'StageTemplateItem'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    duration_days = db.Column(db.Integer, nullable=False, default=1)  # Duração em dias
    order = db.Column(db.Integer, nullable=False)
    templateId = db.Column(db.Integer, db.ForeignKey('StageTemplate.id'), nullable=False)

    def __repr__(self):
        return f'<StageTemplateItem {self.name}>'

class UserArea(db.Model):
    """Tabela de relacionamento para permitir múltiplas áreas por usuário"""
    __tablename__ = 'user_areas'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    area = db.Column(db.String(100), nullable=False)

    def __repr__(self):
        return f'<UserArea user_id={self.user_id} area={self.area}>'

class ProjectHistory(db.Model):
    """Tabela de auditoria/histórico de ações em projetos"""
    __tablename__ = 'project_history'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action_type = db.Column(db.String(50), nullable=False)  # 'create', 'edit', 'delete', 'add_etapa', etc
    action_description = db.Column(db.Text, nullable=False)  # Descrição legível da ação
    old_value = db.Column(db.Text, nullable=True)  # Valor anterior (JSON ou texto)
    new_value = db.Column(db.Text, nullable=True)  # Novo valor (JSON ou texto)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False)
    
    # Relacionamentos
    project = db.relationship('Project', backref=db.backref('history', cascade='all, delete-orphan'))
    user = db.relationship('User', backref='project_actions')

    def __repr__(self):
        return f'<ProjectHistory {self.action_type} by user {self.user_id} at {self.timestamp}>'


class UserNotification(db.Model):
    """Notificações in-app por usuário."""
    __tablename__ = 'user_notification'

    id = db.Column(db.Integer, primary_key=True)
    recipient_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    event_type = db.Column(db.String(80), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    target_url = db.Column(db.String(500), nullable=False)
    is_read = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False)
    read_at = db.Column(db.DateTime, nullable=True)

    recipient = db.relationship('User', foreign_keys=[recipient_user_id], backref='received_notifications')
    actor = db.relationship('User', foreign_keys=[actor_user_id], backref='sent_notifications')

    __table_args__ = (
        db.Index(
            'ix_user_notification_recipient_read_created',
            'recipient_user_id',
            'is_read',
            'created_at',
        ),
    )

    def __repr__(self):
        return f'<UserNotification {self.event_type} to user {self.recipient_user_id}>'


class Task(db.Model):
    """Modelo único de tarefa operacional."""
    __tablename__ = 'task'
    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='programado')  # programado, em_andamento, validacao, finalizado
    responsavel = db.Column(db.String(100), nullable=True)
    ordem = db.Column(db.Integer, nullable=False, default=0)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True)  # Opcional
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False)
    prioridade = db.Column(db.String(20), nullable=True)  # baixa, media, alta, urgente
    tipo_pedido = db.Column(db.String(30), nullable=True)  # bug, melhoria, duvida, outros
    is_archived = db.Column(db.Boolean, nullable=False, default=False, index=True)
    archived_at = db.Column(db.DateTime, nullable=True)
    
    # Relacionamentos
    project = db.relationship('Project', backref=db.backref('tasks', lazy=True))
    created_by = db.relationship('User', backref='created_tasks')
    comments = db.relationship(
        'TaskComment',
        backref='task',
        lazy=True,
        cascade='all, delete-orphan',
        order_by='TaskComment.created_at'
    )
    anexos = db.relationship(
        'TaskAnexo',
        backref='task',
        lazy=True,
        cascade='all, delete-orphan',
        order_by='TaskAnexo.created_at'
    )

    def __init__(self, **kwargs):
        # Compatibilidade legada: Task(titulo=...) e TaskItem(task_id=...)
        legacy_titulo = kwargs.pop('titulo', None)
        legacy_task_id = kwargs.pop('task_id', None)

        if legacy_titulo is not None and 'descricao' not in kwargs:
            kwargs['descricao'] = legacy_titulo

        if legacy_task_id is not None:
            try:
                anchor_id = int(legacy_task_id)
            except (TypeError, ValueError):
                anchor_id = None

            if anchor_id:
                anchor = db.session.get(Task, anchor_id)
                if anchor:
                    kwargs.setdefault('project_id', anchor.project_id)
                    kwargs.setdefault('created_by_id', anchor.created_by_id)

                    if 'ordem' not in kwargs:
                        next_ordem = (
                            db.session.query(db.func.max(Task.ordem))
                            .filter(
                                Task.project_id == anchor.project_id,
                                Task.is_archived.is_(False),
                            )
                            .scalar()
                            or 0
                        )
                        kwargs['ordem'] = next_ordem + 1

        kwargs.setdefault('status', 'programado')
        super().__init__(**kwargs)
    
    def __repr__(self):
        return f'<Task {self.descricao[:50]}>'


    # Compatibilidade de nomenclatura legada (semântica antiga de "tarefa pai").
    @property
    def titulo(self):
        return self.descricao

    @titulo.setter
    def titulo(self, value):
        self.descricao = value

    @property
    def is_finalized(self):
        return self.is_archived

    @is_finalized.setter
    def is_finalized(self, value):
        self.is_archived = bool(value)

    @property
    def finalized_at(self):
        return self.archived_at

    @finalized_at.setter
    def finalized_at(self, value):
        self.archived_at = value

    @property
    def task_id(self):
        return self.id

    @task_id.setter
    def task_id(self, value):
        try:
            anchor_id = int(value)
        except (TypeError, ValueError):
            return

        anchor = db.session.get(Task, anchor_id)
        if not anchor:
            return

        self.project_id = anchor.project_id
        if not self.created_by_id:
            self.created_by_id = anchor.created_by_id

    @property
    def task(self):
        return self

    @property
    def items(self):
        return [self]


class TaskAnexo(db.Model):
    """Anexos de uma tarefa."""
    __tablename__ = 'task_anexo'
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)       # nome original do arquivo
    stored_filename = db.Column(db.String(255), nullable=False)  # nome no disco (uuid)
    content_type = db.Column(db.String(100), nullable=True)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False)

    uploaded_by = db.relationship('User', backref='task_anexos')

    @property
    def task_item(self):
        return self.task

    @property
    def task_item_id(self):
        return self.task_id

    def __repr__(self):
        return f'<TaskAnexo {self.filename}>'


class TaskComment(db.Model):
    """Comentários sobre uma tarefa."""
    __tablename__ = 'task_comment'
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, onupdate=datetime.datetime.utcnow, nullable=True)  # Apenas preenchido quando o comentário for editado
    
    author = db.relationship('User', backref='task_comments')

    @property
    def task_item(self):
        return self.task

    @property
    def task_item_id(self):
        return self.task_id

    @task_item_id.setter
    def task_item_id(self, value):
        self.task_id = value
    
    def __repr__(self):
        return f'<TaskComment {self.id} by user {self.user_id}>'


class LegacyTaskRedirect(db.Model):
    """Mapeamento para redirecionar links legados de tarefas-pai antigas."""
    __tablename__ = 'legacy_task_redirect'
    id = db.Column(db.Integer, primary_key=True)
    legacy_task_id = db.Column(db.Integer, nullable=False, index=True, unique=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True)
    sample_task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False)

    project = db.relationship('Project', backref='legacy_task_redirects')
    sample_task = db.relationship('Task', backref='legacy_redirect_sources')


# Aliases de compatibilidade para rotas legadas (/tarefas/itens/...).
TaskItem = Task
TaskItemComment = TaskComment
TaskItemAnexo = TaskAnexo
