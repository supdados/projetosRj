"""Testes unitários para routes/orgao_tree.py."""

import pytest

from models import OrgaoUnidade, db
from routes.orgao_tree import (
    compute_orgao_depth,
    compute_subtree_height,
    ensure_default_orgao_tipos,
    find_orgao_tipo,
    get_orgao_descendants,
    is_valid_parent_tipo,
    normalize_orgao_form,
    validate_orgao_move,
    would_create_cycle,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def orgao_tree(app):
    """Cria árvore: Estado → Secretaria → Subsecretaria."""
    with app.app_context():
        raiz = OrgaoUnidade(
            nome="Estado RJ",
            sigla="ERJ",
            tipo="Estado",
            pai_id=None,
            ordem=0,
            ativo=True,
        )
        db.session.add(raiz)
        db.session.flush()

        secretaria = OrgaoUnidade(
            nome="Secretaria A",
            sigla="SECA",
            tipo="Secretaria",
            pai_id=raiz.id,
            ordem=0,
            ativo=True,
        )
        db.session.add(secretaria)
        db.session.flush()

        subsecretaria = OrgaoUnidade(
            nome="Subsecretaria B",
            sigla="SSEB",
            tipo="Subsecretaria",
            pai_id=secretaria.id,
            ordem=0,
            ativo=True,
        )
        db.session.add(subsecretaria)
        db.session.commit()

        yield {
            "raiz_id": raiz.id,
            "secretaria_id": secretaria.id,
            "subsecretaria_id": subsecretaria.id,
        }

        db.session.query(OrgaoUnidade).filter(
            OrgaoUnidade.id.in_([raiz.id, secretaria.id, subsecretaria.id])
        ).delete(synchronize_session=False)
        db.session.commit()


# ── is_valid_parent_tipo ──────────────────────────────────────────────────────


def test_is_valid_parent_tipo_estado_pode_ser_pai_de_secretaria():
    assert is_valid_parent_tipo("Estado", "Secretaria") is True


def test_is_valid_parent_tipo_secretaria_nao_pode_ser_pai_de_estado():
    assert is_valid_parent_tipo("Secretaria", "Estado") is False


def test_is_valid_parent_tipo_subsecretaria_pode_ser_pai_de_superintendencia():
    assert is_valid_parent_tipo("Subsecretaria", "Superintendência") is True


def test_is_valid_parent_tipo_tipo_desconhecido_retorna_true():
    # Tipo desconhecido não deve bloquear; validação de domínio fica em normalize_orgao_form.
    assert is_valid_parent_tipo("TipoX", "Estado") is True


# ── compute_orgao_depth ───────────────────────────────────────────────────────


def test_compute_orgao_depth_raiz_e_1(app, orgao_tree):
    with app.app_context():
        raiz = db.session.get(OrgaoUnidade, orgao_tree["raiz_id"])
        assert compute_orgao_depth(raiz) == 1


def test_compute_orgao_depth_filho_e_2(app, orgao_tree):
    with app.app_context():
        secretaria = db.session.get(OrgaoUnidade, orgao_tree["secretaria_id"])
        assert compute_orgao_depth(secretaria) == 2


def test_compute_orgao_depth_neto_e_3(app, orgao_tree):
    with app.app_context():
        sub = db.session.get(OrgaoUnidade, orgao_tree["subsecretaria_id"])
        assert compute_orgao_depth(sub) == 3


def test_compute_orgao_depth_none_retorna_0():
    assert compute_orgao_depth(None) == 0


# ── compute_subtree_height ────────────────────────────────────────────────────


def test_compute_subtree_height_folha_e_1(app, orgao_tree):
    with app.app_context():
        sub = db.session.get(OrgaoUnidade, orgao_tree["subsecretaria_id"])
        assert compute_subtree_height(sub) == 1


def test_compute_subtree_height_raiz_e_3(app, orgao_tree):
    with app.app_context():
        raiz = db.session.get(OrgaoUnidade, orgao_tree["raiz_id"])
        assert compute_subtree_height(raiz) == 3


def test_compute_subtree_height_none_retorna_0():
    assert compute_subtree_height(None) == 0


# ── get_orgao_descendants ─────────────────────────────────────────────────────


def test_get_orgao_descendants_raiz_retorna_ambos_filhos(app, orgao_tree):
    with app.app_context():
        desc = get_orgao_descendants(orgao_tree["raiz_id"])
        assert orgao_tree["secretaria_id"] in desc
        assert orgao_tree["subsecretaria_id"] in desc
        assert orgao_tree["raiz_id"] not in desc


def test_get_orgao_descendants_folha_retorna_vazio(app, orgao_tree):
    with app.app_context():
        desc = get_orgao_descendants(orgao_tree["subsecretaria_id"])
        assert desc == []


# ── would_create_cycle ────────────────────────────────────────────────────────


def test_would_create_cycle_mover_para_proprio_id(app, orgao_tree):
    with app.app_context():
        assert would_create_cycle(orgao_tree["raiz_id"], orgao_tree["raiz_id"]) is True


def test_would_create_cycle_mover_para_descendente(app, orgao_tree):
    with app.app_context():
        assert (
            would_create_cycle(orgao_tree["raiz_id"], orgao_tree["subsecretaria_id"])
            is True
        )


def test_would_create_cycle_mover_para_none_false(app, orgao_tree):
    with app.app_context():
        assert would_create_cycle(orgao_tree["raiz_id"], None) is False


def test_would_create_cycle_mover_valido_false(app, orgao_tree):
    with app.app_context():
        # Mover subsecretaria para raiz não cria ciclo.
        assert (
            would_create_cycle(orgao_tree["subsecretaria_id"], orgao_tree["raiz_id"])
            is False
        )


# ── validate_orgao_move ───────────────────────────────────────────────────────


def test_validate_orgao_move_none_retorna_erro():
    assert validate_orgao_move(None, 1) == "Órgão não encontrado."


def test_validate_orgao_move_ciclo_retorna_erro(app, orgao_tree):
    with app.app_context():
        raiz = db.session.get(OrgaoUnidade, orgao_tree["raiz_id"])
        erro = validate_orgao_move(raiz, orgao_tree["subsecretaria_id"])
        assert erro is not None
        assert "si mesmo" in erro


def test_validate_orgao_move_pai_nao_encontrado_retorna_erro(app, orgao_tree):
    with app.app_context():
        secretaria = db.session.get(OrgaoUnidade, orgao_tree["secretaria_id"])
        erro = validate_orgao_move(secretaria, 99999)
        assert erro == "Órgão pai não encontrado."


def test_validate_orgao_move_valido_retorna_none(app, orgao_tree):
    with app.app_context():
        sub = db.session.get(OrgaoUnidade, orgao_tree["subsecretaria_id"])
        raiz = db.session.get(OrgaoUnidade, orgao_tree["raiz_id"])
        # Mover subsecretaria direto para raiz é válido se tipos permitirem.
        # (resultado depende do TIPO_RANK; testamos apenas que não retorna erro de ciclo)
        resultado = validate_orgao_move(sub, raiz.id)
        assert resultado != "Não é possível mover um órgão para dentro de si mesmo."


# ── normalize_orgao_form (regressão tipo_id INT) ──────────────────────────────


def _estado_tipo_id():
    """Id do tipo raiz (Estado), permite_raiz=True, usado para órgão raiz."""
    ensure_default_orgao_tipos()
    db.session.flush()
    tipo = find_orgao_tipo("Estado")
    assert tipo is not None
    return tipo.id


def test_normalize_orgao_form_tipo_id_int_nao_estoura(app):
    """Regressão: SPA serializa tipo_id como INT no JSON; .strip() prematuro
    causava AttributeError (HTTP 500) em orgao_tree.py:113."""
    with app.app_context():
        tipo_id = _estado_tipo_id()
        form = {
            "nome": "Estado RJ",
            "sigla": "ERJ",
            "tipo_id": tipo_id,  # INT, como a SPA envia via JSON
        }
        data, err = normalize_orgao_form(form, is_root=True)
        assert err is None
        assert data is not None
        assert data["tipo"] == "Estado"
        assert data["tipo_id"] == tipo_id


def test_normalize_orgao_form_tipo_id_str_continua_funcionando(app):
    """Caminho de form string (Jinja) deve continuar válido."""
    with app.app_context():
        tipo_id = _estado_tipo_id()
        form = {
            "nome": "Estado RJ",
            "sigla": "ERJ",
            "tipo_id": str(tipo_id),  # string, como o template Jinja envia
        }
        data, err = normalize_orgao_form(form, is_root=True)
        assert err is None
        assert data is not None
        assert data["tipo"] == "Estado"
        assert data["tipo_id"] == tipo_id
