"""Endpoints de autoatendimento da conta para a SPA (/conta/ajustes).

Substitui o fluxo Jinja de ``/profile/change-password`` (agora KEEP-ENDPOINT:
redirect 302 → ``/conta/ajustes``). Escopo do autoatendimento: nome de exibição,
vínculo de CPF gov.br (adicionar/remover) e troca de senha. O ``username`` NUNCA
é editável aqui — fica com o admin via ``/api/admin/usuarios``.

Estados do vínculo gov.br expostos ao cliente (``GET /api/conta``):
    - ``nenhum``: sem CPF vinculado — a SPA oferece o campo de vínculo.
    - ``cpf_pendente``: CPF cadastrado mas nunca houve login gov.br
      (``govbr_sub`` vazio) — a SPA mostra só os 3 primeiros dígitos + ``*``.
    - ``vinculado``: já logou pelo gov.br (``govbr_sub`` presente) — a SPA
      mostra apenas "gov.br vinculado", SEM nenhum dígito do CPF.

A troca de senha NÃO pede a senha atual (decisão de produto): quem entra pelo
gov.br pode nunca ter definido uma senha local, e exigir a atual deixaria essas
contas sem caminho de autoatendimento. A barreira continua sendo a sessão
autenticada (``api_login_required``) mais o rate limit de 5/min.

Reusa a régua única de força (``services/password_policy``), ``normalize_cpf``
(``services/govbr_oidc``), os métodos de hash do modelo e o log estruturado de
auditoria (``_log_auth_event``, OWASP A09). Resposta no envelope canônico; rate
limit 5/min nas mutações espelhando o legado.
"""

from __future__ import annotations

from flask import Response, g, request

from extensions import limiter
from models import User, db
from services.govbr_oidc import normalize_cpf
from services.password_policy import validate_password_strength

from ..auth import _log_auth_event
from ..blueprint import main_bp
from ..orgao_scope import get_user_primary_orgao
from .envelope import fail, fail_internal, ok
from .negotiation import api_login_required

GOVBR_NENHUM = "nenhum"
GOVBR_CPF_PENDENTE = "cpf_pendente"
GOVBR_VINCULADO = "vinculado"


def _mascarar_cpf(cpf: str) -> str:
    """Mascara o CPF para exibição: 3 primeiros dígitos + ``*`` no resto.

    Exemplo: ``_mascarar_cpf("12345678901")`` → ``"123********"``.
    """
    return f"{cpf[:3]}{'*' * (len(cpf) - 3)}"


def _estado_govbr(user: User) -> dict[str, str | None]:
    """Estado do vínculo gov.br do usuário no shape do ``GET /api/conta``."""
    if user.govbr_sub:
        return {"status": GOVBR_VINCULADO, "cpf_mascarado": None}
    if user.cpf_govbr:
        return {
            "status": GOVBR_CPF_PENDENTE,
            "cpf_mascarado": _mascarar_cpf(user.cpf_govbr),
        }
    return {"status": GOVBR_NENHUM, "cpf_mascarado": None}


def _sigla_orgao_primario(user: User) -> str | None:
    """Sigla do órgão-âncora do usuário (``None`` quando não há vínculo)."""
    primary = get_user_primary_orgao(user)
    return primary.sigla if primary is not None else None


def _payload_conta(user: User) -> dict[str, object]:
    return {
        "name": user.name,
        "username": user.username,
        "orgao_sigla": _sigla_orgao_primario(user),
        "govbr": _estado_govbr(user),
    }


@main_bp.route("/api/conta", methods=["GET"])
@api_login_required
def api_conta() -> Response | tuple[Response, int]:
    """Dados da própria conta para a tela de Ajustes.

    Returns:
        200 ``ok({name, username, orgao_sigla, govbr: {status, cpf_mascarado}})``;
        401 sem sessão. ``orgao_sigla`` é a sigla do órgão-âncora
        (``get_user_primary_orgao``) ou ``None`` sem vínculo. O CPF completo
        NUNCA sai daqui — só a máscara (3 dígitos).
    """
    return ok(_payload_conta(g.user))


@main_bp.route("/api/conta/nome", methods=["POST"])
@api_login_required
@limiter.limit("5 per minute")
def api_conta_trocar_nome() -> Response | tuple[Response, int]:
    """Troca o nome de exibição do usuário autenticado (nunca o ``username``).

    Body: ``{"name": str}``.

    Returns:
        200 ``ok({name})``; 400 ``fail(code="validation")`` para nome vazio;
        401 sem sessão.
    """
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name") or "").strip()
    if not name:
        return fail("O nome é obrigatório.")

    try:
        g.user.name = name
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return fail_internal(exc, "trocar nome da conta")
    _log_auth_event("account_name_changed", user=g.user, provider="local")
    return ok({"name": g.user.name})


@main_bp.route("/api/conta/govbr", methods=["POST"])
@api_login_required
@limiter.limit("5 per minute")
def api_conta_vincular_govbr() -> Response | tuple[Response, int]:
    """Vincula um CPF gov.br à conta (só quando não há vínculo algum).

    Body: ``{"cpf": str}`` (com ou sem pontuação; 11 dígitos).

    Returns:
        200 ``ok({govbr})`` com o estado novo (``cpf_pendente``);
        400 ``fail(code="validation")`` para CPF ausente/malformado, vínculo já
        existente ou CPF indisponível (já usado por outra conta — mensagem
        genérica, sem confirmar a existência de outro usuário); 401 sem sessão.
    """
    if g.user.cpf_govbr or g.user.govbr_sub:
        return fail("Já existe um vínculo gov.br nesta conta. Remova-o primeiro.")

    payload = request.get_json(silent=True) or {}
    try:
        cpf = normalize_cpf(payload.get("cpf"))
    except ValueError as exc:
        return fail(f"CPF inválido: {exc}")
    if not cpf:
        return fail("Informe o CPF a vincular.")

    em_uso = User.query.filter(User.cpf_govbr == cpf, User.id != g.user.id).first()
    if em_uso is not None:
        return fail("CPF indisponível para vínculo.")

    try:
        g.user.cpf_govbr = cpf
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return fail_internal(exc, "vincular CPF gov.br")
    _log_auth_event("govbr_cpf_linked", user=g.user, provider="local")
    return ok({"govbr": _estado_govbr(g.user)})


@main_bp.route("/api/conta/govbr/remover", methods=["POST"])
@api_login_required
@limiter.limit("5 per minute")
def api_conta_remover_govbr() -> Response | tuple[Response, int]:
    """Remove o vínculo gov.br da conta (CPF e, se houver, o ``govbr_sub``).

    Returns:
        200 ``ok({govbr})`` com estado ``nenhum``; 400 ``fail`` quando não há
        vínculo a remover; 401 sem sessão. Após remover, o acesso passa a
        depender de usuário/senha até novo vínculo.
    """
    if not (g.user.cpf_govbr or g.user.govbr_sub):
        return fail("Não há vínculo gov.br para remover.")

    try:
        g.user.cpf_govbr = None
        g.user.govbr_sub = None
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return fail_internal(exc, "remover vínculo gov.br")
    _log_auth_event("govbr_cpf_unlinked", user=g.user, provider="local")
    return ok({"govbr": _estado_govbr(g.user)})


@main_bp.route("/api/conta/senha", methods=["POST"])
@api_login_required
@limiter.limit("5 per minute")
def api_conta_trocar_senha() -> Response | tuple[Response, int]:
    """Define a senha do usuário autenticado (body JSON da SPA /conta/ajustes).

    A senha atual NÃO é pedida: conta que só entra pelo gov.br pode não ter
    senha local, e exigi-la travaria o autoatendimento. A sessão autenticada e o
    rate limit de 5/min são a barreira.

    Body: ``{"nova_senha": str, "confirmacao": str}``.

    Returns:
        200 ``ok({"changed": true})`` na troca efetivada;
        400 ``fail(code="validation")`` para campo faltando, confirmação
        divergente ou força insuficiente (mesma régua do legado);
        401 via ``api_login_required`` sem sessão.
    """
    payload = request.get_json(silent=True) or {}
    nova_senha = payload.get("nova_senha") or ""
    confirmacao = payload.get("confirmacao") or ""

    if not (nova_senha and confirmacao):
        return fail("Preencha a nova senha e a confirmação.")
    if nova_senha != confirmacao:
        return fail("A nova senha e a confirmação não correspondem.")
    erro_forca = validate_password_strength(nova_senha)
    if erro_forca:
        return fail(erro_forca)

    try:
        g.user.set_password(nova_senha)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return fail_internal(exc, "trocar senha da conta")
    _log_auth_event("password_changed", user=g.user, provider="local")
    return ok({"changed": True})
