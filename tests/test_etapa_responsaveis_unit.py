"""Testes unitários de services/etapa_responsaveis.py (mudança #3).

Cobre parse_responsaveis_entries (vazio, não-lista, item não-dict, area_id
inexistente, dedupe, 'Outras') e replace_etapa_responsaveis: substituição das
linhas N:N + mirror legado truncado a 100 chars, e o merge/reuse na edição
(regressão do UNIQUE(etapa_id, area_id) + preservação do id da linha mantida).
"""

import pytest

from models import Etapa, EtapaResponsavel, OrgaoUnidade, Project, db
from services.etapa_responsaveis import (
    OUTRAS_LABEL,
    parse_responsaveis_entries,
    replace_etapa_responsaveis,
    split_responsavel_legado,
)


def _create_area(sigla: str) -> OrgaoUnidade:
    area = OrgaoUnidade(sigla=sigla, nome=f"Área {sigla}", tipo="Secretaria", ordem=0)
    db.session.add(area)
    db.session.flush()
    return area


def _create_etapa() -> Etapa:
    project = Project(titulo="Projeto Responsáveis")
    db.session.add(project)
    db.session.flush()
    etapa = Etapa(descricao="Etapa X", project_id=project.id, ordem=0)
    db.session.add(etapa)
    db.session.flush()
    return etapa


# ── parse_responsaveis_entries ────────────────────────────────────────────────


def test_parse_rejeita_lista_vazia_e_nao_lista(app):
    with app.app_context():
        for raw in ([], None, "SES", {"area_id": 1}):
            with pytest.raises(ValueError, match="Pelo menos uma área responsável"):
                parse_responsaveis_entries(raw)


def test_parse_rejeita_item_nao_dict(app):
    with app.app_context():
        with pytest.raises(ValueError, match="Área responsável inválida"):
            parse_responsaveis_entries(["SES"])


def test_parse_rejeita_area_id_inexistente(app):
    with app.app_context():
        with pytest.raises(ValueError, match="Área responsável inexistente"):
            parse_responsaveis_entries([{"area_id": 99999, "label": "X"}])


def test_parse_resolve_sigla_viva_e_outras(app):
    with app.app_context():
        area = _create_area("SES")
        entries = parse_responsaveis_entries(
            [{"area_id": area.id, "label": "ignorada"}, {"area_id": None, "label": "x"}]
        )
        assert entries == [
            {"area_id": area.id, "label": "SES"},
            {"area_id": None, "label": OUTRAS_LABEL},
        ]


def test_parse_deduplica_areas_e_outras(app):
    with app.app_context():
        area = _create_area("VPD")
        entries = parse_responsaveis_entries(
            [
                {"area_id": area.id},
                {"area_id": area.id},
                {"area_id": None},
                {"area_id": None},
            ]
        )
        assert entries == [
            {"area_id": area.id, "label": "VPD"},
            {"area_id": None, "label": OUTRAS_LABEL},
        ]


# ── replace_etapa_responsaveis ────────────────────────────────────────────────


def test_replace_substitui_linhas_e_reescreve_mirror(app):
    with app.app_context():
        area_a = _create_area("SEA")
        area_b = _create_area("SEB")
        etapa = _create_etapa()

        replace_etapa_responsaveis(etapa, [{"area_id": area_a.id}])
        db.session.commit()
        assert [r.area_id for r in etapa.responsaveis] == [area_a.id]
        assert etapa.responsavel == "SEA"

        replace_etapa_responsaveis(
            etapa, [{"area_id": area_b.id}, {"area_id": None, "label": "Outras"}]
        )
        db.session.commit()
        assert [(r.area_id, r.label, r.ordem) for r in etapa.responsaveis] == [
            (area_b.id, "SEB", 0),
            (None, OUTRAS_LABEL, 1),
        ]
        assert etapa.responsavel == "SEB, Outras"
        assert EtapaResponsavel.query.filter_by(etapa_id=etapa.id).count() == 2


def test_replace_edicao_mantem_area_e_troca_outra_sem_erro(app):
    # Regressão: editar uma etapa que já tinha responsáveis reaproveitando uma
    # área estourava UNIQUE(etapa_id, area_id) porque o SQLAlchemy inseria antes
    # de deletar. O merge/reuse deve emitir UPDATE para a área mantida.
    with app.app_context():
        area_a = _create_area("SEA")
        area_b = _create_area("SEB")
        area_c = _create_area("SEC")
        etapa = _create_etapa()

        replace_etapa_responsaveis(
            etapa, [{"area_id": area_a.id}, {"area_id": area_b.id}]
        )
        db.session.commit()

        replace_etapa_responsaveis(
            etapa, [{"area_id": area_a.id}, {"area_id": area_c.id}]
        )
        db.session.commit()  # antes: IntegrityError ao re-selecionar area_a

        assert [(r.area_id, r.ordem) for r in etapa.responsaveis] == [
            (area_a.id, 0),
            (area_c.id, 1),
        ]
        assert EtapaResponsavel.query.filter_by(etapa_id=etapa.id).count() == 2


def test_replace_reusa_linha_existente_preservando_id(app):
    with app.app_context():
        area_a = _create_area("SEA")
        etapa = _create_etapa()

        replace_etapa_responsaveis(etapa, [{"area_id": area_a.id}])
        db.session.commit()
        id_original = etapa.responsaveis[0].id

        replace_etapa_responsaveis(etapa, [{"area_id": area_a.id}])
        db.session.commit()
        assert etapa.responsaveis[0].id == id_original


def test_replace_trunca_mirror_em_100_chars(app):
    with app.app_context():
        etapa = _create_etapa()
        areas = [_create_area(f"SIGLA-LONGA-{i:02d}") for i in range(10)]

        replace_etapa_responsaveis(etapa, [{"area_id": a.id} for a in areas])
        db.session.commit()
        assert len(etapa.responsaveis) == 10
        assert len(etapa.responsavel) == 100
        assert etapa.responsavel.startswith("SIGLA-LONGA-00")


def test_replace_propaga_erro_de_parse(app):
    with app.app_context():
        etapa = _create_etapa()
        with pytest.raises(ValueError, match="Pelo menos uma área responsável"):
            replace_etapa_responsaveis(etapa, [])
        assert etapa.responsaveis == []


# ── split_responsavel_legado ─────────────────────────────────────────────────


def test_split_legado_quebra_string_concatenada():
    assert split_responsavel_legado("SUBEXE, COODADOS, COOACES") == [
        "SUBEXE",
        "COODADOS",
        "COOACES",
    ]


def test_split_legado_aceita_separadores_variados_e_normaliza_espacos():
    assert split_responsavel_legado("SUBEXE ;COODADOS/ COOACES\nSUPIM  DOIS") == [
        "SUBEXE",
        "COODADOS",
        "COOACES",
        "SUPIM DOIS",
    ]


def test_split_legado_dedupe_case_insensitive_e_ignora_vazios():
    assert split_responsavel_legado("SEA, , sea,SEA ") == ["SEA"]
    assert split_responsavel_legado("") == []
    assert split_responsavel_legado(None) == []
