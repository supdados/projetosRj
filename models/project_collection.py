"""Coleções de projetos: agrupamento livre M:N com dono-usuário.

Primeiro agrupamento pessoal do sistema (análise em
``docs/analise-pastas-personalizadas.md`` §5). ``ProjectCollection`` nasce
pessoal; ``tipo="favoritos"`` é a coleção de sistema (1 por usuário, criada sob
demanda pelo service): não renomeável nem deletável.
"""

from __future__ import annotations

from sqlalchemy.orm import validates

from catalogs.collection_identity import (
    COLLECTION_COLORS,
    COLLECTION_ICONS,
    DEFAULT_COLLECTION_COLOR,
    DEFAULT_COLLECTION_ICON,
)
from time_utils import utc_now

from .base import db

TIPO_COLECAO_CUSTOM = "custom"
TIPO_COLECAO_FAVORITOS = "favoritos"
TIPOS_COLECAO: tuple[str, ...] = (TIPO_COLECAO_CUSTOM, TIPO_COLECAO_FAVORITOS)


class ProjectCollection(db.Model):
    """Coleção de projetos (agrupamento livre criado pelo usuário).

    Exemplo: ``ProjectCollection(owner_user_id=g.user.id, nome="Saúde digital",
    icone="pessoas", cor="success")``.
    """

    __tablename__ = "project_collection"

    id = db.Column(db.Integer, primary_key=True)
    owner_user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False, index=True
    )  # sem ondelete: usuário é soft-deletado (models/user.py deleted_at)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.String(200), nullable=True)
    icone = db.Column(db.String(30), nullable=False, default=DEFAULT_COLLECTION_ICON)
    cor = db.Column(db.String(20), nullable=False, default=DEFAULT_COLLECTION_COLOR)
    tipo = db.Column(db.String(20), nullable=False, default=TIPO_COLECAO_CUSTOM)
    ordem = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

    owner = db.relationship("User")

    __table_args__ = (
        db.UniqueConstraint(
            "owner_user_id", "nome", name="uq_project_collection_owner_nome"
        ),
    )
    # Unicidade de Favoritos (1 por usuário) garantida no service (get-or-create):
    # índice único parcial não é portável SQLite/MySQL.

    @validates("tipo")
    def validate_tipo(self, _key: str, value: str) -> str:
        if value in TIPOS_COLECAO:
            return value
        esperados = "|".join(TIPOS_COLECAO)
        raise ValueError(f"tipo inválido: {value!r}; esperado um de {esperados}")

    @validates("icone")
    def validate_icone(self, _key: str, value: str) -> str:
        if value in COLLECTION_ICONS:
            return value
        esperados = "|".join(sorted(COLLECTION_ICONS))
        raise ValueError(f"ícone inválido: {value!r}; esperado um de {esperados}")

    @validates("cor")
    def validate_cor(self, _key: str, value: str) -> str:
        if value in COLLECTION_COLORS:
            return value
        esperados = "|".join(sorted(COLLECTION_COLORS))
        raise ValueError(
            f"cor inválida: {value!r}; esperado família da régua ({esperados})"
        )

    def __repr__(self) -> str:
        return (
            f"<ProjectCollection {self.id} owner={self.owner_user_id} "
            f"{self.tipo} {self.nome!r}>"
        )


class ProjectCollectionItem(db.Model):
    """Par coleção×projeto. M:N — o mesmo projeto pode estar em N coleções.

    Exemplo: ``ProjectCollectionItem(collection_id=1, project_id=7, ordem=0)``.
    """

    __tablename__ = "project_collection_item"

    id = db.Column(db.Integer, primary_key=True)
    collection_id = db.Column(
        db.Integer,
        db.ForeignKey("project_collection.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id = db.Column(
        db.Integer,
        db.ForeignKey("project.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ordem = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=utc_now)

    __table_args__ = (
        db.UniqueConstraint("collection_id", "project_id", name="uq_collection_item"),
    )

    def __repr__(self) -> str:
        return (
            f"<ProjectCollectionItem collection={self.collection_id} "
            f"project={self.project_id}>"
        )
