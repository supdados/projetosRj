"""Testes dos serializers de projeto e de `/api/me` na S4 (F3-9 e F3-10).

Trava o contrato novo (`permissions`, `access_via`, `tem_vinculo_de_area`) e,
com contador de statements, que expor essas chaves NÃO introduz N+1: partindo de
cache frio, serializar 25 projetos custa as mesmas queries (as dos dois mapas
cacheados em `g`) que serializar 1.
"""

import pytest
from flask import g

from models import OrgaoUnidade, Project, ProjectMember, User, UserOrgao, db
from routes.api.serializers import (
    serialize_project_card,
    serialize_project_detail,
    serialize_user,
)
from services.authorization import (
    MEMBERSHIP_MAP_CACHE_ATTR,
    PAPEL_EDITOR,
    PAPEL_GESTOR,
    ROLE_MAP_CACHE_ATTR,
)
from services.orgao_tree import rebuild_orgao_closure
from services.project_membership import (
    ACCESS_VIA_ADMIN,
    ACCESS_VIA_AREA,
    ACCESS_VIA_CONVITE,
)
from tests.sql_query_counter import SqlQueryCounter

# ── Helpers de fixture ────────────────────────────────────────────────────────


def _add_orgao(sigla: str) -> int:
    orgao = OrgaoUnidade(
        sigla=sigla, nome=sigla, tipo="Secretaria", ordem=0, ativo=True
    )
    db.session.add(orgao)
    db.session.flush()
    return orgao.id


def _add_user(username: str, *, is_admin: bool = False) -> User:
    user = User(
        username=username, name=username.upper(), password_hash="x", is_admin=is_admin
    )
    db.session.add(user)
    db.session.flush()
    return user


def _add_projetos(quantidade: int, orgao_id: int) -> list[int]:
    ids = []
    for numero in range(quantidade):
        projeto = Project(titulo=f"Projeto {numero}", orgao_id=orgao_id)
        db.session.add(projeto)
        db.session.flush()
        ids.append(projeto.id)
    return ids


@pytest.fixture
def cenario(app):
    """AREA com 25 projetos e FORA com 1; um gestor de AREA e um convidado."""
    with app.app_context():
        area = _add_orgao("AREA")
        fora = _add_orgao("FORA")
        rebuild_orgao_closure()
        gestor = _add_user("gestor")
        db.session.add(UserOrgao(user_id=gestor.id, orgao_id=area, papel=PAPEL_GESTOR))
        convidado = _add_user("convidado")
        admin = _add_user("root", is_admin=True)
        ids_area = _add_projetos(25, area)
        (id_fora,) = _add_projetos(1, fora)
        db.session.add(
            ProjectMember(
                project_id=id_fora,
                user_id=convidado.id,
                papel=PAPEL_EDITOR,
                granted_by_id=gestor.id,
            )
        )
        db.session.commit()
        yield {
            "area": area,
            "ids_area": ids_area,
            "id_fora": id_fora,
            "gestor_id": gestor.id,
            "convidado_id": convidado.id,
            "admin_id": admin.id,
        }


def _card(project_id: int, viewer) -> dict:
    projeto = db.session.get(Project, project_id)
    return serialize_project_card(projeto, viewer=viewer)


# ── permissions / access_via no card ──────────────────────────────────────────


def test_card_expoe_permissions_e_access_via(app, cenario):
    with app.test_request_context("/"):
        app.config["CONVITES_HABILITADOS"] = True
        gestor = db.session.get(User, cenario["gestor_id"])
        card = _card(cenario["ids_area"][0], gestor)
        assert card["access_via"] == ACCESS_VIA_AREA
        assert card["permissions"] == {
            "can_edit": True,
            "can_manage": True,
            "can_manage_members": True,
        }


def test_card_marca_convidado_com_badge_de_convite(app, cenario):
    with app.test_request_context("/"):
        convidado = db.session.get(User, cenario["convidado_id"])
        card = _card(cenario["id_fora"], convidado)
        assert card["access_via"] == ACCESS_VIA_CONVITE
        assert card["permissions"]["can_edit"] is True
        assert card["permissions"]["can_manage_members"] is False


def test_card_de_admin_nao_recebe_badge_de_convite(app, cenario):
    with app.test_request_context("/"):
        admin = db.session.get(User, cenario["admin_id"])
        assert _card(cenario["id_fora"], admin)["access_via"] == ACCESS_VIA_ADMIN


def test_card_sem_acesso_tem_access_via_none(app, cenario):
    with app.test_request_context("/"):
        gestor = db.session.get(User, cenario["gestor_id"])
        card = _card(cenario["id_fora"], gestor)
        assert card["access_via"] is None
        assert card["permissions"]["can_edit"] is False


def test_viewer_padrao_e_o_usuario_do_request(app, cenario):
    with app.test_request_context("/"):
        g.user = db.session.get(User, cenario["gestor_id"])
        projeto = db.session.get(Project, cenario["ids_area"][0])
        assert serialize_project_card(projeto)["access_via"] == ACCESS_VIA_AREA


def test_detalhe_carrega_o_mesmo_bloco_de_acesso(app, cenario):
    with app.test_request_context("/"):
        gestor = db.session.get(User, cenario["gestor_id"])
        projeto = db.session.get(Project, cenario["ids_area"][0])
        detalhe = serialize_project_detail(projeto, viewer=gestor)
        assert detalhe["access_via"] == ACCESS_VIA_AREA
        assert detalhe["permissions"]["can_manage"] is True
        assert detalhe["observacao"] == projeto.observacao


# ── zero N+1 ──────────────────────────────────────────────────────────────────


def _custo_do_bloco_de_acesso(app, cenario, quantidade: int) -> int:
    """Queries para serializar `quantidade` projetos já aquecidos, com cache frio.

    Sem derrubar os mapas de `g` a segunda medição sairia de graça (o request
    context de teste reaproveita o app context do fixture) e a comparação viraria
    frio-vs-quente, não N+1.
    """
    with app.test_request_context("/"):
        gestor = db.session.get(User, cenario["gestor_id"])
        list(gestor.orgaos)
        projetos = [
            db.session.get(Project, pid) for pid in cenario["ids_area"][:quantidade]
        ]
        # Primeira passada sem viewer: aquece os lazy loads do próprio card.
        for projeto in projetos:
            serialize_project_card(projeto)
        g.pop(ROLE_MAP_CACHE_ATTR, None)
        g.pop(MEMBERSHIP_MAP_CACHE_ATTR, None)
        with SqlQueryCounter(db.engine) as counter:
            cards = [serialize_project_card(p, viewer=gestor) for p in projetos]
        assert all(card["access_via"] == ACCESS_VIA_AREA for card in cards)
        return counter.total


def test_bloco_de_acesso_nao_cresce_com_o_numero_de_projetos(app, cenario):
    """Zero N+1 (F3-10/F3-29): 25 projetos custam o mesmo que 1."""
    assert _custo_do_bloco_de_acesso(app, cenario, 25) == _custo_do_bloco_de_acesso(
        app, cenario, 1
    )


def test_segunda_serializacao_no_mesmo_request_nao_consulta_nada(app, cenario):
    """Os dois mapas ficam em `g`: reserializar a lista sai de graça."""
    with app.test_request_context("/"):
        gestor = db.session.get(User, cenario["gestor_id"])
        projetos = [db.session.get(Project, pid) for pid in cenario["ids_area"]]
        for projeto in projetos:
            serialize_project_card(projeto, viewer=gestor)
        with SqlQueryCounter(db.engine) as counter:
            cards = [serialize_project_card(p, viewer=gestor) for p in projetos]
        assert counter.total == 0
        assert len(cards) == 25


def test_serializar_sem_viewer_nao_consulta_nada_a_mais(app, cenario):
    with app.test_request_context("/"):
        projeto = db.session.get(Project, cenario["ids_area"][0])
        serialize_project_card(projeto)
        with SqlQueryCounter(db.engine) as counter:
            card = serialize_project_card(projeto)
        assert counter.total == 0
        assert card["access_via"] is None


# ── serialize_user / tem_vinculo_de_area ──────────────────────────────────────


def test_serialize_user_expoe_tem_vinculo_de_area(app, cenario):
    with app.app_context():
        gestor = db.session.get(User, cenario["gestor_id"])
        payload = serialize_user(gestor)
        assert payload["tem_vinculo_de_area"] is True
        assert set(payload) == {
            "id",
            "name",
            "username",
            "is_admin",
            "orgaos",
            "tem_vinculo_de_area",
            "auth_provider",
        }


def test_usuario_so_convite_nao_tem_vinculo_de_area(app, cenario):
    """F3-9: sem vínculo, a SPA esconde o seletor e não chega ao 422."""
    with app.app_context():
        convidado = db.session.get(User, cenario["convidado_id"])
        assert serialize_user(convidado)["tem_vinculo_de_area"] is False


def test_admin_sem_vinculo_mantem_tem_vinculo_de_area(app, cenario):
    with app.app_context():
        admin = db.session.get(User, cenario["admin_id"])
        assert serialize_user(admin)["tem_vinculo_de_area"] is True
