"""Testes unitários de ``scoped_orgao_options`` (routes/orgao_scope.py).

Cobrem a lista de órgãos ATRIBUÍVEIS do picker de Área Responsável — picker de
ESCRITA, filtrado por rank desde F2-6: admin enxerga todos os órgãos ativos;
não admin enxerga só a subtree (vínculo + descendentes, restrita a ativos) dos
vínculos com rank >= editor — leitor recebe ``[]``; o papel default do backfill
S2 (``gestor``) preserva a subtree de antes do filtro. Sem vínculo => lista
vazia. Shape ``{id, sigla, nome, pai_id}`` ordenado por ``sigla``.

Reusa o mesmo padrão de helpers nomeados de ``test_orgao_scope_unit.py`` (sem
stubs inline) sobre a fixture ``app``/banco real.
"""

from models import OrgaoUnidade, User, UserOrgao, db
from routes.orgao_scope import scoped_orgao_options
from services.authorization import PAPEL_EDITOR, PAPEL_LEITOR


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


def _add_user(username, is_admin=False, orgao_ids=(), papel=None):
    user = User(username=username, name=username, orgao="x", is_admin=is_admin)
    user.set_password("x")
    db.session.add(user)
    db.session.flush()
    for oid in orgao_ids:
        vinculo = UserOrgao(user_id=user.id, orgao_id=oid)
        if papel is not None:
            vinculo.papel = papel
        db.session.add(vinculo)
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
        assert {"id", "sigla", "nome", "pai_id"} == set(options[0].keys())
        assert options[siglas.index("AAA")]["id"] == a.id
        assert options[siglas.index("AAA")]["pai_id"] is None
        assert options[siglas.index("BBB")]["nome"] == "Nome BBB"
        assert options[siglas.index("BBB")]["pai_id"] == a.id


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


def test_leitor_gets_empty_options(app):
    """F2-6: o picker é de escrita — vínculo leitor não atribui órgão algum."""
    with app.app_context():
        root = _add_orgao("ROOT", tipo="Secretaria")
        _add_orgao("CHILD", pai_id=root.id)
        leitor = _add_user("leitor", orgao_ids=[root.id], papel=PAPEL_LEITOR)

        assert scoped_orgao_options(leitor) == []


def test_editor_options_restricted_to_own_subtree(app):
    with app.app_context():
        root = _add_orgao("ROOT", tipo="Secretaria")
        child = _add_orgao("CHILD", pai_id=root.id)
        outsider = _add_orgao("OUTRO", tipo="Secretaria")
        editor = _add_user("editor", orgao_ids=[child.id], papel=PAPEL_EDITOR)

        siglas = {o["sigla"] for o in scoped_orgao_options(editor)}

        assert siglas == {"CHILD"}
        assert outsider.sigla not in siglas


def test_mixed_vinculos_only_editor_branch_is_assignable(app):
    """Leitor num ramo e editor noutro: só o ramo editor entra no picker."""
    with app.app_context():
        ramo_leitor = _add_orgao("RLEI", tipo="Secretaria")
        ramo_editor = _add_orgao("REDI", tipo="Secretaria")
        _add_orgao("REDIF", pai_id=ramo_editor.id)
        user = _add_user("misto", orgao_ids=[ramo_leitor.id], papel=PAPEL_LEITOR)
        db.session.add(
            UserOrgao(user_id=user.id, orgao_id=ramo_editor.id, papel=PAPEL_EDITOR)
        )
        db.session.flush()

        siglas = {o["sigla"] for o in scoped_orgao_options(user)}

        assert siglas == {"REDI", "REDIF"}
