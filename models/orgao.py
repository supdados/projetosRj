import unicodedata

from .base import db

DEFAULT_ORGAO_TIPOS = (
    {"nome": "Estado", "nivel": 0, "permite_raiz": True},
    {"nome": "Secretaria", "nivel": 1, "permite_raiz": False},
    {"nome": "Subsecretaria", "nivel": 2, "permite_raiz": False},
    {"nome": "Superintendência", "nivel": 3, "permite_raiz": False},
    {"nome": "Autarquia", "nivel": 2, "permite_raiz": False},
    {"nome": "Fundação", "nivel": 2, "permite_raiz": False},
    {"nome": "Empresa Pública", "nivel": 2, "permite_raiz": False},
    {"nome": "Assessoria", "nivel": 4, "permite_raiz": False},
    {"nome": "Coordenação", "nivel": 5, "permite_raiz": False},
    {"nome": "Departamento", "nivel": 6, "permite_raiz": False},
    {"nome": "Núcleo", "nivel": 7, "permite_raiz": False},
)

ALLOWED_TIPOS = tuple(item["nome"] for item in DEFAULT_ORGAO_TIPOS)
TIPO_RANK = {item["nome"]: item["nivel"] for item in DEFAULT_ORGAO_TIPOS}

MAX_DEPTH = 5


def slugify_orgao_tipo(nome):
    normalized = unicodedata.normalize("NFKD", nome or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    chars = []
    previous_dash = False
    for char in ascii_text.lower():
        if char.isalnum():
            chars.append(char)
            previous_dash = False
        elif not previous_dash:
            chars.append("-")
            previous_dash = True
    return "".join(chars).strip("-")


class OrgaoTipo(db.Model):
    __tablename__ = "orgao_tipo"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(80), nullable=False, unique=True)
    slug = db.Column(db.String(100), nullable=False, unique=True)
    nivel = db.Column(db.Integer, nullable=False)
    descricao = db.Column(db.String(255), nullable=True)
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    is_system = db.Column(db.Boolean, nullable=False, default=False)
    permite_raiz = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(
        db.DateTime, server_default=db.func.now(), onupdate=db.func.now()
    )

    __table_args__ = (
        db.Index("ix_orgao_tipo_nivel", "nivel"),
        db.Index("ix_orgao_tipo_ativo", "ativo"),
    )

    def __repr__(self):
        return f"<OrgaoTipo {self.nome}>"


class OrgaoUnidade(db.Model):
    __tablename__ = "orgao_unidade"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(255), nullable=False)
    sigla = db.Column(db.String(50), nullable=False)
    tipo = db.Column(db.String(50), nullable=False)
    tipo_id = db.Column(
        db.Integer,
        db.ForeignKey("orgao_tipo.id", ondelete="RESTRICT"),
        nullable=True,
    )
    pai_id = db.Column(
        db.Integer,
        db.ForeignKey("orgao_unidade.id", ondelete="RESTRICT"),
        nullable=True,
    )
    ordem = db.Column(db.Integer, nullable=False, default=0)
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    codigo_externo = db.Column(db.String(80), nullable=True)
    data_inicio_vigencia = db.Column(db.Date, nullable=True)
    data_fim_vigencia = db.Column(db.Date, nullable=True)

    pai = db.relationship(
        "OrgaoUnidade",
        remote_side=[id],
        backref=db.backref("filhos", order_by="OrgaoUnidade.ordem", lazy="select"),
    )
    tipo_ref = db.relationship("OrgaoTipo", lazy="joined")

    __table_args__ = (
        db.Index("ix_orgao_unidade_pai_ordem", "pai_id", "ordem"),
        db.Index("ix_orgao_unidade_ativo", "ativo"),
        db.Index("ix_orgao_unidade_tipo_id", "tipo_id"),
        # Backstop contra duplicação no sync SIORG; NULLs múltiplos permitidos.
        db.Index("ix_orgao_unidade_codigo_externo", "codigo_externo", unique=True),
    )

    @property
    def tipo_nome(self):
        return self.tipo_ref.nome if self.tipo_ref else self.tipo

    @property
    def tipo_nivel(self):
        return self.tipo_ref.nivel if self.tipo_ref else TIPO_RANK.get(self.tipo)

    def __repr__(self):
        return f"<OrgaoUnidade {self.sigla}>"


class OrgaoClosure(db.Model):
    __tablename__ = "orgao_closure"

    ancestor_id = db.Column(
        db.Integer,
        db.ForeignKey("orgao_unidade.id", ondelete="CASCADE"),
        primary_key=True,
    )
    descendant_id = db.Column(
        db.Integer,
        db.ForeignKey("orgao_unidade.id", ondelete="CASCADE"),
        primary_key=True,
    )
    depth = db.Column(db.Integer, nullable=False)

    ancestor = db.relationship(
        "OrgaoUnidade",
        foreign_keys=[ancestor_id],
        backref=db.backref("closure_descendants", cascade="all, delete-orphan"),
    )
    descendant = db.relationship(
        "OrgaoUnidade",
        foreign_keys=[descendant_id],
        backref=db.backref("closure_ancestors", cascade="all, delete-orphan"),
    )

    __table_args__ = (
        db.Index("ix_orgao_closure_descendant", "descendant_id"),
        db.Index("ix_orgao_closure_ancestor_depth", "ancestor_id", "depth"),
    )
