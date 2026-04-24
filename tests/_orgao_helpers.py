"""Helpers compartilhados para setup de OrgaoUnidade/UserOrgao em testes."""

from models import OrgaoUnidade, UserOrgao, db


def ensure_orgao(sigla):
    """Garante que o orgao existe e retorna a instancia. Cria sob SETD se novo."""
    existing = OrgaoUnidade.query.filter(
        db.func.lower(OrgaoUnidade.sigla) == sigla.lower()
    ).first()
    if existing is not None:
        return existing
    setd = OrgaoUnidade.query.filter_by(sigla="SETD").first()
    if setd is None:
        setd = OrgaoUnidade(
            sigla="SETD",
            nome="SETD",
            tipo="Secretaria",
            pai_id=None,
            ordem=0,
            ativo=True,
        )
        db.session.add(setd)
        db.session.flush()
    orgao = OrgaoUnidade(
        sigla=sigla,
        nome=sigla,
        tipo="Subsecretaria",
        pai_id=setd.id,
        ordem=0,
        ativo=True,
    )
    db.session.add(orgao)
    db.session.flush()
    return orgao


def link_user_to_orgao(user_id, sigla):
    """Cria vinculo user_orgao idempotente a partir da sigla."""
    orgao = ensure_orgao(sigla)
    existing = UserOrgao.query.filter_by(user_id=user_id, orgao_id=orgao.id).first()
    if existing is not None:
        return existing
    link = UserOrgao(user_id=user_id, orgao_id=orgao.id)
    db.session.add(link)
    db.session.flush()
    return link
