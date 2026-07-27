"""Regras de convite por projeto (S4/F3-14..F3-16): teto, validade e trilha.

Domínio de ``ProjectMember``: valida o payload, cria/reativa/altera/revoga a
ÚNICA linha por par (projeto, usuário) e enfileira o evento em
``AutorizacaoAudit``. Nada de ``request``/``g`` aqui — o HTTP (gates, envelope,
anti-enumeração) fica em ``routes/api/project_members.py``.

Só ESCRITA e validação: a leitura de membership (flags, ``access_via``, membros
herdados, flag da feature) mora em ``services/project_membership.py``.

Teto rígido do convite: ``papeis_de_convite()`` (leitor|editor). Gestor nunca
entra, nem no POST nem no PUT — convite não concede gestão.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Iterable

from models import (
    ALVO_PROJETO,
    ORIGEM_CONVITE,
    OrgaoUnidade,
    ProjectMember,
    User,
    UserOrgao,
    db,
    papeis_de_convite,
    registrar_autorizacao,
)
from time_utils import utc_now

if TYPE_CHECKING:
    from models import Project

# Colaboração pontual em governo: o formulário abre com 90 dias (§7).
EXPIRACAO_PADRAO_DIAS: int = 90

STATUS_ATIVO = "ativo"
STATUS_EXPIRADO = "expirado"
STATUS_REVOGADO = "revogado"


class ConviteInvalido(ValueError):
    """Payload de convite recusado (papel fora do teto, data, auto-convite)."""


def parse_papel_convite(raw: object) -> str:
    """Valida o papel pedido contra o teto do convite.

    Exemplo: ``parse_papel_convite("editor") == "editor"``; ``"gestor"`` levanta
    ``ConviteInvalido`` (o dado nunca chega ao banco).
    """
    permitidos = papeis_de_convite()
    if isinstance(raw, str) and raw in permitidos:
        return raw
    esperados = "|".join(permitidos)
    raise ConviteInvalido(f"papel inválido: {raw!r}; esperado um de {esperados}")


def parse_expires_at(raw: object) -> datetime | None:
    """Converte ISO 8601 em ``datetime`` UTC naive; ``None``/vazio = sem expiração.

    Exemplo: ``parse_expires_at("2026-12-31")``.
    """
    if raw is None or raw == "":
        return None
    if not isinstance(raw, str):
        raise ConviteInvalido(_erro_expires_at(raw))
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ConviteInvalido(_erro_expires_at(raw)) from exc
    return _to_utc_naive(parsed)


def _erro_expires_at(raw: object) -> str:
    return (
        f"expires_at inválido: {raw!r}; esperado data ISO 8601 "
        "(ex.: '2026-12-31' ou '2026-12-31T18:00:00')"
    )


def _to_utc_naive(value: datetime) -> datetime:
    # As colunas DateTime guardam UTC naive; `is_active` compara com utc_now().
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def expiracao_padrao(*, agora: datetime | None = None) -> datetime:
    """Validade sugerida ao formulário: ``agora + 90 dias``."""
    return (agora or utc_now()) + timedelta(days=EXPIRACAO_PADRAO_DIAS)


def status_do_convite(membro: ProjectMember) -> str:
    """``"revogado"`` | ``"expirado"`` | ``"ativo"`` — o que a UI exibe."""
    if membro.revoked_at is not None:
        return STATUS_REVOGADO
    if membro.is_active:
        return STATUS_ATIVO
    return STATUS_EXPIRADO


def find_membro(project_id: int, user_id: int) -> ProjectMember | None:
    """Linha única do par (projeto, usuário), ativa ou não."""
    return ProjectMember.query.filter_by(project_id=project_id, user_id=user_id).first()


def conceder_convite(
    project: "Project",
    convidado: User,
    *,
    papel: str,
    expires_at: datetime | None,
    ator: User,
) -> ProjectMember:
    """Cria o convite ou REATIVA a linha existente (unique constraint do par).

    Exemplo: ``conceder_convite(projeto, convidado, papel="leitor",
    expires_at=expiracao_padrao(), ator=g.user)``.
    """
    existente = find_membro(project.id, convidado.id)
    if existente is None:
        return _criar_convite(
            project, convidado, papel=papel, expires_at=expires_at, ator=ator
        )
    if existente.is_active:
        raise ConviteInvalido(
            f"convite já ativo para user_id={convidado.id}; "
            "use PUT para alterar papel ou validade"
        )
    return _reativar_convite(existente, papel=papel, expires_at=expires_at, ator=ator)


def _criar_convite(
    project: "Project",
    convidado: User,
    *,
    papel: str,
    expires_at: datetime | None,
    ator: User,
) -> ProjectMember:
    membro = ProjectMember(
        project_id=project.id,
        user_id=convidado.id,
        papel=papel,
        granted_by_id=ator.id,
        expires_at=expires_at,
    )
    db.session.add(membro)
    _auditar(membro, "convite_criado", ator_id=ator.id)
    return membro


def _reativar_convite(
    membro: ProjectMember,
    *,
    papel: str,
    expires_at: datetime | None,
    ator: User,
) -> ProjectMember:
    membro.papel = papel
    membro.expires_at = expires_at
    membro.revoked_at = None
    membro.revoked_by_id = None
    membro.granted_by_id = ator.id
    _auditar(membro, "convite_reativado", ator_id=ator.id)
    return membro


def alterar_convite(
    membro: ProjectMember,
    *,
    papel: str,
    expires_at: datetime | None,
    ator: User,
) -> ProjectMember:
    """Muda papel/validade de um convite não revogado (evento ``convite_alterado``)."""
    if membro.revoked_at is not None:
        raise ConviteInvalido(
            f"convite revogado: member_id={membro.id}; "
            "recrie pelo POST para reativar antes de alterar"
        )
    membro.papel = papel
    membro.expires_at = expires_at
    _auditar(membro, "convite_alterado", ator_id=ator.id)
    return membro


def revogar_convite(membro: ProjectMember, *, ator: User) -> ProjectMember:
    """Revogação SOFT: preserva a linha, grava quem revogou e quando."""
    if membro.revoked_at is not None:
        raise ConviteInvalido(
            f"convite já revogado: member_id={membro.id}; "
            "recrie pelo POST para conceder acesso de novo"
        )
    membro.revoked_at = utc_now()
    membro.revoked_by_id = ator.id
    _auditar(membro, "convite_revogado", ator_id=ator.id)
    return membro


def _auditar(membro: ProjectMember, evento: str, *, ator_id: int) -> None:
    registrar_autorizacao(
        evento=evento,
        user_id=membro.user_id,
        ator_id=ator_id,
        alvo_tipo=ALVO_PROJETO,
        alvo_id=membro.project_id,
        detalhe={
            "papel": membro.papel,
            # `origem` só recebe o server_default no INSERT; a trilha registra o
            # valor efetivo mesmo antes do flush.
            "origem": membro.origem or ORIGEM_CONVITE,
            "expires_at": _iso_ou_none(membro.expires_at),
        },
    )


def _iso_ou_none(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def buscar_convidaveis(termo: str, *, limite: int = 20) -> list[User]:
    """Usuários ATIVOS cujo nome/username casa com ``termo`` (autocomplete)."""
    like = f"%{termo}%"
    return (
        User.query.filter(User.deleted_at.is_(None))
        .filter(db.or_(User.name.ilike(like), User.username.ilike(like)))
        .order_by(User.name)
        .limit(limite)
        .all()
    )


def siglas_por_usuario(user_ids: Iterable[int]) -> dict[int, str]:
    """``{user_id: sigla do 1º vínculo}`` em UMA query (sem N+1 no autocomplete)."""
    ids = [int(user_id) for user_id in user_ids]
    if not ids:
        return {}
    rows = (
        db.session.query(UserOrgao.user_id, OrgaoUnidade.sigla)
        .join(OrgaoUnidade, OrgaoUnidade.id == UserOrgao.orgao_id)
        .filter(UserOrgao.user_id.in_(ids))
        .order_by(UserOrgao.user_id, OrgaoUnidade.sigla)
        .all()
    )
    siglas: dict[int, str] = {}
    for user_id, sigla in rows:
        siglas.setdefault(user_id, sigla)
    return siglas
