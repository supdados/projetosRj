"""Testes unitários da validação cruzada data_fim >= data_inicio (bug 2.3).

Cobre services/etapas_mutation.py: update_regular_field (inversão direta e
cascata interna legítima do data_inicio) e create_etapa_record (criação com
datas invertidas).
"""

import pytest

from models import Etapa, Project, db
from services.etapas_dates import (
    _add_business_days,
    _business_days_between,
    _normalize_to_business_day,
)
from services.etapas_mutation import create_etapa_record, update_regular_field


def _create_project() -> Project:
    project = Project(titulo="Projeto Datas")
    db.session.add(project)
    db.session.flush()
    return project


def _create_etapa(project, *, data_inicio=None, data_fim=None) -> Etapa:
    etapa = Etapa(
        descricao="Etapa X",
        project_id=project.id,
        ordem=0,
        data_inicio=data_inicio,
        data_fim=data_fim,
    )
    db.session.add(etapa)
    db.session.flush()
    return etapa


def test_update_regular_field_rejeita_data_fim_anterior_ao_inicio(app):
    import datetime

    with app.app_context():
        project = _create_project()
        etapa = _create_etapa(
            project,
            data_inicio=datetime.date(2026, 1, 20),
            data_fim=datetime.date(2026, 1, 30),
        )

        with pytest.raises(ValueError, match="não pode ser anterior"):
            update_regular_field(etapa, "data_fim", "2026-01-15")

        # falha antes de mutar — data_fim original preservada
        assert etapa.data_fim == datetime.date(2026, 1, 30)


def test_update_regular_field_cascata_interna_legitima_do_data_inicio_passa(app):
    """Mover data_inicio além do antigo data_fim é válido: o serviço propaga a
    mesma variação de dias úteis ao data_fim, então o PAR FINAL segue coerente
    mesmo que o data_fim antigo fique "para trás" do novo data_inicio.
    """
    import datetime

    with app.app_context():
        project = _create_project()
        old_start = datetime.date(2026, 1, 5)  # segunda-feira
        old_end = datetime.date(2026, 1, 9)  # sexta-feira
        etapa = _create_etapa(project, data_inicio=old_start, data_fim=old_end)

        new_start = datetime.date(2026, 1, 19)  # segunda seguinte, após old_end
        days_diff = _business_days_between(old_start, new_start)
        expected_end = _normalize_to_business_day(
            _add_business_days(old_end, days_diff), forward=True
        )

        response = update_regular_field(etapa, "data_inicio", new_start.isoformat())

        assert etapa.data_inicio == new_start
        assert etapa.data_fim >= etapa.data_inicio
        assert etapa.data_fim == expected_end
        assert response["updatedEndDate"] == expected_end.isoformat()


def test_create_etapa_record_rejeita_datas_invertidas(app):
    import datetime

    with app.app_context():
        project = _create_project()

        with pytest.raises(ValueError, match="não pode ser anterior"):
            create_etapa_record(
                project,
                descricao="Etapa Invertida",
                data_inicio=datetime.date(2026, 2, 10),
                data_fim=datetime.date(2026, 2, 1),
                responsavel=None,
                comentarios=None,
                iniciada=False,
                done=False,
            )

        # não deixou etapa órfã pendurada na sessão após a falha
        assert (
            Etapa.query.filter_by(
                project_id=project.id, descricao="Etapa Invertida"
            ).count()
            == 0
        )
