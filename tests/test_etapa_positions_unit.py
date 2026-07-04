"""Unitários de ``services/etapa_positions.py``.

Fixam a paridade da numeração com a tela de Detalhe: posição 1-based na lista
COMPLETA do projeto, ordenada por ``ordem`` (nulos como 0, desempate por id),
independente do subconjunto exibido em Pendentes.
"""

from __future__ import annotations

from models import Etapa, Project, db
from services.etapa_positions import build_etapa_position_map


def _create_project_with_stages(titulo: str, ordens: list[int]) -> Project:
    project = Project(titulo=titulo, status="Vigente")
    db.session.add(project)
    db.session.flush()
    for ordem in ordens:
        db.session.add(
            Etapa(descricao=f"Etapa ordem {ordem}", project_id=project.id, ordem=ordem)
        )
    db.session.commit()
    return project


def test_positions_follow_ordem_not_id(app, seed_data):
    with app.app_context():
        project = _create_project_with_stages("Posicoes", [30, 10, 20])
        etapas_por_ordem = {e.ordem: e.id for e in project.etapas}

        positions = build_etapa_position_map([project.id])

        assert positions[etapas_por_ordem[10]] == 1
        assert positions[etapas_por_ordem[20]] == 2
        assert positions[etapas_por_ordem[30]] == 3


def test_positions_cover_multiple_projects_in_one_call(app, seed_data):
    with app.app_context():
        project_a = _create_project_with_stages("Posicoes A", [1, 2])
        project_b = _create_project_with_stages("Posicoes B", [1])

        positions = build_etapa_position_map([project_a.id, project_b.id])

        assert sorted(positions[e.id] for e in project_a.etapas) == [1, 2]
        assert [positions[e.id] for e in project_b.etapas] == [1]


def test_positions_tie_on_ordem_breaks_by_id(app, seed_data):
    with app.app_context():
        project = _create_project_with_stages("Posicoes Empate", [7, 7])
        primeiro, segundo = sorted(project.etapas, key=lambda e: e.id)

        positions = build_etapa_position_map([project.id])

        assert positions[primeiro.id] == 1
        assert positions[segundo.id] == 2


def test_positions_empty_input_returns_empty_map(app):
    with app.app_context():
        assert build_etapa_position_map([]) == {}
