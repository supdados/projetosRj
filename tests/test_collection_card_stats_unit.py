"""Números da capa do card de coleção: etapas por situação e áreas.

Cobre ``collection_rollups`` (faixas concluída / em andamento / atrasada) e
``services.collection_areas.areas_por_colecao`` (pílula "N áreas"), mais o
campo ``areas`` de ``serialize_colecao_card``.
"""

from __future__ import annotations

import datetime

import pytest

from models import (
    Etapa,
    OrgaoUnidade,
    Project,
    ProjectCollection,
    ProjectCollectionItem,
    User,
    UserOrgao,
    db,
)
from routes.api.collection_serializers import serialize_colecao_card
from services.atraso import hoje_utc
from services.collection_areas import areas_por_colecao
from services.orgao_tree import rebuild_orgao_closure
from services.project_collections import collection_rollups


def _add_orgao(sigla: str) -> int:
    orgao = OrgaoUnidade(
        sigla=sigla, nome=sigla, tipo="Secretaria", ordem=0, ativo=True
    )
    db.session.add(orgao)
    db.session.flush()
    return orgao.id


def _add_user(
    username: str, *, orgao_id: int | None = None, admin: bool = False
) -> User:
    user = User(
        username=username, name=username.upper(), password_hash="x", is_admin=admin
    )
    db.session.add(user)
    db.session.flush()
    if orgao_id is not None:
        db.session.add(UserOrgao(user_id=user.id, orgao_id=orgao_id, papel="gestor"))
        db.session.flush()
    return user


def _add_project(titulo: str, orgao_id: int | None) -> int:
    projeto = Project(titulo=titulo, orgao_id=orgao_id, status="Vigente")
    db.session.add(projeto)
    db.session.flush()
    return projeto.id


def _dias(offset: int) -> datetime.date:
    # Mesmo relógio do critério de atraso (UTC), para a fronteira não oscilar.
    return hoje_utc() + datetime.timedelta(days=offset)


def _add_etapa(
    project_id: int,
    *,
    inicio: int,
    fim: int | None,
    done: bool = False,
    entry_type: str = "manual",
) -> None:
    db.session.add(
        Etapa(
            descricao="Etapa",
            data_inicio=_dias(inicio),
            data_fim=None if fim is None else _dias(fim),
            project_id=project_id,
            iniciada=done,
            done=done,
            ordem=0,
            entry_type=entry_type,
        )
    )
    db.session.flush()


def _add_colecao(owner_id: int, nome: str, project_ids: list[int]) -> ProjectCollection:
    colecao = ProjectCollection(owner_user_id=owner_id, nome=nome)
    db.session.add(colecao)
    db.session.flush()
    for ordem, project_id in enumerate(project_ids):
        db.session.add(
            ProjectCollectionItem(
                collection_id=colecao.id, project_id=project_id, ordem=ordem
            )
        )
    db.session.flush()
    return colecao


@pytest.fixture
def areas(app):
    """Dono lotado na ALFA; BETA e GAMA só o admin enxerga."""
    with app.app_context():
        alfa = _add_orgao("ALFA")
        beta = _add_orgao("BETA")
        gama = _add_orgao("GAMA")
        rebuild_orgao_closure()
        dono = _add_user("dono_capa", orgao_id=alfa)
        admin = _add_user("admin_capa", admin=True)
        db.session.commit()
        yield {"alfa": alfa, "beta": beta, "gama": gama, "dono": dono, "admin": admin}


def test_rollup_separa_etapas_por_situacao(app, areas):
    with app.test_request_context("/"):
        projeto = _add_project("Capa", areas["alfa"])
        _add_etapa(projeto, inicio=-30, fim=-20, done=True)  # concluída
        _add_etapa(projeto, inicio=-5, fim=5)  # em andamento
        _add_etapa(projeto, inicio=-5, fim=None)  # em andamento, sem fim
        _add_etapa(projeto, inicio=0, fim=0)  # fronteira: fim hoje não atrasa
        _add_etapa(projeto, inicio=-20, fim=-1)  # atrasada
        _add_etapa(projeto, inicio=3, fim=9)  # não iniciada
        _add_etapa(projeto, inicio=-5, fim=5, entry_type="google_meeting")  # fora
        colecao = _add_colecao(areas["dono"].id, "Situação", [projeto])
        db.session.commit()

        rollup = collection_rollups([colecao.id], areas["dono"])[colecao.id]

    assert rollup["etapas_total"] == 6
    assert rollup["etapas_concluidas"] == 1
    assert rollup["etapas_em_andamento"] == 3
    assert rollup["etapas_atrasadas"] == 1
    # A não iniciada é o resto: nenhuma faixa conta a mesma etapa duas vezes.
    soma = (
        rollup["etapas_concluidas"]
        + rollup["etapas_em_andamento"]
        + rollup["etapas_atrasadas"]
    )
    assert rollup["etapas_total"] - soma == 1


def test_etapa_concluida_vencida_conta_so_como_concluida(app, areas):
    with app.test_request_context("/"):
        projeto = _add_project("Antiga", areas["alfa"])
        _add_etapa(projeto, inicio=-30, fim=-10, done=True)
        colecao = _add_colecao(areas["dono"].id, "Antiga", [projeto])
        db.session.commit()

        rollup = collection_rollups([colecao.id], areas["dono"])[colecao.id]

    assert (rollup["etapas_concluidas"], rollup["etapas_atrasadas"]) == (1, 0)
    assert rollup["etapas_em_andamento"] == 0


def test_areas_ordenam_por_projetos_e_sigla_com_sem_area_no_fim(app, areas):
    with app.test_request_context("/"):
        ids = [
            _add_project("G1", areas["gama"]),
            _add_project("B1", areas["beta"]),
            _add_project("B2", areas["beta"]),
            _add_project("A1", areas["alfa"]),
            _add_project("Solto", None),
        ]
        colecao = _add_colecao(areas["admin"].id, "Mista", ids)
        db.session.commit()

        resultado = areas_por_colecao([colecao.id], areas["admin"])[colecao.id]

    assert resultado == [
        {"sigla": "BETA", "projetos": 2},
        {"sigla": "ALFA", "projetos": 1},
        {"sigla": "GAMA", "projetos": 1},
        {"sigla": None, "projetos": 1},
    ]


def test_areas_contam_so_projetos_visiveis_ao_viewer(app, areas):
    with app.test_request_context("/"):
        ids = [
            _add_project("Meu", areas["alfa"]),
            _add_project("Alheio", areas["beta"]),
        ]
        colecao = _add_colecao(areas["dono"].id, "Visível", ids)
        vazia = _add_colecao(areas["dono"].id, "Vazia", [])
        db.session.commit()

        resultado = areas_por_colecao([colecao.id, vazia.id], areas["dono"])

    assert resultado[colecao.id] == [{"sigla": "ALFA", "projetos": 1}]
    assert resultado[vazia.id] == []


def test_areas_sem_ids_devolve_dicionario_vazio(app, areas):
    with app.test_request_context("/"):
        assert areas_por_colecao([], areas["dono"]) == {}


def test_card_serializa_areas_e_faixas_de_etapa(app, areas):
    with app.test_request_context("/"):
        colecao = _add_colecao(areas["dono"].id, "Card", [])
        db.session.commit()
        rollup = {
            "projetos": 2,
            "etapas_total": 5,
            "etapas_concluidas": 1,
            "etapas_em_andamento": 2,
            "etapas_atrasadas": 1,
            "progresso_pct": 20,
        }

        card = serialize_colecao_card(
            colecao,
            rollup,
            papel="dono",
            destinatarios=[],
            areas=[{"sigla": "ALFA", "projetos": 2}],
        )

    assert card["areas"] == [{"sigla": "ALFA", "projetos": 2}]
    assert (card["etapas_em_andamento"], card["etapas_atrasadas"]) == (2, 1)


def test_card_sem_areas_informadas_sai_com_lista_vazia(app, areas):
    with app.test_request_context("/"):
        colecao = _add_colecao(areas["dono"].id, "Sem áreas", [])
        db.session.commit()
        card = serialize_colecao_card(colecao, {}, papel="dono", destinatarios=[])

    assert card["areas"] == []
    assert card["etapas_em_andamento"] == card["etapas_atrasadas"] == 0
