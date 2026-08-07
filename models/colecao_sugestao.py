"""Sugestões de coleção geradas por IA, persistidas como cache durável.

Uma linha por sugestão (não por lote): o requisito é aceitar UMA e descartar
OUTRA, então o status precisa ser por linha e indexável. ``assinatura`` (sha256
do CONJUNTO de ``project_ids``) é a chave de supressão — sugestão já aceita ou
descartada não volta a ser oferecida. Desenho em
``docs/plano-ia-fase2-cache-sugestoes.md`` §3.1.
"""

from __future__ import annotations

from sqlalchemy.orm import validates

from time_utils import utc_now

from .base import db

STATUS_SUGESTAO_PENDENTE = "pendente"
STATUS_SUGESTAO_ACEITA = "aceita"
STATUS_SUGESTAO_DESCARTADA = "descartada"
STATUS_SUGESTAO: tuple[str, ...] = (
    STATUS_SUGESTAO_PENDENTE,
    STATUS_SUGESTAO_ACEITA,
    STATUS_SUGESTAO_DESCARTADA,
)


class ColecaoSugestaoIA(db.Model):
    """Sugestão de agrupamento produzida pelo modelo, com decisão do usuário.

    Exemplo: ``ColecaoSugestaoIA(user_id=g.user.id, lote_id=uuid4().hex,
    input_hash=hash_atual, ordem=0, nome="Infraestrutura urbana",
    justificativa="...", project_ids=[3, 7, 12], assinatura=assinatura_de([3, 7, 12]))``.
    """

    __tablename__ = "colecao_sugestao_ia"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False
    )  # sem ondelete: usuário é soft-deletado (models/user.py deleted_at)
    lote_id = db.Column(db.String(32), nullable=False)
    input_hash = db.Column(db.String(64), nullable=False)
    ordem = db.Column(db.Integer, nullable=False, default=0)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.String(200), nullable=True)
    justificativa = db.Column(db.Text, nullable=False)
    project_ids = db.Column(db.JSON, nullable=False)
    assinatura = db.Column(db.String(64), nullable=False)
    status = db.Column(db.String(12), nullable=False, default=STATUS_SUGESTAO_PENDENTE)
    colecao_id = db.Column(
        db.Integer,
        db.ForeignKey("project_collection.id", ondelete="SET NULL"),
        nullable=True,
    )
    modelo_id = db.Column(db.String(80), nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    decidido_em = db.Column(db.DateTime, nullable=True)

    __table_args__ = (db.Index("ix_colecao_sugestao_user_status", "user_id", "status"),)

    @validates("status")
    def validate_status(self, _key: str, value: str) -> str:
        if value in STATUS_SUGESTAO:
            return value
        esperados = "|".join(STATUS_SUGESTAO)
        raise ValueError(f"status inválido: {value!r}; esperado um de {esperados}")

    def __repr__(self) -> str:
        return (
            f"<ColecaoSugestaoIA {self.id} user={self.user_id} "
            f"{self.status} {self.nome!r}>"
        )
