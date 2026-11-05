"""Curadoria em coleção compartilhada: inclusão, teto, remoção, poda e leitores.

Decisões 2 e 3 da spec: o editor só inclui o que vê pela ÁREA; cada item grava
quem incluiu e o teto (rank de área do incluidor, até editor); o rank via
coleção é ``min(papel do share, teto)``; ninguém deriva do item que ele mesmo
incluiu e o dono LÊ o que outros incluíram. A poda tira os itens de quem perde
o papel editor (revogar, sair, rebaixar). Também cobre os leitores novos:
status por pessoa, destinatários do card, filtro ``?colecao=``, sino e
``access_via``.
"""

from __future__ import annotations

import pytest
from flask import g

from models import (
    PAPEL_SHARE_EDITOR,
    PAPEL_SHARE_VIEWER,
    Project,
    ProjectCollectionItem,
    ProjectCollectionShareResposta,
    ProjectMember,
    UserNotification,
    UserOrgao,
    db,
)
from routes.projects.list_filters import (
    ProjectsListFilters,
    apply_projects_list_filters,
)
from services.authorization import (
    COLLECTION_RANK_CACHE_ATTR,
    PAPEL_EDITOR,
    PAPEL_LEITOR,
    PAPEL_RANK,
    effective_project_rank,
    get_collection_project_rank_map,
)
from services.collection_errors import (
    ColecaoSemPermissao,
    ProjetoForaDoEscopo,
    ProjetoSoPorConvite,
)
from services.collection_participation import colecoes_visiveis_ou_convidadas
from services.collection_shares import (
    MOTIVO_PODA_REBAIXADO,
    MOTIVO_PODA_REVOGADO,
    aceitar_convite,
    compartilhar_colecao,
    itens_incluidos_por,
    itens_que_saem_por_share,
    listar_shares,
    recusar_convite,
    revogar_share,
    sair_da_colecao,
    status_dos_shares,
)
from services.project_collections import (
    adicionar_projeto,
    colecao_project_rows,
    criar_colecao,
    projeto_visivel_para,
    remover_projeto,
)
from services.project_membership import ACCESS_VIA_COLECAO, project_access_via
from tests._collection_share_helpers import (
    colecao_do_dono,
    compartilhar,
    detalhes_de_poda,
    semear_cenario_convite,
)
from time_utils import utc_now

LEITOR = PAPEL_RANK[PAPEL_LEITOR]
EDITOR = PAPEL_RANK[PAPEL_EDITOR]


@pytest.fixture
def cenario(app):
    with app.app_context():
        yield semear_cenario_convite()


def _com_editor(cenario, *, incluir_externo: bool = True):
    """Coleção do dono com o editor (EXT) aceito e, opcionalmente, ``do_ext``."""
    colecao = colecao_do_dono(cenario)
    share = compartilhar(
        colecao, cenario, PAPEL_SHARE_EDITOR, user_id=cenario.editor.id
    )
    aceitar_convite(colecao.id, cenario.editor)
    if incluir_externo:
        adicionar_projeto(colecao, cenario.do_ext_id, ator=cenario.editor)
    db.session.commit()
    return colecao, share


def _item(colecao, project_id: int) -> ProjectCollectionItem | None:
    return ProjectCollectionItem.query.filter_by(
        collection_id=colecao.id, project_id=project_id
    ).first()


def _projeto(project_id: int) -> Project:
    return db.session.get(Project, project_id)


# ── Inclusão (decisão 3) e teto (decisão 2) ───────────────────────────────────


def test_editor_inclui_projeto_da_area_e_grava_autoria_e_teto(app, cenario):
    with app.test_request_context("/"):
        colecao, _ = _com_editor(cenario)
        item = _item(colecao, cenario.do_ext_id)
        # Gestor de área (30) grava o teto limitado a editor (20).
        assert (item.added_by_user_id, item.rank_teto) == (cenario.editor.id, EDITOR)


def test_editor_nao_inclui_projeto_visto_so_por_convite(app, cenario):
    with app.test_request_context("/"):
        colecao, _ = _com_editor(cenario, incluir_externo=False)
        assert projeto_visivel_para(cenario.editor, cenario.so_convite_id) is True
        with pytest.raises(ProjetoSoPorConvite, match="só é visível para você"):
            adicionar_projeto(colecao, cenario.so_convite_id, ator=cenario.editor)


def test_editor_nao_inclui_projeto_que_nao_ve(app, cenario):
    with app.test_request_context("/"):
        colecao, _ = _com_editor(cenario, incluir_externo=False)
        with pytest.raises(ProjetoForaDoEscopo):
            adicionar_projeto(colecao, cenario.do_dono_id + 999, ator=cenario.editor)


def test_dono_inclui_projeto_so_de_convite_com_teto_zero(app, cenario):
    """Regra do dono preservada (visibilidade própria), mas o item não expõe nada."""
    with app.test_request_context("/"):
        db.session.add(
            ProjectMember(
                project_id=cenario.so_convite_id,
                user_id=cenario.dono.id,
                granted_by_id=cenario.editor.id,
                papel="leitor",
            )
        )
        colecao = colecao_do_dono(cenario)
        compartilhar(colecao, cenario, user_id=cenario.convidado.id)
        aceitar_convite(colecao.id, cenario.convidado)
        adicionar_projeto(colecao, cenario.so_convite_id, ator=cenario.dono)
        db.session.commit()
        assert _item(colecao, cenario.so_convite_id).rank_teto == 0
        assert projeto_visivel_para(cenario.convidado, cenario.so_convite_id) is False
        assert projeto_visivel_para(cenario.convidado, cenario.do_dono_id) is True


def test_criar_colecao_grava_autoria_e_teto_nos_itens(app, cenario):
    with app.test_request_context("/"):
        colecao = colecao_do_dono(cenario)
        item = _item(colecao, cenario.do_dono_id)
        assert (item.added_by_user_id, item.rank_teto) == (cenario.dono.id, EDITOR)


def test_criar_colecao_invalida_o_rank_map_do_request(app, cenario):
    """Toda mutação de item/share descarta o cache — inclusive a criação."""
    with app.test_request_context("/"):
        get_collection_project_rank_map(cenario.dono)
        assert COLLECTION_RANK_CACHE_ATTR in g
        criar_colecao(
            cenario.dono, "Nova", None, "camadas", "primary", [cenario.do_dono_id]
        )
        assert COLLECTION_RANK_CACHE_ATTR not in g


def test_reinclusao_que_sobe_o_teto_invalida_o_rank_map_do_request(app, cenario):
    """Item de teto 0 (incluído antes de o dono ganhar a área): re-incluir sobe
    o teto e descarta o cache — o MESMO request já enxerga o acesso novo."""
    with app.test_request_context("/"):
        outra = _projeto(cenario.so_convite_id).orgao_id
        db.session.add(UserOrgao(user_id=cenario.dono.id, orgao_id=outra))
        colecao = colecao_do_dono(cenario)
        db.session.add(
            ProjectCollectionItem(
                collection_id=colecao.id,
                project_id=cenario.so_convite_id,
                added_by_user_id=cenario.dono.id,
                rank_teto=0,
            )
        )
        db.session.commit()
        get_collection_project_rank_map(cenario.dono)
        assert (
            adicionar_projeto(colecao, cenario.so_convite_id, ator=cenario.dono)
            is False
        )
        assert _item(colecao, cenario.so_convite_id).rank_teto == EDITOR
        assert COLLECTION_RANK_CACHE_ATTR not in g


def test_teto_dono_leitor_share_editor_da_so_leitura(app, cenario):
    """Dono que só LÊ não distribui edição: share editor vira leitor no item."""
    with app.test_request_context("/"):
        colecao = criar_colecao(
            cenario.colega, "Leitora", None, "camadas", "primary", [cenario.do_dono_id]
        )
        compartilhar_colecao(
            colecao,
            ator=cenario.colega,
            user_id=cenario.convidado.id,
            papel=PAPEL_SHARE_EDITOR,
        )
        aceitar_convite(colecao.id, cenario.convidado)
        db.session.commit()
        projeto = _projeto(cenario.do_dono_id)
        assert _item(colecao, cenario.do_dono_id).rank_teto == LEITOR
        assert effective_project_rank(cenario.convidado, projeto) == LEITOR


def test_share_editor_em_item_de_dono_gestor_da_editor(app, cenario):
    with app.test_request_context("/"):
        colecao = colecao_do_dono(cenario)
        compartilhar(colecao, cenario, PAPEL_SHARE_EDITOR, user_id=cenario.convidado.id)
        aceitar_convite(colecao.id, cenario.convidado)
        db.session.commit()
        projeto = _projeto(cenario.do_dono_id)
        assert effective_project_rank(cenario.convidado, projeto) == EDITOR


# ── Autoria: dono lê o alheio, ninguém deriva do próprio, remoção ─────────────


def test_dono_le_o_que_editor_de_outra_area_incluiu(app, cenario):
    with app.test_request_context("/"):
        colecao, _ = _com_editor(cenario)
        assert projeto_visivel_para(cenario.dono, cenario.do_ext_id) is True
        assert effective_project_rank(cenario.dono, _projeto(cenario.do_ext_id)) == (
            LEITOR
        )
        linhas = {
            linha["id"]: linha for linha in colecao_project_rows(colecao, cenario.dono)
        }
        assert linhas[cenario.do_ext_id]["adicionado_por"] == {
            "id": cenario.editor.id,
            "name": cenario.editor.name,
        }
        assert linhas[cenario.do_ext_id]["pode_remover"] is True


def test_editor_nao_deriva_do_item_que_ele_incluiu(app, cenario):
    with app.test_request_context("/"):
        _com_editor(cenario)
        assert cenario.do_ext_id not in get_collection_project_rank_map(cenario.editor)


def test_editor_remove_so_o_que_incluiu(app, cenario):
    with app.test_request_context("/"):
        colecao, _ = _com_editor(cenario)
        linhas = {
            linha["id"]: linha["pode_remover"]
            for linha in colecao_project_rows(colecao, cenario.editor)
        }
        assert linhas == {cenario.do_dono_id: False, cenario.do_ext_id: True}
        with pytest.raises(ColecaoSemPermissao):
            remover_projeto(colecao, cenario.do_dono_id, ator=cenario.editor)
        assert remover_projeto(colecao, cenario.do_ext_id, ator=cenario.editor)


# ── Poda ──────────────────────────────────────────────────────────────────────


def test_revogar_editor_poda_os_itens_dele_auditado(app, cenario):
    with app.test_request_context("/"):
        colecao, share = _com_editor(cenario)
        assert itens_que_saem_por_share(colecao, [share]) == {share.id: 1}
        revogar_share(colecao, share.id, ator=cenario.dono)
        db.session.commit()
        assert _item(colecao, cenario.do_ext_id) is None
        assert _item(colecao, cenario.do_dono_id) is not None
        assert detalhes_de_poda(colecao) == [
            {
                "project_id": cenario.do_ext_id,
                "motivo": MOTIVO_PODA_REVOGADO,
                "incluido_por": cenario.editor.id,
            }
        ]
        assert projeto_visivel_para(cenario.dono, cenario.do_ext_id) is False


def test_rebaixar_editor_para_viewer_poda(app, cenario):
    with app.test_request_context("/"):
        colecao, _ = _com_editor(cenario)
        compartilhar(colecao, cenario, PAPEL_SHARE_VIEWER, user_id=cenario.editor.id)
        assert _item(colecao, cenario.do_ext_id) is None
        assert detalhes_de_poda(colecao)[0]["motivo"] == MOTIVO_PODA_REBAIXADO


def test_sair_poda_os_itens_de_quem_saiu(app, cenario):
    with app.test_request_context("/"):
        colecao, _ = _com_editor(cenario)
        assert itens_incluidos_por(colecao, cenario.editor.id) == 1
        assert sair_da_colecao(colecao.id, cenario.editor) == 1
        db.session.commit()
        assert _item(colecao, cenario.do_ext_id) is None


def test_quem_segue_editor_por_outro_share_nao_e_podado(app, cenario):
    """Pessoa + órgão: revogar um deles não tira o editor (nem os itens)."""
    with app.test_request_context("/"):
        colecao, pessoal = _com_editor(cenario, incluir_externo=False)
        do_orgao = compartilhar(
            colecao, cenario, PAPEL_SHARE_EDITOR, orgao_id=cenario.ext_id
        )
        aceitar_convite(colecao.id, cenario.editor)
        adicionar_projeto(colecao, cenario.do_ext_id, ator=cenario.editor)
        db.session.commit()
        shares = [pessoal, do_orgao]
        assert itens_que_saem_por_share(colecao, shares) == {
            pessoal.id: 0,
            do_orgao.id: 0,
        }
        revogar_share(colecao, pessoal.id, ator=cenario.dono)
        db.session.commit()
        assert _item(colecao, cenario.do_ext_id) is not None
        assert itens_que_saem_por_share(colecao, [do_orgao]) == {do_orgao.id: 1}


def test_upsert_de_papel_nao_reseta_resposta_nem_renotifica(app, cenario):
    with app.test_request_context("/"):
        colecao = colecao_do_dono(cenario)
        share = compartilhar(colecao, cenario, user_id=cenario.convidado.id)
        aceitar_convite(colecao.id, cenario.convidado)
        avisos = UserNotification.query.count()
        compartilhar(colecao, cenario, PAPEL_SHARE_EDITOR, user_id=cenario.convidado.id)
        resposta = ProjectCollectionShareResposta.query.filter_by(
            share_id=share.id
        ).one()
        assert resposta.status == "aceito"
        assert UserNotification.query.count() == avisos


def test_revogar_mesma_area_mantem_area_outra_area_perde(app, cenario):
    with app.test_request_context("/"):
        colecao = colecao_do_dono(cenario)
        shares = [
            compartilhar(colecao, cenario, user_id=pessoa.id)
            for pessoa in (cenario.colega, cenario.convidado)
        ]
        for pessoa in (cenario.colega, cenario.convidado):
            aceitar_convite(colecao.id, pessoa)
        db.session.commit()
        for share in shares:
            revogar_share(colecao, share.id, ator=cenario.dono)
        db.session.commit()
        assert projeto_visivel_para(cenario.colega, cenario.do_dono_id) is True
        assert projeto_visivel_para(cenario.convidado, cenario.do_dono_id) is False


# ── Leitores: status, destinatários, sino, filtro, access_via ─────────────────


def _cenario_de_status(cenario):
    colecao = colecao_do_dono(cenario)
    compartilhar(colecao, cenario, user_id=cenario.convidado.id)
    compartilhar(colecao, cenario, user_id=cenario.colega.id)
    compartilhar(colecao, cenario, orgao_id=cenario.orgx_id)
    aceitar_convite(colecao.id, cenario.convidado)
    aceitar_convite(colecao.id, cenario.membro_a)
    db.session.commit()
    return colecao


def test_status_dos_shares_por_pessoa_e_agregado_do_orgao(app, cenario):
    with app.test_request_context("/"):
        colecao = _cenario_de_status(cenario)
        convidado, colega, orgao = listar_shares(colecao)
        recusar_convite(colecao.id, cenario.colega)
        status = status_dos_shares(colecao, [convidado, colega, orgao])
        assert status[convidado.id]["status"] == "aceito"
        assert status[colega.id]["status"] == "recusado"
        assert status[orgao.id]["status"] is None
        assert status[orgao.id]["resumo"] == {
            "membros": 2,
            "aceitos": 1,
            "pendentes": 1,
            "recusados": 0,
            "sairam": 0,
        }
        assert {item["itens_incluidos"] for item in status.values()} == {0}


def test_sino_mostra_coleção_com_papel_ou_convite_e_esconde_recusada(app, cenario):
    with app.test_request_context("/"):
        colecao = _cenario_de_status(cenario)
        recusar_convite(colecao.id, cenario.colega)
        ids = [colecao.id, 999999]
        assert colecoes_visiveis_ou_convidadas(cenario.dono, ids) == {colecao.id}
        assert colecoes_visiveis_ou_convidadas(cenario.convidado, ids) == {colecao.id}
        assert colecoes_visiveis_ou_convidadas(cenario.membro_b, ids) == {colecao.id}
        assert colecoes_visiveis_ou_convidadas(cenario.colega, ids) == set()


def _ids_filtrados(user, collection_id: int) -> set[int]:
    filtros = ProjectsListFilters(selected_colecao_id=collection_id)
    query = apply_projects_list_filters(Project.query, filtros, user)
    return {projeto.id for projeto in query.all()}


def test_filtro_colecao_vale_para_colecao_recebida_aceita(app, cenario):
    with app.test_request_context("/"):
        colecao = _cenario_de_status(cenario)
        assert _ids_filtrados(cenario.convidado, colecao.id) == {cenario.do_dono_id}
        assert _ids_filtrados(cenario.membro_b, colecao.id) == set()


def test_filtro_colecao_nao_vale_quando_o_dono_foi_removido(app, cenario):
    """O colega vê o projeto pela PRÓPRIA área: só o papel na coleção decide.

    Trava a correlação "dono vivo" do ``colecao_com_papel_criterion`` (no WHERE,
    não no ON do JOIN) — sem ela o share do dono removido voltaria a filtrar.
    """
    with app.test_request_context("/"):
        colecao = colecao_do_dono(cenario)
        compartilhar(colecao, cenario, PAPEL_SHARE_VIEWER, user_id=cenario.colega.id)
        aceitar_convite(colecao.id, cenario.colega)
        db.session.commit()
        assert _ids_filtrados(cenario.colega, colecao.id) == {cenario.do_dono_id}

        cenario.dono.deleted_at = utc_now()
        db.session.commit()

        assert _ids_filtrados(cenario.colega, colecao.id) == set()


def test_access_via_colecao_quando_so_a_colecao_da_acesso(app, cenario):
    with app.test_request_context("/"):
        _cenario_de_status(cenario)
        projeto = _projeto(cenario.do_dono_id)
        assert project_access_via(cenario.convidado, projeto) == ACCESS_VIA_COLECAO
        assert project_access_via(cenario.membro_b, projeto) is None
        assert project_access_via(cenario.colega, projeto) == "area"
