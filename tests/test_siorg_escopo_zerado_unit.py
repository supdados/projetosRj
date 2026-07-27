"""Teste do relatório TR-2: sync SIORG que zera o escopo de área de usuários.

Reusa os fakes de ``tests/test_siorg_sync_unit.py``. Regra: só há registro
quando o sync DESATIVA alguma unidade, e o registro é informativo — o escopo de
acesso continua ignorando ``ativo`` (F0-3/F1-4), nada muda para o usuário.
"""

import pytest

from models import OrgaoUnidade, User, UserOrgao, db
from services.authorization import PAPEL_GESTOR, get_user_orgao_role_map
from services.authorization_reports import (
    ler_escopo_zerado,
    usuarios_com_escopo_zerado,
)
from services.siorg_sync import executar_sync_siorg
from tests.test_siorg_sync_unit import ARVORE, MANIFESTO, FakeSiorgClient
from time_utils import utc_now

# ── Helpers ───────────────────────────────────────────────────────────────────


def _client() -> FakeSiorgClient:
    return FakeSiorgClient(MANIFESTO, ARVORE)


def _add_orgao(sigla: str, codigo_externo: str | None) -> OrgaoUnidade:
    orgao = OrgaoUnidade(
        sigla=sigla,
        nome=sigla,
        tipo="Subsecretaria",
        codigo_externo=codigo_externo,
        ativo=True,
        ordem=0,
    )
    db.session.add(orgao)
    db.session.flush()
    return orgao


def _vincula(username: str, orgao_ids: list[int]) -> User:
    user = User(username=username, name=username.upper(), password_hash="x")
    db.session.add(user)
    db.session.flush()
    for orgao_id in orgao_ids:
        db.session.add(
            UserOrgao(user_id=user.id, orgao_id=orgao_id, papel=PAPEL_GESTOR)
        )
    db.session.flush()
    return user


@pytest.fixture
def extinta(app):
    """Unidade com codigo_externo ausente do payload: o sync vai desativá-la."""
    with app.app_context():
        orgao = _add_orgao("EXT", "999")
        db.session.commit()
        yield orgao.id


# ── Sync com desativação ──────────────────────────────────────────────────────


def test_sync_registra_usuario_que_ficou_sem_orgao_ativo(app, extinta):
    with app.app_context():
        _vincula("orfao", [extinta])
        db.session.commit()

        log = executar_sync_siorg(_client(), None, codigo_raiz=2)

        relatados = ler_escopo_zerado(log.usuarios_escopo_zerado)
        assert log.desativadas == 1
        assert [item["username"] for item in relatados] == ["orfao"]


def test_usuario_com_outro_vinculo_ativo_nao_entra_no_relatorio(app, extinta):
    with app.app_context():
        viva = _add_orgao("VIVA", None)
        _vincula("salvo", [extinta, viva.id])
        db.session.commit()

        log = executar_sync_siorg(_client(), None, codigo_raiz=2)

        assert ler_escopo_zerado(log.usuarios_escopo_zerado) == []


def test_usuario_sem_vinculo_no_orgao_desativado_nao_entra(app, extinta):
    with app.app_context():
        viva = _add_orgao("VIVA", None)
        _vincula("alheio", [viva.id])
        db.session.commit()

        log = executar_sync_siorg(_client(), None, codigo_raiz=2)

        assert ler_escopo_zerado(log.usuarios_escopo_zerado) == []


def test_escopo_do_usuario_continua_o_mesmo_apos_o_sync(app, extinta):
    """TR-2 é relatório: o role map segue resolvendo o órgão desativado."""
    with app.app_context():
        user = _vincula("orfao", [extinta])
        db.session.commit()

        executar_sync_siorg(_client(), None, codigo_raiz=2)

        assert db.session.get(OrgaoUnidade, extinta).ativo is False
        assert set(get_user_orgao_role_map(user)) == {extinta}


# ── Sync sem desativação ──────────────────────────────────────────────────────


def test_sync_sem_desativacao_nao_registra_nada(app):
    with app.app_context():
        viva = _add_orgao("VIVA", None)
        _vincula("qualquer", [viva.id])
        db.session.commit()

        log = executar_sync_siorg(_client(), None, codigo_raiz=2)

        assert log.desativadas == 0
        assert log.usuarios_escopo_zerado is None


# ── Função de consulta isolada ────────────────────────────────────────────────


def test_lista_vazia_de_desativados_nao_consulta_nada(app):
    with app.app_context():
        assert usuarios_com_escopo_zerado([]) == []


def test_usuario_soft_deletado_nao_entra_no_relatorio(app, extinta):
    with app.app_context():
        removido = _vincula("removido", [extinta])
        removido.deleted_at = utc_now()
        db.session.commit()
        OrgaoUnidade.query.filter_by(id=extinta).update({"ativo": False})
        db.session.commit()

        assert usuarios_com_escopo_zerado([extinta]) == []
