from models import OrgaoUnidade, User, UserOrgao, db
from routes.orgao_scope import (
    build_nested_orgao_tree,
    expand_orgao_filter_ids,
    get_user_orgao_subtree_ids,
    get_visible_orgao_tree,
    parse_apenas_orgao_flag,
    sanitize_orgao_filter_for_user,
)
from services.authorization import get_user_orgao_role_map
from services.orgao_tree import rebuild_orgao_closure
from tests.sql_query_counter import SqlQueryCounter


def _add_orgao(sigla, pai_id=None, tipo="Subsecretaria", ativo=True):
    o = OrgaoUnidade(
        sigla=sigla,
        nome=sigla,
        tipo=tipo,
        pai_id=pai_id,
        ordem=0,
        ativo=ativo,
    )
    db.session.add(o)
    db.session.flush()
    return o


def _add_user(username, is_admin=False, orgao_ids=()):
    user = User(username=username, name=username, orgao="x", is_admin=is_admin)
    user.set_password("x")
    db.session.add(user)
    db.session.flush()
    for oid in orgao_ids:
        db.session.add(UserOrgao(user_id=user.id, orgao_id=oid))
    db.session.flush()
    return user


def test_admin_sees_all_active_orgaos(app):
    with app.app_context():
        a = _add_orgao("A", tipo="Secretaria")
        b = _add_orgao("B", pai_id=a.id)
        inativo = _add_orgao("C", ativo=False)
        admin = _add_user("admin", is_admin=True)

        ids = get_user_orgao_subtree_ids(admin)
        assert a.id in ids and b.id in ids
        assert inativo.id not in ids


def test_non_admin_sees_orgao_subtree(app):
    with app.app_context():
        root = _add_orgao("ROOT", tipo="Secretaria")
        child = _add_orgao("CHILD", pai_id=root.id)
        grand = _add_orgao("GRAND", pai_id=child.id)
        outro = _add_orgao("OUTRO", tipo="Secretaria")
        user = _add_user("u", orgao_ids=[root.id])

        ids = get_user_orgao_subtree_ids(user)
        assert ids == {root.id, child.id, grand.id}
        assert outro.id not in ids


def test_non_admin_with_no_orgaos_sees_empty(app):
    with app.app_context():
        _add_orgao("X", tipo="Secretaria")
        user = _add_user("u")
        assert get_user_orgao_subtree_ids(user) == set()


def test_sanitize_filter_rejects_out_of_scope(app):
    with app.app_context():
        inside = _add_orgao("IN", tipo="Secretaria")
        outside = _add_orgao("OUT", tipo="Secretaria")
        user = _add_user("u", orgao_ids=[inside.id])

        ok_id, invalid = sanitize_orgao_filter_for_user(user, inside.id)
        assert ok_id == inside.id and invalid is False

        bad_id, invalid = sanitize_orgao_filter_for_user(user, outside.id)
        assert bad_id is None and invalid is True

        empty_id, invalid = sanitize_orgao_filter_for_user(user, "")
        assert empty_id is None and invalid is False


def test_sanitize_filter_admin_always_allowed(app):
    with app.app_context():
        outside = _add_orgao("OUT", tipo="Secretaria")
        admin = _add_user("admin", is_admin=True)
        ok_id, invalid = sanitize_orgao_filter_for_user(admin, outside.id)
        assert ok_id == outside.id and invalid is False


def test_sanitize_filter_invalid_int(app):
    with app.app_context():
        admin = _add_user("admin", is_admin=True)
        bad_id, invalid = sanitize_orgao_filter_for_user(admin, "abc")
        assert bad_id is None and invalid is True


def test_expand_orgao_filter_includes_descendants(app):
    with app.app_context():
        root = _add_orgao("R", tipo="Secretaria")
        a = _add_orgao("A", pai_id=root.id)
        b = _add_orgao("B", pai_id=root.id)
        c = _add_orgao("C", pai_id=a.id)

        ids = expand_orgao_filter_ids(root.id)
        assert ids == {root.id, a.id, b.id, c.id}

        assert expand_orgao_filter_ids(None) == set()


def test_expand_orgao_filter_sem_descendentes(app):
    with app.app_context():
        root = _add_orgao("R", tipo="Secretaria")
        _add_orgao("A", pai_id=root.id)

        assert expand_orgao_filter_ids(root.id, incluir_descendentes=False) == {root.id}
        assert expand_orgao_filter_ids(None, incluir_descendentes=False) == set()


def test_parse_apenas_orgao_flag():
    assert parse_apenas_orgao_flag("1") is True
    assert parse_apenas_orgao_flag("true") is True
    assert parse_apenas_orgao_flag(True) is True
    assert parse_apenas_orgao_flag("0") is False
    assert parse_apenas_orgao_flag("") is False
    assert parse_apenas_orgao_flag(None) is False
    assert parse_apenas_orgao_flag(False) is False


# --- A3: arvore visivel a partir de TODOS os vinculos ------------------------
# O colapso de `user_orgao` (services/user_orgao_collapse.py) deixa o usuario
# com varios vinculos irmaos de topo; montar a arvore so a partir do primary
# escondia os ramos dos demais e fazia `?orgao=` valido virar 422.
# Ancestrais dos vinculos ficam FORA da arvore (cada vinculo vira raiz), mas
# seguem aceitos por `sanitize_orgao_filter_for_user` (URLs antigas).


def _arvore_irmaos():
    """RAIZ -> {RAMO_A -> FOLHA_A, RAMO_B -> FOLHA_B, RAMO_C}, com closure."""
    raiz = _add_orgao("RAIZ", tipo="Secretaria")
    ramo_a = _add_orgao("RAMO_A", pai_id=raiz.id)
    ramo_b = _add_orgao("RAMO_B", pai_id=raiz.id)
    ramo_c = _add_orgao("RAMO_C", pai_id=raiz.id)
    folha_a = _add_orgao("FOLHA_A", pai_id=ramo_a.id)
    folha_b = _add_orgao("FOLHA_B", pai_id=ramo_b.id)
    rebuild_orgao_closure()
    return {
        "raiz": raiz,
        "ramo_a": ramo_a,
        "ramo_b": ramo_b,
        "ramo_c": ramo_c,
        "folha_a": folha_a,
        "folha_b": folha_b,
    }


def test_visible_tree_uniao_de_todos_os_vinculos(app):
    with app.app_context():
        arv = _arvore_irmaos()
        user = _add_user("u", orgao_ids=[arv["ramo_a"].id, arv["ramo_b"].id])

        nodes = {node["id"]: node for node in get_visible_orgao_tree(user)}

        assert set(nodes) == {
            arv["ramo_a"].id,
            arv["ramo_b"].id,
            arv["folha_a"].id,
            arv["folha_b"].id,
        }
        assert arv["raiz"].id not in nodes
        assert arv["ramo_c"].id not in nodes
        assert nodes[arv["ramo_a"].id]["is_user_orgao"] is True
        assert nodes[arv["ramo_b"].id]["is_user_orgao"] is True


def test_visible_tree_nao_inclui_ancestral_de_vinculo_profundo(app):
    """Vínculo em folha não recebe NENHUM ancestral (raiz nem ramo)."""
    with app.app_context():
        arv = _arvore_irmaos()
        user = _add_user("u", orgao_ids=[arv["folha_a"].id])

        nodes = get_visible_orgao_tree(user)
        assert {node["id"] for node in nodes} == {arv["folha_a"].id}
        assert nodes[0]["is_user_orgao"] is True


def test_visible_tree_vinculos_em_ramos_distintos_viram_multiplas_raizes(app):
    with app.app_context():
        arv = _arvore_irmaos()
        user = _add_user("u", orgao_ids=[arv["ramo_a"].id, arv["ramo_b"].id])

        roots = build_nested_orgao_tree(get_visible_orgao_tree(user))
        filhos = {root["id"]: [c["id"] for c in root["children"]] for root in roots}
        assert filhos == {
            arv["ramo_a"].id: [arv["folha_a"].id],
            arv["ramo_b"].id: [arv["folha_b"].id],
        }


def test_visible_tree_admin_segue_com_a_arvore_inteira(app):
    with app.app_context():
        arv = _arvore_irmaos()
        admin = _add_user("admin", is_admin=True)

        nodes = {node["id"] for node in get_visible_orgao_tree(admin)}
        assert {orgao.id for orgao in arv.values()} <= nodes


def test_visible_tree_cobre_todo_o_role_map(app):
    with app.app_context():
        arv = _arvore_irmaos()
        user = _add_user("u", orgao_ids=[arv["ramo_a"].id, arv["ramo_b"].id])

        visiveis = {node["id"] for node in get_visible_orgao_tree(user)}
        assert set(get_user_orgao_role_map(user)) <= visiveis


def test_sanitize_aceita_orgao_de_vinculo_nao_primario(app):
    with app.app_context():
        arv = _arvore_irmaos()
        user = _add_user("u", orgao_ids=[arv["ramo_a"].id, arv["ramo_b"].id])

        for orgao in (arv["ramo_b"], arv["folha_b"]):
            orgao_id, invalid = sanitize_orgao_filter_for_user(user, orgao.id)
            assert (orgao_id, invalid) == (orgao.id, False)

        bad_id, invalid = sanitize_orgao_filter_for_user(user, arv["ramo_c"].id)
        assert bad_id is None and invalid is True


def test_sanitize_trata_ancestral_como_filtro_vazio(app):
    """URL antiga com ?orgao=<ancestral> nao quebra: vira filtro vazio, sem 422."""
    with app.app_context():
        arv = _arvore_irmaos()
        user = _add_user("u", orgao_ids=[arv["folha_a"].id])

        for ancestral in (arv["raiz"], arv["ramo_a"]):
            orgao_id, invalid = sanitize_orgao_filter_for_user(user, ancestral.id)
            assert (orgao_id, invalid) == (None, False)


def test_visible_tree_nao_faz_n_mais_1_por_vinculo(app):
    with app.app_context():
        arv = _arvore_irmaos()
        vinculos = [arv["ramo_a"].id, arv["ramo_b"].id, arv["ramo_c"].id]
        user = _add_user("u", orgao_ids=vinculos)
        db.session.expire_all()
        get_visible_orgao_tree(user)  # aquece o identity map dos vinculos

        with SqlQueryCounter(db.engine) as counter:
            get_visible_orgao_tree(user)

        # descendentes + linha dos orgaos = 2, independente de N.
        assert counter.total == 2


def test_visible_tree_sem_closure_cai_no_fallback(app):
    with app.app_context():
        raiz = _add_orgao("RAIZ", tipo="Secretaria")
        ramo_a = _add_orgao("RAMO_A", pai_id=raiz.id)
        ramo_b = _add_orgao("RAMO_B", pai_id=raiz.id)
        folha_b = _add_orgao("FOLHA_B", pai_id=ramo_b.id)
        user = _add_user("u", orgao_ids=[ramo_a.id, ramo_b.id])

        visiveis = {node["id"] for node in get_visible_orgao_tree(user)}
        assert visiveis == {ramo_a.id, ramo_b.id, folha_b.id}


def test_visible_tree_mantem_vinculo_inativo_e_corta_descendente_inativo(app):
    with app.app_context():
        raiz = _add_orgao("RAIZ", tipo="Secretaria")
        ramo_a = _add_orgao("RAMO_A", pai_id=raiz.id, ativo=False)
        ramo_b = _add_orgao("RAMO_B", pai_id=raiz.id)
        folha_b = _add_orgao("FOLHA_B", pai_id=ramo_b.id, ativo=False)
        rebuild_orgao_closure()
        user = _add_user("u", orgao_ids=[ramo_a.id, ramo_b.id])

        visiveis = {node["id"] for node in get_visible_orgao_tree(user)}
        assert visiveis == {ramo_a.id, ramo_b.id}
        assert folha_b.id not in visiveis
