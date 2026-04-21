"""Testes unitários para services/task_mutation.py.

Todas as funções são puras (operam em atributos de objetos Python sem commit),
por isso não precisam de Flask context nem de DB — usamos FakeTask simples.
"""

from dataclasses import dataclass, field

import pytest

from services.task_mutation import (
    apply_task_edits,
    apply_task_order,
    archive_task,
    bulk_archive_finalized,
    parse_unique_task_order_ids,
    unarchive_task,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


@dataclass
class FakeTask:
    id: int = 1
    descricao: str = 'Descricao original'
    status: str = 'nao_iniciada'
    responsavel: str | None = None
    prioridade: str | None = None
    tipo_pedido: str | None = None
    project_id: int | None = None
    is_archived: bool = False
    archived_at: object = None
    ordem: int = 1


@dataclass
class FakeProject:
    id: int = 42


class FakeScopeQuery:
    """Simula SQLAlchemy query com .all() retornando lista fixa."""

    def __init__(self, tasks: list):
        self._tasks = tasks

    def all(self) -> list:
        return list(self._tasks)


# ── parse_unique_task_order_ids ───────────────────────────────────────────────


def test_parse_ids_returns_empty_for_non_list():
    assert parse_unique_task_order_ids('nao-lista') == []
    assert parse_unique_task_order_ids(None) == []
    assert parse_unique_task_order_ids(123) == []


def test_parse_ids_returns_empty_list_unchanged():
    assert parse_unique_task_order_ids([]) == []


def test_parse_ids_converts_strings_to_int():
    assert parse_unique_task_order_ids(['1', '2', '3']) == [1, 2, 3]


def test_parse_ids_skips_non_numeric():
    assert parse_unique_task_order_ids([1, 'abc', 2, None]) == [1, 2]


def test_parse_ids_deduplicates_preserving_first_occurrence():
    assert parse_unique_task_order_ids([3, 1, 3, 2, 1]) == [3, 1, 2]


def test_parse_ids_handles_float_strings():
    # int('1.5') raises ValueError — deve ser ignorado
    assert parse_unique_task_order_ids(['1', '1.5', '2']) == [1, 2]


# ── apply_task_edits ──────────────────────────────────────────────────────────


def test_apply_task_edits_returns_snapshot_of_old_values():
    task = FakeTask(
        descricao='Antes',
        status='nao_iniciada',
        responsavel='Ana',
        prioridade='baixa',
        tipo_pedido='bug',
        project_id=7,
    )
    diff = apply_task_edits(
        task,
        descricao='Depois',
        status='em_andamento',
        responsavel='Bruno',
        prioridade='alta',
        tipo_pedido='melhoria',
        project=FakeProject(id=99),
    )
    assert diff.old_descricao == 'Antes'
    assert diff.old_status == 'nao_iniciada'
    assert diff.old_responsavel == 'Ana'
    assert diff.old_prioridade == 'baixa'
    assert diff.old_tipo == 'bug'
    assert diff.old_project_id == 7


def test_apply_task_edits_mutates_task_attributes():
    task = FakeTask()
    project = FakeProject(id=55)
    apply_task_edits(
        task,
        descricao='Nova',
        status='em_andamento',
        responsavel='Carlos',
        prioridade='urgente',
        tipo_pedido='outros',
        project=project,
    )
    assert task.descricao == 'Nova'
    assert task.status == 'em_andamento'
    assert task.responsavel == 'Carlos'
    assert task.prioridade == 'urgente'
    assert task.tipo_pedido == 'outros'
    assert task.project_id == 55


def test_apply_task_edits_clears_responsavel_when_falsy():
    task = FakeTask(responsavel='Alguem')
    apply_task_edits(
        task, descricao='X', status='nao_iniciada',
        responsavel='', prioridade=None, tipo_pedido=None, project=None,
    )
    assert task.responsavel is None


def test_apply_task_edits_clears_project_when_none():
    task = FakeTask(project_id=10)
    apply_task_edits(
        task, descricao='X', status='nao_iniciada',
        responsavel=None, prioridade=None, tipo_pedido=None, project=None,
    )
    assert task.project_id is None


# ── archive_task ──────────────────────────────────────────────────────────────


def test_archive_task_sets_is_archived_true():
    task = FakeTask(is_archived=False)
    archive_task(task)
    assert task.is_archived is True


def test_archive_task_sets_archived_at():
    task = FakeTask(archived_at=None)
    archive_task(task)
    assert task.archived_at is not None


# ── unarchive_task ────────────────────────────────────────────────────────────


def test_unarchive_task_clears_is_archived():
    task = FakeTask(is_archived=True)
    unarchive_task(task)
    assert task.is_archived is False


def test_unarchive_task_clears_archived_at():
    task = FakeTask(archived_at='2025-01-01')
    unarchive_task(task)
    assert task.archived_at is None


def test_unarchive_task_resets_status_to_nao_iniciada():
    task = FakeTask(status='finalizada', is_archived=True)
    unarchive_task(task)
    assert task.status == 'nao_iniciada'


# ── bulk_archive_finalized ────────────────────────────────────────────────────


def test_bulk_archive_finalized_archives_all_tasks():
    tasks = [FakeTask(id=i, is_archived=False) for i in range(1, 4)]
    archived_ids = bulk_archive_finalized(tasks)
    assert all(t.is_archived is True for t in tasks)
    assert all(t.archived_at is not None for t in tasks)
    assert archived_ids == [1, 2, 3]


def test_bulk_archive_finalized_returns_empty_for_empty_list():
    assert bulk_archive_finalized([]) == []


def test_bulk_archive_finalized_uses_same_timestamp():
    tasks = [FakeTask(id=i) for i in range(1, 3)]
    bulk_archive_finalized(tasks)
    assert tasks[0].archived_at == tasks[1].archived_at


# ── apply_task_order ──────────────────────────────────────────────────────────


def test_apply_task_order_puts_requested_ids_first():
    t1 = FakeTask(id=1, ordem=3)
    t2 = FakeTask(id=2, ordem=1)
    t3 = FakeTask(id=3, ordem=2)
    query = FakeScopeQuery([t1, t2, t3])

    apply_task_order(query, ordered_ids=[3, 1])

    assert t3.ordem == 1  # primeiro pedido
    assert t1.ordem == 2  # segundo pedido
    assert t2.ordem == 3  # restante


def test_apply_task_order_starts_at_one():
    tasks = [FakeTask(id=i, ordem=99) for i in range(1, 4)]
    query = FakeScopeQuery(tasks)

    apply_task_order(query, ordered_ids=[2, 1, 3])

    assert tasks[1].ordem == 1
    assert tasks[0].ordem == 2
    assert tasks[2].ordem == 3


def test_apply_task_order_ignores_ids_not_in_scope():
    t1 = FakeTask(id=1, ordem=0)
    t2 = FakeTask(id=2, ordem=0)
    query = FakeScopeQuery([t1, t2])

    apply_task_order(query, ordered_ids=[99, 1, 2])  # 99 não existe no escopo

    assert t1.ordem == 1
    assert t2.ordem == 2


def test_apply_task_order_with_empty_ordered_ids_preserves_scope_order():
    t1 = FakeTask(id=1)
    t2 = FakeTask(id=2)
    query = FakeScopeQuery([t1, t2])

    apply_task_order(query, ordered_ids=[])

    assert t1.ordem == 1
    assert t2.ordem == 2
