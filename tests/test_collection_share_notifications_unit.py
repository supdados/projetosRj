"""Notificações do convite de coleção compartilhada.

Só a CONCESSÃO de share notifica o destinatário (``colecao_convite`` — o acesso
só vale depois do aceite): upsert de papel e revogação são silenciosos. Share
de pessoa alcança aquele usuário; share de órgão alcança os ATIVOS com vínculo
no órgão EXATO (sem subárvore), sempre sem o ator. Aceite, recusa e saída
avisam o DONO. O antigo ``colecao_compartilhada`` ficou só como histórico.
"""

import pytest

from models import (
    OrgaoUnidade,
    PAPEL_SHARE_EDITOR,
    PAPEL_SHARE_VIEWER,
    ProjectCollection,
    User,
    UserNotification,
    UserOrgao,
    db,
)
from services.collection_shares import (
    aceitar_convite,
    compartilhar_colecao,
    recusar_convite,
    reenviar_convite,
    revogar_share,
    sair_da_colecao,
)
from services.notifications import (
    EVENTO_COLECAO_CONVITE,
    EVENTO_COLECAO_CONVITE_ACEITO,
    EVENTO_COLECAO_CONVITE_RECUSADO,
    EVENTO_COLECAO_PARTICIPANTE_SAIU,
)
from services.orgao_tree import rebuild_orgao_closure
from services.project_collections import criar_colecao
from time_utils import utc_now


def _add_orgao(sigla: str, pai_id: int | None = None) -> int:
    orgao = OrgaoUnidade(
        sigla=sigla, nome=sigla, tipo="Secretaria", pai_id=pai_id, ordem=0, ativo=True
    )
    db.session.add(orgao)
    db.session.flush()
    return orgao.id


def _add_user(username: str, *, orgao_ids: list[int], removido: bool = False) -> User:
    user = User(
        username=username,
        name=username.upper(),
        password_hash="x",
        deleted_at=utc_now() if removido else None,
    )
    db.session.add(user)
    db.session.flush()
    for orgao_id in orgao_ids:
        db.session.add(UserOrgao(user_id=user.id, orgao_id=orgao_id, papel="gestor"))
    db.session.flush()
    return user


@pytest.fixture
def cenario_notificacao(app):
    """Dono em AREAA e DESTINO; destinatários em DESTINO; FILHO é subárvore de DESTINO."""
    with app.app_context():
        area_a = _add_orgao("AREAA")
        destino = _add_orgao("DESTINO")
        filho = _add_orgao("FILHO", pai_id=destino)
        rebuild_orgao_closure()
        dono = _add_user("dono_notif", orgao_ids=[area_a, destino])
        convidado = _add_user("convidado_notif", orgao_ids=[destino])
        colega = _add_user("colega_notif", orgao_ids=[destino])
        _add_user("removido_notif", orgao_ids=[destino], removido=True)
        estranho = _add_user("estranho_notif", orgao_ids=[area_a])
        subordinado = _add_user("subordinado_notif", orgao_ids=[filho])
        db.session.commit()
        yield {
            "dono": dono,
            "convidado": convidado,
            "colega": colega,
            "estranho": estranho,
            "subordinado": subordinado,
            "destino_id": destino,
            "area_a_id": area_a,
            "filho_id": filho,
        }


def _colecao_do_dono(cenario, nome: str = "Compartilhada") -> ProjectCollection:
    colecao = criar_colecao(cenario["dono"], nome, None, "camadas", "primary", None)
    db.session.commit()
    return colecao


def _compartilhar(colecao, cenario, papel=PAPEL_SHARE_VIEWER, **destino):
    share = compartilhar_colecao(colecao, ator=cenario["dono"], papel=papel, **destino)
    db.session.commit()
    return share


def _notificacoes(evento: str = EVENTO_COLECAO_CONVITE) -> list[UserNotification]:
    return (
        UserNotification.query.filter_by(event_type=evento)
        .order_by(UserNotification.id)
        .all()
    )


def _destinatarios() -> set[int]:
    return {notificacao.recipient_user_id for notificacao in _notificacoes()}


# ── Concessão ─────────────────────────────────────────────────────────────────


def test_share_com_pessoa_notifica_somente_o_destinatario(app, cenario_notificacao):
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_notificacao, "Saúde digital")
        _compartilhar(
            colecao, cenario_notificacao, user_id=cenario_notificacao["convidado"].id
        )

        notificacoes = _notificacoes()
        assert len(notificacoes) == 1
        notificacao = notificacoes[0]
        assert notificacao.recipient_user_id == cenario_notificacao["convidado"].id
        assert notificacao.actor_user_id == cenario_notificacao["dono"].id
        assert notificacao.title == 'Convite para a coleção "Saúde digital"'
        assert "leitor" in notificacao.message
        assert "aceitar" in notificacao.message


def test_share_com_pessoa_aponta_para_a_pagina_da_colecao(app, cenario_notificacao):
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_notificacao)
        _compartilhar(
            colecao,
            cenario_notificacao,
            papel=PAPEL_SHARE_EDITOR,
            user_id=cenario_notificacao["convidado"].id,
        )

        assert _notificacoes()[0].target_url == f"/colecoes/{colecao.id}"


def test_share_com_orgao_notifica_ativos_do_orgao_e_exclui_ator(
    app, cenario_notificacao
):
    """Ator lotado no órgão de destino não se autonotifica; removido fica de fora."""
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_notificacao)
        _compartilhar(
            colecao, cenario_notificacao, orgao_id=cenario_notificacao["destino_id"]
        )

        assert _destinatarios() == {
            cenario_notificacao["convidado"].id,
            cenario_notificacao["colega"].id,
        }


def test_share_com_orgao_nao_alcanca_lotacao_de_outro_orgao(app, cenario_notificacao):
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_notificacao)
        _compartilhar(
            colecao, cenario_notificacao, orgao_id=cenario_notificacao["destino_id"]
        )

        assert cenario_notificacao["estranho"].id not in _destinatarios()


def test_share_com_orgao_nao_desce_para_a_subarvore(app, cenario_notificacao):
    """Lotado só no órgão FILHO não ganha acesso pelo share do pai — nem aviso."""
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_notificacao)
        _compartilhar(
            colecao, cenario_notificacao, orgao_id=cenario_notificacao["destino_id"]
        )

        assert _destinatarios() == {
            cenario_notificacao["convidado"].id,
            cenario_notificacao["colega"].id,
        }
        assert cenario_notificacao["subordinado"].id not in _destinatarios()


def test_criar_colecao_com_compartilhamentos_notifica(app, cenario_notificacao):
    """POST atômico: um aviso por pessoa, com o papel MAIS ALTO dos shares."""
    with app.test_request_context("/"):
        criar_colecao(
            cenario_notificacao["dono"],
            "Nasce compartilhada",
            None,
            "camadas",
            "primary",
            None,
            [
                {
                    "user_id": cenario_notificacao["convidado"].id,
                    "papel": PAPEL_SHARE_EDITOR,
                },
                {
                    "orgao_id": cenario_notificacao["destino_id"],
                    "papel": PAPEL_SHARE_VIEWER,
                },
            ],
        )
        db.session.commit()

        notificacoes = _notificacoes()
        assert sorted(
            notificacao.recipient_user_id for notificacao in notificacoes
        ) == sorted(
            [
                cenario_notificacao["convidado"].id,
                cenario_notificacao["colega"].id,
            ]
        )
        papel_por_destinatario = {
            notificacao.recipient_user_id: (
                "editor" if "editor" in notificacao.message else "leitor"
            )
            for notificacao in notificacoes
        }
        assert papel_por_destinatario == {
            cenario_notificacao["convidado"].id: "editor",
            cenario_notificacao["colega"].id: "leitor",
        }


# ── Silêncio: upsert e revogação ──────────────────────────────────────────────


def test_upsert_de_papel_nao_renotifica(app, cenario_notificacao):
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_notificacao)
        _compartilhar(
            colecao, cenario_notificacao, user_id=cenario_notificacao["convidado"].id
        )
        _compartilhar(
            colecao,
            cenario_notificacao,
            papel=PAPEL_SHARE_EDITOR,
            user_id=cenario_notificacao["convidado"].id,
        )

        assert len(_notificacoes()) == 1


def test_revogacao_nao_notifica(app, cenario_notificacao):
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_notificacao)
        share = _compartilhar(
            colecao, cenario_notificacao, user_id=cenario_notificacao["convidado"].id
        )

        assert (
            revogar_share(colecao, share.id, ator=cenario_notificacao["dono"]) is True
        )
        db.session.commit()
        assert len(_notificacoes()) == 1


# ── Respostas avisam o dono ───────────────────────────────────────────────────


def _dono_recebeu(cenario, evento: str) -> UserNotification:
    (notificacao,) = _notificacoes(evento)
    assert notificacao.recipient_user_id == cenario["dono"].id
    assert notificacao.actor_user_id == cenario["convidado"].id
    return notificacao


def test_aceite_avisa_o_dono(app, cenario_notificacao):
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_notificacao, "Obras")
        _compartilhar(
            colecao, cenario_notificacao, user_id=cenario_notificacao["convidado"].id
        )
        aceitar_convite(colecao.id, cenario_notificacao["convidado"])
        db.session.commit()

        notificacao = _dono_recebeu(cenario_notificacao, EVENTO_COLECAO_CONVITE_ACEITO)
        assert (notificacao.title, notificacao.message) == (
            'CONVIDADO_NOTIF aceitou o convite para a coleção "Obras"',
            "CONVIDADO_NOTIF aceitou o convite para a sua coleção compartilhada.",
        )
        assert notificacao.target_url == f"/colecoes/{colecao.id}"


def test_recusa_avisa_o_dono(app, cenario_notificacao):
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_notificacao)
        _compartilhar(
            colecao, cenario_notificacao, user_id=cenario_notificacao["convidado"].id
        )
        recusar_convite(colecao.id, cenario_notificacao["convidado"])
        db.session.commit()

        notificacao = _dono_recebeu(
            cenario_notificacao, EVENTO_COLECAO_CONVITE_RECUSADO
        )
        assert (notificacao.title, notificacao.message) == (
            'CONVIDADO_NOTIF recusou o convite para a coleção "Compartilhada"',
            "CONVIDADO_NOTIF recusou o convite para a sua coleção compartilhada.",
        )


def test_saida_avisa_o_dono(app, cenario_notificacao):
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_notificacao)
        _compartilhar(
            colecao, cenario_notificacao, user_id=cenario_notificacao["convidado"].id
        )
        aceitar_convite(colecao.id, cenario_notificacao["convidado"])
        sair_da_colecao(colecao.id, cenario_notificacao["convidado"])
        db.session.commit()

        notificacao = _dono_recebeu(
            cenario_notificacao, EVENTO_COLECAO_PARTICIPANTE_SAIU
        )
        # Regressão: o molde comum produzia "saiu de a coleção".
        assert (notificacao.title, notificacao.message) == (
            'CONVIDADO_NOTIF saiu da coleção "Compartilhada"',
            "CONVIDADO_NOTIF saiu da sua coleção compartilhada.",
        )


def test_reenviar_notifica_de_novo_quem_recusou(app, cenario_notificacao):
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_notificacao)
        share = _compartilhar(
            colecao, cenario_notificacao, user_id=cenario_notificacao["convidado"].id
        )
        recusar_convite(colecao.id, cenario_notificacao["convidado"])
        reenviar_convite(colecao, share.id, ator=cenario_notificacao["dono"])
        db.session.commit()

        assert [n.recipient_user_id for n in _notificacoes()] == [
            cenario_notificacao["convidado"].id,
            cenario_notificacao["convidado"].id,
        ]
