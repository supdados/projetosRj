"""Endpoints JSON das COLEÇÕES de projetos (Fase 1 — coleções pessoais).

As 8 rotas da §6 do plano, todas no envelope canônico e anexadas ao ``main_bp``
ÚNICO (nenhuma URL existente muda):

    - ``GET    /api/colecoes``                        — índice (Favoritos 1ª).
    - ``POST   /api/colecoes``                        — cria coleção + itens.
    - ``PUT    /api/colecoes/<cid>``                  — renomeia/reestiliza.
    - ``DELETE /api/colecoes/<cid>``                  — apaga (itens junto).
    - ``GET    /api/colecoes/<cid>/projetos``         — página interna.
    - ``POST   /api/colecoes/<cid>/projetos``         — adiciona projeto.
    - ``DELETE /api/colecoes/<cid>/projetos/<pid>``   — remove projeto.
    - ``POST   /api/projetos/<pid>/favorito``         — toggle da estrela.

O toggle mora aqui (e não em ``projects_write``) por ser açúcar sobre a coleção
Favoritos: o cliente nunca precisa conhecer o id dela.

Rotas finas: parse do payload aqui, regra em ``services/project_collections.py``,
commit/rollback nesta camada. Coleção de OUTRO dono responde ``fail_not_found``
(nunca 403) e projeto invisível ao ator também — mesmo contrato anti-enumeração
de S5/F4-2b.
"""

from __future__ import annotations

from typing import Any, Callable

from flask import Response, g, request

from catalogs.collection_identity import (
    DEFAULT_COLLECTION_COLOR,
    DEFAULT_COLLECTION_ICON,
)
from models import ProjectCollection, db
from services.project_collections import (
    ColecaoInvalida,
    ProjetoForaDoEscopo,
    adicionar_projeto,
    apagar_colecao,
    colecao_do_usuario,
    colecao_project_rows,
    collection_rollups,
    criar_colecao,
    editar_colecao,
    favoritos_existente,
    get_or_create_favoritos,
    listar_colecoes,
    remover_projeto,
    toggle_favorito,
)

from ..blueprint import main_bp
from .envelope import fail, fail_internal, fail_not_found, ok
from .negotiation import api_login_required
from .serializers import serialize_colecao_resumo, serialize_project_collection_row

_ApiResponse = Response | tuple[Response, int]

_CAMPOS_EDITAVEIS = ("nome", "descricao", "icone", "cor")


# ── Helpers ──────────────────────────────────────────────────────────────────


def _erro_de_colecao(exc: ColecaoInvalida) -> tuple[Response, int]:
    """Projeto fora do escopo vira 404 anti-enumeração; o resto é 422."""
    if isinstance(exc, ProjetoForaDoEscopo):
        return fail_not_found()
    return fail(str(exc), status=422, code="validation")


def _ler_json() -> tuple[dict[str, Any] | None, Any]:
    payload = request.get_json(silent=True)
    if isinstance(payload, dict):
        return payload, None
    return None, fail(
        "Corpo JSON inválido; esperado um objeto.", status=422, code="validation"
    )


def _load_colecao(collection_id: int) -> tuple[ProjectCollection | None, Any]:
    """Coleção do usuário corrente; de outro dono é indistinguível de inexistente."""
    colecao = colecao_do_usuario(g.user.id, collection_id)
    if colecao is None:
        return None, fail_not_found()
    return colecao, None


def _mutar(acao: Callable[[], _ApiResponse], log_label: str) -> _ApiResponse:
    """Monta a resposta dentro da transação e comita; traduz erros de domínio."""
    try:
        resposta = acao()
        db.session.commit()
    except ColecaoInvalida as exc:
        db.session.rollback()
        return _erro_de_colecao(exc)
    except Exception as exc:
        db.session.rollback()
        return fail_internal(exc, log_label)
    return resposta


def _resumo(colecao: ProjectCollection) -> dict[str, Any]:
    rollup = collection_rollups([colecao.id], g.user)[colecao.id]
    return serialize_colecao_resumo(colecao, rollup)


def _parse_project_id(raw: object) -> int:
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise ColecaoInvalida(
            f"project_id inválido: {raw!r}; esperado o id inteiro do projeto"
        )
    return raw


def _parse_project_ids(raw: object) -> list[int]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ColecaoInvalida(
            f"project_ids inválido: {raw!r}; esperado lista de ids inteiros"
        )
    return [_parse_project_id(item) for item in raw]


# ── Índice e mutação da coleção ──────────────────────────────────────────────


@main_bp.route("/api/colecoes", methods=["GET"])
@api_login_required
def api_colecoes_list() -> _ApiResponse:
    """Lista as coleções do usuário com rollup agregado; Favoritos sempre 1ª.

    Leitura pura: o caminho comum não comita. Só o primeiro acesso — quando a
    Favoritos precisa nascer — faz um commit isolado dessa criação.
    """
    try:
        _garantir_favoritos()
        return ok({"colecoes": _indice_payload()})
    except Exception as exc:
        db.session.rollback()
        return fail_internal(exc, "listar coleções")


def _garantir_favoritos() -> None:
    if favoritos_existente(g.user.id) is not None:
        return
    get_or_create_favoritos(g.user.id)
    db.session.commit()


def _indice_payload() -> list[dict[str, Any]]:
    colecoes = listar_colecoes(g.user.id)
    rollups = collection_rollups([colecao.id for colecao in colecoes], g.user)
    return [
        serialize_colecao_resumo(colecao, rollups[colecao.id]) for colecao in colecoes
    ]


@main_bp.route("/api/colecoes", methods=["POST"])
@api_login_required
def api_colecao_criar() -> _ApiResponse:
    """Cria coleção custom: ``{nome, descricao?, icone, cor, project_ids?[]}``.

    Um único POST cobre os dois passos do modal (identidade + seleção); qualquer
    projeto fora do escopo do ator invalida a criação inteira.
    """
    payload, invalid = _ler_json()
    if invalid:
        return invalid
    return _mutar(
        lambda: ok({"colecao": _resumo(_criar_da_payload(payload))}), "criar coleção"
    )


def _criar_da_payload(payload: dict[str, Any]) -> ProjectCollection:
    return criar_colecao(
        g.user,
        payload.get("nome"),
        payload.get("descricao"),
        payload.get("icone") or DEFAULT_COLLECTION_ICON,
        payload.get("cor") or DEFAULT_COLLECTION_COLOR,
        _parse_project_ids(payload.get("project_ids")),
    )


@main_bp.route("/api/colecoes/<int:collection_id>", methods=["PUT"])
@api_login_required
def api_colecao_atualizar(collection_id: int) -> _ApiResponse:
    """Edita nome/descrição/ícone/cor; campos ausentes ficam intactos.

    Favoritos é coleção de sistema: qualquer edição responde 422.
    """
    colecao, missing = _load_colecao(collection_id)
    if missing:
        return missing
    payload, invalid = _ler_json()
    if invalid:
        return invalid
    campos = {campo: payload[campo] for campo in _CAMPOS_EDITAVEIS if campo in payload}
    return _mutar(
        lambda: ok({"colecao": _resumo(editar_colecao(colecao, **campos))}),
        "editar coleção",
    )


@main_bp.route("/api/colecoes/<int:collection_id>", methods=["DELETE"])
@api_login_required
def api_colecao_apagar(collection_id: int) -> _ApiResponse:
    """Apaga a coleção e seus itens; os projetos ficam intactos (422 em Favoritos)."""
    colecao, missing = _load_colecao(collection_id)
    if missing:
        return missing
    return _mutar(lambda: _apagar_e_confirmar(colecao), "apagar coleção")


def _apagar_e_confirmar(colecao: ProjectCollection) -> _ApiResponse:
    apagar_colecao(colecao)
    return ok()


# ── Itens da coleção ─────────────────────────────────────────────────────────


@main_bp.route("/api/colecoes/<int:collection_id>/projetos", methods=["GET"])
@api_login_required
def api_colecao_projetos_list(collection_id: int) -> _ApiResponse:
    """Página interna: cabeçalho da coleção + linhas dos projetos visíveis."""
    colecao, missing = _load_colecao(collection_id)
    if missing:
        return missing
    linhas = colecao_project_rows(colecao, g.user)
    return ok(
        {
            "colecao": _resumo(colecao),
            "projetos": [serialize_project_collection_row(linha) for linha in linhas],
        }
    )


@main_bp.route("/api/colecoes/<int:collection_id>/projetos", methods=["POST"])
@api_login_required
def api_colecao_projeto_adicionar(collection_id: int) -> _ApiResponse:
    """Adiciona ``{project_id}`` à coleção; duplicado é sucesso (idempotente)."""
    colecao, missing = _load_colecao(collection_id)
    if missing:
        return missing
    payload, invalid = _ler_json()
    if invalid:
        return invalid
    return _mutar(
        lambda: _adicionar_e_confirmar(colecao, payload), "adicionar projeto à coleção"
    )


def _adicionar_e_confirmar(
    colecao: ProjectCollection, payload: dict[str, Any]
) -> _ApiResponse:
    adicionar_projeto(
        colecao, _parse_project_id(payload.get("project_id")), ator=g.user
    )
    return ok()


@main_bp.route(
    "/api/colecoes/<int:collection_id>/projetos/<int:project_id>", methods=["DELETE"]
)
@api_login_required
def api_colecao_projeto_remover(collection_id: int, project_id: int) -> _ApiResponse:
    """Remove o projeto da coleção; projeto que não estava lá também responde ok."""
    colecao, missing = _load_colecao(collection_id)
    if missing:
        return missing
    return _mutar(
        lambda: _remover_e_confirmar(colecao, project_id),
        "remover projeto da coleção",
    )


def _remover_e_confirmar(colecao: ProjectCollection, project_id: int) -> _ApiResponse:
    remover_projeto(colecao, project_id)
    return ok()


# ── Atalho de favorito (estrela do card) ─────────────────────────────────────


@main_bp.route("/api/projetos/<int:project_id>/favorito", methods=["POST"])
@api_login_required
def api_projeto_favorito_toggle(project_id: int) -> _ApiResponse:
    """Alterna o projeto na coleção Favoritos e devolve o estado resultante.

    Projeto inexistente ou fora do escopo responde 404 anti-enumeração.
    """
    return _mutar(
        lambda: ok({"favorito": toggle_favorito(g.user, project_id)}),
        "alternar favorito do projeto",
    )
