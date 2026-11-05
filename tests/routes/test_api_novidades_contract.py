"""Contrato HTTP das Novidades: listar/fechar (pessoa) e gestão (admin)."""

from datetime import datetime

import pytest

from models import Novidade, db

SLUG = "colecoes-2026-11"


@pytest.fixture
def novidade(app):
    with app.app_context():
        db.session.add(
            Novidade(
                slug=SLUG,
                titulo="Coleções",
                ativa=True,
                publicada_em=datetime(2026, 11, 5),
            )
        )
        db.session.commit()


def _novidades(client) -> list[dict]:
    response = client.get("/api/novidades")
    assert response.status_code == 200
    return response.get_json()["data"]["novidades"]


def test_lista_a_novidade_ativa_ainda_nao_vista(client_user, novidade):
    assert _novidades(client_user) == [
        {
            "slug": SLUG,
            "titulo": "Coleções",
            "publicada_em": "2026-11-05T00:00:00Z",
            "vista": False,
        }
    ]


def test_fechar_marca_vista_e_repetir_nao_rebaixa(client_user, novidade):
    concluiu = client_user.post(
        f"/api/novidades/{SLUG}/vista", json={"concluida": True}
    )
    de_novo = client_user.post(f"/api/novidades/{SLUG}/vista", json={})

    assert concluiu.get_json()["data"] == {"slug": SLUG, "concluida": True}
    assert de_novo.get_json()["data"] == {"slug": SLUG, "concluida": True}
    assert _novidades(client_user)[0]["vista"] is True


def test_fechar_novidade_inexistente_e_404(client_user, novidade):
    response = client_user.post("/api/novidades/nao-existe/vista", json={})
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "not_found"


def test_pessoa_comum_nao_acessa_a_gestao(client_user, novidade):
    assert client_user.get("/api/admin/novidades").status_code == 403
    assert (
        client_user.put(
            f"/api/admin/novidades/{SLUG}", json={"ativa": False}
        ).status_code
        == 403
    )


def test_admin_ve_alcance_e_desliga(client_admin, client_user, novidade):
    client_user.post(f"/api/novidades/{SLUG}/vista", json={"concluida": True})

    lista = client_admin.get("/api/admin/novidades").get_json()["data"]
    item = lista["novidades"][0]
    assert (item["slug"], item["ativa"], item["vistas"], item["concluidas"]) == (
        SLUG,
        True,
        1,
        1,
    )
    assert lista["usuarios_ativos"] >= 2

    desligou = client_admin.put(f"/api/admin/novidades/{SLUG}", json={"ativa": False})
    assert desligou.get_json()["data"]["novidade"]["ativa"] is False
    assert _novidades(client_user) == []


def test_admin_exige_ativa_booleano(client_admin, novidade):
    response = client_admin.put(f"/api/admin/novidades/{SLUG}", json={"ativa": "sim"})
    assert response.status_code == 422
    assert "recebido 'sim'" in response.get_json()["error"]["message"]


def test_mostrar_de_novo_reabre_para_quem_ja_viu(client_admin, client_user, novidade):
    client_user.post(f"/api/novidades/{SLUG}/vista", json={})

    response = client_admin.post(f"/api/admin/novidades/{SLUG}/mostrar-de-novo")

    assert response.get_json()["data"] == {"removidas": 1}
    assert _novidades(client_user)[0]["vista"] is False
