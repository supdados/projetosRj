"""Projeções em lote para cards: contadores e datas sem materializar os filhos."""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date

from sqlalchemy import and_, case, func
from sqlalchemy.orm import Load, joinedload, selectinload

from models import Etapa, Task, TaskAnexo, TaskAssignee, TaskComment, db


@dataclass(frozen=True)
class ProjectCardStatistics:
    data_inicio: date | None = None
    data_fim: date | None = None
    total: int = 0
    concluidas: int = 0


@dataclass(frozen=True)
class TaskCardCounts:
    comments: int = 0
    attachments: int = 0


def _id_batches(ids: Iterable[int]) -> Iterator[list[int]]:
    values = list(dict.fromkeys(ids))
    for offset in range(0, len(values), 500):
        yield values[offset : offset + 500]


def project_card_statistics(
    project_ids: Iterable[int],
) -> dict[int, ProjectCardStatistics]:
    """Agrega todas as etapas dos IDs autorizados; ex.: ``project_card_statistics([7])``.

    Datas incluem reuniões; progresso considera apenas workflow, como as
    properties de Project. Nenhum objeto Etapa precisa ser criado no ORM.
    """
    result: dict[int, ProjectCardStatistics] = {}
    workflow = Etapa.entry_type != "google_meeting"
    completed = and_(workflow, Etapa.iniciada.is_(True), Etapa.done.is_(True))
    for batch in _id_batches(project_ids):
        result.update({project_id: ProjectCardStatistics() for project_id in batch})
        rows = (
            db.session.query(
                Etapa.project_id,
                func.min(Etapa.data_inicio),
                func.max(Etapa.data_fim),
                func.sum(case((workflow, 1), else_=0)),
                func.sum(case((completed, 1), else_=0)),
            )
            .filter(Etapa.project_id.in_(batch))
            .group_by(Etapa.project_id)
            .all()
        )
        for project_id, start, end, total, done in rows:
            result[project_id] = ProjectCardStatistics(
                start, end, int(total or 0), int(done or 0)
            )
    return result


def task_card_counts(task_ids: Iterable[int]) -> dict[int, TaskCardCounts]:
    """Conta comentários/anexos separadamente, sem JOIN cartesiano; ex.: ``task_card_counts([7])``."""
    result: dict[int, TaskCardCounts] = {}
    for batch in _id_batches(task_ids):
        comments = dict(
            db.session.query(TaskComment.task_id, func.count(TaskComment.id))
            .filter(TaskComment.task_id.in_(batch))
            .group_by(TaskComment.task_id)
            .all()
        )
        attachments = dict(
            db.session.query(TaskAnexo.task_id, func.count(TaskAnexo.id))
            .filter(TaskAnexo.task_id.in_(batch))
            .group_by(TaskAnexo.task_id)
            .all()
        )
        result.update(
            {
                task_id: TaskCardCounts(
                    comments.get(task_id, 0), attachments.get(task_id, 0)
                )
                for task_id in batch
            }
        )
    return result


def task_card_load_options() -> tuple[Load, ...]:
    """Relações necessárias ao card; conteúdo de comentários/anexos fica no detalhe."""
    return (
        joinedload(Task.project),
        selectinload(Task.assignees).joinedload(TaskAssignee.user),
    )
