"""Coleções de projetos: agrupamento livre M:N com dono-usuário.

Primeiro agrupamento pessoal do sistema (análise em
``docs/analise-pastas-personalizadas.md`` §5). ``ProjectCollection`` nasce
pessoal; ``tipo="favoritos"`` é a coleção de sistema (1 por usuário, criada sob
demanda pelo service): não renomeável nem deletável.

Compartilhamento com aceite: share novo nasce ``exige_aceite=True`` (convite
pendente) e só concede depois de uma ``ProjectCollectionShareResposta``
``aceito`` da pessoa alcançada; shares anteriores à migração ficaram
``exige_aceite=False`` (legado, valem sem aceite). A regra de quando um share
vale mora em ``services/collection_access.py`` — nunca reimplementar aqui.
"""

from __future__ import annotations

import sqlalchemy as sa
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

PAPEL_SHARE_VIEWER = "viewer"
PAPEL_SHARE_EDITOR = "editor"
PAPEIS_SHARE: tuple[str, ...] = (PAPEL_SHARE_VIEWER, PAPEL_SHARE_EDITOR)

STATUS_RESPOSTA_ACEITO = "aceito"
STATUS_RESPOSTA_RECUSADO = "recusado"
STATUS_RESPOSTA_SAIU = "saiu"
STATUS_RESPOSTA_SHARE: tuple[str, ...] = (
    STATUS_RESPOSTA_ACEITO,
    STATUS_RESPOSTA_RECUSADO,
    STATUS_RESPOSTA_SAIU,
)


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

    ``added_by_user_id`` = quem incluiu (NULL só em linha legada, lida como do
    dono). ``rank_teto`` = rank de ÁREA do incluidor no momento da inclusão,
    limitado a editor: o acesso que o item concede via share nunca passa dele
    (NULL = legado sem teto; 0 = não concede nada). Exemplo:
    ``ProjectCollectionItem(collection_id=1, project_id=7, ordem=0,
    added_by_user_id=3, rank_teto=20)``.
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
    added_by_user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=True, index=True
    )  # sem ondelete: usuário é soft-deletado (models/user.py deleted_at)
    rank_teto = db.Column(db.SmallInteger, nullable=True)

    added_by = db.relationship("User", foreign_keys=[added_by_user_id])

    __table_args__ = (
        db.UniqueConstraint("collection_id", "project_id", name="uq_collection_item"),
    )

    def __repr__(self) -> str:
        return (
            f"<ProjectCollectionItem collection={self.collection_id} "
            f"project={self.project_id}>"
        )


class ProjectCollectionShare(db.Model):
    """Compartilhamento de coleção com pessoa OU órgão exato (§5 do doc).

    Exatamente um de ``user_id``/``orgao_id`` (XOR validado no service — CHECK
    não é portável). Share com órgão alcança SÓ o órgão exato de lotação, sem
    subárvore SIORG. Exemplo: ``ProjectCollectionShare(collection_id=1,
    user_id=7, papel="editor", created_by_user_id=2)``.
    """

    __tablename__ = "project_collection_share"

    id = db.Column(db.Integer, primary_key=True)
    collection_id = db.Column(
        db.Integer,
        db.ForeignKey("project_collection.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    orgao_id = db.Column(
        db.Integer, db.ForeignKey("orgao_unidade.id"), nullable=True, index=True
    )
    papel = db.Column(db.String(20), nullable=False, default=PAPEL_SHARE_VIEWER)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now)
    # Default FECHADO (convite pendente): esquecer o campo nunca concede acesso.
    # As linhas anteriores à migração receberam false (legado sem aceite).
    exige_aceite = db.Column(
        db.Boolean, nullable=False, default=True, server_default=sa.true()
    )

    user = db.relationship("User", foreign_keys=[user_id])
    orgao = db.relationship("OrgaoUnidade")

    __table_args__ = (
        db.UniqueConstraint(
            "collection_id", "user_id", name="uq_collection_share_user"
        ),
        db.UniqueConstraint(
            "collection_id", "orgao_id", name="uq_collection_share_orgao"
        ),
    )

    @validates("papel")
    def validate_papel(self, _key: str, value: str) -> str:
        if value in PAPEIS_SHARE:
            return value
        esperados = "|".join(PAPEIS_SHARE)
        raise ValueError(f"papel inválido: {value!r}; esperado um de {esperados}")

    def __repr__(self) -> str:
        destino = f"user={self.user_id}" if self.user_id else f"orgao={self.orgao_id}"
        return (
            f"<ProjectCollectionShare collection={self.collection_id} "
            f"{destino} {self.papel}>"
        )


class ProjectCollectionShareResposta(db.Model):
    """Resposta de UMA pessoa a um share (pessoa ou órgão): aceito/recusado/saiu.

    Por pessoa, não por share: um share de órgão alcança N pessoas e cada uma
    aceita por si. Ausência de linha = pendente (se o share exige aceite) ou
    legado. Exemplo: ``ProjectCollectionShareResposta(share_id=4, user_id=7,
    status="aceito")``.
    """

    __tablename__ = "project_collection_share_resposta"

    id = db.Column(db.Integer, primary_key=True)
    share_id = db.Column(
        db.Integer,
        db.ForeignKey("project_collection_share.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False, index=True
    )  # sem ondelete: usuário é soft-deletado (models/user.py deleted_at)
    status = db.Column(db.String(12), nullable=False)
    respondido_em = db.Column(db.DateTime, nullable=False, default=utc_now)

    user = db.relationship("User")

    __table_args__ = (
        db.UniqueConstraint("share_id", "user_id", name="uq_collection_share_resposta"),
    )

    @validates("status")
    def validate_status(self, _key: str, value: str) -> str:
        if value in STATUS_RESPOSTA_SHARE:
            return value
        esperados = "|".join(STATUS_RESPOSTA_SHARE)
        raise ValueError(f"status inválido: {value!r}; esperado um de {esperados}")

    def __repr__(self) -> str:
        return (
            f"<ProjectCollectionShareResposta share={self.share_id} "
            f"user={self.user_id} {self.status}>"
        )
