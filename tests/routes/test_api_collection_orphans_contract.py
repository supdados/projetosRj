"""Itens ÓRFÃOS (incluidor já sem papel editor) e custo do modal de shares.

Órfão nasce quando quem incluiu é desativado ou sai do órgão do share: o item
fica até a próxima poda, que roda em QUALQUER revogar/recusar/rebaixar/sair.
Contrato: ``itens_orfaos`` no topo de ``GET .../compartilhamentos`` e de
``GET .../projetos`` (fora dos ``itens_incluidos`` por share, sem dupla
contagem); a poda grava ``motivo='incluidor_sem_papel'`` — não o motivo da
mutação de outra pessoa — e "sair" só conta os itens do próprio ator.

E o orçamento: o modal (GET e POST de convite) custa queries CONSTANTES em N
shares e N incluidores (antes, 2 queries por incluidor e 1 por share).
"""

from __future__ import annotations

import pytest

from models import (
    ALVO_COLECAO,
    AutorizacaoAudit,
    Project,
    User,
    UserOrgao,
    db,
)
from time_utils import utc_now
from tests.routes._collection_http_helpers import (
    IdsDoCenario,
    aceito,
    cliente_de,
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
from tests.sql_query_counter import SqlQueryCounter


@pytest.fixture
def ids(app) -> IdsDoCenario:
    return semear_ids(app)


def _incluir(app, user_id: int, cid: int, project_id: int) -> None:
    body = {"project_id": project_id}
    dados(post(app, user_id, f"/api/colecoes/{cid}/projetos", body))


def _motivos_da_poda(app, cid: int) -> dict[int, str]:
    with app.app_context():
        linhas = AutorizacaoAudit.query.filter_by(
            alvo_tipo=ALVO_COLECAO, alvo_id=cid, evento="colecao_projeto_removido"
        ).all()
        return {
            linha.detalhe["project_id"]: linha.detalhe["motivo"] for linha in linhas
        }


def _shares_do_modal(app, ids: IdsDoCenario, cid: int) -> dict:
    return dados(get(app, ids.dono, f"/api/colecoes/{cid}/compartilhamentos"))


def _desativar(app, user_id: int) -> None:
    with app.app_context():
        db.session.get(User, user_id).deleted_at = utc_now()
        db.session.commit()


def _com_editor_desativado(app, ids: IdsDoCenario) -> int:
    """Editor (EXT) incluiu ``do_ext`` e foi desativado; membro_a segue editor."""
    cid = criar_colecao(app, ids.dono, [ids.do_dono])
    convidar(app, ids.dono, cid, papel="editor", user_id=ids.editor)
    aceito(app, ids.editor, cid)
    _incluir(app, ids.editor, cid, ids.do_ext)
    convidar(app, ids.dono, cid, papel="editor", user_id=ids.membro_a)
    aceito(app, ids.membro_a, cid)
    _desativar(app, ids.editor)
    return cid


def test_modal_e_pagina_contam_o_orfao_a_parte(app, ids):
    cid = _com_editor_desativado(app, ids)

    modal = _shares_do_modal(app, ids, cid)
    pagina = dados(get(app, ids.membro_a, f"/api/colecoes/{cid}/projetos"))

    assert modal["itens_orfaos"] == 1
    # Sem dupla contagem: o share do desativado não promete o item no diálogo.
    assert {s["itens_incluidos"] for s in modal["compartilhamentos"]} == {0}
    assert (pagina["itens_orfaos"], pagina["itens_incluidos_por_mim"]) == (1, 0)


def _mutacao_de_outra_pessoa(app, ids: IdsDoCenario, cid: int, como: str) -> None:
    base = f"/api/colecoes/{cid}/compartilhamentos"
    if como == "rebaixar_outro":
        convidar(app, ids.dono, cid, papel="viewer", user_id=ids.membro_a)
        return
    if como == "sair":
        saida = dados(post(app, ids.membro_a, f"/api/colecoes/{cid}/sair"))
        assert saida == {"status": "saiu", "itens_removidos": 0}
        return
    share = convidar(app, ids.dono, cid, user_id=ids.membro_b)
    if como == "recusa_de_terceiro":
        dados(responder(app, ids.membro_b, cid, "recusar"))
        return
    aceito(app, ids.membro_b, cid)
    dados(delete(app, ids.dono, f"{base}/{share['id']}"))


@pytest.mark.parametrize(
    "como", ["revogar_outro", "recusa_de_terceiro", "rebaixar_outro", "sair"]
)
def test_poda_de_orfao_grava_motivo_proprio(app, ids, como):
    cid = _com_editor_desativado(app, ids)

    _mutacao_de_outra_pessoa(app, ids, cid, como)

    assert ids_dos_projetos_da_colecao(app, ids.dono, cid) == {ids.do_dono}
    assert _motivos_da_poda(app, cid) == {ids.do_ext: "incluidor_sem_papel"}


def test_incluidor_que_mudou_de_orgao_vira_orfao_do_share_de_area(app, ids):
    cid = criar_colecao(app, ids.dono, [ids.do_dono])
    do_orgao = convidar(app, ids.dono, cid, papel="editor", orgao_id=ids.ext)
    aceito(app, ids.editor, cid)
    _incluir(app, ids.editor, cid, ids.do_ext)
    with app.app_context():
        UserOrgao.query.filter_by(user_id=ids.editor, orgao_id=ids.ext).delete()
        db.session.add(UserOrgao(user_id=ids.editor, orgao_id=ids.area, papel="gestor"))
        db.session.commit()
    share_b = convidar(app, ids.dono, cid, user_id=ids.membro_b)
    aceito(app, ids.membro_b, cid)

    modal = _shares_do_modal(app, ids, cid)
    por_id = {s["id"]: s["itens_incluidos"] for s in modal["compartilhamentos"]}
    assert (por_id[do_orgao["id"]], modal["itens_orfaos"]) == (0, 1)

    base = f"/api/colecoes/{cid}/compartilhamentos"
    dados(delete(app, ids.dono, f"{base}/{share_b['id']}"))
    assert _motivos_da_poda(app, cid) == {ids.do_ext: "incluidor_sem_papel"}


# ── Orçamento de queries do modal (constante em N shares e N incluidores) ────


def _editores_de_ext(app, ids: IdsDoCenario, total: int) -> list[tuple[int, int]]:
    """``total`` pares (editor gestor em EXT, projeto em EXT que ele inclui)."""
    with app.app_context():
        pares = []
        for indice in range(total):
            user = User(
                username=f"incl{indice}", name=f"INCL{indice}", password_hash="x"
            )
            projeto = Project(
                titulo=f"Ext {indice}", orgao_id=ids.ext, status="Vigente"
            )
            db.session.add_all([user, projeto])
            db.session.flush()
            db.session.add(UserOrgao(user_id=user.id, orgao_id=ids.ext, papel="gestor"))
            pares.append((user.id, projeto.id))
        db.session.commit()
        return pares


def _colecao_com_incluidores(
    app, ids: IdsDoCenario, pares: list[tuple[int, int]], nome: str
) -> int:
    cid = criar_colecao(app, ids.dono, [ids.do_dono], nome=nome)
    convidar(app, ids.dono, cid, orgao_id=ids.orgx)
    for user_id, project_id in pares:
        convidar(app, ids.dono, cid, papel="editor", user_id=user_id)
        aceito(app, user_id, cid)
        _incluir(app, user_id, cid, project_id)
    return cid


def _queries(app, user_id: int, chamada) -> int:
    client = cliente_de(app, user_id)
    with app.app_context():
        engine = db.engine
    with SqlQueryCounter(engine) as queries:
        response = chamada(client)
    assert response.status_code == 200, response.get_data(as_text=True)
    return queries.total


def test_modal_de_compartilhamentos_custa_queries_constantes(app, ids):
    pares = _editores_de_ext(app, ids, 6)
    pequena = _colecao_com_incluidores(app, ids, pares[:2], "Pequena")
    grande = _colecao_com_incluidores(app, ids, pares, "Grande")

    def listar(cid: int):
        return lambda client: client.get(f"/api/colecoes/{cid}/compartilhamentos")

    def convidar_membro(cid: int):
        body = {"user_id": ids.membro_a, "papel": "viewer"}
        return lambda client: client.post(
            f"/api/colecoes/{cid}/compartilhamentos", json=body
        )

    assert _queries(app, ids.dono, listar(pequena)) == _queries(
        app, ids.dono, listar(grande)
    )
    assert _queries(app, ids.dono, convidar_membro(pequena)) == _queries(
        app, ids.dono, convidar_membro(grande)
    )
    modal = _shares_do_modal(app, ids, grande)
    assert sum(s["itens_incluidos"] for s in modal["compartilhamentos"]) == 6
