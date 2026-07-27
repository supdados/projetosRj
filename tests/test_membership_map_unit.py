"""Testes unitários do mapa de convites (S4/F3-5) e do filtro de listagem (§5.3).

Trava as bordas de segurança: revogado/expirado/soft-deletado fora do mapa,
teto rígido de editor mesmo com linha adulterada no banco, cache por request
sem vazamento entre usuários e o OR de membership nas listagens.
"""

from datetime import timedelta

import pytest
from sqlalchemy import text

from models import OrgaoUnidade, Project, ProjectMember, db
from services.authorization import (
    PAPEL_EDITOR,
    PAPEL_LEITOR,
    PAPEL_RANK,
    get_active_membership_map,
    project_visibility_criterion,
)
from tests.test_authorization_unit import SqlQueryCounter
from time_utils import utc_now

# ── Fakes nomeados ────────────────────────────────────────────────────────────


class FakeVinculoArea:
    """Substitui ``UserOrgao``: o serviço só lê ``orgao_id`` e ``papel``."""

    def __init__(self, orgao_id: int, papel: str) -> None:
        self.orgao_id = orgao_id
        self.papel = papel


class FakeConvidado:
    """Substitui ``User``: o serviço lê ``id``, ``is_admin``, ``deleted_at``, ``orgaos``."""

    def __init__(
        self,
        user_id: int | None,
        *,
        vinculos: tuple[tuple[int, str], ...] = (),
        deleted_at=None,
        is_admin: bool = False,
    ) -> None:
        self.id = user_id
        self.is_admin = is_admin
        self.deleted_at = deleted_at
        self.orgaos = [FakeVinculoArea(oid, papel) for oid, papel in vinculos]


# ── Helpers de fixture ────────────────────────────────────────────────────────


def _grava_convite(
    project_id: int,
    user_id: int,
    papel: str,
    *,
    expires_at=None,
    revogado: bool = False,
) -> ProjectMember:
    convite = ProjectMember(
        project_id=project_id,
        user_id=user_id,
        papel=papel,
        granted_by_id=1,
        expires_at=expires_at,
    )
    if revogado:
        convite.revoked_at = utc_now()
        convite.revoked_by_id = 1
    db.session.add(convite)
    db.session.flush()
    return convite


def _grava_convite_adulterado(project_id: int, user_id: int, papel: str) -> None:
    """INSERT cru: simula linha que burlou o validator do modelo."""
    db.session.execute(
        text(
            "INSERT INTO project_member "
            "(project_id, user_id, papel, origem, granted_by_id, created_at) "
            "VALUES (:p, :u, :papel, 'convite', 1, :agora)"
        ),
        {"p": project_id, "u": user_id, "papel": papel, "agora": utc_now()},
    )
    db.session.flush()


def _add_orgao(sigla: str, pai_id: int | None) -> int:
    orgao = OrgaoUnidade(
        sigla=sigla, nome=sigla, tipo="Secretaria", pai_id=pai_id, ordem=0, ativo=True
    )
    db.session.add(orgao)
    db.session.flush()
    return orgao.id


def _add_projeto(titulo: str, orgao_id: int | None) -> int:
    projeto = Project(titulo=titulo, orgao_id=orgao_id)
    db.session.add(projeto)
    db.session.flush()
    return projeto.id


@pytest.fixture
def cenario_listagem(app):
    """Órgão AREA (do usuário) e FORA (alheio), com um projeto em cada + um órfão."""
    with app.app_context():
        area = _add_orgao("AREA", None)
        fora = _add_orgao("FORA", None)
        yield {
            "area": area,
            "fora": fora,
            "proj_area": _add_projeto("Projeto da área", area),
            "proj_fora": _add_projeto("Projeto alheio", fora),
            "proj_sem_orgao": _add_projeto("Projeto órfão", None),
        }


# ── get_active_membership_map ─────────────────────────────────────────────────


def test_convites_leitor_e_editor_entram_no_mapa_com_rank(app):
    with app.app_context():
        _grava_convite(701, 91, PAPEL_LEITOR)
        _grava_convite(702, 91, PAPEL_EDITOR)
        assert get_active_membership_map(FakeConvidado(91)) == {
            701: PAPEL_RANK[PAPEL_LEITOR],
            702: PAPEL_RANK[PAPEL_EDITOR],
        }


def test_convite_revogado_fica_fora_do_mapa(app):
    with app.app_context():
        _grava_convite(701, 91, PAPEL_EDITOR, revogado=True)
        assert get_active_membership_map(FakeConvidado(91)) == {}


def test_convite_expirado_fica_fora_na_leitura(app):
    """Expiração é lazy (§7): decide na leitura, sem cron nem UPDATE."""
    with app.app_context():
        _grava_convite(701, 91, PAPEL_EDITOR, expires_at=utc_now() - timedelta(days=1))
        assert get_active_membership_map(FakeConvidado(91)) == {}


def test_convite_sem_expiracao_ou_com_expiracao_futura_esta_ativo(app):
    with app.app_context():
        _grava_convite(701, 91, PAPEL_LEITOR)
        _grava_convite(702, 91, PAPEL_LEITOR, expires_at=utc_now() + timedelta(days=90))
        assert set(get_active_membership_map(FakeConvidado(91))) == {701, 702}


def test_convidado_soft_deletado_perde_o_mapa(app):
    with app.app_context():
        _grava_convite(701, 91, PAPEL_EDITOR)
        convidado = FakeConvidado(91, deleted_at=utc_now())
        assert get_active_membership_map(convidado) == {}


def test_user_none_ou_sem_id_retorna_mapa_vazio(app):
    with app.app_context():
        assert get_active_membership_map(None) == {}
        assert get_active_membership_map(FakeConvidado(None)) == {}


def test_mapa_ignora_convites_de_outros_usuarios(app):
    with app.app_context():
        _grava_convite(701, 91, PAPEL_EDITOR)
        _grava_convite(702, 92, PAPEL_LEITOR)
        assert set(get_active_membership_map(FakeConvidado(91))) == {701}


def test_linha_adulterada_com_gestor_clampa_ao_teto_editor(app):
    """Teto rígido: nem UPDATE direto no banco concede gestão via convite."""
    with app.app_context():
        _grava_convite_adulterado(701, 91, "gestor")
        assert get_active_membership_map(FakeConvidado(91)) == {
            701: PAPEL_RANK[PAPEL_EDITOR]
        }


def test_papel_desconhecido_no_banco_fica_fora_do_mapa(app):
    with app.app_context():
        _grava_convite_adulterado(701, 91, "dono")
        assert get_active_membership_map(FakeConvidado(91)) == {}


def test_mapa_usa_uma_query_para_n_convites(app):
    with app.app_context():
        for numero in range(50):
            _grava_convite(800 + numero, 91, PAPEL_LEITOR)
        with SqlQueryCounter(db.engine) as counter:
            mapa = get_active_membership_map(FakeConvidado(91))
        assert counter.total == 1
        assert len(mapa) == 50


def test_segunda_chamada_no_mesmo_request_nao_consulta_o_banco(app):
    with app.test_request_context("/"):
        _grava_convite(701, 91, PAPEL_EDITOR)
        primeiro = get_active_membership_map(FakeConvidado(91))
        with SqlQueryCounter(db.engine) as counter:
            segundo = get_active_membership_map(FakeConvidado(91))
        assert counter.total == 0
        assert segundo == primeiro


def test_cache_do_request_nao_vaza_entre_usuarios(app):
    with app.test_request_context("/"):
        _grava_convite(701, 91, PAPEL_EDITOR)
        _grava_convite(702, 92, PAPEL_LEITOR)
        assert set(get_active_membership_map(FakeConvidado(91))) == {701}
        assert set(get_active_membership_map(FakeConvidado(92))) == {702}


def test_revogacao_vale_no_request_seguinte(app):
    with app.test_request_context("/"):
        convite = _grava_convite(701, 91, PAPEL_EDITOR)
        assert set(get_active_membership_map(FakeConvidado(91))) == {701}
        convite.revoked_at = utc_now()
        db.session.flush()
    with app.test_request_context("/"):
        assert get_active_membership_map(FakeConvidado(91)) == {}


# ── project_visibility_criterion (filtro §5.3 das listagens) ──────────────────


def _ids_visiveis(user) -> set[int]:
    query = Project.query.filter(project_visibility_criterion(user))
    return {projeto.id for projeto in query.all()}


def test_criterion_une_subtree_de_area_e_convite(app, cenario_listagem):
    with app.app_context():
        _grava_convite(cenario_listagem["proj_fora"], 91, PAPEL_LEITOR)
        user = FakeConvidado(91, vinculos=((cenario_listagem["area"], PAPEL_EDITOR),))
        assert _ids_visiveis(user) == {
            cenario_listagem["proj_area"],
            cenario_listagem["proj_fora"],
        }


def test_criterion_so_convite_lista_so_o_projeto_convidado(app, cenario_listagem):
    with app.app_context():
        _grava_convite(cenario_listagem["proj_fora"], 91, PAPEL_LEITOR)
        assert _ids_visiveis(FakeConvidado(91)) == {cenario_listagem["proj_fora"]}


def test_criterion_alcanca_projeto_sem_orgao_via_convite(app, cenario_listagem):
    with app.app_context():
        _grava_convite(cenario_listagem["proj_sem_orgao"], 91, PAPEL_LEITOR)
        assert _ids_visiveis(FakeConvidado(91)) == {cenario_listagem["proj_sem_orgao"]}


def test_criterion_sem_escopo_devolve_lista_vazia(app, cenario_listagem):
    with app.app_context():
        assert _ids_visiveis(FakeConvidado(91)) == set()


def test_criterion_convite_revogado_nao_lista(app, cenario_listagem):
    with app.app_context():
        _grava_convite(cenario_listagem["proj_fora"], 91, PAPEL_EDITOR, revogado=True)
        assert _ids_visiveis(FakeConvidado(91)) == set()


def test_criterion_sem_convites_equivale_ao_filtro_antigo(app, cenario_listagem):
    """Equivalência S4: zero linhas em project_member ⇒ mesma lista de sempre."""
    with app.app_context():
        user = FakeConvidado(91, vinculos=((cenario_listagem["area"], PAPEL_LEITOR),))
        from services.authorization import get_user_orgao_subtree_ids

        subtree = get_user_orgao_subtree_ids(user)
        antigo = {
            projeto.id
            for projeto in Project.query.filter(Project.orgao_id.in_(subtree)).all()
        }
        assert _ids_visiveis(user) == antigo == {cenario_listagem["proj_area"]}
