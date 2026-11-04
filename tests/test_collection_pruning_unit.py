"""Poda com incluidores órfãos e a avaliação EM LOTE de quem segue editor.

- Uma mesma poda pode tirar itens de quem perdeu o editor pela mutação (motivo
  da mutação) e de quem já estava sem papel (``incluidor_sem_papel``); "sair"
  devolve só os itens do próprio ator.
- ``incluidores_sem_editor`` julga N pessoas de uma vez em Python; precisa dar
  EXATAMENTE o que o SQL de ``shares_validos_do_usuario`` daria pessoa a pessoa
  (equivalência por estado: aceito, legado, pendente, recusado, saiu, viewer,
  órgão aceito/pendente, quem saiu do órgão, removido, dono removido).
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from models import (
    PAPEL_SHARE_EDITOR,
    PAPEL_SHARE_VIEWER,
    STATUS_RESPOSTA_ACEITO,
    STATUS_RESPOSTA_RECUSADO,
    STATUS_RESPOSTA_SAIU,
    OrgaoUnidade,
    Project,
    ProjectCollectionItem,
    ProjectCollectionShare,
    ProjectCollectionShareResposta,
    User,
    UserOrgao,
    db,
)
from services.collection_participation import shares_validos_do_usuario
from services.collection_shares import (
    MOTIVO_PODA_INCLUIDOR_SEM_PAPEL,
    MOTIVO_PODA_REVOGADO,
    aceitar_convite,
    incluidores_sem_editor,
    prever_poda,
    revogar_share,
    sair_da_colecao,
)
from services.project_collections import adicionar_projeto
from tests._collection_share_helpers import (
    colecao_do_dono,
    compartilhar,
    detalhes_de_poda,
    semear_cenario_convite,
)
from time_utils import utc_now


@pytest.fixture
def cenario(app):
    with app.app_context():
        yield semear_cenario_convite()


def _projeto(titulo: str, orgao_id: int | None) -> int:
    projeto = Project(titulo=titulo, orgao_id=orgao_id, status="Vigente")
    db.session.add(projeto)
    db.session.flush()
    return projeto.id


# ── Motivo por item e contagem de "sair" ──────────────────────────────────────


def _orfao_e_editor_vivo(cenario):
    """Editor (EXT) incluiu ``do_ext`` e foi desativado; membro_a (ORGX) segue
    editor e incluiu um projeto do ORGX."""
    colecao = colecao_do_dono(cenario)
    do_editor = compartilhar(
        colecao, cenario, PAPEL_SHARE_EDITOR, user_id=cenario.editor.id
    )
    do_membro = compartilhar(
        colecao, cenario, PAPEL_SHARE_EDITOR, user_id=cenario.membro_a.id
    )
    aceitar_convite(colecao.id, cenario.editor)
    aceitar_convite(colecao.id, cenario.membro_a)
    do_orgx = _projeto("Projeto ORGX", cenario.orgx_id)
    adicionar_projeto(colecao, cenario.do_ext_id, ator=cenario.editor)
    adicionar_projeto(colecao, do_orgx, ator=cenario.membro_a)
    cenario.editor.deleted_at = utc_now()
    db.session.commit()
    return colecao, do_editor, do_membro, do_orgx


def test_previsao_separa_o_orfao_do_que_sai_por_share(app, cenario):
    with app.test_request_context("/"):
        colecao, do_editor, do_membro, _ = _orfao_e_editor_vivo(cenario)

        previsao = prever_poda(colecao, [do_editor, do_membro])

        assert previsao.por_share == {do_editor.id: 0, do_membro.id: 1}
        assert previsao.por_editor == {cenario.membro_a.id: 1}
        assert previsao.orfaos == 1


@pytest.mark.parametrize(
    ("acao", "motivo"),
    [("revogar", MOTIVO_PODA_REVOGADO), ("sair", "participante_saiu")],
)
def test_mesma_poda_atribui_cada_item_ao_seu_motivo(app, cenario, acao, motivo):
    with app.test_request_context("/"):
        colecao, _, do_membro, do_orgx = _orfao_e_editor_vivo(cenario)

        if acao == "revogar":
            revogar_share(colecao, do_membro.id, ator=cenario.dono)
        else:
            assert sair_da_colecao(colecao.id, cenario.membro_a) == 1
        db.session.commit()

        assert {d["project_id"]: d["motivo"] for d in detalhes_de_poda(colecao)} == {
            cenario.do_ext_id: MOTIVO_PODA_INCLUIDOR_SEM_PAPEL,
            do_orgx: motivo,
        }


# ── Equivalência: lote em Python × SQL pessoa a pessoa ───────────────────────


@dataclass(frozen=True)
class EstadoDoIncluidor:
    """Como a pessoa chega (ou não) ao papel editor na coleção."""

    nome: str
    papel: str | None = PAPEL_SHARE_EDITOR
    via_orgao: bool = False
    exige_aceite: bool = True
    resposta: str | None = STATUS_RESPOSTA_ACEITO
    lotada_no_orgao: bool = True
    removida: bool = False


ESTADOS = (
    EstadoDoIncluidor("aceito"),
    EstadoDoIncluidor("legado", exige_aceite=False, resposta=None),
    EstadoDoIncluidor("pendente", resposta=None),
    EstadoDoIncluidor("recusado", resposta=STATUS_RESPOSTA_RECUSADO),
    EstadoDoIncluidor("saiu", resposta=STATUS_RESPOSTA_SAIU),
    EstadoDoIncluidor("viewer", papel=PAPEL_SHARE_VIEWER),
    EstadoDoIncluidor("orgao_aceito", via_orgao=True),
    EstadoDoIncluidor("orgao_pendente", via_orgao=True, resposta=None),
    EstadoDoIncluidor(
        "orgao_legado", via_orgao=True, exige_aceite=False, resposta=None
    ),
    EstadoDoIncluidor("saiu_do_orgao", via_orgao=True, lotada_no_orgao=False),
    EstadoDoIncluidor("removido", removida=True),
    EstadoDoIncluidor("sem_share", papel=None),
)
EDITORES_ESPERADOS = {"aceito", "legado", "orgao_aceito", "orgao_legado"}


def _incluidor_no_estado(colecao, dono: User, estado: EstadoDoIncluidor) -> User:
    orgao = OrgaoUnidade(sigla=estado.nome, nome=estado.nome, tipo="Secretaria")
    user = User(username=f"i_{estado.nome}", name=estado.nome, password_hash="x")
    db.session.add_all([orgao, user])
    db.session.flush()
    if estado.lotada_no_orgao:
        db.session.add(UserOrgao(user_id=user.id, orgao_id=orgao.id, papel="gestor"))
    if estado.removida:
        user.deleted_at = utc_now()
    if estado.papel is not None:
        _share_no_estado(colecao, dono, user, orgao.id, estado)
    db.session.add(
        ProjectCollectionItem(
            collection_id=colecao.id,
            project_id=_projeto(f"P {estado.nome}", orgao.id),
            added_by_user_id=user.id,
            rank_teto=20,
        )
    )
    return user


def _share_no_estado(colecao, dono, user, orgao_id, estado) -> None:
    share = ProjectCollectionShare(
        collection_id=colecao.id,
        user_id=None if estado.via_orgao else user.id,
        orgao_id=orgao_id if estado.via_orgao else None,
        papel=estado.papel,
        created_by_user_id=dono.id,
        exige_aceite=estado.exige_aceite,
    )
    db.session.add(share)
    db.session.flush()
    if estado.resposta is not None:
        db.session.add(
            ProjectCollectionShareResposta(
                share_id=share.id, user_id=user.id, status=estado.resposta
            )
        )


def _sem_editor_pelo_sql(colecao, incluidores: list[User]) -> set[int]:
    return {
        user.id
        for user in incluidores
        if user.deleted_at is not None
        or not any(
            share.papel == PAPEL_SHARE_EDITOR
            for share in shares_validos_do_usuario(user, [colecao.id])
        )
    }


@pytest.mark.parametrize("dono_removido", [False, True])
def test_lote_equivale_ao_sql_em_todos_os_estados(app, cenario, dono_removido):
    with app.test_request_context("/"):
        colecao = colecao_do_dono(cenario)
        incluidores = [
            _incluidor_no_estado(colecao, cenario.dono, estado) for estado in ESTADOS
        ]
        if dono_removido:
            cenario.dono.deleted_at = utc_now()
        db.session.commit()

        sem_editor = incluidores_sem_editor(colecao)

        assert sem_editor == _sem_editor_pelo_sql(colecao, incluidores)
        editores = {u.name for u in incluidores if u.id not in sem_editor}
        assert editores == (set() if dono_removido else EDITORES_ESPERADOS)
