"""Trilha de autorização (S4/F3-4): só concessão, alteração e revogação.

Nada de ``acesso_negado`` por request — um usuário martelando endpoint proibido
encheria a tabela. Negação de ação em tarefa continua em ``TaskAccessAudit``.
"""

from __future__ import annotations

from sqlalchemy.orm import validates

from time_utils import utc_now

from .base import db

EVENTOS_AUTORIZACAO: tuple[str, ...] = (
    "papel_concedido",
    "papel_alterado",
    "papel_revogado",
    "convite_criado",
    "convite_alterado",
    "convite_revogado",
    "convite_reativado",
    "colecao_share_concedido",
    "colecao_share_alterado",
    "colecao_share_revogado",
    "colecao_projeto_adicionado",
    "colecao_projeto_removido",
)

ALVO_ORGAO = "orgao"
ALVO_PROJETO = "project"
ALVO_COLECAO = "colecao"
ALVOS_AUTORIZACAO: tuple[str, ...] = (ALVO_ORGAO, ALVO_PROJETO, ALVO_COLECAO)


class AutorizacaoAudit(db.Model):
    __tablename__ = "autorizacao_audit"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)
    ator_id = db.Column(db.Integer, nullable=False)
    evento = db.Column(db.String(40), nullable=False)
    alvo_tipo = db.Column(db.String(20), nullable=False)
    alvo_id = db.Column(db.Integer, nullable=False)
    detalhe = db.Column(db.JSON, nullable=True)
    criado_em = db.Column(db.DateTime, default=utc_now, nullable=False, index=True)

    @validates("evento")
    def validate_evento(self, _key: str, value: str) -> str:
        if value in EVENTOS_AUTORIZACAO:
            return value
        esperados = "|".join(EVENTOS_AUTORIZACAO)
        raise ValueError(f"evento inválido: {value!r}; esperado um de {esperados}")

    @validates("alvo_tipo")
    def validate_alvo_tipo(self, _key: str, value: str) -> str:
        if value in ALVOS_AUTORIZACAO:
            return value
        esperados = "|".join(ALVOS_AUTORIZACAO)
        raise ValueError(f"alvo_tipo inválido: {value!r}; esperado um de {esperados}")

    def __repr__(self) -> str:
        return f"<AutorizacaoAudit {self.evento} {self.alvo_tipo}={self.alvo_id} user={self.user_id}>"


def registrar_autorizacao(
    *,
    evento: str,
    user_id: int,
    ator_id: int,
    alvo_tipo: str,
    alvo_id: int,
    detalhe: dict[str, object] | None = None,
) -> AutorizacaoAudit:
    """Enfileira um evento da trilha na sessão (o commit é do chamador).

    Exemplo: ``registrar_autorizacao(evento="convite_criado", user_id=7,
    ator_id=1, alvo_tipo=ALVO_PROJETO, alvo_id=42, detalhe={"papel": "editor"})``.
    """
    linha = AutorizacaoAudit(
        evento=evento,
        user_id=user_id,
        ator_id=ator_id,
        alvo_tipo=alvo_tipo,
        alvo_id=alvo_id,
        detalhe=detalhe,
    )
    db.session.add(linha)
    return linha
