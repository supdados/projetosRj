"""Novidades do produto (onboarding "Novidades") e quem já viu cada uma.

O CONTEÚDO de cada novidade (passos, textos, ilustrações) vive no frontend
(``frontend/src/lib/novidades/``), indexado pelo ``slug``; aqui fica só o que
muda em tempo de execução: se ela está ativa e quem já a viu. Por quê: o
conteúdo tem ilustração em componente e precisa de deploy de qualquer jeito,
mas ligar/desligar e "mostrar de novo para todos" não podem depender de deploy.

Nova novidade = conteúdo no frontend + uma migração que insere a linha.
"""

from __future__ import annotations

from time_utils import utc_now

from .base import db

SLUG_NOVIDADE_MAX = 64


class Novidade(db.Model):
    """Uma novidade anunciável. Exemplo: ``Novidade(slug="colecoes-2026-11",
    titulo="Coleções", ativa=True)``.

    ``publicada_em`` ordena o que aparece primeiro (mais recente primeiro).
    """

    __tablename__ = "novidade"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(SLUG_NOVIDADE_MAX), nullable=False)
    titulo = db.Column(db.String(120), nullable=False)
    ativa = db.Column(db.Boolean, nullable=False, default=False)
    publicada_em = db.Column(db.DateTime, nullable=False, default=utc_now)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    __table_args__ = (db.UniqueConstraint("slug", name="uq_novidade_slug"),)


class NovidadeVista(db.Model):
    """Uma pessoa já viu (e fechou) uma novidade.

    ``concluida`` = chegou ao último passo; ``False`` = dispensou antes ("Agora
    não", X ou Esc). As duas contam como vista: o modal não volta sozinho.
    Exemplo: ``NovidadeVista(novidade_id=1, user_id=7, concluida=True)``.
    """

    __tablename__ = "novidade_vista"

    id = db.Column(db.Integer, primary_key=True)
    novidade_id = db.Column(
        db.Integer,
        db.ForeignKey("novidade.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False, index=True
    )  # sem ondelete: usuário é soft-deletado (models/user.py deleted_at)
    concluida = db.Column(db.Boolean, nullable=False, default=False)
    vista_em = db.Column(db.DateTime, nullable=False, default=utc_now)

    __table_args__ = (
        db.UniqueConstraint("novidade_id", "user_id", name="uq_novidade_vista"),
    )
