"""Corridas da coleção compartilhada pela API: sempre 404/403 limpo, nunca 500.

O request paralelo é simulado por ``ConexaoConcorrente`` (outra conexão ao
mesmo SQLite) chamada de dentro de uma fake NOMEADA, no ponto exato da janela:

- Sair × revogar / sair × sair: a saída é transição condicional (UPDATE ...
  WHERE status='aceito'); antes, o UPDATE às cegas dava ``StaleDataError``
  (500) ou duplicava o aviso ao dono e a auditoria.
- Incluir × revogar/rebaixar o editor: o papel é relido DEPOIS do INSERT; antes,
  o item nascia de quem já não era editor (órfão, expondo o projeto).
"""

from __future__ import annotations

from typing import Any, Callable

import pytest

from models import (
    ALVO_COLECAO,
    AutorizacaoAudit,
    ProjectCollectionItem,
    ProjectCollectionShare,
    ProjectCollectionShareResposta,
    UserNotification,
    db,
)
from services import collection_invites, project_collections
from tests.routes._collection_http_helpers import (
    NOT_FOUND_BODY,
    ConexaoConcorrente,
    aceito,
    convidar,
    criar_colecao,
    dados,
    post,
    semear_ids,
)

_APAGAR_RESPOSTAS = "DELETE FROM project_collection_share_resposta WHERE share_id = ?"
_APAGAR_SHARE = "DELETE FROM project_collection_share WHERE id = ?"


@pytest.fixture
def ids(app):
    return semear_ids(app)


def _revogacao(share_id: int) -> tuple[tuple[str, tuple[Any, ...]], ...]:
    """O que ``revogar_share`` commita: respostas e o share."""
    return ((_APAGAR_RESPOSTAS, (share_id,)), (_APAGAR_SHARE, (share_id,)))


def _assert_404_identico(response) -> None:
    assert response.status_code == 404
    assert response.get_json() == NOT_FOUND_BODY


def _saidas_registradas(app, cid: int) -> tuple[int, int]:
    """(avisos ``colecao_participante_saiu`` ao dono, auditorias da saída)."""
    with app.app_context():
        avisos = UserNotification.query.filter_by(
            event_type="colecao_participante_saiu"
        ).count()
        auditorias = AutorizacaoAudit.query.filter_by(
            alvo_tipo=ALVO_COLECAO, alvo_id=cid, evento="colecao_participante_saiu"
        ).count()
    return avisos, auditorias


# ── Sair × revogar / sair × sair ─────────────────────────────────────────────


class LeituraSeguidaDeCommitConcorrente:
    """Fake de ``shares_e_respostas_do_usuario``: devolve a leitura REAL e, logo
    depois, commita outro request pela conexão concorrente (antes da escrita)."""

    def __init__(
        self,
        leitura_real: Callable[..., Any],
        conexao: ConexaoConcorrente,
        *comandos: tuple[str, tuple[Any, ...]],
    ) -> None:
        self.leitura_real = leitura_real
        self.conexao = conexao
        self.comandos = comandos

    def __call__(self, *args: Any) -> Any:
        pares = self.leitura_real(*args)
        self.conexao.commitar(*self.comandos)
        return pares


def _sair_com_commit_no_meio(app, monkeypatch, user_id: int, cid: int, *comandos):
    monkeypatch.setattr(
        collection_invites,
        "shares_e_respostas_do_usuario",
        LeituraSeguidaDeCommitConcorrente(
            collection_invites.shares_e_respostas_do_usuario,
            ConexaoConcorrente(app),
            *comandos,
        ),
    )
    return post(app, user_id, f"/api/colecoes/{cid}/sair")


def test_corrida_sair_x_revogar_responde_404_limpo(app, ids, monkeypatch):
    cid = criar_colecao(app, ids.dono, [ids.do_dono])
    share = convidar(app, ids.dono, cid, user_id=ids.convidado)
    aceito(app, ids.convidado, cid)

    response = _sair_com_commit_no_meio(
        app, monkeypatch, ids.convidado, cid, *_revogacao(share["id"])
    )

    _assert_404_identico(response)
    with app.app_context():
        assert ProjectCollectionShareResposta.query.count() == 0
    assert _saidas_registradas(app, cid) == (0, 0)


def test_saida_ja_registrada_por_outro_request_responde_404_sem_reavisar(
    app, ids, monkeypatch
):
    cid = criar_colecao(app, ids.dono, [ids.do_dono])
    share = convidar(app, ids.dono, cid, user_id=ids.convidado)
    aceito(app, ids.convidado, cid)
    outra_saida = (
        "UPDATE project_collection_share_resposta SET status = 'saiu'"
        " WHERE share_id = ? AND user_id = ?",
        (share["id"], ids.convidado),
    )

    response = _sair_com_commit_no_meio(
        app, monkeypatch, ids.convidado, cid, outra_saida
    )

    _assert_404_identico(response)
    assert _saidas_registradas(app, cid) == (0, 0)


def _share_legado(app, ids, cid: int, user_id: int) -> int:
    with app.app_context():
        share = ProjectCollectionShare(
            collection_id=cid,
            user_id=user_id,
            papel="viewer",
            created_by_user_id=ids.dono,
            exige_aceite=False,
        )
        db.session.add(share)
        db.session.commit()
        return share.id


def test_corrida_sair_de_share_legado_x_revogar_nao_grava_saida_orfa(
    app, ids, monkeypatch
):
    """Share legado não tem resposta: a saída é INSERT, que no SQLite sem FK
    aceitaria share revogado no meio — a releitura dos shares fecha a janela."""
    cid = criar_colecao(app, ids.dono, [ids.do_dono])
    share_id = _share_legado(app, ids, cid, ids.convidado)

    response = _sair_com_commit_no_meio(
        app, monkeypatch, ids.convidado, cid, *_revogacao(share_id)
    )

    _assert_404_identico(response)
    with app.app_context():
        assert ProjectCollectionShareResposta.query.count() == 0
    assert _saidas_registradas(app, cid) == (0, 0)


# ── Incluir × revogar/rebaixar o editor ──────────────────────────────────────


class CommitConcorrenteAposOGate:
    """Fake de ``area_project_rank`` em ``adicionar_projeto``: roda DEPOIS do
    gate de papel e ANTES do INSERT; commita a mutação do dono nesse meio."""

    def __init__(
        self,
        real: Callable[..., int],
        conexao: ConexaoConcorrente,
        *comandos: tuple[str, tuple[Any, ...]],
    ) -> None:
        self.real = real
        self.conexao = conexao
        self.comandos = comandos

    def __call__(self, *args: Any) -> int:
        rank = self.real(*args)
        self.conexao.commitar(*self.comandos)
        return rank


def _mutacao_do_dono(como: str, share_id: int) -> tuple:
    if como == "revogar":
        return _revogacao(share_id)
    rebaixar = "UPDATE project_collection_share SET papel = 'viewer' WHERE id = ?"
    return ((rebaixar, (share_id,)),)


def _assert_recusa_da_inclusao(response, como: str) -> None:
    """Revogado no meio = sem papel: o MESMO 404 de quem já chega revogado
    (``carregar_acesso``); rebaixado segue vendo a coleção: 403."""
    if como == "revogar":
        _assert_404_identico(response)
        return
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize("como", ["revogar", "rebaixar"])
def test_inclusao_x_perda_do_editor_nao_deixa_item_orfao(app, ids, monkeypatch, como):
    cid = criar_colecao(app, ids.dono, [ids.do_dono])
    share = convidar(app, ids.dono, cid, papel="editor", user_id=ids.editor)
    aceito(app, ids.editor, cid)
    monkeypatch.setattr(
        project_collections,
        "area_project_rank",
        CommitConcorrenteAposOGate(
            project_collections.area_project_rank,
            ConexaoConcorrente(app),
            *_mutacao_do_dono(como, share["id"]),
        ),
    )

    response = post(
        app, ids.editor, f"/api/colecoes/{cid}/projetos", {"project_id": ids.do_ext}
    )

    _assert_recusa_da_inclusao(response, como)
    with app.app_context():
        assert (
            ProjectCollectionItem.query.filter_by(
                collection_id=cid, project_id=ids.do_ext
            ).count()
            == 0
        )


def test_inclusao_sem_corrida_continua_valendo_para_o_editor(app, ids):
    """Controle: a releitura não barra o editor que SEGUE editor."""
    cid = criar_colecao(app, ids.dono, [ids.do_dono])
    convidar(app, ids.dono, cid, papel="editor", user_id=ids.editor)
    aceito(app, ids.editor, cid)

    dados(
        post(
            app, ids.editor, f"/api/colecoes/{cid}/projetos", {"project_id": ids.do_ext}
        )
    )

    with app.app_context():
        item = ProjectCollectionItem.query.filter_by(
            collection_id=cid, project_id=ids.do_ext
        ).one()
        assert item.added_by_user_id == ids.editor
