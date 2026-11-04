"""Ciclo do convite de coleção (services/collection_shares + collection_invites).

pendente → aceito | recusado; depois do aceite (ou legado), "sair"; o dono
pode reenviar para quem recusou/saiu e revogar. Cobre também as regressões de
segurança da spec: reuso de rowid (share novo não herda resposta) e corrida
aceitar × revogar (404 limpo, nunca 500). Inclusão, teto, poda e leitores do
card ficam em ``tests/test_collection_curation_unit.py``.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from models import (
    PAPEL_SHARE_EDITOR,
    PAPEL_SHARE_VIEWER,
    STATUS_RESPOSTA_ACEITO,
    STATUS_RESPOSTA_RECUSADO,
    STATUS_RESPOSTA_SAIU,
    ProjectCollectionShare,
    ProjectCollectionShareResposta,
    db,
)
from services import collection_invites
from services.collection_errors import (
    ColecaoInvalida,
    ColecaoSemPermissao,
    ConviteIndisponivel,
)
from services.collection_shares import (
    aceitar_convite,
    convite_pendente,
    convites_pendentes_de,
    recusar_convite,
    reenviar_convite,
    revogar_share,
    sair_da_colecao,
)
from services.project_collections import (
    apagar_colecao,
    listar_colecoes,
    papel_do_usuario,
    projeto_visivel_para,
)
from tests._collection_share_helpers import (
    colecao_do_dono,
    compartilhar,
    eventos_de,
    semear_cenario_convite,
)


@pytest.fixture
def cenario(app):
    with app.app_context():
        yield semear_cenario_convite()


def _respostas(share_id: int) -> dict[int, str]:
    linhas = ProjectCollectionShareResposta.query.filter_by(share_id=share_id).all()
    return {linha.user_id: linha.status for linha in linhas}


def _ids_no_indice(user) -> list[int]:
    return [colecao.id for colecao, _ in listar_colecoes(user.id)[1:]]


# ── pendente ──────────────────────────────────────────────────────────────────


def test_share_novo_nasce_convite_pendente_sem_acesso(app, cenario):
    with app.test_request_context("/"):
        colecao = colecao_do_dono(cenario)
        share = compartilhar(
            colecao, cenario, PAPEL_SHARE_EDITOR, user_id=cenario.convidado.id
        )
        assert share.exige_aceite is True
        assert papel_do_usuario(colecao, cenario.convidado) is None
        assert projeto_visivel_para(cenario.convidado, cenario.do_dono_id) is False
        assert _ids_no_indice(cenario.convidado) == []
        (convite,) = convites_pendentes_de(cenario.convidado)
        assert (convite.colecao.id, convite.papel) == (colecao.id, PAPEL_SHARE_EDITOR)
        assert convite.colecao.owner.id == cenario.dono.id


def test_dono_nao_tem_convite_do_proprio_share_de_orgao(app, cenario):
    with app.test_request_context("/"):
        colecao = colecao_do_dono(cenario)
        compartilhar(colecao, cenario, orgao_id=cenario.area_id)
        assert convite_pendente(colecao.id, cenario.dono) is None
        assert convite_pendente(colecao.id, cenario.colega) is not None
        with pytest.raises(ConviteIndisponivel):
            aceitar_convite(colecao.id, cenario.dono)


# ── aceitar ───────────────────────────────────────────────────────────────────


def test_aceitar_concede_acesso_e_sai_dos_pendentes(app, cenario):
    with app.test_request_context("/"):
        colecao = colecao_do_dono(cenario)
        share = compartilhar(colecao, cenario, user_id=cenario.convidado.id)
        assert aceitar_convite(colecao.id, cenario.convidado).id == colecao.id
        db.session.commit()
        assert _respostas(share.id) == {cenario.convidado.id: STATUS_RESPOSTA_ACEITO}
        assert papel_do_usuario(colecao, cenario.convidado) == PAPEL_SHARE_VIEWER
        assert projeto_visivel_para(cenario.convidado, cenario.do_dono_id) is True
        assert _ids_no_indice(cenario.convidado) == [colecao.id]
        assert convites_pendentes_de(cenario.convidado) == []
        assert eventos_de(colecao)[-1] == "colecao_convite_aceito"


def test_aceitar_resolve_share_pessoal_e_de_orgao_juntos(app, cenario):
    """Pessoa + órgão de lotação: um aceite responde os dois; vence o editor."""
    with app.test_request_context("/"):
        colecao = colecao_do_dono(cenario)
        pessoal = compartilhar(colecao, cenario, user_id=cenario.convidado.id)
        do_orgao = compartilhar(
            colecao, cenario, PAPEL_SHARE_EDITOR, orgao_id=cenario.ext_id
        )
        assert convite_pendente(colecao.id, cenario.convidado).papel == (
            PAPEL_SHARE_EDITOR
        )
        aceitar_convite(colecao.id, cenario.convidado)
        db.session.commit()
        for share in (pessoal, do_orgao):
            assert _respostas(share.id)[cenario.convidado.id] == STATUS_RESPOSTA_ACEITO
        assert papel_do_usuario(colecao, cenario.convidado) == PAPEL_SHARE_EDITOR


def test_aceite_de_share_de_orgao_e_por_pessoa(app, cenario):
    with app.test_request_context("/"):
        colecao = colecao_do_dono(cenario)
        compartilhar(colecao, cenario, orgao_id=cenario.orgx_id)
        aceitar_convite(colecao.id, cenario.membro_a)
        db.session.commit()
        assert projeto_visivel_para(cenario.membro_a, cenario.do_dono_id) is True
        assert projeto_visivel_para(cenario.membro_b, cenario.do_dono_id) is False
        assert convite_pendente(colecao.id, cenario.membro_b) is not None


@pytest.mark.parametrize("alvo", ["inexistente", "sem_convite", "ja_aceito"])
def test_aceitar_sem_convite_disponivel_e_404(app, cenario, alvo):
    """Anti-enumeração: os três casos levantam o MESMO erro (404 na rota)."""
    with app.test_request_context("/"):
        colecao = colecao_do_dono(cenario)
        compartilhar(colecao, cenario, user_id=cenario.convidado.id)
        colecao_id = 999999 if alvo == "inexistente" else colecao.id
        ator = cenario.membro_a if alvo == "sem_convite" else cenario.convidado
        if alvo == "ja_aceito":
            aceitar_convite(colecao.id, cenario.convidado)
            db.session.commit()
        with pytest.raises(ConviteIndisponivel):
            aceitar_convite(colecao_id, ator)


# ── recusar ───────────────────────────────────────────────────────────────────


def test_recusar_nao_concede_e_nao_pode_mais_aceitar(app, cenario):
    with app.test_request_context("/"):
        colecao = colecao_do_dono(cenario)
        share = compartilhar(colecao, cenario, user_id=cenario.convidado.id)
        recusar_convite(colecao.id, cenario.convidado)
        db.session.commit()
        assert _respostas(share.id) == {cenario.convidado.id: STATUS_RESPOSTA_RECUSADO}
        assert papel_do_usuario(colecao, cenario.convidado) is None
        assert convites_pendentes_de(cenario.convidado) == []
        with pytest.raises(ConviteIndisponivel):
            aceitar_convite(colecao.id, cenario.convidado)
        assert eventos_de(colecao)[-1] == "colecao_convite_recusado"


# ── sair ──────────────────────────────────────────────────────────────────────


def test_sair_tira_o_acesso_e_marca_todos_os_shares(app, cenario):
    with app.test_request_context("/"):
        colecao = colecao_do_dono(cenario)
        pessoal = compartilhar(colecao, cenario, user_id=cenario.convidado.id)
        aceitar_convite(colecao.id, cenario.convidado)
        do_orgao = compartilhar(colecao, cenario, orgao_id=cenario.ext_id)
        assert sair_da_colecao(colecao.id, cenario.convidado) == 0
        db.session.commit()
        for share in (pessoal, do_orgao):
            assert _respostas(share.id)[cenario.convidado.id] == STATUS_RESPOSTA_SAIU
        assert papel_do_usuario(colecao, cenario.convidado) is None
        assert convite_pendente(colecao.id, cenario.convidado) is None
        assert eventos_de(colecao)[-1] == "colecao_participante_saiu"


def test_sair_de_share_legado_tambem_tira_o_acesso(app, cenario):
    with app.test_request_context("/"):
        colecao = colecao_do_dono(cenario)
        db.session.add(
            ProjectCollectionShare(
                collection_id=colecao.id,
                user_id=cenario.convidado.id,
                papel=PAPEL_SHARE_VIEWER,
                created_by_user_id=cenario.dono.id,
                exige_aceite=False,
            )
        )
        db.session.commit()
        assert papel_do_usuario(colecao, cenario.convidado) == PAPEL_SHARE_VIEWER
        sair_da_colecao(colecao.id, cenario.convidado)
        db.session.commit()
        assert papel_do_usuario(colecao, cenario.convidado) is None


@pytest.mark.parametrize("quem", ["pendente", "dono", "estranho"])
def test_sair_sem_participacao_valida_e_404(app, cenario, quem):
    with app.test_request_context("/"):
        colecao = colecao_do_dono(cenario)
        compartilhar(colecao, cenario, user_id=cenario.convidado.id)
        ator = {
            "pendente": cenario.convidado,
            "dono": cenario.dono,
            "estranho": cenario.membro_a,
        }[quem]
        with pytest.raises(ConviteIndisponivel):
            sair_da_colecao(colecao.id, ator)


# ── reenviar ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("negativa", [recusar_convite, "sair"])
def test_reenviar_reconvida_quem_recusou_ou_saiu(app, cenario, negativa):
    with app.test_request_context("/"):
        colecao = colecao_do_dono(cenario)
        share = compartilhar(colecao, cenario, user_id=cenario.convidado.id)
        if negativa == "sair":
            aceitar_convite(colecao.id, cenario.convidado)
            sair_da_colecao(colecao.id, cenario.convidado)
        else:
            negativa(colecao.id, cenario.convidado)
        assert reenviar_convite(colecao, share.id, ator=cenario.dono) == 1
        db.session.commit()
        assert _respostas(share.id) == {}
        assert convite_pendente(colecao.id, cenario.convidado) is not None
        assert eventos_de(colecao)[-1] == "colecao_convite_reenviado"


def test_reenviar_share_legado_de_orgao_preserva_quem_tinha_acesso(app, cenario):
    """Legado vira convite: quem via continua vendo; quem saiu volta pendente
    (apagar o "saiu" de um legado sem isso devolveria acesso sem consentimento)."""
    with app.test_request_context("/"):
        colecao = colecao_do_dono(cenario)
        share = ProjectCollectionShare(
            collection_id=colecao.id,
            orgao_id=cenario.orgx_id,
            papel=PAPEL_SHARE_VIEWER,
            created_by_user_id=cenario.dono.id,
            exige_aceite=False,
        )
        db.session.add(share)
        db.session.commit()
        sair_da_colecao(colecao.id, cenario.membro_a)
        assert reenviar_convite(colecao, share.id, ator=cenario.dono) == 1
        db.session.commit()
        assert share.exige_aceite is True
        assert _respostas(share.id) == {cenario.membro_b.id: STATUS_RESPOSTA_ACEITO}
        assert papel_do_usuario(colecao, cenario.membro_b) == PAPEL_SHARE_VIEWER
        assert papel_do_usuario(colecao, cenario.membro_a) is None
        assert convite_pendente(colecao.id, cenario.membro_a) is not None


def test_reenviar_exige_dono_share_da_colecao_e_alguma_negativa(app, cenario):
    with app.test_request_context("/"):
        colecao = colecao_do_dono(cenario)
        outra = colecao_do_dono(cenario, "Outra")
        share = compartilhar(colecao, cenario, user_id=cenario.convidado.id)
        with pytest.raises(ColecaoInvalida, match="nada a reenviar"):
            reenviar_convite(colecao, share.id, ator=cenario.dono)
        with pytest.raises(ConviteIndisponivel):
            reenviar_convite(outra, share.id, ator=cenario.dono)
        with pytest.raises(ColecaoSemPermissao):
            reenviar_convite(colecao, share.id, ator=cenario.convidado)


# ── revogar / apagar e reuso de rowid ─────────────────────────────────────────


def test_revogar_apaga_respostas_e_corta_o_acesso(app, cenario):
    with app.test_request_context("/"):
        colecao = colecao_do_dono(cenario)
        share = compartilhar(colecao, cenario, user_id=cenario.convidado.id)
        aceitar_convite(colecao.id, cenario.convidado)
        db.session.commit()
        assert revogar_share(colecao, share.id, ator=cenario.dono) is True
        db.session.commit()
        assert ProjectCollectionShareResposta.query.count() == 0
        assert projeto_visivel_para(cenario.convidado, cenario.do_dono_id) is False


def test_apagar_colecao_apaga_respostas(app, cenario):
    with app.test_request_context("/"):
        colecao = colecao_do_dono(cenario)
        compartilhar(colecao, cenario, user_id=cenario.convidado.id)
        aceitar_convite(colecao.id, cenario.convidado)
        apagar_colecao(colecao)
        db.session.commit()
        assert ProjectCollectionShareResposta.query.count() == 0
        assert ProjectCollectionShare.query.count() == 0


def test_share_novo_nao_herda_resposta_de_share_apagado_com_mesmo_id(app, cenario):
    """Regressão (rowid SQLite): resposta "aceito" órfã — share apagado por fora
    do service, sem CASCADE — não pode ser herdada por um share novo."""
    with app.test_request_context("/"):
        colecao = colecao_do_dono(cenario)
        antigo = compartilhar(colecao, cenario, user_id=cenario.convidado.id)
        aceitar_convite(colecao.id, cenario.convidado)
        db.session.commit()
        antigo_id = antigo.id
        db.session.expunge(antigo)
        db.session.execute(
            text("DELETE FROM project_collection_share WHERE id = :id"),
            {"id": antigo_id},
        )
        db.session.commit()
        assert ProjectCollectionShareResposta.query.count() == 1  # órfã de fato
        novo = compartilhar(colecao, cenario, user_id=cenario.convidado.id)
        assert novo.id == antigo_id  # reproduz o reuso, sem AUTOINCREMENT
        assert ProjectCollectionShareResposta.query.count() == 0
        assert papel_do_usuario(colecao, cenario.convidado) is None
        assert convite_pendente(colecao.id, cenario.convidado) is not None


# ── corrida ───────────────────────────────────────────────────────────────────


def test_corrida_aceitar_x_revogar_vira_404_e_nao_grava(app, cenario, monkeypatch):
    """O aceite leu o share pendente; o dono revogou antes da escrita."""
    with app.test_request_context("/"):
        colecao = colecao_do_dono(cenario)
        share = compartilhar(colecao, cenario, user_id=cenario.convidado.id)
        lidos = collection_invites.shares_pendentes_do_usuario(
            cenario.convidado, [colecao.id]
        )
        revogar_share(colecao, share.id, ator=cenario.dono)
        db.session.commit()
        monkeypatch.setattr(
            collection_invites, "shares_pendentes_do_usuario", lambda *_a: lidos
        )
        with pytest.raises(ConviteIndisponivel):
            aceitar_convite(colecao.id, cenario.convidado)
        db.session.rollback()
        assert ProjectCollectionShareResposta.query.count() == 0


def test_corrida_de_dois_aceites_vira_404(app, cenario, monkeypatch):
    """Duplo clique: o segundo aceite esbarra na UNIQUE(share_id, user_id)."""
    with app.test_request_context("/"):
        colecao = colecao_do_dono(cenario)
        compartilhar(colecao, cenario, user_id=cenario.convidado.id)
        lidos = collection_invites.shares_pendentes_do_usuario(
            cenario.convidado, [colecao.id]
        )
        aceitar_convite(colecao.id, cenario.convidado)
        db.session.commit()
        monkeypatch.setattr(
            collection_invites, "shares_pendentes_do_usuario", lambda *_a: lidos
        )
        with pytest.raises(ConviteIndisponivel):
            aceitar_convite(colecao.id, cenario.convidado)
        db.session.rollback()
        assert ProjectCollectionShareResposta.query.count() == 1
