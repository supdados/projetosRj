"""Unit tests para o sub-agrupamento Projeto > Etapa > Tarefa do hub.

Testa a lógica de ``_group_hub_tasks_by_project`` em isolamento, sem Flask
context — usa fakes simples no lugar de modelos SQLAlchemy.
"""

from dataclasses import dataclass, field

import pytest

from routes.tasks.hub import _group_hub_tasks_by_project


@dataclass
class FakeOrgao:
    sigla: str = ""


@dataclass
class FakeProject:
    id: int = 1
    titulo: str = "Projeto"
    orgao_ref: FakeOrgao | None = None


@dataclass
class FakeEtapa:
    id: int
    descricao: str
    ordem: int = 0
    done: bool = False


@dataclass
class FakeTask:
    id: int
    descricao: str = "Tarefa"
    status: str = "nao_iniciada"
    prioridade: str | None = None
    tipo_pedido: str | None = None
    responsavel: str | None = None
    project: FakeProject | None = None
    etapa: FakeEtapa | None = None
    is_archived: bool = False
    created_by_id: int = 1
    comments: list = field(default_factory=list)
    anexos: list = field(default_factory=list)


@pytest.fixture(autouse=True)
def stub_permission_flags(monkeypatch):
    monkeypatch.setattr(
        "routes.tasks.hub._task_permission_flags",
        lambda _task: {"can_delete": True, "can_finalize": True, "is_author": True},
    )


def _make_project():
    return FakeProject(id=1, titulo="Projeto A", orgao_ref=FakeOrgao(sigla="SUP"))


def test_groups_legacy_bucket_appears_first_within_project():
    project = _make_project()
    etapa = FakeEtapa(id=10, descricao="Etapa 1", ordem=0)
    legacy = FakeTask(id=1, project=project, etapa=None)
    in_stage = FakeTask(id=2, project=project, etapa=etapa)

    groups = _group_hub_tasks_by_project([legacy, in_stage])
    assert len(groups) == 1
    stages = groups[0]["stages"]
    assert [s["etapa_value"] for s in stages] == ["sem_etapa", "10"]
    assert stages[0]["is_legacy_bucket"] is True


def test_stages_are_sorted_by_etapa_ordem():
    project = _make_project()
    etapa_a = FakeEtapa(id=10, descricao="Etapa A", ordem=2)
    etapa_b = FakeEtapa(id=20, descricao="Etapa B", ordem=0)
    etapa_c = FakeEtapa(id=30, descricao="Etapa C", ordem=1)

    tasks = [
        FakeTask(id=1, project=project, etapa=etapa_a),
        FakeTask(id=2, project=project, etapa=etapa_b),
        FakeTask(id=3, project=project, etapa=etapa_c),
    ]
    groups = _group_hub_tasks_by_project(tasks)
    stages = groups[0]["stages"]
    assert [s["etapa_value"] for s in stages] == ["20", "30", "10"]


def test_flattened_tasks_have_first_of_stage_flags():
    project = _make_project()
    etapa_a = FakeEtapa(id=10, descricao="Etapa A", ordem=0)
    etapa_b = FakeEtapa(id=20, descricao="Etapa B", ordem=1)
    tasks = [
        FakeTask(id=1, project=project, etapa=etapa_a),
        FakeTask(id=2, project=project, etapa=etapa_a),
        FakeTask(id=3, project=project, etapa=etapa_b),
    ]
    groups = _group_hub_tasks_by_project(tasks)
    flat = groups[0]["tasks"]
    assert [t.hub_is_first_of_stage for t in flat] == [True, False, True]
    assert flat[0].hub_stage_id == 10
    assert flat[2].hub_stage_id == 20


def test_tasks_within_stage_are_sorted_by_status():
    project = _make_project()
    etapa = FakeEtapa(id=10, descricao="Etapa A", ordem=0)
    # Mesma prioridade: ordena por status (nao_iniciada → … → finalizada).
    tasks = [
        FakeTask(
            id=1, project=project, etapa=etapa, prioridade="alta", status="finalizada"
        ),
        FakeTask(
            id=2, project=project, etapa=etapa, prioridade="alta", status="nao_iniciada"
        ),
        FakeTask(
            id=3, project=project, etapa=etapa, prioridade="alta", status="para_ajustes"
        ),
        FakeTask(
            id=4, project=project, etapa=etapa, prioridade="alta", status="em_andamento"
        ),
        FakeTask(
            id=5,
            project=project,
            etapa=etapa,
            prioridade="alta",
            status="para_validacao",
        ),
    ]
    groups = _group_hub_tasks_by_project(tasks)
    assert [t.id for t in groups[0]["tasks"]] == [2, 4, 5, 3, 1]


def test_same_status_is_ordered_by_priority():
    project = _make_project()
    etapa = FakeEtapa(id=10, descricao="Etapa A", ordem=0)
    # Mesmo status: desempata por prioridade (urgente → alta → media → baixa).
    tasks = [
        FakeTask(
            id=1,
            project=project,
            etapa=etapa,
            status="em_andamento",
            prioridade="baixa",
        ),
        FakeTask(
            id=2,
            project=project,
            etapa=etapa,
            status="em_andamento",
            prioridade="urgente",
        ),
        FakeTask(
            id=3,
            project=project,
            etapa=etapa,
            status="em_andamento",
            prioridade="media",
        ),
        FakeTask(
            id=4, project=project, etapa=etapa, status="em_andamento", prioridade="alta"
        ),
    ]
    groups = _group_hub_tasks_by_project(tasks)
    assert [t.id for t in groups[0]["tasks"]] == [2, 4, 3, 1]


def test_status_outranks_priority():
    project = _make_project()
    etapa = FakeEtapa(id=10, descricao="Etapa A", ordem=0)
    # Status tem precedência sobre prioridade: nao_iniciada/baixa vem antes de
    # finalizada/urgente.
    tasks = [
        FakeTask(
            id=1,
            project=project,
            etapa=etapa,
            status="finalizada",
            prioridade="urgente",
        ),
        FakeTask(
            id=2,
            project=project,
            etapa=etapa,
            status="nao_iniciada",
            prioridade="baixa",
        ),
    ]
    groups = _group_hub_tasks_by_project(tasks)
    assert [t.id for t in groups[0]["tasks"]] == [2, 1]


def test_same_status_and_priority_preserves_manual_order():
    project = _make_project()
    etapa = FakeEtapa(id=10, descricao="Etapa A", ordem=0)
    # Mesmo status e prioridade: a ordem de entrada (Task.ordem) é mantida.
    tasks = [
        FakeTask(id=7, project=project, etapa=etapa, prioridade="alta"),
        FakeTask(id=3, project=project, etapa=etapa, prioridade="alta"),
        FakeTask(id=5, project=project, etapa=etapa, prioridade="alta"),
    ]
    groups = _group_hub_tasks_by_project(tasks)
    assert [t.id for t in groups[0]["tasks"]] == [7, 3, 5]


def test_tasks_without_priority_sort_after_prioritized():
    project = _make_project()
    etapa = FakeEtapa(id=10, descricao="Etapa A", ordem=0)
    tasks = [
        FakeTask(id=1, project=project, etapa=etapa, prioridade=None),
        FakeTask(id=2, project=project, etapa=etapa, prioridade="baixa"),
    ]
    groups = _group_hub_tasks_by_project(tasks)
    assert [t.id for t in groups[0]["tasks"]] == [2, 1]


def test_orphan_tasks_without_project_skip_stage_bucket():
    legacy_no_project = FakeTask(id=1, project=None, etapa=None)
    groups = _group_hub_tasks_by_project([legacy_no_project])
    assert len(groups) == 1
    assert groups[0]["project_id"] is None
    # Sem etapa quando não há projeto — sub-hierarquia não aplica.
    assert groups[0]["stages"] == []


def test_done_etapa_is_marked_in_stage_bucket():
    project = _make_project()
    etapa = FakeEtapa(id=10, descricao="Concluída", done=True)
    task = FakeTask(id=1, project=project, etapa=etapa)
    groups = _group_hub_tasks_by_project([task])
    stages = groups[0]["stages"]
    assert stages[0]["etapa_done"] is True
