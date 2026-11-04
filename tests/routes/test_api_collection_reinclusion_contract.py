"""Re-inclusão idempotente de projeto na coleção sobe o teto de QUEM incluiu.

Antes, o POST de um projeto que já estava na coleção respondia 200 sem efeito:
um item incluído com teto 0 (dono que só via o projeto por convite) ficava preso
mesmo depois de o dono ganhar a área — os membros nunca passavam a vê-lo.
Agora o teto vira max(atual, teto de agora) quando quem re-inclui é quem
incluiu (o dono, no item próprio/legado); item de outra pessoa fica intocado.
"""

from __future__ import annotations

import pytest

from models import Project, ProjectCollectionItem, ProjectMember, UserOrgao, db
from tests.routes._collection_http_helpers import (
    IdsDoCenario,
    aceito,
    convidar,
    criar_colecao,
    dados,
    get,
    ids_dos_projetos_da_colecao,
    post,
    semear_ids,
)


@pytest.fixture
def ids(app) -> IdsDoCenario:
    return semear_ids(app)


def _incluir(app, user_id: int, cid: int, project_id: int) -> None:
    body = {"project_id": project_id}
    dados(post(app, user_id, f"/api/colecoes/{cid}/projetos", body))


def _item(app, cid: int, project_id: int) -> tuple[int | None, int | None]:
    """``(added_by_user_id, rank_teto)`` do item."""
    with app.app_context():
        item = ProjectCollectionItem.query.filter_by(
            collection_id=cid, project_id=project_id
        ).one()
        return item.added_by_user_id, item.rank_teto


def _lotar(app, user_id: int, orgao_id: int, papel: str) -> None:
    with app.app_context():
        UserOrgao.query.filter_by(user_id=user_id, orgao_id=orgao_id).delete()
        db.session.add(UserOrgao(user_id=user_id, orgao_id=orgao_id, papel=papel))
        db.session.commit()


def test_dono_que_ganhou_area_reinclui_e_membros_passam_a_ver(app, ids):
    with app.app_context():
        db.session.add(
            ProjectMember(
                project_id=ids.so_convite,
                user_id=ids.dono,
                granted_by_id=ids.editor,
                papel="leitor",
            )
        )
        db.session.commit()
        orgao_do_projeto = db.session.get(Project, ids.so_convite).orgao_id
    cid = criar_colecao(app, ids.dono, [ids.do_dono])
    convidar(app, ids.dono, cid, user_id=ids.convidado)
    aceito(app, ids.convidado, cid)
    _incluir(app, ids.dono, cid, ids.so_convite)
    assert _item(app, cid, ids.so_convite) == (ids.dono, 0)
    assert ids_dos_projetos_da_colecao(app, ids.convidado, cid) == {ids.do_dono}

    _lotar(app, ids.dono, orgao_do_projeto, "gestor")
    _incluir(app, ids.dono, cid, ids.so_convite)

    assert _item(app, cid, ids.so_convite) == (ids.dono, 20)
    assert ids_dos_projetos_da_colecao(app, ids.convidado, cid) == {
        ids.do_dono,
        ids.so_convite,
    }
    dados(get(app, ids.convidado, f"/api/projetos/{ids.so_convite}/detalhe"))


def test_reinclusao_so_sobe_o_teto_de_quem_incluiu(app, ids):
    with app.app_context():
        projeto = Project(titulo="Da Area", orgao_id=ids.area, status="Vigente")
        db.session.add(projeto)
        db.session.commit()
        da_area = projeto.id
    cid = criar_colecao(app, ids.dono, [ids.do_dono])
    convidar(app, ids.dono, cid, papel="editor", user_id=ids.colega)
    aceito(app, ids.colega, cid)
    _incluir(app, ids.colega, cid, da_area)  # colega é LEITOR na área: teto 10
    assert _item(app, cid, da_area) == (ids.colega, 10)

    _incluir(app, ids.dono, cid, da_area)  # dono gestor: item alheio, intocado
    assert _item(app, cid, da_area) == (ids.colega, 10)

    _lotar(app, ids.colega, ids.area, "gestor")
    _incluir(app, ids.colega, cid, da_area)  # o próprio incluidor sobe o teto
    assert _item(app, cid, da_area) == (ids.colega, 20)
