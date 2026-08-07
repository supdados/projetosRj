"""Endpoints JSON das COLEÇÕES de projetos (Fases 1 e 2).

As rotas da §6 do plano de coleções, todas no envelope canônico e anexadas ao
``main_bp`` ÚNICO (nenhuma URL existente muda):

    - ``GET    /api/colecoes``                        — índice (Favoritos 1ª).
    - ``POST   /api/colecoes``                        — cria coleção + itens
      (``sugestao_id`` opcional marca a sugestão de IA como aceita).
    - ``PUT    /api/colecoes/<cid>``                  — renomeia/reestiliza.
    - ``DELETE /api/colecoes/<cid>``                  — apaga (itens junto).
    - ``GET    /api/colecoes/<cid>/projetos``         — página interna.
    - ``POST   /api/colecoes/<cid>/projetos``         — adiciona projeto.
    - ``DELETE /api/colecoes/<cid>/projetos/<pid>``   — remove projeto.
    - ``POST   /api/projetos/<pid>/favorito``         — toggle da estrela.
    - ``GET    /api/colecoes/<cid>/compartilhamentos``            — lista shares.
    - ``POST   /api/colecoes/<cid>/compartilhamentos``            — concede/upsert.
    - ``DELETE /api/colecoes/<cid>/compartilhamentos/<sid>``      — revoga.
    - ``GET    /api/colecoes/<cid>/cronograma``       — Gantt das etapas.

As rotas de SUGESTÕES por IA (``/api/colecoes/sugestoes*``) moram em
``routes/api/collection_suggestions.py`` (mesmo ``main_bp``).

O toggle mora aqui (e não em ``projects_write``) por ser açúcar sobre a coleção
Favoritos: o cliente nunca precisa conhecer o id dela.

Rotas finas: parse do payload aqui, regra em ``services/project_collections.py``,
commit/rollback nesta camada. Papel decide o gate: leitura (dono/viewer/editor),
itens (dono/editor) e gestão da coleção e dos shares (só dono). Quem NÃO alcança
a coleção recebe ``fail_not_found`` (nunca 403) — mesmo contrato anti-enumeração
de S5/F4-2b, que vale também para projeto invisível ao ator.
"""

from __future__ import annotations

from typing import Any, Callable

from flask import Response, current_app, g, request

from catalogs.collection_identity import (
    DEFAULT_COLLECTION_COLOR,
    DEFAULT_COLLECTION_ICON,
)
from models import (
    PAPEL_SHARE_EDITOR,
    PAPEL_SHARE_VIEWER,
    ProjectCollection,
    db,
)
from services.ai import marcar_aceita
from services.project_collections import (
    ColecaoInvalida,
    ColecaoSemPermissao,
    PAPEL_COLECAO_DONO,
    ProjetoForaDoEscopo,
    adicionar_projeto,
    apagar_colecao,
    colecao_cronograma_rows,
    colecao_project_rows,
    colecao_visivel_para,
    collection_ids_com_share,
    collection_rollups,
    compartilhar_colecao,
    criar_colecao,
    editar_colecao,
    favoritos_existente,
    get_or_create_favoritos,
    listar_colecoes,
    listar_shares,
    remover_projeto,
    revogar_share,
    toggle_favorito,
)
from ..blueprint import main_bp
from .envelope import fail, fail_internal, fail_not_found, ok
from .negotiation import api_login_required
from .serializers import (
    serialize_colecao_resumo,
    serialize_colecao_share,
    serialize_cronograma_projeto,
    serialize_project_collection_row,
)

_ApiResponse = Response | tuple[Response, int]
_Acesso = tuple[ProjectCollection, str]

_CAMPOS_EDITAVEIS = ("nome", "descricao", "icone", "cor")

_PAPEIS_LEITURA = (PAPEL_COLECAO_DONO, PAPEL_SHARE_EDITOR, PAPEL_SHARE_VIEWER)
_PAPEIS_ITENS = (PAPEL_COLECAO_DONO, PAPEL_SHARE_EDITOR)
_PAPEIS_DONO = (PAPEL_COLECAO_DONO,)

_SEM_PERMISSAO = "Você não tem permissão para esta ação na coleção."


# ── Helpers ──────────────────────────────────────────────────────────────────


def _erro_de_colecao(exc: ColecaoInvalida) -> tuple[Response, int]:
    """Projeto fora do escopo vira 404; papel insuficiente 403; o resto é 422."""
    if isinstance(exc, ProjetoForaDoEscopo):
        return fail_not_found()
    if isinstance(exc, ColecaoSemPermissao):
        return fail(_SEM_PERMISSAO, status=403, code="forbidden")
    return fail(str(exc), status=422, code="validation")


def _ler_json() -> tuple[dict[str, Any] | None, Any]:
    payload = request.get_json(silent=True)
    if isinstance(payload, dict):
        return payload, None
    return None, fail(
        "Corpo JSON inválido; esperado um objeto.", status=422, code="validation"
    )


def _load_acesso(
    collection_id: int, papeis: tuple[str, ...]
) -> tuple[_Acesso | None, Any]:
    """Coleção + papel do ator; 404 se ele não a alcança, 403 se o papel não cobre."""
    acesso = colecao_visivel_para(g.user, collection_id)
    if acesso is None:
        return None, fail_not_found()
    if acesso[1] not in papeis:
        return None, fail(_SEM_PERMISSAO, status=403, code="forbidden")
    return acesso, None


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


def _resumo(colecao: ProjectCollection, papel: str) -> dict[str, Any]:
    rollup = collection_rollups([colecao.id], g.user)[colecao.id]
    return serialize_colecao_resumo(
        colecao,
        rollup,
        papel=papel,
        compartilhada=bool(collection_ids_com_share([colecao.id])),
    )


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


def _parse_destinatario_id(raw: object, campo: str) -> int | None:
    if raw is None:
        return None
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise ColecaoInvalida(f"{campo} inválido: {raw!r}; esperado id inteiro")
    return raw


def _parse_share_spec(raw: object) -> dict[str, Any]:
    """Destinatário + papel do share; XOR e whitelist de papel ficam no service."""
    if not isinstance(raw, dict):
        raise ColecaoInvalida(
            f"compartilhamento inválido: {raw!r}; esperado objeto com "
            "user_id ou orgao_id e papel"
        )
    return {
        "user_id": _parse_destinatario_id(raw.get("user_id"), "user_id"),
        "orgao_id": _parse_destinatario_id(raw.get("orgao_id"), "orgao_id"),
        "papel": raw.get("papel"),
    }


def _parse_compartilhamentos(raw: object) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ColecaoInvalida(
            f"compartilhamentos inválido: {raw!r}; esperado lista de objetos"
        )
    return [_parse_share_spec(item) for item in raw]


# ── Índice e mutação da coleção ──────────────────────────────────────────────


@main_bp.route("/api/colecoes", methods=["GET"])
@api_login_required
def api_colecoes_list() -> _ApiResponse:
    """Lista minhas coleções (Favoritos 1ª) + as compartilhadas comigo, com rollup.

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
    acessos = listar_colecoes(g.user.id)
    ids = [colecao.id for colecao, _ in acessos]
    rollups = collection_rollups(ids, g.user)
    compartilhadas = collection_ids_com_share(ids)
    return [
        serialize_colecao_resumo(
            colecao,
            rollups[colecao.id],
            papel=papel,
            compartilhada=colecao.id in compartilhadas,
        )
        for colecao, papel in acessos
    ]


@main_bp.route("/api/colecoes", methods=["POST"])
@api_login_required
def api_colecao_criar() -> _ApiResponse:
    """Cria coleção custom: ``{nome, descricao?, icone, cor, project_ids?[],
    compartilhamentos?[], sugestao_id?}``.

    Um único POST cobre os dois passos do modal (identidade + seleção); sem
    ``compartilhamentos`` a coleção nasce pessoal ("Só eu"). Qualquer projeto
    fora do escopo do ator invalida a criação inteira. ``sugestao_id`` marca a
    sugestão de IA como aceita no mesmo commit; valor inválido só loga warning.
    """
    payload, invalid = _ler_json()
    if invalid:
        return invalid
    return _mutar(
        lambda: ok(
            {
                "colecao": _resumo(
                    _criar_e_vincular_sugestao(payload), PAPEL_COLECAO_DONO
                )
            }
        ),
        "criar coleção",
    )


def _criar_e_vincular_sugestao(payload: dict[str, Any]) -> ProjectCollection:
    colecao = _criar_da_payload(payload)
    _marcar_sugestao_aceita(payload.get("sugestao_id"), colecao.id)
    return colecao


def _marcar_sugestao_aceita(raw: object, colecao_id: int) -> None:
    """Bookkeeping tolerante (plano IA Fase 2 §3.3): nunca derruba a criação."""
    if raw is None:
        return
    if not isinstance(raw, int) or isinstance(raw, bool):
        current_app.logger.warning(
            "sugestao_id inválido no aceite: %r; esperado id inteiro", raw
        )
        return
    marcar_aceita(g.user.id, raw, colecao_id)


def _criar_da_payload(payload: dict[str, Any]) -> ProjectCollection:
    return criar_colecao(
        g.user,
        payload.get("nome"),
        payload.get("descricao"),
        payload.get("icone") or DEFAULT_COLLECTION_ICON,
        payload.get("cor") or DEFAULT_COLLECTION_COLOR,
        _parse_project_ids(payload.get("project_ids")),
        _parse_compartilhamentos(payload.get("compartilhamentos")),
    )


@main_bp.route("/api/colecoes/<int:collection_id>", methods=["PUT"])
@api_login_required
def api_colecao_atualizar(collection_id: int) -> _ApiResponse:
    """Edita nome/descrição/ícone/cor; campos ausentes ficam intactos.

    Só o dono edita (403 para quem a vê via share); Favoritos é coleção de
    sistema: qualquer edição responde 422.
    """
    acesso, missing = _load_acesso(collection_id, _PAPEIS_DONO)
    if missing:
        return missing
    payload, invalid = _ler_json()
    if invalid:
        return invalid
    campos = {campo: payload[campo] for campo in _CAMPOS_EDITAVEIS if campo in payload}
    return _mutar(
        lambda: ok({"colecao": _editar_e_resumir(acesso[0], campos)}),
        "editar coleção",
    )


def _editar_e_resumir(
    colecao: ProjectCollection, campos: dict[str, Any]
) -> dict[str, Any]:
    return _resumo(editar_colecao(colecao, **campos), PAPEL_COLECAO_DONO)


@main_bp.route("/api/colecoes/<int:collection_id>", methods=["DELETE"])
@api_login_required
def api_colecao_apagar(collection_id: int) -> _ApiResponse:
    """Apaga a coleção e seus itens; os projetos ficam intactos (422 em Favoritos)."""
    acesso, missing = _load_acesso(collection_id, _PAPEIS_DONO)
    if missing:
        return missing
    return _mutar(lambda: _apagar_e_confirmar(acesso[0]), "apagar coleção")


def _apagar_e_confirmar(colecao: ProjectCollection) -> _ApiResponse:
    apagar_colecao(colecao)
    return ok()


# ── Itens da coleção ─────────────────────────────────────────────────────────


@main_bp.route("/api/colecoes/<int:collection_id>/projetos", methods=["GET"])
@api_login_required
def api_colecao_projetos_list(collection_id: int) -> _ApiResponse:
    """Página interna: cabeçalho da coleção + linhas dos projetos visíveis."""
    acesso, missing = _load_acesso(collection_id, _PAPEIS_LEITURA)
    if missing:
        return missing
    colecao, papel = acesso
    linhas = colecao_project_rows(colecao, g.user)
    return ok(
        {
            "colecao": _resumo(colecao, papel),
            "projetos": [serialize_project_collection_row(linha) for linha in linhas],
        }
    )


@main_bp.route("/api/colecoes/<int:collection_id>/projetos", methods=["POST"])
@api_login_required
def api_colecao_projeto_adicionar(collection_id: int) -> _ApiResponse:
    """Adiciona ``{project_id}`` à coleção; duplicado é sucesso (idempotente)."""
    acesso, missing = _load_acesso(collection_id, _PAPEIS_ITENS)
    if missing:
        return missing
    payload, invalid = _ler_json()
    if invalid:
        return invalid
    return _mutar(
        lambda: _adicionar_e_confirmar(acesso[0], payload),
        "adicionar projeto à coleção",
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
    acesso, missing = _load_acesso(collection_id, _PAPEIS_ITENS)
    if missing:
        return missing
    return _mutar(
        lambda: _remover_e_confirmar(acesso[0], project_id),
        "remover projeto da coleção",
    )


def _remover_e_confirmar(colecao: ProjectCollection, project_id: int) -> _ApiResponse:
    remover_projeto(colecao, project_id, ator=g.user)
    return ok()


# ── Compartilhamentos (só o dono) ────────────────────────────────────────────


@main_bp.route("/api/colecoes/<int:collection_id>/compartilhamentos", methods=["GET"])
@api_login_required
def api_colecao_shares_list(collection_id: int) -> _ApiResponse:
    """Lista quem enxerga a coleção (pessoas e órgãos exatos) — só o dono."""
    acesso, missing = _load_acesso(collection_id, _PAPEIS_DONO)
    if missing:
        return missing
    shares = listar_shares(acesso[0])
    return ok(
        {"compartilhamentos": [serialize_colecao_share(share) for share in shares]}
    )


@main_bp.route("/api/colecoes/<int:collection_id>/compartilhamentos", methods=["POST"])
@api_login_required
def api_colecao_share_criar(collection_id: int) -> _ApiResponse:
    """Concede ``{user_id | orgao_id, papel}``; destinatário repetido vira upsert.

    422 em Favoritos, XOR violado ou papel fora de ``viewer|editor``.
    """
    acesso, missing = _load_acesso(collection_id, _PAPEIS_DONO)
    if missing:
        return missing
    payload, invalid = _ler_json()
    if invalid:
        return invalid
    return _mutar(
        lambda: ok({"compartilhamento": _conceder_share(acesso[0], payload)}),
        "compartilhar coleção",
    )


def _conceder_share(
    colecao: ProjectCollection, payload: dict[str, Any]
) -> dict[str, Any]:
    spec = _parse_share_spec(payload)
    share = compartilhar_colecao(
        colecao,
        ator=g.user,
        user_id=spec["user_id"],
        orgao_id=spec["orgao_id"],
        papel=spec["papel"],
    )
    return serialize_colecao_share(share)


@main_bp.route(
    "/api/colecoes/<int:collection_id>/compartilhamentos/<int:share_id>",
    methods=["DELETE"],
)
@api_login_required
def api_colecao_share_revogar(collection_id: int, share_id: int) -> _ApiResponse:
    """Revoga o share; o acesso derivado aos projetos cai no mesmo commit."""
    acesso, missing = _load_acesso(collection_id, _PAPEIS_DONO)
    if missing:
        return missing
    return _mutar(
        lambda: _revogar_e_confirmar(acesso[0], share_id),
        "revogar compartilhamento da coleção",
    )


def _revogar_e_confirmar(colecao: ProjectCollection, share_id: int) -> _ApiResponse:
    if not revogar_share(colecao, share_id, ator=g.user):
        return fail_not_found()
    return ok()


# ── Cronograma (Gantt da página interna) ─────────────────────────────────────


@main_bp.route("/api/colecoes/<int:collection_id>/cronograma", methods=["GET"])
@api_login_required
def api_colecao_cronograma(collection_id: int) -> _ApiResponse:
    """Etapas datadas dos projetos visíveis, com a faixa da barra já decidida."""
    acesso, missing = _load_acesso(collection_id, _PAPEIS_LEITURA)
    if missing:
        return missing
    linhas = colecao_cronograma_rows(acesso[0], g.user)
    return ok({"projetos": [serialize_cronograma_projeto(linha) for linha in linhas]})


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
