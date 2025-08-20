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
    area_responsavel = db.Column(db.String(100), nullable=True) # Pode ser nulo para admin geral
    is_admin = db.Column(db.Boolean, default=False, nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

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
    order = db.Column(db.Integer, nullable=False)
    templateId = db.Column(db.Integer, db.ForeignKey('StageTemplate.id'), nullable=False)

    def __repr__(self):
        return f'<StageTemplateItem {self.name}>'
