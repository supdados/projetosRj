"""Contrato HTTP da coleção compartilhada com aceite e curadoria.

Trava, pela API que a SPA consome, as invariantes da spec: anti-enumeração
(404 idêntico para inexistente/sem convite/revogado/já respondido), só o dono
gerencia shares, aceite e recusa só do próprio destinatário, o editor remove só
o que incluiu e não inclui projeto visto só por convite, o teto do incluidor,
mesma área × outra área ao revogar, poda ao revogar/sair/rebaixar, reenvio e as
regressões de reuso de rowid e da corrida aceitar × revogar.

A matriz estado × superfície e o orçamento de queries do índice ficam em
``test_api_collection_shares_matrix.py``; sino, busca e picker em
``test_api_collection_invites_contract.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from models import (
    ALVO_COLECAO,
    AutorizacaoAudit,
    ProjectCollectionItem,
    ProjectCollectionShareResposta,
    UserNotification,
)
from services import collection_invites
from tests.routes._collection_http_helpers import (
    NOT_FOUND_BODY,
    aceito,
    card_do_indice,
    convidar,
    criar_colecao,
    dados,
    delete,
    get,
    ids_dos_projetos_da_colecao,
    post,
    responder,
    semear_ids,
)


@pytest.fixture
def ids(app):
    return semear_ids(app)


def _colecao(app, ids) -> int:
    return criar_colecao(app, ids.dono, [ids.do_dono])


def _com_editor(app, ids) -> tuple[int, dict]:
    """Coleção do dono com o editor (EXT) aceito e ``do_ext`` incluído por ele."""
    cid = _colecao(app, ids)
    share = convidar(app, ids.dono, cid, papel="editor", user_id=ids.editor)
    aceito(app, ids.editor, cid)
    dados(
        post(
            app, ids.editor, f"/api/colecoes/{cid}/projetos", {"project_id": ids.do_ext}
        )
    )
    return cid, share


def _assert_404_identico(response) -> None:
    assert response.status_code == 404
    assert response.get_json() == NOT_FOUND_BODY


def _assert_403(response) -> None:
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "forbidden"


# ── Anti-enumeração ──────────────────────────────────────────────────────────


_ACAO_DO_ESTADO = {"aceito": "aceitar", "recusado": "recusar"}


def _alvo_sem_convite(app, ids, alvo: str) -> int:
    if alvo == "inexistente":
        return 999999
    cid = _colecao(app, ids)
    if alvo == "estranho":
        return cid
    share = convidar(app, ids.dono, cid, user_id=ids.convidado)
    if alvo == "revogado":
        dados(
            delete(
                app, ids.dono, f"/api/colecoes/{cid}/compartilhamentos/{share['id']}"
            )
        )
    elif alvo in _ACAO_DO_ESTADO:
        dados(responder(app, ids.convidado, cid, _ACAO_DO_ESTADO[alvo]))
    return cid


@pytest.mark.parametrize(
    "alvo", ["inexistente", "estranho", "revogado", "aceito", "recusado"]
)
def test_rotas_do_convite_respondem_o_mesmo_404(app, ids, alvo):
    cid = _alvo_sem_convite(app, ids, alvo)

    for response in (
        get(app, ids.convidado, f"/api/colecoes/{cid}/convite"),
        responder(app, ids.convidado, cid, "aceitar"),
        responder(app, ids.convidado, cid, "recusar"),
    ):
        _assert_404_identico(response)


@pytest.mark.parametrize("quem", ["inexistente", "pendente", "dono", "estranho"])
def test_sair_sem_participacao_valida_e_404_identico(app, ids, quem):
    cid = 999999 if quem == "inexistente" else _colecao(app, ids)
    if quem == "pendente":
        convidar(app, ids.dono, cid, user_id=ids.convidado)
    user_id = {"dono": ids.dono, "estranho": ids.membro_b}.get(quem, ids.convidado)

    _assert_404_identico(post(app, user_id, f"/api/colecoes/{cid}/sair"))


def test_pendente_so_ve_metadados_do_convite(app, ids):
    cid = _colecao(app, ids)
    convidar(app, ids.dono, cid, user_id=ids.convidado)

    for sufixo in ("projetos", "cronograma", "compartilhamentos"):
        _assert_404_identico(get(app, ids.convidado, f"/api/colecoes/{cid}/{sufixo}"))
    convite = dados(get(app, ids.convidado, f"/api/colecoes/{cid}/convite"))["convite"]
    assert set(convite) == {
        "id",
        "nome",
        "descricao",
        "icone",
        "cor",
        "owner",
        "papel",
        "convidado_em",
    }
    assert convite["id"] == cid
    assert convite["owner"] == {"id": ids.dono, "nome": "DONO"}
    assert convite["papel"] == "viewer"
    assert card_do_indice(app, ids.convidado, cid) is None


def test_aceitar_devolve_o_card_e_tira_dos_convites(app, ids):
    cid = _colecao(app, ids)
    convidar(app, ids.dono, cid, papel="editor", user_id=ids.convidado)
    convites = dados(get(app, ids.convidado, "/api/colecoes/convites"))["convites"]
    assert [convite["id"] for convite in convites] == [cid]

    resposta = aceito(app, ids.convidado, cid)

    assert resposta["status"] == "aceito"
    assert resposta["colecao"]["id"] == cid
    assert resposta["colecao"]["papel"] == "editor"
    assert resposta["colecao"]["projetos"] == 1
    assert dados(get(app, ids.convidado, "/api/colecoes/convites"))["convites"] == []
    assert card_do_indice(app, ids.convidado, cid) is not None
    assert ids_dos_projetos_da_colecao(app, ids.convidado, cid) == {ids.do_dono}


# ── Só o dono gerencia ───────────────────────────────────────────────────────


def test_participante_nao_gerencia_shares_e_estranho_toma_404(app, ids):
    cid, share = _com_editor(app, ids)
    base = f"/api/colecoes/{cid}/compartilhamentos"
    chamadas = [
        lambda uid: get(app, uid, base),
        lambda uid: post(app, uid, base, {"user_id": ids.convidado, "papel": "viewer"}),
        lambda uid: delete(app, uid, f"{base}/{share['id']}"),
        lambda uid: post(app, uid, f"{base}/{share['id']}/reenviar"),
    ]

    for chamada in chamadas:
        _assert_403(chamada(ids.editor))
        _assert_404_identico(chamada(ids.membro_b))


def test_aceite_e_recusa_sao_do_proprio_destinatario(app, ids):
    cid = _colecao(app, ids)
    convidar(app, ids.dono, cid, user_id=ids.convidado)

    for intruso in (ids.membro_a, ids.dono):
        _assert_404_identico(responder(app, intruso, cid, "aceitar"))
        _assert_404_identico(responder(app, intruso, cid, "recusar"))
    assert dados(get(app, ids.convidado, f"/api/colecoes/{cid}/convite"))
    with app.app_context():
        assert ProjectCollectionShareResposta.query.count() == 0


# ── Curadoria (decisões 2 e 3) ───────────────────────────────────────────────


def test_editor_remove_so_o_que_incluiu_e_pode_remover_vem_do_servidor(app, ids):
    cid, _ = _com_editor(app, ids)
    pagina = dados(get(app, ids.editor, f"/api/colecoes/{cid}/projetos"))
    linhas = {linha["id"]: linha for linha in pagina["projetos"]}

    assert linhas[ids.do_dono]["adicionado_por"] == {"id": ids.dono, "name": "DONO"}
    assert linhas[ids.do_dono]["pode_remover"] is False
    assert linhas[ids.do_ext]["adicionado_por"] == {"id": ids.editor, "name": "EDITOR"}
    assert linhas[ids.do_ext]["pode_remover"] is True
    assert pagina["itens_incluidos_por_mim"] == 1
    _assert_403(delete(app, ids.editor, f"/api/colecoes/{cid}/projetos/{ids.do_dono}"))
    dados(delete(app, ids.editor, f"/api/colecoes/{cid}/projetos/{ids.do_ext}"))
    assert ids_dos_projetos_da_colecao(app, ids.editor, cid) == {ids.do_dono}


def test_dono_ve_e_remove_o_que_o_editor_incluiu(app, ids):
    cid, _ = _com_editor(app, ids)
    pagina = dados(get(app, ids.dono, f"/api/colecoes/{cid}/projetos"))

    assert {linha["id"] for linha in pagina["projetos"]} == {ids.do_dono, ids.do_ext}
    assert all(linha["pode_remover"] for linha in pagina["projetos"])
    assert pagina["itens_incluidos_por_mim"] == 0
    dados(delete(app, ids.dono, f"/api/colecoes/{cid}/projetos/{ids.do_ext}"))


def test_editor_nao_inclui_projeto_visto_so_por_convite(app, ids):
    cid, _ = _com_editor(app, ids)

    response = post(
        app, ids.editor, f"/api/colecoes/{cid}/projetos", {"project_id": ids.so_convite}
    )

    assert response.status_code == 422
    assert "convite" in response.get_json()["error"]["message"]
    with app.app_context():
        assert (
            ProjectCollectionItem.query.filter_by(
                collection_id=cid, project_id=ids.so_convite
            ).count()
            == 0
        )


def _permissao_de_edicao(app, user_id: int, project_id: int) -> dict:
    projeto = dados(get(app, user_id, f"/api/projetos/{project_id}/detalhe"))["project"]
    return {
        "can_edit": projeto["permissions"]["can_edit"],
        "via": projeto["access_via"],
    }


def test_teto_dono_leitor_inclui_e_share_editor_da_so_leitura(app, ids):
    # O colega é LEITOR na área: o item dele grava teto leitor.
    do_colega = criar_colecao(app, ids.colega, [ids.do_dono], nome="Do colega")
    convidar(app, ids.colega, do_colega, papel="editor", user_id=ids.convidado)
    aceito(app, ids.convidado, do_colega)
    assert _permissao_de_edicao(app, ids.convidado, ids.do_dono) == {
        "can_edit": False,
        "via": "colecao",
    }

    do_dono = criar_colecao(app, ids.dono, [ids.do_dono], nome="Do dono gestor")
    convidar(app, ids.dono, do_dono, papel="editor", user_id=ids.convidado)
    aceito(app, ids.convidado, do_dono)
    assert _permissao_de_edicao(app, ids.convidado, ids.do_dono)["can_edit"] is True


def test_revogar_mesma_area_mantem_e_outra_area_perde(app, ids):
    cid = _colecao(app, ids)
    shares = [
        convidar(app, ids.dono, cid, user_id=user_id)
        for user_id in (ids.colega, ids.convidado)
    ]
    for user_id in (ids.colega, ids.convidado):
        aceito(app, user_id, cid)
        dados(get(app, user_id, f"/api/projetos/{ids.do_dono}/detalhe"))

    for share in shares:
        dados(
            delete(
                app, ids.dono, f"/api/colecoes/{cid}/compartilhamentos/{share['id']}"
            )
        )

    dados(get(app, ids.colega, f"/api/projetos/{ids.do_dono}/detalhe"))
    _assert_404_identico(
        get(app, ids.convidado, f"/api/projetos/{ids.do_dono}/detalhe")
    )


# ── Poda ─────────────────────────────────────────────────────────────────────


def _perder_o_editor(app, ids, cid: int, share: dict, como: str) -> None:
    base = f"/api/colecoes/{cid}/compartilhamentos"
    if como == "revogar":
        dados(delete(app, ids.dono, f"{base}/{share['id']}"))
    elif como == "sair":
        saida = dados(post(app, ids.editor, f"/api/colecoes/{cid}/sair"))
        assert saida == {"status": "saiu", "itens_removidos": 1}
    else:
        convidar(app, ids.dono, cid, papel="viewer", user_id=ids.editor)


@pytest.mark.parametrize(
    ("como", "motivo"),
    [
        ("revogar", "share_revogado"),
        ("sair", "participante_saiu"),
        ("rebaixar", "papel_rebaixado"),
    ],
)
def test_poda_tira_os_itens_de_quem_perdeu_o_editor(app, ids, como, motivo):
    cid, share = _com_editor(app, ids)
    shares = dados(get(app, ids.dono, f"/api/colecoes/{cid}/compartilhamentos"))
    assert shares["compartilhamentos"][0]["itens_incluidos"] == 1

    _perder_o_editor(app, ids, cid, share, como)

    assert ids_dos_projetos_da_colecao(app, ids.dono, cid) == {ids.do_dono}
    with app.app_context():
        detalhes = [
            linha.detalhe
            for linha in AutorizacaoAudit.query.filter_by(
                alvo_tipo=ALVO_COLECAO, alvo_id=cid, evento="colecao_projeto_removido"
            )
        ]
    assert [(d["project_id"], d["motivo"]) for d in detalhes] == [(ids.do_ext, motivo)]


# ── Reenviar ─────────────────────────────────────────────────────────────────


def _convites_recebidos(app, user_id: int) -> int:
    with app.app_context():
        return UserNotification.query.filter_by(
            recipient_user_id=user_id, event_type="colecao_convite"
        ).count()


def test_reenviar_reconvida_quem_recusou_e_notifica_de_novo(app, ids):
    cid = _colecao(app, ids)
    share = convidar(app, ids.dono, cid, user_id=ids.convidado)
    dados(responder(app, ids.convidado, cid, "recusar"))
    url = f"/api/colecoes/{cid}/compartilhamentos/{share['id']}/reenviar"
    shares = dados(get(app, ids.dono, f"/api/colecoes/{cid}/compartilhamentos"))
    assert shares["compartilhamentos"][0]["status"] == "recusado"

    reenvio = dados(post(app, ids.dono, url))

    assert reenvio["reconvidados"] == 1
    assert reenvio["compartilhamento"]["status"] == "pendente"
    assert dados(get(app, ids.convidado, f"/api/colecoes/{cid}/convite"))
    assert _convites_recebidos(app, ids.convidado) == 2
    assert post(app, ids.dono, url).status_code == 422


def test_reenviar_share_de_outra_colecao_e_404(app, ids):
    cid = _colecao(app, ids)
    outra = criar_colecao(app, ids.dono, [], nome="Outra")
    share = convidar(app, ids.dono, outra, user_id=ids.convidado)
    dados(responder(app, ids.convidado, outra, "recusar"))

    response = post(
        app, ids.dono, f"/api/colecoes/{cid}/compartilhamentos/{share['id']}/reenviar"
    )

    _assert_404_identico(response)


# ── Payloads novos ───────────────────────────────────────────────────────────


def test_compartilhamentos_trazem_status_por_pessoa_e_agregado_do_orgao(app, ids):
    cid = _colecao(app, ids)
    pessoa = convidar(app, ids.dono, cid, user_id=ids.convidado)
    assert pessoa["status"] == "pendente"
    assert pessoa["exige_aceite"] is True
    convidar(app, ids.dono, cid, orgao_id=ids.orgx)
    aceito(app, ids.membro_a, cid)

    shares = dados(get(app, ids.dono, f"/api/colecoes/{cid}/compartilhamentos"))
    por_tipo = {
        "user" if share["user_id"] else "orgao": share
        for share in shares["compartilhamentos"]
    }

    assert por_tipo["user"]["status"] == "pendente"
    assert por_tipo["user"]["resumo"] is None
    assert por_tipo["orgao"]["status"] is None
    assert por_tipo["orgao"]["resumo"] == {
        "membros": 2,
        "aceitos": 1,
        "pendentes": 1,
        "recusados": 0,
        "sairam": 0,
    }
    assert {s["itens_incluidos"] for s in shares["compartilhamentos"]} == {0}


def test_card_do_indice_marca_compartilhada_sem_listar_destinatarios(app, ids):
    cid = _colecao(app, ids)
    assert card_do_indice(app, ids.dono, cid)["compartilhada"] is False
    convidar(app, ids.dono, cid, user_id=ids.convidado)
    convidar(app, ids.dono, cid, user_id=ids.editor)
    aceito(app, ids.convidado, cid)
    dados(responder(app, ids.editor, cid, "recusar"))

    do_dono = card_do_indice(app, ids.dono, cid)
    do_membro = card_do_indice(app, ids.convidado, cid)

    # Share recusado/pendente ainda conta: a flag é "tem share", não "tem aceite".
    assert do_dono["compartilhada"] is True
    assert do_membro["compartilhada"] is True
    for card in (do_dono, do_membro):
        assert "destinatarios" not in card
        assert "destinatarios_total" not in card


# ── Regressões ───────────────────────────────────────────────────────────────


def test_share_novo_apos_revogar_nasce_pendente(app, ids):
    """Reuso de rowid: o share novo não pode herdar o "aceito" do revogado."""
    cid = _colecao(app, ids)
    antigo = convidar(app, ids.dono, cid, user_id=ids.convidado)
    aceito(app, ids.convidado, cid)
    dados(
        delete(app, ids.dono, f"/api/colecoes/{cid}/compartilhamentos/{antigo['id']}")
    )

    novo = convidar(app, ids.dono, cid, user_id=ids.convidado)

    assert novo["status"] == "pendente"
    _assert_404_identico(get(app, ids.convidado, f"/api/colecoes/{cid}/projetos"))
    assert dados(get(app, ids.convidado, f"/api/colecoes/{cid}/convite"))


@dataclass(frozen=True)
class ShareLidoAntes:
    """O que o aceite leu antes da revogação concorrente (só o id importa)."""

    id: int
    collection_id: int


class LeituraAtrasadaDePendentes:
    """Fake de ``shares_pendentes_do_usuario`` que devolve a leitura velha."""

    def __init__(self, shares: list[ShareLidoAntes]) -> None:
        self.shares = shares

    def __call__(self, *_args: object) -> list[ShareLidoAntes]:
        return self.shares


def test_corrida_aceitar_x_revogar_responde_404_limpo(app, ids, monkeypatch):
    cid = _colecao(app, ids)
    share = convidar(app, ids.dono, cid, user_id=ids.convidado)
    dados(delete(app, ids.dono, f"/api/colecoes/{cid}/compartilhamentos/{share['id']}"))
    monkeypatch.setattr(
        collection_invites,
        "shares_pendentes_do_usuario",
        LeituraAtrasadaDePendentes([ShareLidoAntes(share["id"], cid)]),
    )

    _assert_404_identico(responder(app, ids.convidado, cid, "aceitar"))
    with app.app_context():
        assert ProjectCollectionShareResposta.query.count() == 0


def test_duplo_clique_no_aceite_responde_404_limpo(app, ids, monkeypatch):
    cid = _colecao(app, ids)
    share = convidar(app, ids.dono, cid, user_id=ids.convidado)
    aceito(app, ids.convidado, cid)
    monkeypatch.setattr(
        collection_invites,
        "shares_pendentes_do_usuario",
        LeituraAtrasadaDePendentes([ShareLidoAntes(share["id"], cid)]),
    )

    _assert_404_identico(responder(app, ids.convidado, cid, "aceitar"))
    with app.app_context():
        assert ProjectCollectionShareResposta.query.count() == 1
