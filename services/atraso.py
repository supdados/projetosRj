"""Fonte única da definição de "projeto atrasado" (1 definição, 1 relógio).

DECISÃO DE PRODUTO (final, 2026-08): projeto atrasado = existe etapa de
workflow NÃO concluída (``done=False``, ``entry_type != "google_meeting"``)
com ``data_fim < hoje``, onde hoje = ``time_utils.utc_now().date()`` (UTC).
A fronteira ``data_fim == hoje`` NÃO é atraso; ``data_inicio`` NÃO participa
do critério. Vale para TODOS os consumidores (Lista de Projetos, Projetos
Pendentes, Dashboard e Coleções) — nenhum deles pode redefinir o critério
nem usar outro relógio.
"""

from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import and_, exists

from models import Etapa, Project, db
from time_utils import utc_now


def hoje_utc() -> datetime.date:
    """Relógio único do critério de atraso: ``utc_now().date()`` (UTC)."""
    return utc_now().date()


def etapa_vencida_criterion(hoje: datetime.date | None = None) -> Any:
    """Condição SQL de etapa vencida, sobre colunas de ``Etapa``.

    Serve tanto ao EXISTS de ``projeto_atrasado_criterion`` quanto a
    agregados que já têm ``Etapa`` no FROM (ex.: ``SUM(CASE ...)`` das
    Coleções). Exemplo: ``query.filter(etapa_vencida_criterion())``.
    """
    data_referencia = hoje if hoje is not None else hoje_utc()
    return and_(
        Etapa.done.is_(False),
        Etapa.entry_type != "google_meeting",
        Etapa.data_fim < data_referencia,
    )


def projeto_atrasado_criterion(hoje: datetime.date | None = None) -> Any:
    """EXISTS correlacionado com ``Project``: ao menos uma etapa vencida.

    Exemplo: ``Project.query.filter(projeto_atrasado_criterion())``; negue com
    ``~`` para "no prazo".
    """
    return exists().where(
        and_(Etapa.project_id == Project.id, etapa_vencida_criterion(hoje))
    )


def etapa_esta_vencida(etapa: Etapa, hoje: datetime.date | None = None) -> bool:
    """Espelho em Python do ``etapa_vencida_criterion`` para etapas já carregadas."""
    if etapa.done or etapa.entry_type == "google_meeting":
        return False
    if etapa.data_fim is None:
        return False
    data_referencia = hoje if hoje is not None else hoje_utc()
    return etapa.data_fim < data_referencia


def contar_projetos_atrasados(
    project_query: Any, hoje: datetime.date | None = None
) -> int:
    """COUNT de projetos atrasados sobre uma query de ``Project`` já escopada."""
    return int(project_query.filter(projeto_atrasado_criterion(hoje)).count())


def projeto_esta_atrasado(project_id: int, hoje: datetime.date | None = None) -> bool:
    """Flag de atraso de UM projeto, em uma query (EXISTS)."""
    etapa_vencida = db.session.query(Etapa.id).filter(
        Etapa.project_id == project_id, etapa_vencida_criterion(hoje)
    )
    return bool(db.session.query(etapa_vencida.exists()).scalar())
