"""Novidades (onboarding): o que cada pessoa ainda não viu e a gestão do admin.

O conteúdo mora no frontend (``frontend/src/lib/novidades/``); aqui só o estado
de execução — ativa ou não, quem já viu. Regras:

- A pessoa recebe as novidades ATIVAS, da mais recente para a mais antiga, cada
  uma com ``vista``. O frontend abre sozinho a mais recente não vista.
- Fechar a novidade (concluindo ou dispensando) conta como vista; concluir
  depois de ter dispensado promove a linha a ``concluida`` (nunca rebaixa).
- O admin liga/desliga e pode "mostrar de novo para todos" (apaga as vistas).

Nenhuma função commita: a rota commita (padrão de ``services.collection_shares``).
"""

from __future__ import annotations

from datetime import datetime
from typing import TypedDict

from sqlalchemy import func

from models import Novidade, NovidadeVista, User, db


class NovidadeInexistente(LookupError):
    """Slug sem novidade (ou, para quem não é admin, novidade desligada)."""

    def __init__(self, slug: str) -> None:
        super().__init__(f"Novidade {slug!r} não existe ou não está ativa.")
        self.slug = slug


class NovidadeDoUsuario(TypedDict):
    """Uma novidade ativa do ponto de vista de UMA pessoa."""

    slug: str
    titulo: str
    publicada_em: datetime
    vista: bool


class NovidadeAdmin(TypedDict):
    """Uma novidade com o alcance, para a tela de administração."""

    slug: str
    titulo: str
    ativa: bool
    publicada_em: datetime
    vistas: int
    concluidas: int


def novidades_ativas_para(user_id: int) -> list[NovidadeDoUsuario]:
    """Ativas, mais recente primeiro, com ``vista`` da pessoa — 2 queries.

    Ex.: ``novidades_ativas_para(7)`` →
    ``[{"slug": "colecoes-2026-11", "titulo": "Coleções", "vista": False, ...}]``.
    """
    ativas = (
        Novidade.query.filter(Novidade.ativa.is_(True))
        .order_by(Novidade.publicada_em.desc(), Novidade.id.desc())
        .all()
    )
    vistas = _ids_vistos_por(user_id, [novidade.id for novidade in ativas])
    return [
        NovidadeDoUsuario(
            slug=novidade.slug,
            titulo=novidade.titulo,
            publicada_em=novidade.publicada_em,
            vista=novidade.id in vistas,
        )
        for novidade in ativas
    ]


def marcar_vista(user_id: int, slug: str, *, concluida: bool) -> NovidadeVista:
    """Registra que a pessoa fechou a novidade ATIVA ``slug``; idempotente.

    Ex.: ``marcar_vista(7, "colecoes-2026-11", concluida=True)``. Novidade
    inexistente ou desligada → ``NovidadeInexistente``.
    """
    novidade = Novidade.query.filter_by(slug=slug, ativa=True).first()
    if novidade is None:
        raise NovidadeInexistente(slug)
    vista = NovidadeVista.query.filter_by(
        novidade_id=novidade.id, user_id=user_id
    ).first()
    if vista is None:
        vista = NovidadeVista(
            novidade_id=novidade.id, user_id=user_id, concluida=concluida
        )
        db.session.add(vista)
        return vista
    vista.concluida = vista.concluida or concluida
    return vista


def listar_para_admin() -> list[NovidadeAdmin]:
    """Todas as novidades (ativas ou não) com quantos viram e concluíram — 2 queries.

    Ex.: ``listar_para_admin()[0]["vistas"]`` → ``42``.
    """
    novidades = Novidade.query.order_by(
        Novidade.publicada_em.desc(), Novidade.id.desc()
    ).all()
    alcance = _alcance_por_novidade()
    return [
        NovidadeAdmin(
            slug=novidade.slug,
            titulo=novidade.titulo,
            ativa=bool(novidade.ativa),
            publicada_em=novidade.publicada_em,
            vistas=alcance.get(novidade.id, (0, 0))[0],
            concluidas=alcance.get(novidade.id, (0, 0))[1],
        )
        for novidade in novidades
    ]


def total_usuarios_ativos() -> int:
    """Base do "N de M viram" da tela de admin (usuários não excluídos)."""
    return User.query.filter(User.deleted_at.is_(None)).count()


def definir_ativa(slug: str, ativa: bool) -> Novidade:
    """Liga ou desliga a novidade ``slug``. Ex.: ``definir_ativa("colecoes-2026-11", False)``."""
    novidade = _novidade_por_slug(slug)
    novidade.ativa = ativa
    return novidade


def mostrar_de_novo(slug: str) -> int:
    """Apaga as vistas de ``slug``: ela volta a abrir sozinha para todos.

    Devolve quantas vistas saíram. Ex.: ``mostrar_de_novo("colecoes-2026-11")`` → ``42``.
    """
    novidade = _novidade_por_slug(slug)
    return NovidadeVista.query.filter_by(novidade_id=novidade.id).delete(
        synchronize_session=False
    )


def _novidade_por_slug(slug: str) -> Novidade:
    novidade = Novidade.query.filter_by(slug=slug).first()
    if novidade is None:
        raise NovidadeInexistente(slug)
    return novidade


def _ids_vistos_por(user_id: int, novidade_ids: list[int]) -> set[int]:
    if not novidade_ids:
        return set()
    rows = db.session.query(NovidadeVista.novidade_id).filter(
        NovidadeVista.user_id == user_id,
        NovidadeVista.novidade_id.in_(novidade_ids),
    )
    return {novidade_id for (novidade_id,) in rows}


def _alcance_por_novidade() -> dict[int, tuple[int, int]]:
    """``{novidade_id: (vistas, concluidas)}`` em 1 query agregada."""
    rows = db.session.query(
        NovidadeVista.novidade_id,
        func.count(NovidadeVista.id),
        func.sum(db.case((NovidadeVista.concluida.is_(True), 1), else_=0)),
    ).group_by(NovidadeVista.novidade_id)
    return {
        novidade_id: (int(vistas), int(concluidas or 0))
        for novidade_id, vistas, concluidas in rows
    }
