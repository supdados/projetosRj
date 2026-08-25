"""Contrato HTTP das 3 rotas de Projetos Relacionados (Feature 1, seção 1.6).

Trava as invariantes de segurança do vínculo simétrico: anti-enumeração (alvo
inexistente e alvo invisível devolvem o MESMO corpo), gate de remoção só no
projeto da URL (o editor do lado B remove chamando a rota com B), autocomplete
com visibilidade no SQL e payload do detalhe filtrando o outro lado invisível.

Fixtures de ``tests/conftest.py``: ``client_user`` é gestor de área em Auditoria
(vê ``project_id`` e ``project_complete_id``), ``client_outsider`` é gestor em
VPD (vê só ``foreign_project_id``).
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from models import Project, ProjectHistory, ProjectMember, ProjectRelation, User, db
from services.authorization import PAPEL_LEITOR
from services.project_relations import RELATED_MAX_PER_PROJECT

RELACIONADO_KEYS = {"id", "titulo", "status", "prioridade", "orgao_sigla"}
CANDIDATO_KEYS = {"id", "titulo", "status", "orgao_sigla"}


def _assert_ok(payload: Any) -> Any:
    assert payload["ok"] is True
    assert "error" not in payload
    return payload["data"]


def _assert_fail(payload: Any, *, code: str) -> str:
    assert payload["ok"] is False
    assert "data" not in payload
    assert payload["error"]["code"] == code
    assert isinstance(payload["error"]["message"], str)
    assert payload["error"]["message"]
    return payload["error"]["message"]


def _criar_relacao(app, project_a_id: int, project_b_id: int, ator_id: int) -> int:
    with app.app_context():
        relacao = ProjectRelation(
            project_low_id=min(project_a_id, project_b_id),
            project_high_id=max(project_a_id, project_b_id),
            created_by_user_id=ator_id,
        )
        db.session.add(relacao)
        db.session.commit()
        return relacao.id


def _pares_relacionados(app) -> set[tuple[int, int]]:
    with app.app_context():
        return {
            (relacao.project_low_id, relacao.project_high_id)
            for relacao in ProjectRelation.query.all()
        }


@pytest.fixture
def projetos_extras(app, seed_data):
    """13 projetos visíveis em Auditoria: alimentam teto (12) e limite (10)."""
    with app.app_context():
        criados = []
        for indice in range(1, 14):
            projeto = Project(
                titulo=f"Projeto Extra {indice:02d}",
                orgao_id=seed_data["auditoria_orgao_id"],
                orgao="Orgao A",
                prioridade="media",
                status="Vigente",
                objetivo_id=1,
                resultado_esperado_id=1,
            )
            db.session.add(projeto)
            criados.append(projeto)
        db.session.commit()
        return [projeto.id for projeto in criados]


@pytest.fixture
def client_convidado_leitor(app, seed_data):
    """Convidado ``leitor`` no projeto semeado: vê o projeto, não pode mutar."""
    with app.app_context():
        convidado = User(
            username="convidado_relacoes",
            name="Convidado Relacoes",
            orgao="Orgao Teste",
        )
        convidado.set_password("senha123")
        db.session.add(convidado)
        db.session.flush()
        db.session.add(
            ProjectMember(
                project_id=seed_data["project_id"],
                user_id=convidado.id,
                papel=PAPEL_LEITOR,
                granted_by_id=seed_data["admin_id"],
            )
        )
        db.session.commit()
        convidado_id = convidado.id

    http_client = app.test_client()
    with http_client.session_transaction() as session:
        session["user_id"] = convidado_id
        session["login_at"] = time.time()
    return http_client


# ── POST /api/projetos/<id>/relacionados ─────────────────────────────────────


def test_post_vincula_projetos_visiveis_e_grava_par_canonico(
    app, client_user, seed_data
):
    """Origem com id MAIOR ainda grava ``low < high`` (canonicalização)."""
    origem_id = seed_data["project_complete_id"]
    alvo_id = seed_data["project_id"]

    response = client_user.post(
        f"/api/projetos/{origem_id}/relacionados",
        json={"related_project_id": alvo_id},
    )

    assert response.status_code == 200
    assert _assert_ok(response.get_json()) == {}
    assert _pares_relacionados(app) == {
        (min(origem_id, alvo_id), max(origem_id, alvo_id))
    }


def test_post_grava_historico_apenas_na_origem(app, client_user, seed_data):
    origem_id = seed_data["project_id"]
    client_user.post(
        f"/api/projetos/{origem_id}/relacionados",
        json={"related_project_id": seed_data["project_complete_id"]},
    )

    with app.app_context():
        historico = ProjectHistory.query.filter_by(
            action_type="relacionar_projeto"
        ).all()
    assert [linha.project_id for linha in historico] == [origem_id]


def test_post_auto_vinculo_e_422_com_id_na_mensagem(app, client_user, seed_data):
    project_id = seed_data["project_id"]

    response = client_user.post(
        f"/api/projetos/{project_id}/relacionados",
        json={"related_project_id": project_id},
    )

    assert response.status_code == 422
    mensagem = _assert_fail(response.get_json(), code="validation")
    assert str(project_id) in mensagem
    assert _pares_relacionados(app) == set()


def test_post_duplicata_e_422_e_nao_cria_segunda_linha(app, client_user, seed_data):
    origem_id = seed_data["project_id"]
    corpo = {"related_project_id": seed_data["project_complete_id"]}
    client_user.post(f"/api/projetos/{origem_id}/relacionados", json=corpo)

    response = client_user.post(f"/api/projetos/{origem_id}/relacionados", json=corpo)

    assert response.status_code == 422
    _assert_fail(response.get_json(), code="validation")
    assert len(_pares_relacionados(app)) == 1


def test_post_acima_do_teto_e_422(app, client_user, seed_data, projetos_extras):
    origem_id = seed_data["project_id"]
    for outro_id in projetos_extras[:RELATED_MAX_PER_PROJECT]:
        _criar_relacao(app, origem_id, outro_id, seed_data["admin_id"])

    response = client_user.post(
        f"/api/projetos/{origem_id}/relacionados",
        json={"related_project_id": seed_data["project_complete_id"]},
    )

    assert response.status_code == 422
    mensagem = _assert_fail(response.get_json(), code="validation")
    assert str(RELATED_MAX_PER_PROJECT) in mensagem
    assert len(_pares_relacionados(app)) == RELATED_MAX_PER_PROJECT


@pytest.mark.parametrize(
    "corpo",
    [[], ["related_project_id"], "texto", 7, {}, {"related_project_id": "12"}],
)
def test_post_corpo_invalido_e_422(app, client_user, seed_data, corpo):
    response = client_user.post(
        f"/api/projetos/{seed_data['project_id']}/relacionados", json=corpo
    )

    assert response.status_code == 422
    _assert_fail(response.get_json(), code="validation")
    assert _pares_relacionados(app) == set()


def test_post_de_convidado_leitor_e_403(app, client_convidado_leitor, seed_data):
    """Leitor VÊ o projeto, mas vincular exige editor na origem."""
    response = client_convidado_leitor.post(
        f"/api/projetos/{seed_data['project_id']}/relacionados",
        json={"related_project_id": seed_data["project_complete_id"]},
    )

    assert response.status_code == 403
    _assert_fail(response.get_json(), code="forbidden")
    assert _pares_relacionados(app) == set()


def test_post_alvo_invisivel_e_inexistente_tem_corpo_identico(
    app, client_user, seed_data
):
    """Anti-enumeração: projeto de outra área e id inexistente são o MESMO 404."""
    url = f"/api/projetos/{seed_data['project_id']}/relacionados"

    invisivel = client_user.post(
        url, json={"related_project_id": seed_data["foreign_project_id"]}
    )
    inexistente = client_user.post(url, json={"related_project_id": 999_999})

    assert invisivel.status_code == inexistente.status_code == 404
    assert invisivel.get_data() == inexistente.get_data()
    _assert_fail(invisivel.get_json(), code="not_found")
    assert _pares_relacionados(app) == set()


def test_post_em_origem_fora_do_escopo_e_404(app, client_user, seed_data):
    response = client_user.post(
        f"/api/projetos/{seed_data['foreign_project_id']}/relacionados",
        json={"related_project_id": seed_data["project_id"]},
    )

    assert response.status_code == 404
    _assert_fail(response.get_json(), code="not_found")
    assert _pares_relacionados(app) == set()


def test_post_sem_sessao_e_401(client, seed_data):
    response = client.post(
        f"/api/projetos/{seed_data['project_id']}/relacionados",
        json={"related_project_id": seed_data["project_complete_id"]},
    )

    assert response.status_code == 401
    _assert_fail(response.get_json(), code="unauthenticated")


# ── DELETE /api/projetos/<id>/relacionados/<related_id> ──────────────────────


def test_delete_pelo_lado_b_remove_o_par(app, client_outsider, seed_data):
    """Editor de B remove o vínculo criado a partir de A, com B na URL."""
    lado_a = seed_data["project_id"]
    lado_b = seed_data["foreign_project_id"]
    _criar_relacao(app, lado_a, lado_b, seed_data["admin_id"])

    response = client_outsider.delete(f"/api/projetos/{lado_b}/relacionados/{lado_a}")

    assert response.status_code == 200
    assert _assert_ok(response.get_json()) == {}
    assert _pares_relacionados(app) == set()


def test_delete_de_par_inexistente_e_404(app, client_user, seed_data):
    response = client_user.delete(
        f"/api/projetos/{seed_data['project_id']}"
        f"/relacionados/{seed_data['project_complete_id']}"
    )

    assert response.status_code == 404
    _assert_fail(response.get_json(), code="not_found")


def test_delete_do_proprio_id_e_404(client_user, seed_data):
    project_id = seed_data["project_id"]
    response = client_user.delete(
        f"/api/projetos/{project_id}/relacionados/{project_id}"
    )

    assert response.status_code == 404
    _assert_fail(response.get_json(), code="not_found")


def test_delete_de_convidado_leitor_e_403_e_preserva_o_par(
    app, client_convidado_leitor, seed_data
):
    lado_a = seed_data["project_id"]
    lado_b = seed_data["project_complete_id"]
    _criar_relacao(app, lado_a, lado_b, seed_data["admin_id"])

    response = client_convidado_leitor.delete(
        f"/api/projetos/{lado_a}/relacionados/{lado_b}"
    )

    assert response.status_code == 403
    _assert_fail(response.get_json(), code="forbidden")
    assert len(_pares_relacionados(app)) == 1


def test_delete_em_origem_fora_do_escopo_e_404(app, client_user, seed_data):
    lado_a = seed_data["project_id"]
    lado_b = seed_data["foreign_project_id"]
    _criar_relacao(app, lado_a, lado_b, seed_data["admin_id"])

    response = client_user.delete(f"/api/projetos/{lado_b}/relacionados/{lado_a}")

    assert response.status_code == 404
    _assert_fail(response.get_json(), code="not_found")
    assert len(_pares_relacionados(app)) == 1


# ── GET /api/projetos/<id>/relacionados/candidatos ───────────────────────────


def test_candidatos_exclui_proprio_projeto_e_ja_vinculados(
    app, client_user, seed_data, projetos_extras
):
    origem_id = seed_data["project_id"]
    vinculado_id = projetos_extras[0]
    _criar_relacao(app, origem_id, vinculado_id, seed_data["admin_id"])

    response = client_user.get(
        f"/api/projetos/{origem_id}/relacionados/candidatos?q=Projeto"
    )

    assert response.status_code == 200
    ids = {item["id"] for item in _assert_ok(response.get_json())}
    assert origem_id not in ids
    assert vinculado_id not in ids


def test_candidatos_exclui_projeto_fora_do_escopo_de_visibilidade(
    client_user, seed_data
):
    response = client_user.get(
        f"/api/projetos/{seed_data['project_id']}/relacionados/candidatos?q=Projeto"
    )

    itens = _assert_ok(response.get_json())
    assert {item["id"] for item in itens} == {seed_data["project_complete_id"]}
    assert set(itens[0].keys()) == CANDIDATO_KEYS


def test_candidatos_com_percentual_nao_devolve_tudo(client_user, seed_data):
    """``%`` é escapado: vira busca literal, não coringa."""
    response = client_user.get(
        f"/api/projetos/{seed_data['project_id']}/relacionados/candidatos?q=%25%25"
    )

    assert response.status_code == 200
    assert _assert_ok(response.get_json()) == []


@pytest.mark.parametrize("termo", ["", "P", "  a  "])
def test_candidatos_abaixo_do_piso_devolve_lista_vazia(client_user, seed_data, termo):
    response = client_user.get(
        f"/api/projetos/{seed_data['project_id']}/relacionados/candidatos",
        query_string={"q": termo},
    )

    assert response.status_code == 200
    assert _assert_ok(response.get_json()) == []


def test_candidatos_limita_em_dez(client_user, seed_data, projetos_extras):
    response = client_user.get(
        f"/api/projetos/{seed_data['project_id']}/relacionados/candidatos?q=Extra"
    )

    assert len(_assert_ok(response.get_json())) == 10


def test_candidatos_em_projeto_fora_do_escopo_e_404(client_user, seed_data):
    response = client_user.get(
        f"/api/projetos/{seed_data['foreign_project_id']}"
        "/relacionados/candidatos?q=Projeto"
    )

    assert response.status_code == 404
    _assert_fail(response.get_json(), code="not_found")


# ── GET /api/projetos/<id>/detalhe → "relacionados" ──────────────────────────


def test_detalhe_lista_relacionado_visivel_com_as_chaves_do_contrato(
    app, client_user, seed_data
):
    origem_id = seed_data["project_id"]
    outro_id = seed_data["project_complete_id"]
    _criar_relacao(app, origem_id, outro_id, seed_data["admin_id"])

    data = _assert_ok(client_user.get(f"/api/projetos/{origem_id}/detalhe").get_json())

    assert len(data["relacionados"]) == 1
    item = data["relacionados"][0]
    assert set(item.keys()) == RELACIONADO_KEYS
    assert item["id"] == outro_id
    assert item["titulo"] == "Projeto Concluivel"
    assert item["orgao_sigla"] == "Auditoria"


def test_detalhe_omite_relacionado_invisivel_ao_viewer(
    app, client_user, client_admin, seed_data
):
    """O mesmo par: invisível some para quem não vê o outro lado, admin vê."""
    origem_id = seed_data["project_id"]
    _criar_relacao(
        app, origem_id, seed_data["foreign_project_id"], seed_data["admin_id"]
    )

    do_viewer = _assert_ok(
        client_user.get(f"/api/projetos/{origem_id}/detalhe").get_json()
    )
    do_admin = _assert_ok(
        client_admin.get(f"/api/projetos/{origem_id}/detalhe").get_json()
    )

    assert do_viewer["relacionados"] == []
    assert [item["id"] for item in do_admin["relacionados"]] == [
        seed_data["foreign_project_id"]
    ]
