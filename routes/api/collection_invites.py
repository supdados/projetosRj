"""Endpoints JSON do CONVITE de coleção compartilhada (aceite e saída).

Rotas novas da coleção com aceite, no ``main_bp`` ÚNICO (nenhuma URL existente
muda):

    - ``GET  /api/colecoes/convites``                       — meus convites.
    - ``GET  /api/colecoes/<cid>/convite``                  — convite de UMA.
    - ``POST /api/colecoes/<cid>/convite/aceitar``          — aceita.
    - ``POST /api/colecoes/<cid>/convite/recusar``          — recusa.
    - ``POST /api/colecoes/<cid>/sair``                     — sai (aceito/legado).
    - ``POST /api/colecoes/<cid>/compartilhamentos/<sid>/reenviar`` — só dono.
    - ``GET  /api/colecoes/destinatarios?q=``               — busca de pessoas.

Anti-enumeração: o lado do destinatário resolve SEMPRE por (coleção, usuário
logado), nunca por ``share_id`` vindo do cliente. Coleção inexistente, sem
convite para mim, convite revogado, já respondido ou perdido numa corrida
respondem o MESMO ``fail_not_found`` (``ConviteIndisponivel`` →
``erro_de_colecao``). O convite expõe só metadados — nenhum projeto,
contagem ou cronograma antes do aceite. Só o reenvio usa ``share_id``: é do
dono, e o service valida que o share é da coleção.

Rotas finas: regra em ``services/collection_shares.py`` (fachada), commit via
``mutar`` (``routes/api/collection_http.py``).
"""

from __future__ import annotations

from typing import Any

from flask import g, request

from extensions import limiter
from models import ProjectCollection, ProjectCollectionShare, db
from services.collection_errors import ConviteIndisponivel
from services.collection_shares import (
    aceitar_convite,
    buscar_pessoas_para_compartilhar,
    convite_pendente,
    convites_pendentes_de,
    recusar_convite,
    reenviar_convite,
    sair_da_colecao,
    status_dos_shares,
)
from services.project_collections import papel_do_usuario
from services.project_invites import siglas_por_usuario
from ..blueprint import main_bp
from .collection_http import (
    PAPEIS_DONO,
    ApiResponse,
    carregar_acesso,
    mutar,
    resumo_da_colecao,
)
from .collection_serializers import (
    serialize_colecao_share_com_status,
    serialize_convite_colecao,
    serialize_pessoa_destinavel,
)
from .envelope import fail_not_found, ok
from .negotiation import api_login_required

STATUS_ACEITO = "aceito"
STATUS_RECUSADO = "recusado"
STATUS_SAIU = "saiu"

# Busca aberta a qualquer logado (decisão 4): piso de 2 caracteres para não
# virar listagem do diretório; teto do termo só para não montar LIKE absurdo.
_MIN_TERMO_BUSCA = 2
_MAX_TERMO_BUSCA = 100
# Sem freio, um laço pelos bigramas/trigramas junta nome + lotação de todo o
# quadro em minutos (os pisos acima não bastam). Folga para digitar no modal.
_LIMITE_BUSCA_DESTINATARIOS = "60 per minute"


def _chave_da_busca_por_usuario() -> str:
    """Balde por PESSOA logada (não por IP): servidores atrás do mesmo NAT do
    órgão não dividem o limite, e trocar de IP não renova o de ninguém."""
    return f"user:{g.user.id}"


# ── Convites do usuário logado (metadados apenas) ────────────────────────────


@main_bp.route("/api/colecoes/convites", methods=["GET"])
@api_login_required
def api_colecao_convites_list() -> ApiResponse:
    """Convites PENDENTES do usuário logado, mais recentes primeiro.

    Só metadados (nome, ícone, cor, descrição, dono, papel, data); pessoal e
    órgão da mesma coleção viram UM convite com o papel mais alto.
    """
    convites = convites_pendentes_de(g.user)
    return ok({"convites": [serialize_convite_colecao(c) for c in convites]})


@main_bp.route("/api/colecoes/<int:collection_id>/convite", methods=["GET"])
@api_login_required
def api_colecao_convite_get(collection_id: int) -> ApiResponse:
    """Convite pendente desta coleção para mim; sem convite → 404 idêntico.

    É o fallback da página ``/colecoes/<id>`` quando ``.../projetos`` dá 404.
    """
    convite = convite_pendente(collection_id, g.user)
    if convite is None:
        return fail_not_found()
    return ok({"convite": serialize_convite_colecao(convite)})


@main_bp.route("/api/colecoes/<int:collection_id>/convite/aceitar", methods=["POST"])
@api_login_required
def api_colecao_convite_aceitar(collection_id: int) -> ApiResponse:
    """Aceita TODOS os convites pendentes desta coleção que me alcançam.

    Devolve o card já com o acesso novo (rollup e destinatários). Duplo
    clique, revogação no meio ou nada pendente → 404 idêntico, nunca 500.
    """
    return mutar(
        lambda: _aceitar_e_resumir(collection_id), "aceitar convite de coleção"
    )


def _aceitar_e_resumir(collection_id: int) -> ApiResponse:
    colecao = aceitar_convite(collection_id, g.user)
    return ok({"status": STATUS_ACEITO, "colecao": _card_pos_aceite(colecao)})


def _card_pos_aceite(colecao: ProjectCollection) -> dict[str, Any]:
    papel = papel_do_usuario(colecao, g.user)
    if papel is None:
        # Aceite gravado mas o share deixou de valer (ex.: dono removido no
        # meio): falha fechada — ``mutar`` desfaz e responde o 404 idêntico.
        raise ConviteIndisponivel(f"aceite sem papel válido na coleção id={colecao.id}")
    return resumo_da_colecao(colecao, papel)


@main_bp.route("/api/colecoes/<int:collection_id>/convite/recusar", methods=["POST"])
@api_login_required
def api_colecao_convite_recusar(collection_id: int) -> ApiResponse:
    """Recusa TODOS os convites pendentes desta coleção que me alcançam.

    O dono é avisado e vê "recusado"; só ele pode reenviar. Sem convite → 404.
    """
    return mutar(
        lambda: _recusar_e_confirmar(collection_id), "recusar convite de coleção"
    )


def _recusar_e_confirmar(collection_id: int) -> ApiResponse:
    recusar_convite(collection_id, g.user)
    return ok({"status": STATUS_RECUSADO})


@main_bp.route("/api/colecoes/<int:collection_id>/sair", methods=["POST"])
@api_login_required
def api_colecao_sair(collection_id: int) -> ApiResponse:
    """Sai da coleção (quem aceitou ou é legado); os projetos que incluí saem.

    ``itens_removidos`` = quantos projetos incluídos por mim saíram junto.
    Dono, pendente ou estranho → 404 idêntico.
    """
    return mutar(lambda: _sair_e_contar(collection_id), "sair da coleção")


def _sair_e_contar(collection_id: int) -> ApiResponse:
    removidos = sair_da_colecao(collection_id, g.user)
    return ok({"status": STATUS_SAIU, "itens_removidos": removidos})


# ── Reenvio (só o dono) ──────────────────────────────────────────────────────


@main_bp.route(
    "/api/colecoes/<int:collection_id>/compartilhamentos/<int:share_id>/reenviar",
    methods=["POST"],
)
@api_login_required
def api_colecao_share_reenviar(collection_id: int, share_id: int) -> ApiResponse:
    """Reconvida quem recusou ou saiu daquele share e notifica de novo.

    Só o dono (403 para quem participa; 404 para quem não alcança a coleção).
    Share de outra coleção → 404; ninguém recusou/saiu → 422.
    """
    acesso, missing = carregar_acesso(collection_id, PAPEIS_DONO)
    if missing:
        return missing
    return mutar(
        lambda: _reenviar_e_resumir(acesso[0], share_id),
        "reenviar convite de coleção",
    )


def _reenviar_e_resumir(colecao: ProjectCollection, share_id: int) -> ApiResponse:
    reconvidados = reenviar_convite(colecao, share_id, ator=g.user)
    share = db.session.get(ProjectCollectionShare, share_id)
    status = status_dos_shares(colecao, [share])[share.id]
    return ok(
        {
            "reconvidados": reconvidados,
            "compartilhamento": serialize_colecao_share_com_status(share, status),
        }
    )


# ── Busca de destinatários (decisão 4) ───────────────────────────────────────


@main_bp.route("/api/colecoes/destinatarios", methods=["GET"])
@api_login_required
@limiter.limit(_LIMITE_BUSCA_DESTINATARIOS, key_func=_chave_da_busca_por_usuario)
def api_colecao_destinatarios_busca() -> ApiResponse:
    """Pessoas para compartilhar: ``{usuarios: [{id, name, orgao_sigla}]}``.

    Aberta a qualquer logado — sem ``CONVITES_HABILITADOS`` e sem gate de
    gestor (é o que destrava compartilhar com a própria equipe). Termo com
    menos de 2 caracteres → lista vazia; até 20 resultados por nome; exclui o
    próprio usuário e inativos; nunca CPF, hash ou username. Até 60 buscas por
    minuto por pessoa (429 acima disso).
    """
    termo = (request.args.get("q") or "").strip()[:_MAX_TERMO_BUSCA]
    if len(termo) < _MIN_TERMO_BUSCA:
        return ok({"usuarios": []})
    usuarios = buscar_pessoas_para_compartilhar(termo, ator=g.user)
    siglas = siglas_por_usuario(user.id for user in usuarios)
    return ok(
        {
            "usuarios": [
                serialize_pessoa_destinavel(user, siglas.get(user.id))
                for user in usuarios
            ]
        }
    )
