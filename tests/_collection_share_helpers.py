"""Cenário e atalhos dos testes de coleção compartilhada com aceite.

Compartilhado por ``tests/test_collection_shares_unit.py`` (ciclo do convite)
e ``tests/test_collection_curation_unit.py`` (inclusão, teto, poda, leitores).
"""

from __future__ import annotations

from dataclasses import dataclass

from models import (
    ALVO_COLECAO,
    PAPEL_SHARE_VIEWER,
    AutorizacaoAudit,
    OrgaoUnidade,
    Project,
    ProjectCollection,
    ProjectCollectionShare,
    ProjectMember,
    User,
    UserOrgao,
    db,
)
from services.collection_shares import compartilhar_colecao
from services.orgao_tree import rebuild_orgao_closure
from services.project_collections import criar_colecao


@dataclass
class CenarioConvite:
    """Dono em AREAA; colega leitor na MESMA área; convidado/editor em EXT;
    membros do órgão ORGX. ``so_convite`` é visto pelo editor só por convite."""

    dono: User
    colega: User
    convidado: User
    editor: User
    membro_a: User
    membro_b: User
    area_id: int
    ext_id: int
    orgx_id: int
    do_dono_id: int
    do_ext_id: int
    so_convite_id: int


def _orgao(sigla: str) -> int:
    orgao = OrgaoUnidade(sigla=sigla, nome=sigla, tipo="Secretaria", ordem=0)
    db.session.add(orgao)
    db.session.flush()
    return orgao.id


def _usuario(nome: str, orgao_id: int, papel: str = "gestor") -> User:
    user = User(username=nome, name=nome.upper(), password_hash="x")
    db.session.add(user)
    db.session.flush()
    db.session.add(UserOrgao(user_id=user.id, orgao_id=orgao_id, papel=papel))
    db.session.flush()
    return user


def _projeto(titulo: str, orgao_id: int) -> int:
    projeto = Project(titulo=titulo, orgao_id=orgao_id, status="Vigente")
    db.session.add(projeto)
    db.session.flush()
    return projeto.id


def semear_cenario_convite() -> CenarioConvite:
    """Grava e commita o cenário; chamar dentro de ``app.app_context()``."""
    area, ext, orgx, outra = (_orgao(s) for s in ("AREAA", "EXT", "ORGX", "OUTRA"))
    rebuild_orgao_closure()
    editor = _usuario("editor", ext)
    so_convite_id = _projeto("Projeto So Convite", outra)
    db.session.add(
        ProjectMember(
            project_id=so_convite_id,
            user_id=editor.id,
            granted_by_id=editor.id,
            papel="editor",
        )
    )
    cenario = CenarioConvite(
        dono=_usuario("dono", area),
        colega=_usuario("colega", area, papel="leitor"),
        convidado=_usuario("convidado", ext),
        editor=editor,
        membro_a=_usuario("membro_a", orgx),
        membro_b=_usuario("membro_b", orgx),
        area_id=area,
        ext_id=ext,
        orgx_id=orgx,
        do_dono_id=_projeto("Projeto do Dono", area),
        do_ext_id=_projeto("Projeto Externo", ext),
        so_convite_id=so_convite_id,
    )
    db.session.commit()
    return cenario


def colecao_do_dono(cenario: CenarioConvite, nome: str = "Compartilhada"):
    """Coleção custom do dono com ``do_dono`` já incluído (commitada)."""
    colecao = criar_colecao(
        cenario.dono, nome, None, "camadas", "primary", [cenario.do_dono_id]
    )
    db.session.commit()
    return colecao


def compartilhar(
    colecao: ProjectCollection,
    cenario: CenarioConvite,
    papel: str = PAPEL_SHARE_VIEWER,
    **destino: int,
) -> ProjectCollectionShare:
    """Share novo (convite pendente) pelo dono, commitado."""
    share = compartilhar_colecao(colecao, ator=cenario.dono, papel=papel, **destino)
    db.session.commit()
    return share


def eventos_de(colecao: ProjectCollection) -> list[str]:
    linhas = (
        AutorizacaoAudit.query.filter_by(alvo_tipo=ALVO_COLECAO, alvo_id=colecao.id)
        .order_by(AutorizacaoAudit.id)
        .all()
    )
    return [linha.evento for linha in linhas]


def detalhes_de_poda(colecao: ProjectCollection) -> list[dict[str, object]]:
    linhas = (
        AutorizacaoAudit.query.filter_by(
            alvo_tipo=ALVO_COLECAO,
            alvo_id=colecao.id,
            evento="colecao_projeto_removido",
        )
        .order_by(AutorizacaoAudit.id)
        .all()
    )
    return [linha.detalhe for linha in linhas]
