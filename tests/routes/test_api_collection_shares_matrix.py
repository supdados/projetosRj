"""Matriz estado do share × superfície, pela API, e orçamento de queries do índice.

Um projeto de AREAA (com etapa datada e tarefa) entra na coleção do dono; o
destinatário é de OUTRA área, então tudo o que ele vê do projeto vem da
coleção. Para cada estado do share, TODAS as superfícies que listam ou abrem
projeto precisam concordar — um leitor esquecido sem o filtro de aceite
vazaria convite pendente/recusado na aplicação inteira (risco 1 da síntese).

Os estados com acesso são os casos positivos: provam que cada superfície de
fato enxerga o projeto via coleção, o que dá sentido aos negativos.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Callable

import pytest

from models import (
    Etapa,
    Project,
    ProjectCollectionShare,
    Task,
    UserNotification,
    db,
)
from tests.routes._collection_http_helpers import (
    IdsDoCenario,
    aceito,
    card_do_indice,
    cliente_de,
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
from tests.sql_query_counter import SqlQueryCounter

TITULO = "Matriz Visibilidade"
TAREFA = "Tarefa Matriz Zeta"

ESTADOS = (
    "legado",
    "pendente",
    "aceito",
    "recusado",
    "saiu",
    "revogado",
    "orgao_aceito",
    "orgao_pendente",
)
ESTADOS_COM_ACESSO = {"legado", "aceito", "orgao_aceito"}
# Aviso da coleção fica no sino enquanto há papel OU convite pendente.
ESTADOS_COM_AVISO = ESTADOS_COM_ACESSO | {"pendente", "orgao_pendente"}


@dataclass(frozen=True)
class AlvoDaMatriz:
    """Coleção e projeto observados; ``viewer`` é quem o estado alcança."""

    ids: IdsDoCenario
    collection_id: int
    viewer: int


def _semear_projeto_da_matriz(app, ids: IdsDoCenario) -> None:
    with app.app_context():
        projeto = db.session.get(Project, ids.do_dono)
        projeto.titulo = TITULO
        etapa = Etapa(
            descricao="Etapa da matriz",
            data_inicio=datetime.date(2026, 3, 1),
            data_fim=datetime.date(2026, 3, 20),
            project_id=projeto.id,
            ordem=0,
        )
        db.session.add(etapa)
        db.session.flush()
        db.session.add(
            Task(
                descricao=TAREFA,
                project_id=projeto.id,
                etapa_id=etapa.id,
                created_by_id=ids.dono,
            )
        )
        db.session.commit()


def _legado(app, ids: IdsDoCenario, cid: int) -> None:
    with app.app_context():
        db.session.add_all(
            [
                ProjectCollectionShare(
                    collection_id=cid,
                    user_id=ids.convidado,
                    papel="viewer",
                    created_by_user_id=ids.dono,
                    exige_aceite=False,
                ),
                UserNotification(
                    recipient_user_id=ids.convidado,
                    actor_user_id=ids.dono,
                    event_type="colecao_compartilhada",
                    title="Coleção compartilhada",
                    message="Compartilhada com você",
                    target_url=f"/colecoes/{cid}",
                ),
            ]
        )
        db.session.commit()


def _montar_estado(app, ids: IdsDoCenario, cid: int, estado: str) -> int:
    """Leva o share ao ``estado`` pela API; devolve quem observa."""
    if estado == "legado":
        _legado(app, ids, cid)
        return ids.convidado
    if estado.startswith("orgao_"):
        convidar(app, ids.dono, cid, orgao_id=ids.orgx)
        if estado == "orgao_aceito":
            aceito(app, ids.membro_a, cid)
        return ids.membro_a
    share = convidar(app, ids.dono, cid, user_id=ids.convidado)
    if estado == "recusado":
        dados(responder(app, ids.convidado, cid, "recusar"))
    if estado in ("aceito", "saiu", "revogado"):
        aceito(app, ids.convidado, cid)
    if estado == "saiu":
        dados(post(app, ids.convidado, f"/api/colecoes/{cid}/sair"))
    if estado == "revogado":
        url = f"/api/colecoes/{cid}/compartilhamentos/{share['id']}"
        dados(delete(app, ids.dono, url))
    return ids.convidado


def _status_ou_404(app, alvo: AlvoDaMatriz, path: str) -> bool:
    response = get(app, alvo.viewer, path)
    assert response.status_code in (200, 404), response.get_data(as_text=True)
    return response.status_code == 200


def _texto(app, alvo: AlvoDaMatriz, path: str) -> str:
    response = get(app, alvo.viewer, path)
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _na_lista(app, alvo: AlvoDaMatriz) -> bool:
    return alvo.ids.do_dono in ids_da_lista_de_projetos(app, alvo.viewer)


def _no_detalhe(app, alvo: AlvoDaMatriz) -> bool:
    return _status_ou_404(app, alvo, f"/api/projetos/{alvo.ids.do_dono}/detalhe")


def _na_busca(app, alvo: AlvoDaMatriz) -> bool:
    return TITULO in _texto(app, alvo, "/api/busca?q=Matriz&limit=all")


def _no_dashboard(app, alvo: AlvoDaMatriz) -> bool:
    return TITULO in _texto(app, alvo, "/api/dashboard")


def _nas_tarefas(app, alvo: AlvoDaMatriz) -> bool:
    return TAREFA in _texto(app, alvo, "/api/tarefas")


def _no_indice(app, alvo: AlvoDaMatriz) -> bool:
    return card_do_indice(app, alvo.viewer, alvo.collection_id) is not None


def _nos_projetos_da_colecao(app, alvo: AlvoDaMatriz) -> bool:
    path = f"/api/colecoes/{alvo.collection_id}/projetos"
    if not _status_ou_404(app, alvo, path):
        return False
    return TITULO in _texto(app, alvo, path)


def _no_cronograma(app, alvo: AlvoDaMatriz) -> bool:
    path = f"/api/colecoes/{alvo.collection_id}/cronograma"
    if not _status_ou_404(app, alvo, path):
        return False
    return TITULO in _texto(app, alvo, path)


SUPERFICIES_DE_PROJETO: dict[str, Callable[..., bool]] = {
    "lista_de_projetos": _na_lista,
    "detalhe": _no_detalhe,
    "busca": _na_busca,
    "dashboard": _no_dashboard,
    "tarefas": _nas_tarefas,
    "indice_de_colecoes": _no_indice,
    "projetos_da_colecao": _nos_projetos_da_colecao,
    "cronograma": _no_cronograma,
}


def _aviso_no_sino(app, alvo: AlvoDaMatriz) -> bool:
    itens = dados(get(app, alvo.viewer, "/api/notificacoes"))["items"]
    destino = f"/colecoes/{alvo.collection_id}"
    return any(item["target_url"] == destino for item in itens)


@pytest.fixture
def ids(app) -> IdsDoCenario:
    ids = semear_ids(app)
    _semear_projeto_da_matriz(app, ids)
    return ids


@pytest.mark.parametrize("estado", ESTADOS)
def test_estado_do_share_decide_todas_as_superficies(app, ids, estado):
    cid = criar_colecao(app, ids.dono, [ids.do_dono])
    alvo = AlvoDaMatriz(ids, cid, _montar_estado(app, ids, cid, estado))
    esperado = estado in ESTADOS_COM_ACESSO

    vistos = {nome: ver(app, alvo) for nome, ver in SUPERFICIES_DE_PROJETO.items()}

    assert vistos == {nome: esperado for nome in SUPERFICIES_DE_PROJETO}
    assert _aviso_no_sino(app, alvo) is (estado in ESTADOS_COM_AVISO)


# ── Orçamento de queries do índice (lado do dono) ────────────────────────────


def _dono_com_colecoes_compartilhadas(
    app, ids: IdsDoCenario, total: int, *, inicio: int = 0
) -> None:
    for indice in range(inicio, inicio + total):
        cid = criar_colecao(app, ids.dono, [ids.do_dono], nome=f"Lote {indice}")
        convidar(app, ids.dono, cid, user_id=ids.convidado)
        convidar(app, ids.dono, cid, papel="editor", orgao_id=ids.orgx)
        aceito(app, ids.membro_a, cid)


def _queries_do_indice(app, user_id: int) -> int:
    client = cliente_de(app, user_id)
    assert client.get("/api/colecoes").status_code == 200  # aquece a Favoritos
    with app.app_context():
        engine = db.engine
    with SqlQueryCounter(engine) as queries:
        response = client.get("/api/colecoes")
    assert response.status_code == 200
    return queries.total


def test_indice_do_dono_com_compartilhamentos_custa_queries_constantes(app, ids):
    _dono_com_colecoes_compartilhadas(app, ids, 2)
    com_duas = _queries_do_indice(app, ids.dono)

    _dono_com_colecoes_compartilhadas(app, ids, 6, inicio=2)
    com_oito = _queries_do_indice(app, ids.dono)

    assert com_oito == com_duas
    assert com_oito <= 20
    card = card_do_indice(app, ids.dono, _ultima_colecao_do_dono(app, ids))
    assert card["compartilhada"] is True


def _ultima_colecao_do_dono(app, ids: IdsDoCenario) -> int:
    colecoes = dados(get(app, ids.dono, "/api/colecoes"))["colecoes"]
    return max(card["id"] for card in colecoes if card["tipo"] == "custom")


def test_indice_do_membro_com_destinatarios_custa_queries_constantes(app, ids):
    _dono_com_colecoes_compartilhadas(app, ids, 2)
    com_duas = _queries_do_indice(app, ids.membro_a)

    _dono_com_colecoes_compartilhadas(app, ids, 6, inicio=2)
    com_oito = _queries_do_indice(app, ids.membro_a)

    assert com_oito == com_duas
    assert com_oito <= 20
