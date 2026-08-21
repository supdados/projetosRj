"""``?orgao=<sigla>`` com sigla duplicada pós-SIORG (M3).

O organograma real tem CHEGAB, ASSCOM, ASSJUR, CORREG e OUVI duas vezes (uma na
SETD, outra no PRODERJ). O ``.first()`` sem ``order_by`` de
``/api/tarefas/sugestoes-responsavel`` devolvia linha arbitrária, então o mesmo
pedido podia virar 200 ou 403 conforme o plano do banco.
"""

from __future__ import annotations

import time

from models import OrgaoUnidade, User, UserOrgao, db


def _add_orgao(sigla: str, nome: str, pai_id: int | None = None) -> OrgaoUnidade:
    orgao = OrgaoUnidade(
        sigla=sigla, nome=nome, tipo="Subsecretaria", pai_id=pai_id, ordem=0
    )
    db.session.add(orgao)
    db.session.flush()
    return orgao


def _add_user(username: str, orgao_id: int, *, is_admin: bool = False) -> User:
    user = User(username=username, name=username, orgao="x", is_admin=is_admin)
    user.set_password("x")
    db.session.add(user)
    db.session.flush()
    db.session.add(UserOrgao(user_id=user.id, orgao_id=orgao_id))
    db.session.flush()
    return user


def _cenario_chegab_duplicada(app) -> dict[str, int]:
    """Duas CHEGAB irmãs (SETD e PRODERJ), uma pessoa vinculada em cada."""
    with app.app_context():
        setd = _add_orgao("SETD", "Secretaria de Transformação Digital")
        proderj = _add_orgao("PRODERJ", "Centro de Tecnologia")
        chegab_setd = _add_orgao("CHEGAB", "Chefia de Gabinete SETD", setd.id)
        chegab_proderj = _add_orgao("CHEGAB", "Chefia de Gabinete PRODERJ", proderj.id)
        ana = _add_user("ana.setd", chegab_setd.id)
        bruno = _add_user("bruno.proderj", chegab_proderj.id)
        admin = _add_user("admin.geral", setd.id, is_admin=True)
        db.session.commit()
        return {
            "chegab_setd_id": chegab_setd.id,
            "chegab_proderj_id": chegab_proderj.id,
            "ana_id": ana.id,
            "bruno_id": bruno.id,
            "admin_id": admin.id,
        }


def _login(client, user_id: int) -> None:
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["login_at"] = time.time()


def _nomes(response) -> set[str]:
    payload = response.get_json()
    assert payload["ok"] is True, payload
    return {user["name"] for user in payload["data"]["users"]}


def test_sigla_ambigua_resolve_no_escopo_do_usuario(app, client):
    ids = _cenario_chegab_duplicada(app)
    _login(client, ids["bruno_id"])

    response = client.get("/api/tarefas/sugestoes-responsavel?orgao=CHEGAB")

    assert response.status_code == 200
    nomes = _nomes(response)
    assert "bruno.proderj" in nomes
    assert "ana.setd" not in nomes


def test_sigla_ambigua_fora_do_escopo_escolhe_o_menor_id(app, client):
    """Admin alcança as duas: a escolha é o menor id, não a ordem do banco."""
    ids = _cenario_chegab_duplicada(app)
    assert ids["chegab_setd_id"] < ids["chegab_proderj_id"]
    _login(client, ids["admin_id"])

    response = client.get("/api/tarefas/sugestoes-responsavel?orgao=chegab")

    assert response.status_code == 200
    nomes = _nomes(response)
    assert "ana.setd" in nomes
    assert "bruno.proderj" not in nomes


def test_sigla_inexistente_continua_400(app, client):
    ids = _cenario_chegab_duplicada(app)
    _login(client, ids["bruno_id"])

    response = client.get("/api/tarefas/sugestoes-responsavel?orgao=NAOEXISTE")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "validation"
