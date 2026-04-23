from .base import db


ALLOWED_TIPOS = (
    'Estado',
    'Secretaria',
    'Subsecretaria',
    'Superintendência',
    'Autarquia',
    'Fundação',
    'Empresa Pública',
    'Assessoria',
    'Coordenação',
    'Núcleo',
    'Departamento',
)

# Rank por tipo: pai precisa ter rank ESTRITAMENTE menor que o filho.
# Mesma rank entre tipos significa que ambos podem coexistir como irmãos
# sob o mesmo pai (ex.: Subsecretaria, Autarquia, Fundação e Empresa Pública
# são todos descendentes diretos de Secretaria).
TIPO_RANK = {
    'Estado': 0,
    'Secretaria': 1,
    'Subsecretaria': 2,
    'Superintendência': 3,
    'Autarquia': 2,
    'Fundação': 2,
    'Empresa Pública': 2,
    'Assessoria': 4,
    'Coordenação': 5,
    'Departamento': 6,
    'Núcleo': 7,
}

MAX_DEPTH = 5


class OrgaoUnidade(db.Model):
    __tablename__ = 'orgao_unidade'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(255), nullable=False)
    sigla = db.Column(db.String(50), nullable=False)
    tipo = db.Column(db.String(50), nullable=False)
    pai_id = db.Column(
        db.Integer,
        db.ForeignKey('orgao_unidade.id', ondelete='RESTRICT'),
        nullable=True,
    )
    ordem = db.Column(db.Integer, nullable=False, default=0)
    ativo = db.Column(db.Boolean, nullable=False, default=True)

    pai = db.relationship(
        'OrgaoUnidade',
        remote_side=[id],
        backref=db.backref('filhos', order_by='OrgaoUnidade.ordem', lazy='select'),
    )

    __table_args__ = (
        db.Index('ix_orgao_unidade_pai_ordem', 'pai_id', 'ordem'),
        db.Index('ix_orgao_unidade_ativo', 'ativo'),
    )

    def __repr__(self):
        return f'<OrgaoUnidade {self.sigla}>'
