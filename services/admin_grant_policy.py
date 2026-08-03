"""Política de concessão do status de administrador.

Só o administrador principal (`is_super_admin`) pode ligar ou desligar a flag
`is_admin` de qualquer conta, e a própria conta principal nunca perde a flag nem
pode ser excluída. Todas as funções são puras (sem Flask, sem `db.session`) e
devolvem `None` quando a ação é permitida ou a mensagem PT de erro quando negada.

Ex.: `denial_for_admin_flag_change(ator, alvo, True) or conceder()`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - evita ciclo models <-> services
    from models.user import User

MSG_ATOR_AUSENTE = "Ação não permitida: nenhum usuário autenticado na sessão."
MSG_CONCEDER_NEGADO = (
    "Somente o administrador principal pode conceder o status de administrador "
    "(alvo: {alvo})."
)
MSG_REMOVER_NEGADO = (
    "Somente o administrador principal pode remover o status de administrador "
    "(alvo: {alvo})."
)
MSG_SUPER_ADMIN_IMUTAVEL = (
    "A conta do administrador principal ({alvo}) não pode perder o status de "
    "administrador."
)
MSG_SUPER_ADMIN_INDELEVEL = (
    "A conta do administrador principal ({alvo}) não pode ser excluída."
)
MSG_GERIR_ADMIN_NEGADO = (
    "Somente o administrador principal pode editar ou excluir contas de "
    "administrador ({alvo}). Você pode gerenciar apenas usuários que não são "
    "administradores."
)


def _rotulo(user: "User | None") -> str:
    """Nome legível do usuário para compor a mensagem de erro."""
    if user is None:
        return "novo usuário"
    return getattr(user, "username", None) or "usuário desconhecido"


def is_super_admin(user: "User | None") -> bool:
    """True só para a conta do administrador principal e ativa.

    Ex.: `is_super_admin(g.user)` — conta soft-deletada devolve False.
    """
    if user is None:
        return False
    return bool(getattr(user, "is_super_admin", False)) and user.deleted_at is None


def can_grant_admin(actor: "User | None") -> bool:
    """True quando o ator pode ligar/desligar `is_admin` de outras contas."""
    return is_super_admin(actor)


def denial_for_admin_flag_change(
    actor: "User | None", target: "User | None", new_flag: bool
) -> str | None:
    """Motivo para recusar a mudança de `is_admin`, ou None se permitida.

    `target=None` representa criação de conta. Ex.:
    `denial_for_admin_flag_change(ator, None, True)`.
    """
    current = bool(target.is_admin) if target is not None else False
    if bool(new_flag) == current:
        return None
    if not new_flag and is_super_admin(target):
        return MSG_SUPER_ADMIN_IMUTAVEL.format(alvo=_rotulo(target))
    if actor is None:
        return MSG_ATOR_AUSENTE
    if not can_grant_admin(actor):
        template = MSG_CONCEDER_NEGADO if new_flag else MSG_REMOVER_NEGADO
        return template.format(alvo=_rotulo(target))
    return None


def denial_for_managing_user(actor: "User | None", target: "User | None") -> str | None:
    """Motivo para recusar edição/exclusão do alvo, ou None se permitida.

    Admin comum gerencia apenas contas não-admin e a si próprio.
    Ex.: `denial_for_managing_user(g.user, usuario)`.
    """
    if actor is None or target is None:
        return MSG_ATOR_AUSENTE
    if is_super_admin(actor):
        return None
    if target.id == actor.id:
        return None
    if bool(target.is_admin) or is_super_admin(target):
        return MSG_GERIR_ADMIN_NEGADO.format(alvo=_rotulo(target))
    return None


def denial_for_deleting_user(actor: "User | None", target: "User | None") -> str | None:
    """Motivo para recusar a exclusão do alvo, ou None se permitida.

    A conta principal é indelével para qualquer ator, inclusive ela mesma.
    Ex.: `denial_for_deleting_user(g.user, usuario)`.
    """
    if is_super_admin(target):
        return MSG_SUPER_ADMIN_INDELEVEL.format(alvo=_rotulo(target))
    return denial_for_managing_user(actor, target)


def resolve_admin_flag(
    actor: "User | None", target: "User | None", requested: bool | None
) -> tuple[bool, str | None]:
    """Valor efetivo de `is_admin` e o motivo da recusa, se houver.

    `requested=None` (campo ausente no payload) mantém o valor atual.
    Ex.: `efetivo, negacao = resolve_admin_flag(g.user, usuario, None)`.
    """
    current = bool(target.is_admin) if target is not None else False
    if requested is None or bool(requested) == current:
        return current, None
    denial = denial_for_admin_flag_change(actor, target, bool(requested))
    if denial:
        return current, denial
    return bool(requested), None


def apply_admin_flag(
    actor: "User | None", target: "User", requested: bool | None
) -> str | None:
    """Grava `is_admin` no alvo quando permitido; devolve o motivo da recusa.

    Único ponto do fonte autorizado a atribuir `.is_admin`. Nada é mutado quando
    a política nega. Ex.: `apply_admin_flag(g.user, usuario, True)`.
    """
    effective, denial = resolve_admin_flag(actor, target, requested)
    if denial:
        return denial
    target.is_admin = effective
    return None
