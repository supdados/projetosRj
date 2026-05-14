"""Mutações sobre Task — sem Flask context direto.

O commit fica a cargo do caller (rota). Notificações também: estas funções só
alteram estado de modelos. Isso permite testar a lógica sem subir o app.
"""

from dataclasses import dataclass

from time_utils import utc_now
from services.task_status import FINALIZED_TASK_STATUSES


@dataclass
class TaskEditDiff:
    """Snapshot dos campos ANTES da edição, usado para decidir notificações."""

    old_descricao: str
    old_status: str
    old_responsavel: str | None
    old_prioridade: str | None
    old_tipo: str | None
    old_project_id: int | None
    old_etapa_id: int | None = None


def apply_task_edits(
    task,
    *,
    descricao: str,
    status: str,
    responsavel: str | None,
    prioridade: str | None,
    tipo_pedido: str | None,
    project,
    etapa=None,
    apply_etapa: bool = False,
) -> TaskEditDiff:
    """Aplica edições no ``task`` e devolve snapshot pré-mutação.

    Quando ``apply_etapa=True``, ``task.etapa_id`` recebe ``etapa.id`` (ou None
    se ``etapa is None``). Caso contrário, o campo é preservado — útil para
    edições parciais que não tocam na etapa.
    """
    diff = TaskEditDiff(
        old_descricao=task.descricao,
        old_status=task.status,
        old_responsavel=task.responsavel,
        old_prioridade=task.prioridade,
        old_tipo=task.tipo_pedido,
        old_project_id=task.project_id,
        old_etapa_id=task.etapa_id,
    )

    task.descricao = descricao
    task.status = status
    task.responsavel = responsavel if responsavel else None
    task.prioridade = prioridade
    task.tipo_pedido = tipo_pedido
    task.project_id = project.id if project else None
    if apply_etapa:
        task.etapa_id = etapa.id if etapa else None

    return diff


def is_task_open(task) -> bool:
    """Tarefa que ainda 'pesa' na etapa: não arquivada e não finalizada."""
    if task.is_archived:
        return False
    return task.status not in FINALIZED_TASK_STATUSES


def move_task_to_etapa(task, etapa) -> int | None:
    """Reassocia a tarefa a uma etapa (ou desassocia, se ``etapa is None``).

    Pré-condições devem ser validadas pelo caller: a etapa deve pertencer ao
    mesmo projeto da tarefa e não estar concluída. Não faz commit. Retorna o
    ``etapa_id`` anterior.
    """
    previous_etapa_id = task.etapa_id
    task.etapa_id = etapa.id if etapa else None
    return previous_etapa_id


def archive_task(task) -> None:
    """Marca tarefa como arquivada. Não faz commit."""
    task.is_archived = True
    task.archived_at = utc_now()


def unarchive_task(task) -> None:
    """Desarquiva e reseta status para 'nao_iniciada'. Não faz commit."""
    task.is_archived = False
    task.archived_at = None
    task.status = "nao_iniciada"


def bulk_archive_finalized(tasks) -> list[int]:
    """Arquiva em lote tarefas ``tasks`` (presumidas finalizadas).

    Retorna lista de ids arquivados. Não faz commit.
    """
    now = utc_now()
    archived_ids: list[int] = []
    for task in tasks:
        task.is_archived = True
        task.archived_at = now
        archived_ids.append(task.id)
    return archived_ids


def parse_unique_task_order_ids(raw_ids) -> list[int]:
    """Normaliza lista de ids para reorder: converte para int e remove duplicatas.

    Entrada inválida (não-lista, ids não-numéricos) é silenciosamente ignorada.
    """
    if not isinstance(raw_ids, list):
        return []

    ordered_ids: list[int] = []
    seen: set[int] = set()
    for raw_id in raw_ids:
        try:
            task_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if task_id in seen:
            continue
        seen.add(task_id)
        ordered_ids.append(task_id)

    return ordered_ids


def apply_task_order(scope_query, ordered_ids: list[int]) -> None:
    """Reordena tasks: as em ``ordered_ids`` vão para o topo; demais seguem ordem relativa.

    Não faz commit. ``scope_query`` deve ser uma query SQLAlchemy já escopada.
    """
    scope_tasks = scope_query.all()
    tasks_by_id = {task.id: task for task in scope_tasks}

    ordered_tasks = [tasks_by_id[tid] for tid in ordered_ids if tid in tasks_by_id]
    ordered_task_ids = {task.id for task in ordered_tasks}
    remaining_tasks = [task for task in scope_tasks if task.id not in ordered_task_ids]

    for index, task in enumerate(ordered_tasks + remaining_tasks, start=1):
        task.ordem = index
