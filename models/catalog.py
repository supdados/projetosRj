from .base import db


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
