"""Testes unitários de ``scoped_orgao_options`` (routes/orgao_scope.py).

Cobrem o escopo da lista de órgãos atribuíveis usada no picker de Área
Responsável do Detalhe de Projeto: admin enxerga todos os órgãos ativos; não
admin enxerga apenas a própria subtree (vínculo + descendentes), sempre restrita
a ativos; não admin sem vínculo recebe lista vazia. O shape devolvido é
``{id, sigla, nome}`` ordenado por ``sigla``.

Reusa o mesmo padrão de helpers nomeados de ``test_orgao_scope_unit.py`` (sem
stubs inline) sobre a fixture ``app``/banco real.
"""

from models import OrgaoUnidade, User, UserOrgao, db
from routes.orgao_scope import scoped_orgao_options


def _add_orgao(sigla, pai_id=None, tipo="Subsecretaria", ativo=True):
    orgao = OrgaoUnidade(
        sigla=sigla,
        nome=f"Nome {sigla}",
        tipo=tipo,
        pai_id=pai_id,
        ordem=0,
        ativo=ativo,
    )
    db.session.add(orgao)
    db.session.flush()
    return orgao


def _add_user(username, is_admin=False, orgao_ids=()):
    user = User(username=username, name=username, orgao="x", is_admin=is_admin)
    user.set_password("x")
    db.session.add(user)
    db.session.flush()
    for oid in orgao_ids:
        db.session.add(UserOrgao(user_id=user.id, orgao_id=oid))
    db.session.flush()
    return user


def test_admin_options_include_all_active_orgaos_sorted_by_sigla(app):
    with app.app_context():
        a = _add_orgao("AAA", tipo="Secretaria")
        b = _add_orgao("BBB", pai_id=a.id)
        _add_orgao("CCC", ativo=False)
        admin = _add_user("admin", is_admin=True)

        options = scoped_orgao_options(admin)
        siglas = [o["sigla"] for o in options]

        assert "AAA" in siglas and "BBB" in siglas
        assert "CCC" not in siglas
        assert siglas == sorted(siglas)
        assert {"id", "sigla", "nome"} == set(options[0].keys())
        assert options[siglas.index("AAA")]["id"] == a.id
        assert options[siglas.index("BBB")]["nome"] == "Nome BBB"


def test_non_admin_options_restricted_to_subtree_active(app):
    with app.app_context():
        root = _add_orgao("ROOT", tipo="Secretaria")
        child = _add_orgao("CHILD", pai_id=root.id)
        inactive_child = _add_orgao("INACT", pai_id=root.id, ativo=False)
        outsider = _add_orgao("OUTRO", tipo="Secretaria")
        user = _add_user("u", orgao_ids=[root.id])

        siglas = {o["sigla"] for o in scoped_orgao_options(user)}

        assert siglas == {"ROOT", "CHILD"}
        assert "INACT" not in siglas
        assert outsider.sigla not in siglas


def test_non_admin_without_vinculo_gets_empty_list(app):
    with app.app_context():
        _add_orgao("SOLO", tipo="Secretaria")
        user = _add_user("u")
        assert scoped_orgao_options(user) == []
