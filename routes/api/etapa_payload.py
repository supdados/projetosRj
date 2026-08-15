"""Payload canônico de UMA etapa (fonte única do shape de etapa da API).

Junta num ponto só o que antes vivia espalhado: ``serialize_etapa_detail``
(campos da etapa), a contagem read-only de tarefas por etapa e o bloco
read-only da reunião Google. GET do detalhe, mutações de etapa e mutações de
reunião passam TODAS por aqui, de modo que o front recebe sempre o mesmo shape
(o serializer legado ``_serialize_etapa_payload`` foi aposentado).

Faz consultas (contagem de tarefas) — os serializers de ``serializers.py``
seguem puros.
"""

from __future__ import annotations

from typing import Any

from models import Etapa, Project, Task, db
from services.etapas_dates import meeting_payload_block

from .serializers import serialize_etapa_detail


def task_counts_by_etapa(project: Project) -> dict[int, dict[str, int]]:
    """Conta tarefas não arquivadas por etapa do projeto (total e finalizadas).

    SOMENTE LEITURA (2 queries agregadas, sem N+1). Exemplo:
    ``task_counts_by_etapa(project)[etapa.id]["done"]``.

    Args:
        project: Instância de ``Project``.

    Returns:
        ``{etapa_id: {"total": int, "done": int}}``.
    """
    total_rows = _count_tasks_by_etapa(project.id, only_done=False)
    done_rows = _count_tasks_by_etapa(project.id, only_done=True)
    totals = {etapa_id: int(count) for etapa_id, count in total_rows}
    dones = {etapa_id: int(count) for etapa_id, count in done_rows}
    return {
        etapa_id: {"total": total, "done": dones.get(etapa_id, 0)}
        for etapa_id, total in totals.items()
    }


def _count_tasks_by_etapa(project_id: int, *, only_done: bool) -> list[tuple[int, int]]:
    query = db.session.query(Task.etapa_id, db.func.count(Task.id)).filter(
        Task.project_id == project_id,
        Task.etapa_id.isnot(None),
        Task.is_archived.is_(False),
    )
    if only_done:
        query = query.filter(Task.status == "finalizada")
    return query.group_by(Task.etapa_id).all()


def etapa_detail_payload(etapa: Etapa, connection: Any = None) -> dict[str, Any]:
    """Serializa UMA etapa no shape canônico do detalhe.

    Exemplo: ``etapa_detail_payload(etapa, connection)`` numa resposta de
    criar/editar reunião.

    Args:
        etapa: Instância de ``Etapa``.
        connection: Conexão Google do usuário atual (define ``can_manage`` do
            bloco ``meeting``); ``None`` quando o usuário não tem conta ligada.

    Returns:
        ``dict`` JSON-safe da etapa (com ``meeting`` só em etapa-reunião).
    """
    counts = task_counts_by_etapa(etapa.project).get(etapa.id, {})
    return serialize_etapa_detail(
        etapa,
        task_total=counts.get("total", 0),
        task_done=counts.get("done", 0),
        meeting=meeting_payload_block(etapa, connection),
    )


def project_etapas_payload(
    project: Project, connection: Any = None
) -> list[dict[str, Any]]:
    """Etapas do projeto ordenadas por ``ordem``, no shape canônico do detalhe.

    Args:
        project: Instância de ``Project``.
        connection: Conexão Google do usuário atual (ver ``etapa_detail_payload``).

    Returns:
        Lista de ``dict`` JSON-safe, uma por etapa.
    """
    counts = task_counts_by_etapa(project)
    etapas = sorted(
        project.etapas, key=lambda e: (e.ordem if e.ordem is not None else 0)
    )
    return [
        serialize_etapa_detail(
            etapa,
            task_total=counts.get(etapa.id, {}).get("total", 0),
            task_done=counts.get(etapa.id, {}).get("done", 0),
            meeting=meeting_payload_block(etapa, connection),
        )
        for etapa in etapas
    ]
