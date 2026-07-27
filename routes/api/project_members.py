"""Endpoints JSON de MEMBROS do projeto — convites (S4/F3-11..F3-16, F3-26).

As 5 rotas novas da §6.5 do plano, todas no envelope canônico e anexadas ao
``main_bp`` ÚNICO (nenhuma URL existente muda):

    - ``GET    /api/projetos/<id>/membros``          — diretos + herdados.
    - ``POST   /api/projetos/<id>/membros``          — cria ou reativa convite.
    - ``PUT    /api/projetos/<id>/membros/<mid>``    — altera papel/validade.
    - ``DELETE /api/projetos/<id>/membros/<mid>``    — revoga (soft).
    - ``GET    /api/usuarios/busca?q=``              — autocomplete de convidáveis.

Contrato desta superfície (F3-26, anti-enumeração — rotas ANTIGAS seguem em 403):
rank 0 no projeto, projeto inexistente e flag ``CONVITES_HABILITADOS`` desligada
respondem o MESMO 404 ``not_found``; rank >= leitor sem gestão responde 403.

Gate de gestão: ``user_can_manage_members`` (``services/project_membership.py``)
— rank >= gestor por vínculo de ÁREA ou admin, NUNCA por convite (auto-promoção
do Redmine #11075). É o mesmo predicado que alimenta
``permissions.can_manage_members`` nos serializers, então o botão da SPA e o
gate da rota não podem divergir. O piso do admin chega pelo serviço, o que
dispensa ler a flag global inline aqui (grep-gate F0-6).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from flask import Response, g, request
from sqlalchemy.orm import joinedload

from models import OrgaoUnidade, Project, ProjectMember, User, UserOrgao, db
from services.authorization import (
    ADMIN_RANK,
    PAPEL_GESTOR,
    PAPEL_RANK,
    area_project_rank,
    effective_project_rank,
    get_user_orgao_role_map,
)
from services.notifications import notify_project_invite
from services.project_invites import (
    ConviteInvalido,
    alterar_convite,
    buscar_convidaveis,
    conceder_convite,
    find_membro,
    parse_expires_at,
    parse_papel_convite,
    revogar_convite,
    siglas_por_usuario,
    status_do_convite,
)
from services.project_membership import (
    InheritedMember,
    convites_habilitados,
    list_inherited_members,
    user_can_manage_members,
)
from time_utils import iso_utc

from ..blueprint import main_bp
from .envelope import fail, fail_internal, ok
from .negotiation import api_login_required

# Mensagem única do 404: projeto inexistente, projeto invisível e feature
# desligada são indistinguíveis por design.
_NAO_ENCONTRADO = "Recurso não encontrado."
_SEM_GESTAO = "Você não pode gerenciar os membros deste projeto."
_SEM_CONVITE = "Você não pode convidar pessoas para projetos."
_MIN_TERMO_BUSCA = 2

_ApiResponse = Response | tuple[Response, int]


# ── Gates ────────────────────────────────────────────────────────────────────


def _not_found() -> tuple[Response, int]:
    return fail(_NAO_ENCONTRADO, status=404, code="not_found")


def _convites_desligados() -> tuple[Response, int] | None:
    """404 quando a flag está off (F3-23): a feature não se anuncia."""
    if convites_habilitados():
        return None
    return _not_found()


def _is_admin_global(user: User | None) -> bool:
    # Sem projeto, `area_project_rank` só alcança ADMIN_RANK para admin global —
    # a flag global fica lida pelo serviço, não inline aqui (grep-gate F0-6).
    return area_project_rank(user, None) >= ADMIN_RANK


def _load_projeto_gerenciavel(project_id: int) -> tuple[Project | None, Any]:
    """Carrega o projeto aplicando flag, anti-enumeração e gate de gestão."""
    desligado = _convites_desligados()
    if desligado:
        return None, desligado
    project = db.session.get(Project, project_id)
    if project is None or effective_project_rank(g.user, project) == 0:
        return None, _not_found()
    # Mesmo predicado que decide `permissions.can_manage_members` no serializer:
    # o botão que a SPA mostra e o gate que a rota aplica não podem divergir.
    if not user_can_manage_members(g.user, project):
        return None, fail(_SEM_GESTAO, status=403, code="forbidden")
    return project, None


def _load_membro(project: Project, member_id: int) -> tuple[ProjectMember | None, Any]:
    """Membro do projeto informado; de outro projeto é indistinguível de inexistente."""
    membro = db.session.get(ProjectMember, member_id)
    if membro is None or membro.project_id != project.id:
        return None, _not_found()
    return membro, None


# ── Serialização (sem CPF, sem hash, sem tokens) ─────────────────────────────


def _nome_de(user: User | None) -> str | None:
    return user.name if user is not None else None


def _serialize_membro(
    membro: ProjectMember, sigla: str | None = None
) -> dict[str, Any]:
    """Convite direto no formato de ``ProjectMemberDireto`` (types/projectMembers.ts)."""
    return {
        "id": membro.id,
        "user_id": membro.user_id,
        "user_name": _nome_de(membro.user),
        "user_username": getattr(membro.user, "username", None),
        "user_orgao_sigla": sigla,
        "papel": membro.papel,
        "status": status_do_convite(membro),
        "created_at": iso_utc(membro.created_at),
        "expires_at": iso_utc(membro.expires_at),
        "revoked_at": iso_utc(membro.revoked_at),
        "granted_by_name": _nome_de(membro.granted_by),
        "revoked_by_name": _nome_de(membro.revoked_by),
    }


def _serialize_herdado(membro: InheritedMember) -> dict[str, Any]:
    """Membro herdado por área: read-only, sem ``id`` (não há linha para editar)."""
    return {
        "user_id": membro["user_id"],
        "user_name": membro["name"],
        "user_username": membro["username"],
        "papel": membro["papel"],
        "orgao_id": membro["via_orgao_id"],
        "orgao_sigla": membro["via_orgao_sigla"],
        "orgao_nome": None,
    }


def _serialize_convidavel(user: User, sigla: str | None) -> dict[str, Any]:
    return {
        "id": user.id,
        "name": user.name,
        "username": user.username,
        "orgao_sigla": sigla,
    }


def _membros_diretos(project: Project) -> list[ProjectMember]:
    return (
        ProjectMember.query.options(
            joinedload(ProjectMember.user),
            joinedload(ProjectMember.granted_by),
            joinedload(ProjectMember.revoked_by),
        )
        .filter(ProjectMember.project_id == project.id)
        .order_by(ProjectMember.created_at.asc(), ProjectMember.id.asc())
        .all()
    )


def _membros_payload(project: Project) -> dict[str, Any]:
    diretos = _membros_diretos(project)
    siglas = siglas_por_usuario(membro.user_id for membro in diretos)
    return {
        "diretos": [_serialize_membro(m, siglas.get(m.user_id)) for m in diretos],
        "herdados": [_serialize_herdado(m) for m in list_inherited_members(project)],
    }


# ── Mutação ──────────────────────────────────────────────────────────────────


def _invalid(message: str) -> tuple[Response, int]:
    return fail(message, status=400, code="validation")


def _read_json_object() -> tuple[dict[str, Any] | None, Any]:
    payload = request.get_json(silent=True)
    if isinstance(payload, dict):
        return payload, None
    return None, _invalid("Corpo JSON inválido; esperado um objeto.")


def _commit_convite(acao: Callable[[], ProjectMember], log_label: str) -> _ApiResponse:
    """Executa a mutação e comita; traduz ``ConviteInvalido`` em 400."""
    try:
        membro = acao()
        db.session.commit()
    except ConviteInvalido as exc:
        db.session.rollback()
        return _invalid(str(exc))
    except Exception as exc:
        db.session.rollback()
        return fail_internal(exc, log_label)
    return ok(_serialize_membro(membro))


def _resolve_convidado(raw: object) -> User:
    """Valida o alvo do convite: existente, ativo e diferente de quem convida."""
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise ConviteInvalido(
            f"user_id inválido: {raw!r}; esperado o id inteiro do convidado"
        )
    if raw == g.user.id:
        raise ConviteInvalido(
            "auto-convite bloqueado: você não pode conceder acesso a si mesmo"
        )
    convidado = db.session.get(User, raw)
    if convidado is None or convidado.deleted_at is not None:
        raise ConviteInvalido(
            f"usuário inválido: user_id={raw} inexistente ou removido"
        )
    return convidado


def _criar_ou_reativar(project: Project, payload: dict[str, Any]) -> ProjectMember:
    convidado = _resolve_convidado(payload.get("user_id"))
    membro = conceder_convite(
        project,
        convidado,
        papel=parse_papel_convite(payload.get("papel")),
        expires_at=parse_expires_at(payload.get("expires_at")),
        ator=g.user,
    )
    db.session.flush()
    notify_project_invite(project, membro.user_id, g.user.id, membro.papel)
    return membro


def _aplicar_alteracao(membro: ProjectMember, payload: dict[str, Any]) -> ProjectMember:
    papel = (
        parse_papel_convite(payload["papel"]) if "papel" in payload else membro.papel
    )
    expires_at = (
        parse_expires_at(payload["expires_at"])
        if "expires_at" in payload
        else membro.expires_at
    )
    return alterar_convite(membro, papel=papel, expires_at=expires_at, ator=g.user)


# ── Rotas ────────────────────────────────────────────────────────────────────


@main_bp.route("/api/projetos/<int:project_id>/membros", methods=["GET"])
@api_login_required
def api_projeto_membros_list(project_id: int) -> _ApiResponse:
    """Lista convites diretos (com status) e membros herdados por área.

    Restrita a quem gerencia: convidado-leitor não enumera membros.
    """
    project, denied = _load_projeto_gerenciavel(project_id)
    if denied:
        return denied
    return ok(_membros_payload(project))


@main_bp.route("/api/projetos/<int:project_id>/membros", methods=["POST"])
@api_login_required
def api_projeto_membro_criar(project_id: int) -> _ApiResponse:
    """Cria ou reativa um convite: ``{user_id, papel, expires_at?}``.

    Papel fora de ``leitor|editor`` e auto-convite respondem 400.
    """
    project, denied = _load_projeto_gerenciavel(project_id)
    if denied:
        return denied
    payload, invalid = _read_json_object()
    if invalid:
        return invalid
    return _commit_convite(
        lambda: _criar_ou_reativar(project, payload), "criar convite de projeto"
    )


@main_bp.route(
    "/api/projetos/<int:project_id>/membros/<int:member_id>", methods=["PUT"]
)
@api_login_required
def api_projeto_membro_atualizar(project_id: int, member_id: int) -> _ApiResponse:
    """Altera papel e/ou validade do convite (campos ausentes ficam como estão)."""
    project, denied = _load_projeto_gerenciavel(project_id)
    if denied:
        return denied
    membro, missing = _load_membro(project, member_id)
    if missing:
        return missing
    payload, invalid = _read_json_object()
    if invalid:
        return invalid
    return _commit_convite(
        lambda: _aplicar_alteracao(membro, payload), "alterar convite de projeto"
    )


@main_bp.route(
    "/api/projetos/<int:project_id>/membros/<int:member_id>", methods=["DELETE"]
)
@api_login_required
def api_projeto_membro_revogar(project_id: int, member_id: int) -> _ApiResponse:
    """Revoga o convite (soft): grava ``revoked_at`` e ``revoked_by_id``."""
    project, denied = _load_projeto_gerenciavel(project_id)
    if denied:
        return denied
    membro, missing = _load_membro(project, member_id)
    if missing:
        return missing
    return _commit_convite(
        lambda: revogar_convite(membro, ator=g.user), "revogar convite de projeto"
    )


# ── Convite em lote por órgão (compartilhar com área = snapshot) ─────────────


def _resolve_orgao_do_lote(raw: object) -> OrgaoUnidade:
    # Órgão não é recurso protegido por rank: inexistente responde 400, não 404.
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise ConviteInvalido(
            f"orgao_id inválido: {raw!r}; esperado o id inteiro do órgão"
        )
    orgao = db.session.get(OrgaoUnidade, raw)
    if orgao is None:
        raise ConviteInvalido(f"órgão inválido: orgao_id={raw} inexistente")
    return orgao


def _usuarios_diretos_do_orgao(orgao_id: int) -> list[User]:
    """Ativos com vínculo DIRETO no órgão — sem subárvore (decisão de 2026-07-27)."""
    return (
        User.query.join(UserOrgao, UserOrgao.user_id == User.id)
        .filter(UserOrgao.orgao_id == orgao_id, User.deleted_at.is_(None))
        .order_by(User.id)
        .all()
    )


def _convidar_lote(project: Project, payload: dict[str, Any]) -> dict[str, int]:
    """Valida o payload UMA vez e aplica a semântica do POST individual por alvo."""
    papel = parse_papel_convite(payload.get("papel"))
    expires_at = parse_expires_at(payload.get("expires_at"))
    orgao = _resolve_orgao_do_lote(payload.get("orgao_id"))
    contagens = {"convidados": 0, "reativados": 0, "pulados": 0}
    for alvo in _usuarios_diretos_do_orgao(orgao.id):
        contagens[_convidar_alvo_do_lote(project, alvo, papel, expires_at)] += 1
    return contagens


def _convidar_alvo_do_lote(
    project: Project, alvo: User, papel: str, expires_at: datetime | None
) -> str:
    """O que no POST individual seria 400 (self, convite ativo) aqui vira pulo."""
    if alvo.id == g.user.id or area_project_rank(alvo, project) > 0:
        return "pulados"
    existente = find_membro(project.id, alvo.id)
    if existente is not None and existente.is_active:
        return "pulados"
    membro = conceder_convite(
        project, alvo, papel=papel, expires_at=expires_at, ator=g.user
    )
    db.session.flush()
    notify_project_invite(project, membro.user_id, g.user.id, membro.papel)
    return "convidados" if existente is None else "reativados"


@main_bp.route("/api/projetos/<int:project_id>/membros/lote", methods=["POST"])
@api_login_required
def api_projeto_membros_lote(project_id: int) -> _ApiResponse:
    """Convite em LOTE por órgão: ``{orgao_id, papel, expires_at?}`` → contagens.

    Snapshot de HOJE dos vínculos DIRETOS do órgão (sem subárvore, sem vínculo
    dinâmico projeto×órgão — sprint futura). Transação única: erro desfaz tudo.
    """
    project, denied = _load_projeto_gerenciavel(project_id)
    if denied:
        return denied
    payload, invalid = _read_json_object()
    if invalid:
        return invalid
    try:
        contagens = _convidar_lote(project, payload)
        db.session.commit()
    except ConviteInvalido as exc:
        db.session.rollback()
        return _invalid(str(exc))
    except Exception as exc:
        db.session.rollback()
        return fail_internal(exc, "convite em lote por órgão")
    return ok(contagens)


def _pode_convidar_em_algum_orgao(user: User | None) -> bool:
    """Rank >= gestor em pelo menos um órgão (admin passa pelo piso global)."""
    if _is_admin_global(user):
        return True
    ranks = get_user_orgao_role_map(user).values()
    return max(ranks, default=0) >= PAPEL_RANK[PAPEL_GESTOR]


@main_bp.route("/api/usuarios/busca", methods=["GET"])
@api_login_required
def api_usuarios_busca() -> _ApiResponse:
    """Autocomplete de convidáveis: ``{id, name, username, orgao_sigla}``.

    Existe porque ``GET /api/admin/usuarios`` é ``api_admin_required`` e um
    Gestor não-admin tomaria 403 lá. NUNCA devolve CPF, hash ou vínculo Gov.br.
    """
    desligado = _convites_desligados()
    if desligado:
        return desligado
    if not _pode_convidar_em_algum_orgao(g.user):
        return fail(_SEM_CONVITE, status=403, code="forbidden")
    termo = (request.args.get("q") or "").strip()
    if len(termo) < _MIN_TERMO_BUSCA:
        return ok({"usuarios": []})
    return ok({"usuarios": _convidaveis_payload(termo)})


def _convidaveis_payload(termo: str) -> list[dict[str, Any]]:
    usuarios = buscar_convidaveis(termo)
    siglas = siglas_por_usuario(user.id for user in usuarios)
    return [_serialize_convidavel(user, siglas.get(user.id)) for user in usuarios]
