"""Gates HTTP comuns às rotas de coleção (índice, itens, shares e convites).

Extraído de ``routes/api/collections.py`` para que ``collection_invites.py``
use os MESMOS gates e a MESMA tradução de erro — o 404 anti-enumeração precisa
sair idêntico em todas as rotas de coleção — sem importar privados de outro
módulo, e para manter os dois arquivos abaixo de 500 linhas.

Contrato de erro (hierarquia de ``services.collection_errors``):
``ProjetoForaDoEscopo``/``ConviteIndisponivel`` → 404 ``fail_not_found``;
``ColecaoSemPermissao`` → 403; o resto de ``ColecaoInvalida`` → 422.
"""

from __future__ import annotations

from typing import Any, Callable

from flask import Response, g, request

from models import PAPEL_SHARE_EDITOR, PAPEL_SHARE_VIEWER, ProjectCollection, db
from services.collection_areas import areas_por_colecao
from services.collection_shares import collection_ids_com_share
from services.project_collections import (
    PAPEL_COLECAO_DONO,
    ColecaoInvalida,
    ColecaoSemPermissao,
    ProjetoForaDoEscopo,
    colecao_visivel_para,
    collection_rollups,
)

from .collection_serializers import serialize_colecao_card
from .envelope import fail, fail_internal, fail_not_found

ApiResponse = Response | tuple[Response, int]
AcessoColecao = tuple[ProjectCollection, str]

PAPEIS_LEITURA = (PAPEL_COLECAO_DONO, PAPEL_SHARE_EDITOR, PAPEL_SHARE_VIEWER)
PAPEIS_ITENS = (PAPEL_COLECAO_DONO, PAPEL_SHARE_EDITOR)
PAPEIS_DONO = (PAPEL_COLECAO_DONO,)

SEM_PERMISSAO = "Você não tem permissão para esta ação na coleção."


def erro_de_colecao(exc: ColecaoInvalida) -> tuple[Response, int]:
    """Fora do escopo/convite indisponível → 404; papel insuficiente → 403; resto 422.

    Exemplo: ``except ColecaoInvalida as exc: return erro_de_colecao(exc)``.
    """
    if isinstance(exc, ProjetoForaDoEscopo):
        return fail_not_found()
    if isinstance(exc, ColecaoSemPermissao):
        return fail(SEM_PERMISSAO, status=403, code="forbidden")
    return fail(str(exc), status=422, code="validation")


def ler_json() -> tuple[dict[str, Any] | None, Any]:
    """Corpo JSON objeto ou ``(None, 422)``. Exemplo: ``payload, erro = ler_json()``."""
    payload = request.get_json(silent=True)
    if isinstance(payload, dict):
        return payload, None
    return None, fail(
        "Corpo JSON inválido; esperado um objeto.", status=422, code="validation"
    )


def carregar_acesso(
    collection_id: int, papeis: tuple[str, ...]
) -> tuple[AcessoColecao | None, Any]:
    """Coleção + papel do ator; 404 se ele não a alcança, 403 se o papel não cobre.

    Convite pendente NÃO alcança (``colecao_visivel_para`` → ``None``): quem só
    foi convidado toma o mesmo 404 de coleção inexistente. Exemplo:
    ``acesso, erro = carregar_acesso(cid, PAPEIS_DONO)``.
    """
    acesso = colecao_visivel_para(g.user, collection_id)
    if acesso is None:
        return None, fail_not_found()
    if acesso[1] not in papeis:
        return None, fail(SEM_PERMISSAO, status=403, code="forbidden")
    return acesso, None


def mutar(acao: Callable[[], ApiResponse], log_label: str) -> ApiResponse:
    """Monta a resposta dentro da transação e comita; traduz erros de domínio.

    Exemplo: ``return mutar(lambda: ok(fazer()), "aceitar convite de coleção")``.
    """
    try:
        resposta = acao()
        db.session.commit()
    except ColecaoInvalida as exc:
        db.session.rollback()
        return erro_de_colecao(exc)
    except Exception as exc:
        db.session.rollback()
        return fail_internal(exc, log_label)
    return resposta


def cards_das_colecoes(acessos: list[AcessoColecao]) -> list[dict[str, Any]]:
    """Cards do índice em lote: rollups (1 query) + áreas (1 query) + flag
    ``compartilhada`` (1 query) — constante em N coleções (orçamento ≤ 20 do
    índice em ``tests/routes/test_read_materialization.py``).
    """
    ids = [colecao.id for colecao, _ in acessos]
    rollups = collection_rollups(ids, g.user)
    areas = areas_por_colecao(ids, g.user)
    com_share = collection_ids_com_share(ids)
    return [
        serialize_colecao_card(
            colecao,
            rollups[colecao.id],
            papel=papel,
            compartilhada=colecao.id in com_share,
            areas=areas.get(colecao.id, []),
        )
        for colecao, papel in acessos
    ]


def resumo_da_colecao(colecao: ProjectCollection, papel: str) -> dict[str, Any]:
    """Card de UMA coleção (criar, editar, aceitar, página interna)."""
    return cards_das_colecoes([(colecao, papel)])[0]
