"""Atalhos HTTP dos testes de coleção compartilhada (contrato e matriz).

O cenário vem de ``tests/_collection_share_helpers.semear_cenario_convite``
(dono/colega em AREAA, convidado/editor em EXT, membros em ORGX), mas aqui só
os IDS atravessam a fronteira: cada request abre o próprio app context, e
segurar a sessão do seed aberta travaria o SQLite dos requests.
"""

from __future__ import annotations

import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from typing import Any

from flask import Flask
from flask.testing import FlaskClient
from werkzeug.test import TestResponse

from tests._collection_share_helpers import semear_cenario_convite

NOT_FOUND_BODY = {
    "ok": False,
    "error": {"code": "not_found", "message": "Recurso não encontrado."},
}


@dataclass(frozen=True)
class IdsDoCenario:
    """Ids do cenário de convite (ver ``CenarioConvite``)."""

    dono: int
    colega: int
    convidado: int
    editor: int
    membro_a: int
    membro_b: int
    area: int
    ext: int
    orgx: int
    do_dono: int
    do_ext: int
    so_convite: int


def semear_ids(app: Flask) -> IdsDoCenario:
    """Semeia e commita o cenário; devolve só os ids (fora do app context)."""
    with app.app_context():
        cenario = semear_cenario_convite()
        return IdsDoCenario(
            dono=cenario.dono.id,
            colega=cenario.colega.id,
            convidado=cenario.convidado.id,
            editor=cenario.editor.id,
            membro_a=cenario.membro_a.id,
            membro_b=cenario.membro_b.id,
            area=cenario.area_id,
            ext=cenario.ext_id,
            orgx=cenario.orgx_id,
            do_dono=cenario.do_dono_id,
            do_ext=cenario.do_ext_id,
            so_convite=cenario.so_convite_id,
        )


def cliente_de(app: Flask, user_id: int) -> FlaskClient:
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["login_at"] = time.time()
    return client


def get(app: Flask, user_id: int, path: str) -> TestResponse:
    return cliente_de(app, user_id).get(path)


def post(
    app: Flask, user_id: int, path: str, body: dict[str, Any] | None = None
) -> TestResponse:
    return cliente_de(app, user_id).post(path, json=body or {})


def delete(app: Flask, user_id: int, path: str) -> TestResponse:
    return cliente_de(app, user_id).delete(path)


def dados(response: TestResponse, status: int = 200) -> Any:
    """``data`` do envelope, exigindo o status esperado."""
    assert response.status_code == status, response.get_data(as_text=True)
    payload = response.get_json()
    assert payload["ok"] is True
    return payload["data"]


def criar_colecao(
    app: Flask, dono_id: int, project_ids: list[int], nome: str = "Compartilhada"
) -> int:
    body = {"nome": nome, "icone": "camadas", "cor": "primary"}
    body["project_ids"] = project_ids
    return dados(post(app, dono_id, "/api/colecoes", body))["colecao"]["id"]


def convidar(
    app: Flask,
    dono_id: int,
    collection_id: int,
    *,
    papel: str = "viewer",
    **destino: int,
) -> dict[str, Any]:
    """POST do dono em ``.../compartilhamentos``; devolve o share serializado."""
    response = post(
        app,
        dono_id,
        f"/api/colecoes/{collection_id}/compartilhamentos",
        {"papel": papel, **destino},
    )
    return dados(response)["compartilhamento"]


def responder(app: Flask, user_id: int, collection_id: int, acao: str) -> TestResponse:
    """``acao`` = ``aceitar`` | ``recusar``."""
    return post(app, user_id, f"/api/colecoes/{collection_id}/convite/{acao}")


def aceito(app: Flask, user_id: int, collection_id: int) -> dict[str, Any]:
    return dados(responder(app, user_id, collection_id, "aceitar"))


def ids_dos_projetos_da_colecao(
    app: Flask, user_id: int, collection_id: int
) -> set[int]:
    linhas = dados(get(app, user_id, f"/api/colecoes/{collection_id}/projetos"))
    return {linha["id"] for linha in linhas["projetos"]}


def card_do_indice(
    app: Flask, user_id: int, collection_id: int
) -> dict[str, Any] | None:
    colecoes = dados(get(app, user_id, "/api/colecoes"))["colecoes"]
    return next((card for card in colecoes if card["id"] == collection_id), None)


def ids_da_lista_de_projetos(app: Flask, user_id: int, query: str = "") -> set[int]:
    data = dados(get(app, user_id, f"/api/projetos?status=&per_page=100{query}"))
    return {projeto["id"] for projeto in data["projetos"]}


class ConexaoConcorrente:
    """Outra conexão ao MESMO arquivo SQLite do teste: o commit dela simula um
    request paralelo no meio do request em teste (o banco usa NullPool e, no
    pysqlite, a transação do request só começa na primeira escrita)."""

    def __init__(self, app: Flask) -> None:
        uri = str(app.config["SQLALCHEMY_DATABASE_URI"])
        self.caminho = uri.removeprefix("sqlite:///")

    def commitar(self, *comandos: tuple[str, tuple[Any, ...]]) -> None:
        with closing(sqlite3.connect(self.caminho)) as conexao, conexao:
            for sql, parametros in comandos:
                conexao.execute(sql, parametros)
