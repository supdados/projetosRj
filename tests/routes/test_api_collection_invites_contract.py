"""Contrato HTTP das superfícies em volta do convite de coleção.

- Sino: ``/api/notificacoes`` esconde aviso de coleção que a pessoa perdeu
  (recusa, revogação, saída — inclusive o legado ``colecao_compartilhada``) e
  ``/api/notificacoes/resumo`` conta só o que ela veria + convites pendentes.
- Busca de destinatários (decisão 4): aberta a qualquer logado, sem a flag de
  convites nem gate de gestor, por NOME, sem CPF/username, sem o próprio ator.
- Picker: ``?visibilidade=area|propria`` e ``?colecao=``/``?excluir_colecao=``
  valendo para coleção recebida ACEITA (nunca para convite pendente).
"""

from __future__ import annotations

import pytest

from extensions import limiter
from models import ProjectCollectionShare, User, UserNotification, db
from time_utils import utc_now
from tests.routes._collection_http_helpers import (
    aceito,
    convidar,
    criar_colecao,
    dados,
    delete,
    get,
    ids_da_lista_de_projetos,
    post,
    responder,
    semear_ids,
)


@pytest.fixture
def ids(app):
    return semear_ids(app)


def _alvos_no_sino(app, user_id: int) -> list[tuple[str, str]]:
    itens = dados(get(app, user_id, "/api/notificacoes"))["items"]
    return [(item["event_type"], item["target_url"]) for item in itens]


def _resumo(app, user_id: int) -> dict:
    return dados(get(app, user_id, "/api/notificacoes/resumo"))


# ── Criação com compartilhamentos iniciais ───────────────────────────────────


def test_criar_com_compartilhamentos_iniciais_vira_convite(app, ids):
    body = {
        "nome": "Nova",
        "icone": "camadas",
        "cor": "primary",
        "project_ids": [ids.do_dono],
        "compartilhamentos": [{"user_id": ids.convidado, "papel": "editor"}],
    }

    card = dados(post(app, ids.dono, "/api/colecoes", body))["colecao"]

    assert card["compartilhada"] is True
    assert card["destinatarios"] == [
        {
            "tipo": "user",
            "id": ids.convidado,
            "nome": "CONVIDADO",
            "sigla": None,
            "papel": "editor",
            "status": "pendente",
        }
    ]
    assert card["destinatarios_total"] == 1
    convites = dados(get(app, ids.convidado, "/api/colecoes/convites"))["convites"]
    assert [(c["id"], c["papel"]) for c in convites] == [(card["id"], "editor")]
    assert (
        get(app, ids.convidado, f"/api/colecoes/{card['id']}/projetos").status_code
        == 404
    )


# ── Sino ─────────────────────────────────────────────────────────────────────


def test_convite_aparece_no_sino_e_no_resumo_ate_ser_recusado(app, ids):
    cid = criar_colecao(app, ids.dono, [ids.do_dono])
    convidar(app, ids.dono, cid, user_id=ids.convidado)
    alvo = ("colecao_convite", f"/colecoes/{cid}")

    assert alvo in _alvos_no_sino(app, ids.convidado)
    assert _resumo(app, ids.convidado) == {
        "unread_count": 1,
        "convites_pendentes": 1,
        "convites": [{"collection_id": cid, "nome": "Compartilhada"}],
    }

    dados(responder(app, ids.convidado, cid, "recusar"))

    assert alvo not in _alvos_no_sino(app, ids.convidado)
    assert _resumo(app, ids.convidado) == {
        "unread_count": 0,
        "convites_pendentes": 0,
        "convites": [],
    }
    assert ("colecao_convite_recusado", f"/colecoes/{cid}") in _alvos_no_sino(
        app, ids.dono
    )


@pytest.mark.parametrize("perda", ["revogar", "sair"])
def test_aviso_da_colecao_some_de_quem_perdeu_o_acesso(app, ids, perda):
    cid = criar_colecao(app, ids.dono, [ids.do_dono])
    share = convidar(app, ids.dono, cid, user_id=ids.convidado)
    aceito(app, ids.convidado, cid)
    assert ("colecao_convite", f"/colecoes/{cid}") in _alvos_no_sino(app, ids.convidado)

    if perda == "revogar":
        url = f"/api/colecoes/{cid}/compartilhamentos/{share['id']}"
        dados(delete(app, ids.dono, url))
    else:
        dados(post(app, ids.convidado, f"/api/colecoes/{cid}/sair"))

    assert _alvos_no_sino(app, ids.convidado) == []
    assert _resumo(app, ids.convidado)["unread_count"] == 0


def _share_legado_com_aviso(app, ids, cid: int) -> int:
    with app.app_context():
        share = ProjectCollectionShare(
            collection_id=cid,
            user_id=ids.convidado,
            papel="viewer",
            created_by_user_id=ids.dono,
            exige_aceite=False,
        )
        aviso = UserNotification(
            recipient_user_id=ids.convidado,
            actor_user_id=ids.dono,
            event_type="colecao_compartilhada",
            title="Coleção compartilhada",
            message="Compartilhada com você",
            target_url=f"/colecoes/{cid}",
        )
        db.session.add_all([share, aviso])
        db.session.commit()
        return share.id


def test_aviso_legado_colecao_compartilhada_some_apos_revogar(app, ids):
    cid = criar_colecao(app, ids.dono, [ids.do_dono])
    share_id = _share_legado_com_aviso(app, ids, cid)
    legado = ("colecao_compartilhada", f"/colecoes/{cid}")
    assert legado in _alvos_no_sino(app, ids.convidado)

    dados(delete(app, ids.dono, f"/api/colecoes/{cid}/compartilhamentos/{share_id}"))

    assert legado not in _alvos_no_sino(app, ids.convidado)


def test_resumo_nao_conta_aviso_oculto_nem_lido(app, ids):
    with app.app_context():
        db.session.add_all(
            [
                UserNotification(
                    recipient_user_id=ids.convidado,
                    event_type="projeto_atualizado",
                    title="Oculto",
                    message="Projeto de outra área",
                    target_url=f"/projetos/{ids.do_dono}",
                ),
                UserNotification(
                    recipient_user_id=ids.convidado,
                    event_type="projeto_atualizado",
                    title="Lido",
                    message="Projeto da área",
                    target_url=f"/projetos/{ids.do_ext}",
                    is_read=True,
                    read_at=utc_now(),
                ),
                UserNotification(
                    recipient_user_id=ids.convidado,
                    event_type="projeto_atualizado",
                    title="Visível",
                    message="Projeto da área",
                    target_url=f"/projetos/{ids.do_ext}",
                ),
            ]
        )
        db.session.commit()

    assert _resumo(app, ids.convidado)["unread_count"] == 1


# ── Busca de destinatários ───────────────────────────────────────────────────


def _busca(app, user_id: int, termo: str) -> list[dict]:
    path = f"/api/colecoes/destinatarios?q={termo}"
    return dados(get(app, user_id, path))["usuarios"]


def test_busca_aberta_a_leitor_sem_flag_de_convites(app, ids):
    assert app.config["CONVITES_HABILITADOS"] is False
    usuarios = _busca(app, ids.colega, "membro")  # colega é só LEITOR

    assert [usuario["id"] for usuario in usuarios] == [ids.membro_a, ids.membro_b]
    assert all(set(usuario) == {"id", "name", "orgao_sigla"} for usuario in usuarios)
    assert usuarios[0]["orgao_sigla"] == "ORGX"


def test_busca_exige_dois_caracteres_e_exclui_o_proprio_e_inativos(app, ids):
    with app.app_context():
        db.session.get(User, ids.membro_b).deleted_at = utc_now()
        db.session.commit()

    assert _busca(app, ids.membro_a, "m") == []
    assert _busca(app, ids.membro_a, "membro") == []
    assert [u["id"] for u in _busca(app, ids.colega, "membro")] == [ids.membro_a]


def test_busca_nao_casa_username_nem_curinga(app, ids):
    with app.app_context():
        db.session.add(
            User(username="12345678901", name="Pessoa Gov", password_hash="x")
        )
        db.session.commit()

    assert _busca(app, ids.colega, "12345678") == []
    assert _busca(app, ids.colega, "%25%25") == []
    assert [u["name"] for u in _busca(app, ids.colega, "pessoa")] == ["Pessoa Gov"]


def test_busca_devolve_no_maximo_vinte(app, ids):
    with app.app_context():
        db.session.add_all(
            User(username=f"lote{i:02}", name=f"Lote {i:02}", password_hash="x")
            for i in range(25)
        )
        db.session.commit()

    assert len(_busca(app, ids.colega, "lote")) == 20


@pytest.fixture
def limite_zerado():
    """O storage do limiter é global ao processo: zera antes e DEPOIS, para o
    balde esgotado aqui não vazar para outro teste do mesmo worker."""
    limiter.reset()
    yield
    limiter.reset()


def test_busca_tem_limite_de_taxa_por_pessoa(app, ids, limite_zerado):
    """60 buscas/minuto por pessoa: varrer o diretório por bigramas esbarra no 429."""
    for _ in range(60):
        _busca(app, ids.colega, "membro")

    assert get(app, ids.colega, "/api/colecoes/destinatarios?q=me").status_code == 429
    # O balde é da PESSOA (não do IP, igual no cliente de teste): outra segue.
    assert [u["id"] for u in _busca(app, ids.convidado, "membro")] == [
        ids.membro_a,
        ids.membro_b,
    ]


# ── Picker e filtros de coleção ──────────────────────────────────────────────


def _editor_aceito(app, ids) -> int:
    cid = criar_colecao(app, ids.dono, [ids.do_dono])
    convidar(app, ids.dono, cid, papel="editor", user_id=ids.editor)
    aceito(app, ids.editor, cid)
    return cid


def test_picker_visibilidade_area_e_propria(app, ids):
    _editor_aceito(app, ids)
    todos = {ids.do_ext, ids.so_convite, ids.do_dono}

    assert ids_da_lista_de_projetos(app, ids.editor) == todos
    assert ids_da_lista_de_projetos(app, ids.editor, "&visibilidade=area") == {
        ids.do_ext
    }
    assert ids_da_lista_de_projetos(app, ids.editor, "&visibilidade=propria") == {
        ids.do_ext,
        ids.so_convite,
    }


def test_picker_visibilidade_invalida_e_422(app, ids):
    response = get(app, ids.editor, "/api/projetos?visibilidade=tudo")

    assert response.status_code == 422
    assert "visibilidade" in response.get_json()["error"]["message"]


def test_filtros_de_colecao_valem_para_colecao_recebida_aceita(app, ids):
    cid = _editor_aceito(app, ids)
    dados(
        post(
            app, ids.editor, f"/api/colecoes/{cid}/projetos", {"project_id": ids.do_ext}
        )
    )

    assert ids_da_lista_de_projetos(app, ids.editor, f"&colecao={cid}") == {
        ids.do_dono,
        ids.do_ext,
    }
    picker = ids_da_lista_de_projetos(
        app, ids.editor, f"&excluir_colecao={cid}&visibilidade=area"
    )
    assert picker == set()


def test_filtros_de_colecao_so_valem_depois_do_aceite(app, ids):
    # O colega vê ``do_dono`` pela própria área: só o papel decide o filtro.
    cid = criar_colecao(app, ids.dono, [ids.do_dono])
    convidar(app, ids.dono, cid, user_id=ids.colega)

    assert ids_da_lista_de_projetos(app, ids.colega, f"&colecao={cid}") == set()
    assert ids_da_lista_de_projetos(app, ids.colega, f"&excluir_colecao={cid}") == {
        ids.do_dono
    }

    aceito(app, ids.colega, cid)

    assert ids_da_lista_de_projetos(app, ids.colega, f"&colecao={cid}") == {ids.do_dono}
    assert ids_da_lista_de_projetos(app, ids.colega, f"&excluir_colecao={cid}") == set()
