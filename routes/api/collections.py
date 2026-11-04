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
``routes/api/collection_suggestions.py``; as do CONVITE (lado do destinatário:
listar, aceitar, recusar, sair), o reenvio do dono e a busca de destinatários,
em ``routes/api/collection_invites.py`` — todas no mesmo ``main_bp``. Gates e
tradução de erro compartilhados: ``routes/api/collection_http.py``.

O toggle mora aqui (e não em ``projects_write``) por ser açúcar sobre a coleção
Favoritos: o cliente nunca precisa conhecer o id dela.

Rotas finas: parse do payload aqui, regra em ``services/project_collections.py``,
commit/rollback nesta camada. Papel decide o gate: leitura (dono/viewer/editor),
itens (dono/editor) e gestão da coleção e dos shares (só dono). Quem NÃO alcança
a coleção recebe ``fail_not_found`` (nunca 403) — mesmo contrato anti-enumeração
de S5/F4-2b, que vale também para projeto invisível ao ator e para quem só tem
CONVITE pendente (não vê projetos nem cronograma antes de aceitar).
"""

from __future__ import annotations

from typing import Any

from flask import current_app, g

from catalogs.collection_identity import (
    DEFAULT_COLLECTION_COLOR,
    DEFAULT_COLLECTION_ICON,
)
from models import ProjectCollection, db
from services.ai import ia_habilitada, marcar_aceita
from services.collection_shares import (
    compartilhar_colecao,
    listar_shares,
    prever_poda,
    revogar_share,
    status_dos_shares,
)
from services.project_collections import (
    ColecaoInvalida,
    PAPEL_COLECAO_DONO,
    adicionar_projeto,
    apagar_colecao,
    colecao_cronograma_rows,
    colecao_project_rows,
    criar_colecao,
    editar_colecao,
    favoritos_existente,
    get_or_create_favoritos,
    listar_colecoes,
    remover_projeto,
    toggle_favorito,
)
from ..blueprint import main_bp
from .collection_http import (
    PAPEIS_DONO,
    PAPEIS_ITENS,
    PAPEIS_LEITURA,
    ApiResponse,
    cards_das_colecoes,
    carregar_acesso,
    ler_json,
    mutar,
    resumo_da_colecao,
)
from .collection_serializers import (
    serialize_colecao_projeto_row,
    serialize_colecao_share_com_status,
)
from .envelope import fail_internal, fail_not_found, ok
from .negotiation import api_login_required
from .serializers import serialize_cronograma_projeto

_CAMPOS_EDITAVEIS = ("nome", "descricao", "icone", "cor")


# ── Helpers ──────────────────────────────────────────────────────────────────


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
def api_colecoes_list() -> ApiResponse:
    """Lista minhas coleções (Favoritos 1ª) + as compartilhadas comigo, com rollup.

    Leitura pura: o caminho comum não comita. Só o primeiro acesso — quando a
    Favoritos precisa nascer — faz um commit isolado dessa criação.
    """
    try:
        _garantir_favoritos()
        return ok({"colecoes": _indice_payload(), "ia_disponivel": ia_habilitada()})
    except Exception as exc:
        db.session.rollback()
        return fail_internal(exc, "listar coleções")


def _garantir_favoritos() -> None:
    if favoritos_existente(g.user.id) is not None:
        return
    get_or_create_favoritos(g.user.id)
    db.session.commit()


def _indice_payload() -> list[dict[str, Any]]:
    # Convite pendente não entra: ``listar_colecoes`` só traz share válido, e
    # os convites têm rota própria (``GET /api/colecoes/convites``).
    return cards_das_colecoes(listar_colecoes(g.user.id))


@main_bp.route("/api/colecoes", methods=["POST"])
@api_login_required
def api_colecao_criar() -> ApiResponse:
    """Cria coleção custom: ``{nome, descricao?, icone, cor, project_ids?[],
    compartilhamentos?[], sugestao_id?}``.

    Um único POST cobre os dois passos do modal (identidade + seleção); sem
    ``compartilhamentos`` a coleção nasce pessoal ("Só eu"). Qualquer projeto
    fora do escopo do ator invalida a criação inteira. ``sugestao_id`` marca a
    sugestão de IA como aceita no mesmo commit; valor inválido só loga warning.
    """
    payload, invalid = ler_json()
    if invalid:
        return invalid
    return mutar(
        lambda: ok(
            {
                "colecao": resumo_da_colecao(
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
def api_colecao_atualizar(collection_id: int) -> ApiResponse:
    """Edita nome/descrição/ícone/cor; campos ausentes ficam intactos.

    Só o dono edita (403 para quem a vê via share); Favoritos é coleção de
    sistema: qualquer edição responde 422.
    """
    acesso, missing = carregar_acesso(collection_id, PAPEIS_DONO)
    if missing:
        return missing
    payload, invalid = ler_json()
    if invalid:
        return invalid
    campos = {campo: payload[campo] for campo in _CAMPOS_EDITAVEIS if campo in payload}
    return mutar(
        lambda: ok({"colecao": _editar_e_resumir(acesso[0], campos)}),
        "editar coleção",
    )


def _editar_e_resumir(
    colecao: ProjectCollection, campos: dict[str, Any]
) -> dict[str, Any]:
    return resumo_da_colecao(editar_colecao(colecao, **campos), PAPEL_COLECAO_DONO)


@main_bp.route("/api/colecoes/<int:collection_id>", methods=["DELETE"])
@api_login_required
def api_colecao_apagar(collection_id: int) -> ApiResponse:
    """Apaga a coleção e seus itens; os projetos ficam intactos (422 em Favoritos)."""
    acesso, missing = carregar_acesso(collection_id, PAPEIS_DONO)
    if missing:
        return missing
    return mutar(lambda: _apagar_e_confirmar(acesso[0]), "apagar coleção")


def _apagar_e_confirmar(colecao: ProjectCollection) -> ApiResponse:
    apagar_colecao(colecao)
    return ok()


# ── Itens da coleção ─────────────────────────────────────────────────────────


@main_bp.route("/api/colecoes/<int:collection_id>/projetos", methods=["GET"])
@api_login_required
def api_colecao_projetos_list(collection_id: int) -> ApiResponse:
    """Página interna: cabeçalho da coleção + linhas dos projetos visíveis.

    Cada linha traz ``adicionado_por``/``pode_remover`` decididos no servidor.
    Diálogo "Sair da coleção": ``itens_incluidos_por_mim`` (projetos meus que
    saem junto; 0 para o dono, que não sai) e ``itens_orfaos`` (de quem já não
    tem papel editor; saem em qualquer poda, sem dupla contagem com o meu).
    Convite pendente → 404.
    """
    acesso, missing = carregar_acesso(collection_id, PAPEIS_LEITURA)
    if missing:
        return missing
    colecao, papel = acesso
    linhas = colecao_project_rows(colecao, g.user, papel=papel)
    return ok(
        {
            "colecao": resumo_da_colecao(colecao, papel),
            "projetos": [serialize_colecao_projeto_row(linha) for linha in linhas],
            **_contagens_do_dialogo_de_saida(colecao, papel),
        }
    )


def _contagens_do_dialogo_de_saida(
    colecao: ProjectCollection, papel: str
) -> dict[str, int]:
    previsao = prever_poda(colecao)
    meus = 0 if papel == PAPEL_COLECAO_DONO else previsao.por_editor.get(g.user.id, 0)
    return {"itens_incluidos_por_mim": meus, "itens_orfaos": previsao.orfaos}


@main_bp.route("/api/colecoes/<int:collection_id>/projetos", methods=["POST"])
@api_login_required
def api_colecao_projeto_adicionar(collection_id: int) -> ApiResponse:
    """Adiciona ``{project_id}`` à coleção; duplicado é sucesso (idempotente).

    Re-incluir o PRÓPRIO item sobe o teto dele ao rank de área de agora;
    editor rebaixado no meio do request toma 403 e o revogado o 404 idêntico
    (nada gravado nos dois casos).
    """
    acesso, missing = carregar_acesso(collection_id, PAPEIS_ITENS)
    if missing:
        return missing
    payload, invalid = ler_json()
    if invalid:
        return invalid
    return mutar(
        lambda: _adicionar_e_confirmar(acesso[0], payload),
        "adicionar projeto à coleção",
    )


def _adicionar_e_confirmar(
    colecao: ProjectCollection, payload: dict[str, Any]
) -> ApiResponse:
    adicionar_projeto(
        colecao, _parse_project_id(payload.get("project_id")), ator=g.user
    )
    return ok()


@main_bp.route(
    "/api/colecoes/<int:collection_id>/projetos/<int:project_id>", methods=["DELETE"]
)
@api_login_required
def api_colecao_projeto_remover(collection_id: int, project_id: int) -> ApiResponse:
    """Remove o projeto da coleção; projeto que não estava lá também responde ok."""
    acesso, missing = carregar_acesso(collection_id, PAPEIS_ITENS)
    if missing:
        return missing
    return mutar(
        lambda: _remover_e_confirmar(acesso[0], project_id),
        "remover projeto da coleção",
    )


def _remover_e_confirmar(colecao: ProjectCollection, project_id: int) -> ApiResponse:
    remover_projeto(colecao, project_id, ator=g.user)
    return ok()


# ── Compartilhamentos (só o dono) ────────────────────────────────────────────


@main_bp.route("/api/colecoes/<int:collection_id>/compartilhamentos", methods=["GET"])
@api_login_required
def api_colecao_shares_list(collection_id: int) -> ApiResponse:
    """Lista quem recebeu a coleção (pessoas e órgãos exatos) — só o dono.

    Cada share traz o status do convite (pessoa), o agregado por pessoa
    lotada (órgão) e ``itens_incluidos`` (projetos que saem se revogar);
    ``itens_orfaos`` = projetos de quem já não tem papel editor, que saem em
    qualquer revogação (fora dos ``itens_incluidos``, sem dupla contagem).
    """
    acesso, missing = carregar_acesso(collection_id, PAPEIS_DONO)
    if missing:
        return missing
    return ok(_shares_com_status(acesso[0]))


def _shares_com_status(colecao: ProjectCollection) -> dict[str, Any]:
    shares = listar_shares(colecao)
    previsao = prever_poda(colecao, shares)
    status = status_dos_shares(colecao, shares, previsao=previsao)
    return {
        "compartilhamentos": [
            serialize_colecao_share_com_status(s, status[s.id]) for s in shares
        ],
        "itens_orfaos": previsao.orfaos,
    }


@main_bp.route("/api/colecoes/<int:collection_id>/compartilhamentos", methods=["POST"])
@api_login_required
def api_colecao_share_criar(collection_id: int) -> ApiResponse:
    """Convida ``{user_id | orgao_id, papel}``; destinatário repetido vira upsert.

    Share novo nasce CONVITE pendente (sem acesso até o aceite) e notifica;
    upsert só troca o papel (editor→viewer poda o que a pessoa incluiu). 422 em
    Favoritos, XOR violado ou papel fora de ``viewer|editor``.
    """
    acesso, missing = carregar_acesso(collection_id, PAPEIS_DONO)
    if missing:
        return missing
    payload, invalid = ler_json()
    if invalid:
        return invalid
    return mutar(
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
    status = status_dos_shares(colecao, [share])[share.id]
    return serialize_colecao_share_com_status(share, status)


@main_bp.route(
    "/api/colecoes/<int:collection_id>/compartilhamentos/<int:share_id>",
    methods=["DELETE"],
)
@api_login_required
def api_colecao_share_revogar(collection_id: int, share_id: int) -> ApiResponse:
    """Revoga o share; o acesso derivado cai no mesmo commit.

    Também apaga as respostas do share e poda os projetos incluídos por quem
    perdeu o papel editor (auditado). Share alheio/inexistente → 404.
    """
    acesso, missing = carregar_acesso(collection_id, PAPEIS_DONO)
    if missing:
        return missing
    return mutar(
        lambda: _revogar_e_confirmar(acesso[0], share_id),
        "revogar compartilhamento da coleção",
    )


def _revogar_e_confirmar(colecao: ProjectCollection, share_id: int) -> ApiResponse:
    if not revogar_share(colecao, share_id, ator=g.user):
        return fail_not_found()
    return ok()


# ── Cronograma (Gantt da página interna) ─────────────────────────────────────


@main_bp.route("/api/colecoes/<int:collection_id>/cronograma", methods=["GET"])
@api_login_required
def api_colecao_cronograma(collection_id: int) -> ApiResponse:
    """Etapas datadas dos projetos visíveis, com a faixa da barra já decidida."""
    acesso, missing = carregar_acesso(collection_id, PAPEIS_LEITURA)
    if missing:
        return missing
    linhas = colecao_cronograma_rows(acesso[0], g.user)
    return ok({"projetos": [serialize_cronograma_projeto(linha) for linha in linhas]})


# ── Atalho de favorito (estrela do card) ─────────────────────────────────────


@main_bp.route("/api/projetos/<int:project_id>/favorito", methods=["POST"])
@api_login_required
def api_projeto_favorito_toggle(project_id: int) -> ApiResponse:
    """Alterna o projeto na coleção Favoritos e devolve o estado resultante.

    Projeto inexistente ou fora do escopo responde 404 anti-enumeração.
    """
    return mutar(
        lambda: ok({"favorito": toggle_favorito(g.user, project_id)}),
        "alternar favorito do projeto",
    )
