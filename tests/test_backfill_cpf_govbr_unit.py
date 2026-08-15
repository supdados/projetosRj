"""Testes do backfill em massa de ``User.cpf_govbr`` a partir do username legado.

O backfill (auditoria §2.8) é o pré-requisito para o callback gov.br resolver o
vínculo pela coluna indexada em vez do antigo scan O(n) sobre todos os usuários.
"""

import pytest

from models import User, db
from scripts.migrations.backfill_cpf_govbr import (
    apply_cpf_backfill,
    build_cpf_backfill_plan,
)


def _add_user(username, *, name="Usuario Teste", cpf_govbr=None):
    user = User(username=username, name=name, orgao="SETD", cpf_govbr=cpf_govbr)
    user.set_password("senha123")
    db.session.add(user)
    db.session.flush()
    return user.id


@pytest.fixture
def plano(app):
    """Constrói o plano dentro do app_context sobre todos os usuários do banco."""

    def _build():
        return build_cpf_backfill_plan(User.query.order_by(User.id).all())

    return _build


def test_grava_cpf_de_username_formatado_e_de_digitos(app, plano):
    with app.app_context():
        formatado_id = _add_user("123.456.789-01")
        digitos_id = _add_user("98765432100")

        gravados = apply_cpf_backfill(plano())

        assert gravados == 2
        assert db.session.get(User, formatado_id).cpf_govbr == "12345678901"
        assert db.session.get(User, digitos_id).cpf_govbr == "98765432100"


def test_username_que_nao_e_cpf_e_ignorado(app, plano):
    with app.app_context():
        admin_id = _add_user("admin")
        curto_id = _add_user("1234567890")

        resultado = plano()

        assert resultado.to_write == []
        assert resultado.conflicts == {}
        assert db.session.get(User, admin_id).cpf_govbr is None
        assert db.session.get(User, curto_id).cpf_govbr is None


def test_conflito_entre_dois_usernames_nao_grava_nenhum(app, plano):
    with app.app_context():
        com_ponto_id = _add_user("111.222.333-44")
        so_digitos_id = _add_user("11122233344")

        resultado = plano()
        apply_cpf_backfill(resultado)

        assert resultado.to_write == []
        assert resultado.conflicts == {"11122233344": ["111.222.333-44", "11122233344"]}
        assert db.session.get(User, com_ponto_id).cpf_govbr is None
        assert db.session.get(User, so_digitos_id).cpf_govbr is None


def test_conflito_com_cpf_ja_pertencente_a_outro_usuario(app, plano):
    with app.app_context():
        dono_id = _add_user("dono", cpf_govbr="55566677788")
        legado_id = _add_user("555.666.777-88")

        resultado = plano()
        apply_cpf_backfill(resultado)

        assert resultado.conflicts == {"55566677788": ["555.666.777-88", "dono"]}
        assert db.session.get(User, dono_id).cpf_govbr == "55566677788"
        assert db.session.get(User, legado_id).cpf_govbr is None


def test_idempotente_segunda_execucao_nao_grava_nada(app, plano):
    with app.app_context():
        user_id = _add_user("123.456.789-01")
        apply_cpf_backfill(plano())

        segundo = plano()

        assert segundo.to_write == []
        assert segundo.already_filled == 1
        assert apply_cpf_backfill(segundo) == 0
        assert db.session.get(User, user_id).cpf_govbr == "12345678901"


def test_cpf_ja_preenchido_nunca_e_reescrito_pelo_username(app, plano):
    with app.app_context():
        user_id = _add_user("123.456.789-01", cpf_govbr="99988877766")

        resultado = plano()

        assert resultado.to_write == []
        assert db.session.get(User, user_id).cpf_govbr == "99988877766"
