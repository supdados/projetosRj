from models import OrgaoUnidade, User, UserOrgao, db
from routes.orgao_scope import (
    expand_orgao_filter_ids,
    get_user_orgao_subtree_ids,
    sanitize_orgao_filter_for_user,
)


def _add_orgao(sigla, pai_id=None, tipo='Subsecretaria', ativo=True):
    o = OrgaoUnidade(
        sigla=sigla, nome=sigla, tipo=tipo, pai_id=pai_id, ordem=0, ativo=ativo,
    )
    db.session.add(o)
    db.session.flush()
    return o


def _add_user(username, is_admin=False, orgao_ids=()):
    user = User(username=username, name=username, orgao='x', is_admin=is_admin)
    user.set_password('x')
    db.session.add(user)
    db.session.flush()
    for oid in orgao_ids:
        db.session.add(UserOrgao(user_id=user.id, orgao_id=oid))
    db.session.flush()
    return user


def test_admin_sees_all_active_orgaos(app):
    with app.app_context():
        a = _add_orgao('A', tipo='Secretaria')
        b = _add_orgao('B', pai_id=a.id)
        inativo = _add_orgao('C', ativo=False)
        admin = _add_user('admin', is_admin=True)

        ids = get_user_orgao_subtree_ids(admin)
        assert a.id in ids and b.id in ids
        assert inativo.id not in ids


def test_non_admin_sees_orgao_subtree(app):
    with app.app_context():
        root = _add_orgao('ROOT', tipo='Secretaria')
        child = _add_orgao('CHILD', pai_id=root.id)
        grand = _add_orgao('GRAND', pai_id=child.id)
        outro = _add_orgao('OUTRO', tipo='Secretaria')
        user = _add_user('u', orgao_ids=[root.id])

        ids = get_user_orgao_subtree_ids(user)
        assert ids == {root.id, child.id, grand.id}
        assert outro.id not in ids


def test_non_admin_with_no_orgaos_sees_empty(app):
    with app.app_context():
        _add_orgao('X', tipo='Secretaria')
        user = _add_user('u')
        assert get_user_orgao_subtree_ids(user) == set()


def test_sanitize_filter_rejects_out_of_scope(app):
    with app.app_context():
        inside = _add_orgao('IN', tipo='Secretaria')
        outside = _add_orgao('OUT', tipo='Secretaria')
        user = _add_user('u', orgao_ids=[inside.id])

        ok_id, invalid = sanitize_orgao_filter_for_user(user, inside.id)
        assert ok_id == inside.id and invalid is False

        bad_id, invalid = sanitize_orgao_filter_for_user(user, outside.id)
        assert bad_id is None and invalid is True

        empty_id, invalid = sanitize_orgao_filter_for_user(user, '')
        assert empty_id is None and invalid is False


def test_sanitize_filter_admin_always_allowed(app):
    with app.app_context():
        outside = _add_orgao('OUT', tipo='Secretaria')
        admin = _add_user('admin', is_admin=True)
        ok_id, invalid = sanitize_orgao_filter_for_user(admin, outside.id)
        assert ok_id == outside.id and invalid is False


def test_sanitize_filter_invalid_int(app):
    with app.app_context():
        admin = _add_user('admin', is_admin=True)
        bad_id, invalid = sanitize_orgao_filter_for_user(admin, 'abc')
        assert bad_id is None and invalid is True


def test_expand_orgao_filter_includes_descendants(app):
    with app.app_context():
        root = _add_orgao('R', tipo='Secretaria')
        a = _add_orgao('A', pai_id=root.id)
        b = _add_orgao('B', pai_id=root.id)
        c = _add_orgao('C', pai_id=a.id)

        ids = expand_orgao_filter_ids(root.id)
        assert ids == {root.id, a.id, b.id, c.id}

        assert expand_orgao_filter_ids(None) == set()
