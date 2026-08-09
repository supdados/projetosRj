"""Contrato das 5 rotas de membros/convites do projeto (S4/F3-11..F3-14, F3-26).

Trava as invariantes de segurança da sprint: anti-enumeração (rank 0 => 404
idêntico ao de projeto inexistente), gestão só por vínculo de ÁREA (convite
nunca gerencia), teto rígido de papel, auto-convite bloqueado, payload da busca
sem dados sensíveis e os dois estados de ``CONVITES_HABILITADOS``.

Fixtures de ``tests/conftest.py``: ``client_user`` é gestor de área do projeto
semeado (Auditoria), ``client_outsider`` não tem vínculo nenhum nele (VPD).
"""

from __future__ import annotations

from typing import Any

import pytest
import time

from models import (
    AutorizacaoAudit,
    ProjectMember,
    User,
    UserNotification,
    UserOrgao,
    db,
)
from services.authorization import PAPEL_EDITOR, PAPEL_LEITOR
from time_utils import utc_now


@pytest.fixture
def convites_ligados(app):
    """Liga ``CONVITES_HABILITADOS`` (default off em config.py) para o teste."""
    app.config["CONVITES_HABILITADOS"] = True
    yield app
    app.config["CONVITES_HABILITADOS"] = False


def _assert_ok(payload: Any) -> Any:
    assert payload["ok"] is True
    assert "error" not in payload
    return payload["data"]


def _assert_fail(payload: Any, *, code: str) -> None:
    assert payload["ok"] is False
    assert "data" not in payload
    assert payload["error"]["code"] == code
    assert isinstance(payload["error"]["message"], str)
    assert payload["error"]["message"]


def _rebaixa_vinculo(app, user_id: int, papel: str) -> None:
    with app.app_context():
        vinculo = UserOrgao.query.filter_by(user_id=user_id).first()
        vinculo.papel = papel
        db.session.commit()


def _grava_convite(app, project_id: int, user_id: int, papel: str, ator_id: int) -> int:
    with app.app_context():
        membro = ProjectMember(
            project_id=project_id,
            user_id=user_id,
            papel=papel,
            granted_by_id=ator_id,
        )
        db.session.add(membro)
        db.session.commit()
        return membro.id


def _cliente_de(app, user_id: int):
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["login_at"] = time.time()
    return client


# ── Feature flag (F3-23) ─────────────────────────────────────────────────────


def test_flag_desligada_esconde_as_cinco_rotas(client_user, seed_data):
    project_id = seed_data["project_id"]
    respostas = [
        client_user.get(f"/api/projetos/{project_id}/membros"),
        client_user.post(
            f"/api/projetos/{project_id}/membros",
            json={"user_id": seed_data["outsider_id"], "papel": "leitor"},
        ),
        client_user.put(
            f"/api/projetos/{project_id}/membros/1", json={"papel": "leitor"}
        ),
        client_user.delete(f"/api/projetos/{project_id}/membros/1"),
        client_user.get("/api/usuarios/busca?q=usu"),
    ]

    for response in respostas:
        assert response.status_code == 404
        _assert_fail(response.get_json(), code="not_found")


def test_flag_desligada_nao_grava_convite(app, client_user, seed_data):
    response = client_user.post(
        f"/api/projetos/{seed_data['project_id']}/membros",
        json={"user_id": seed_data["outsider_id"], "papel": "leitor"},
    )

    assert response.status_code == 404
    with app.app_context():
        assert ProjectMember.query.count() == 0
        assert AutorizacaoAudit.query.count() == 0


# ── GET /api/projetos/<id>/membros ───────────────────────────────────────────


def test_gestor_de_area_lista_diretos_e_herdados(
    app, convites_ligados, client_user, seed_data
):
    response = client_user.get(f"/api/projetos/{seed_data['project_id']}/membros")

    assert response.status_code == 200
    data = _assert_ok(response.get_json())
    assert set(data) == {"diretos", "herdados"}
    assert data["diretos"] == []
    usernames = {row["user_username"] for row in data["herdados"]}
    assert "user_auditoria" in usernames
    # Herdado é read-only: sem `id`, não há linha de project_member para editar.
    assert all("id" not in row for row in data["herdados"])
    assert all(row["orgao_id"] for row in data["herdados"])


def test_membro_herdado_nao_vira_linha_em_project_member(
    app, convites_ligados, client_user, seed_data
):
    response = client_user.get(f"/api/projetos/{seed_data['project_id']}/membros")

    assert response.status_code == 200
    assert _assert_ok(response.get_json())["herdados"]
    with app.app_context():
        assert ProjectMember.query.count() == 0


def test_rank_zero_responde_404_identico_ao_de_projeto_inexistente(
    convites_ligados, client_outsider, seed_data
):
    fora_do_escopo = client_outsider.get(
        f"/api/projetos/{seed_data['project_id']}/membros"
    )
    inexistente = client_outsider.get("/api/projetos/99999/membros")

    assert fora_do_escopo.status_code == inexistente.status_code == 404
    assert fora_do_escopo.get_json() == inexistente.get_json()
    _assert_fail(fora_do_escopo.get_json(), code="not_found")


def test_leitor_de_area_nao_enumera_membros(app, convites_ligados, seed_data):
    _rebaixa_vinculo(app, seed_data["editable_user_id"], PAPEL_LEITOR)
    client = _cliente_de(app, seed_data["editable_user_id"])

    response = client.get(f"/api/projetos/{seed_data['project_id']}/membros")

    assert response.status_code == 403
    _assert_fail(response.get_json(), code="forbidden")


def test_convidado_editor_nao_gerencia_membros(
    app, convites_ligados, client_outsider, seed_data
):
    _grava_convite(
        app,
        seed_data["project_id"],
        seed_data["outsider_id"],
        PAPEL_EDITOR,
        seed_data["user_id"],
    )

    response = client_outsider.get(f"/api/projetos/{seed_data['project_id']}/membros")

    assert response.status_code == 403
    _assert_fail(response.get_json(), code="forbidden")


def test_admin_gerencia_membros_de_projeto_de_outra_area(
    convites_ligados, client_admin, seed_data
):
    response = client_admin.get(
        f"/api/projetos/{seed_data['foreign_project_id']}/membros"
    )

    assert response.status_code == 200
    _assert_ok(response.get_json())


# ── POST /api/projetos/<id>/membros ──────────────────────────────────────────


def test_post_cria_convite_ativo_com_trilha_e_notificacao(
    app, convites_ligados, client_user, seed_data
):
    response = client_user.post(
        f"/api/projetos/{seed_data['project_id']}/membros",
        json={"user_id": seed_data["outsider_id"], "papel": "editor"},
    )

    assert response.status_code == 200
    data = _assert_ok(response.get_json())
    assert data["papel"] == "editor"
    assert data["status"] == "ativo"
    assert data["user_id"] == seed_data["outsider_id"]
    assert data["granted_by_name"] == "Usuario Auditoria"
    assert "cpf_govbr" not in data

    with app.app_context():
        membro = ProjectMember.query.one()
        assert membro.user_id == seed_data["outsider_id"]
        assert membro.granted_by_id == seed_data["user_id"]
        assert membro.is_active is True
        audit = AutorizacaoAudit.query.one()
        assert audit.evento == "convite_criado"
        assert audit.alvo_tipo == "project"
        assert audit.alvo_id == seed_data["project_id"]
        assert audit.ator_id == seed_data["user_id"]
        assert audit.detalhe["papel"] == "editor"
        assert audit.detalhe["origem"] == "convite"
        notificacao = UserNotification.query.filter_by(
            recipient_user_id=seed_data["outsider_id"],
            event_type="projeto_convite",
        ).one()
        assert str(seed_data["project_id"]) in notificacao.target_url


def test_post_com_papel_gestor_recusa_com_400(
    app, convites_ligados, client_user, seed_data
):
    response = client_user.post(
        f"/api/projetos/{seed_data['project_id']}/membros",
        json={"user_id": seed_data["outsider_id"], "papel": "gestor"},
    )

    assert response.status_code == 400
    _assert_fail(response.get_json(), code="validation")
    with app.app_context():
        assert ProjectMember.query.count() == 0


def test_post_bloqueia_auto_convite(app, convites_ligados, client_user, seed_data):
    response = client_user.post(
        f"/api/projetos/{seed_data['project_id']}/membros",
        json={"user_id": seed_data["user_id"], "papel": "leitor"},
    )

    assert response.status_code == 400
    _assert_fail(response.get_json(), code="validation")
    with app.app_context():
        assert ProjectMember.query.count() == 0


def test_post_recusa_usuario_inexistente(convites_ligados, client_user, seed_data):
    response = client_user.post(
        f"/api/projetos/{seed_data['project_id']}/membros",
        json={"user_id": 99999, "papel": "leitor"},
    )

    assert response.status_code == 400
    _assert_fail(response.get_json(), code="validation")


def test_post_recusa_expires_at_invalido(convites_ligados, client_user, seed_data):
    response = client_user.post(
        f"/api/projetos/{seed_data['project_id']}/membros",
        json={
            "user_id": seed_data["outsider_id"],
            "papel": "leitor",
            "expires_at": "31/12/2026",
        },
    )

    assert response.status_code == 400
    _assert_fail(response.get_json(), code="validation")


# ── PUT / DELETE ─────────────────────────────────────────────────────────────


def test_put_altera_papel_do_convite(app, convites_ligados, client_user, seed_data):
    member_id = _grava_convite(
        app,
        seed_data["project_id"],
        seed_data["outsider_id"],
        PAPEL_LEITOR,
        seed_data["user_id"],
    )

    response = client_user.put(
        f"/api/projetos/{seed_data['project_id']}/membros/{member_id}",
        json={"papel": "editor", "expires_at": "2099-12-31"},
    )

    assert response.status_code == 200
    data = _assert_ok(response.get_json())
    assert data["papel"] == "editor"
    assert data["expires_at"].startswith("2099-12-31")
    with app.app_context():
        assert AutorizacaoAudit.query.one().evento == "convite_alterado"


def test_put_com_papel_gestor_recusa_e_preserva_papel(
    app, convites_ligados, client_user, seed_data
):
    member_id = _grava_convite(
        app,
        seed_data["project_id"],
        seed_data["outsider_id"],
        PAPEL_LEITOR,
        seed_data["user_id"],
    )

    response = client_user.put(
        f"/api/projetos/{seed_data['project_id']}/membros/{member_id}",
        json={"papel": "gestor"},
    )

    assert response.status_code == 400
    _assert_fail(response.get_json(), code="validation")
    with app.app_context():
        assert ProjectMember.query.one().papel == PAPEL_LEITOR


def test_membro_de_outro_projeto_responde_404(
    app, convites_ligados, client_admin, seed_data
):
    member_id = _grava_convite(
        app,
        seed_data["foreign_project_id"],
        seed_data["user_id"],
        PAPEL_LEITOR,
        seed_data["admin_id"],
    )

    response = client_admin.delete(
        f"/api/projetos/{seed_data['project_id']}/membros/{member_id}"
    )

    assert response.status_code == 404
    _assert_fail(response.get_json(), code="not_found")


def test_delete_revoga_soft_e_segunda_revogacao_recusa(
    app, convites_ligados, client_user, seed_data
):
    member_id = _grava_convite(
        app,
        seed_data["project_id"],
        seed_data["outsider_id"],
        PAPEL_LEITOR,
        seed_data["user_id"],
    )

    revogacao = client_user.delete(
        f"/api/projetos/{seed_data['project_id']}/membros/{member_id}"
    )
    repetida = client_user.delete(
        f"/api/projetos/{seed_data['project_id']}/membros/{member_id}"
    )

    assert revogacao.status_code == 200
    assert _assert_ok(revogacao.get_json())["status"] == "revogado"
    assert repetida.status_code == 400
    with app.app_context():
        membro = ProjectMember.query.one()
        assert membro.revoked_at is not None
        assert membro.revoked_by_id == seed_data["user_id"]
        assert AutorizacaoAudit.query.count() == 1


# ── GET /api/usuarios/busca ──────────────────────────────────────────────────


def test_busca_devolve_apenas_campos_publicos(convites_ligados, client_user):
    response = client_user.get("/api/usuarios/busca?q=usuario")

    assert response.status_code == 200
    usuarios = _assert_ok(response.get_json())["usuarios"]
    assert usuarios
    for usuario in usuarios:
        assert set(usuario) == {"id", "name", "username", "orgao_sigla"}


def test_busca_ignora_termo_curto(convites_ligados, client_user):
    response = client_user.get("/api/usuarios/busca?q=u")

    assert response.status_code == 200
    assert _assert_ok(response.get_json())["usuarios"] == []


def test_busca_nega_quem_nao_e_gestor_em_nenhum_orgao(app, convites_ligados, seed_data):
    _rebaixa_vinculo(app, seed_data["editable_user_id"], PAPEL_EDITOR)
    client = _cliente_de(app, seed_data["editable_user_id"])

    response = client.get("/api/usuarios/busca?q=usuario")

    assert response.status_code == 403
    _assert_fail(response.get_json(), code="forbidden")


def test_busca_exige_sessao(convites_ligados, client):
    response = client.get("/api/usuarios/busca?q=usuario")

    assert response.status_code == 401
    _assert_fail(response.get_json(), code="unauthenticated")


# ── POST /api/projetos/<id>/membros/lote ─────────────────────────────────────


def _post_lote(client, project_id: int, payload: dict[str, Any]):
    return client.post(f"/api/projetos/{project_id}/membros/lote", json=payload)


def _cria_usuario_no_orgao(app, username: str, orgao_id: int) -> int:
    with app.app_context():
        user = User(username=username, name=username, orgao="Orgao Teste")
        user.set_password("senha123")
        db.session.add(user)
        db.session.flush()
        db.session.add(UserOrgao(user_id=user.id, orgao_id=orgao_id))
        db.session.commit()
        return user.id


def _vincula_orgao(app, user_id: int, orgao_id: int) -> None:
    with app.app_context():
        db.session.add(UserOrgao(user_id=user_id, orgao_id=orgao_id))
        db.session.commit()


def _revoga_direto(app, member_id: int, ator_id: int) -> None:
    with app.app_context():
        membro = db.session.get(ProjectMember, member_id)
        membro.revoked_at = utc_now()
        membro.revoked_by_id = ator_id
        db.session.commit()


class FakeNotificadorExplosivo:
    """Falha na 2ª notificação para provar o rollback do lote INTEIRO."""

    def __init__(self) -> None:
        self.chamadas = 0

    def __call__(self, *args: Any, **kwargs: Any) -> int:
        self.chamadas += 1
        if self.chamadas == 2:
            raise RuntimeError("falha simulada no meio do lote")
        return 1


def test_lote_flag_desligada_responde_404_identico_ao_inexistente(
    app, client_user, seed_data
):
    payload = {"orgao_id": seed_data["vpd_orgao_id"], "papel": "leitor"}
    desligado = _post_lote(client_user, seed_data["project_id"], payload)
    app.config["CONVITES_HABILITADOS"] = True
    try:
        inexistente = _post_lote(client_user, 99999, payload)
    finally:
        app.config["CONVITES_HABILITADOS"] = False

    assert desligado.status_code == inexistente.status_code == 404
    assert desligado.get_data() == inexistente.get_data()
    _assert_fail(desligado.get_json(), code="not_found")
    with app.app_context():
        assert ProjectMember.query.count() == 0


def test_lote_nao_gestor_recusa_403(app, convites_ligados, seed_data):
    _rebaixa_vinculo(app, seed_data["editable_user_id"], PAPEL_LEITOR)
    client = _cliente_de(app, seed_data["editable_user_id"])

    response = _post_lote(
        client,
        seed_data["project_id"],
        {"orgao_id": seed_data["vpd_orgao_id"], "papel": "leitor"},
    )

    assert response.status_code == 403
    _assert_fail(response.get_json(), code="forbidden")


def test_lote_cria_para_elegiveis_e_pula_self_area_e_convite_ativo(
    app, convites_ligados, client_user, seed_data
):
    vpd = seed_data["vpd_orgao_id"]
    com_convite_ativo = _cria_usuario_no_orgao(app, "vpd_convidado", vpd)
    _grava_convite(
        app,
        seed_data["project_id"],
        com_convite_ativo,
        PAPEL_LEITOR,
        seed_data["user_id"],
    )
    # Self no órgão-alvo e alguém que já vê o projeto pela área: ambos pulam.
    _vincula_orgao(app, seed_data["user_id"], vpd)
    _vincula_orgao(app, seed_data["editable_user_id"], vpd)

    response = _post_lote(
        client_user, seed_data["project_id"], {"orgao_id": vpd, "papel": "editor"}
    )

    assert response.status_code == 200
    contagens = _assert_ok(response.get_json())
    assert contagens == {"convidados": 1, "reativados": 0, "pulados": 3}
    with app.app_context():
        assert ProjectMember.query.count() == 2
        novo = ProjectMember.query.filter_by(user_id=seed_data["outsider_id"]).one()
        assert novo.papel == PAPEL_EDITOR
        assert novo.granted_by_id == seed_data["user_id"]
        assert novo.is_active is True
        audit = AutorizacaoAudit.query.one()
        assert audit.evento == "convite_criado"
        assert audit.user_id == seed_data["outsider_id"]
        assert audit.ator_id == seed_data["user_id"]
        notificacoes = UserNotification.query.filter_by(
            event_type="projeto_convite"
        ).all()
        assert [n.recipient_user_id for n in notificacoes] == [seed_data["outsider_id"]]


def test_lote_reativa_convite_revogado(app, convites_ligados, client_user, seed_data):
    member_id = _grava_convite(
        app,
        seed_data["project_id"],
        seed_data["outsider_id"],
        PAPEL_LEITOR,
        seed_data["user_id"],
    )
    _revoga_direto(app, member_id, seed_data["user_id"])

    response = _post_lote(
        client_user,
        seed_data["project_id"],
        {"orgao_id": seed_data["vpd_orgao_id"], "papel": "editor"},
    )

    assert response.status_code == 200
    assert _assert_ok(response.get_json()) == {
        "convidados": 0,
        "reativados": 1,
        "pulados": 0,
    }
    with app.app_context():
        membro = ProjectMember.query.one()
        assert membro.id == member_id
        assert membro.revoked_at is None
        assert membro.papel == PAPEL_EDITOR
        assert membro.is_active is True
        assert AutorizacaoAudit.query.one().evento == "convite_reativado"


def test_lote_com_papel_gestor_recusa_400(
    app, convites_ligados, client_user, seed_data
):
    response = _post_lote(
        client_user,
        seed_data["project_id"],
        {"orgao_id": seed_data["vpd_orgao_id"], "papel": "gestor"},
    )

    assert response.status_code == 400
    _assert_fail(response.get_json(), code="validation")
    with app.app_context():
        assert ProjectMember.query.count() == 0


def test_lote_orgao_inexistente_responde_400(convites_ligados, client_user, seed_data):
    response = _post_lote(
        client_user, seed_data["project_id"], {"orgao_id": 99999, "papel": "leitor"}
    )

    assert response.status_code == 400
    _assert_fail(response.get_json(), code="validation")


def test_lote_orgao_sem_elegiveis_responde_contagens_zeradas(
    convites_ligados, client_user, seed_data
):
    response = _post_lote(
        client_user,
        seed_data["project_id"],
        {"orgao_id": seed_data["vpe_orgao_id"], "papel": "leitor"},
    )

    assert response.status_code == 200
    assert _assert_ok(response.get_json()) == {
        "convidados": 0,
        "reativados": 0,
        "pulados": 0,
    }


def test_lote_erro_no_meio_desfaz_tudo(
    app, convites_ligados, client_user, seed_data, monkeypatch
):
    _cria_usuario_no_orgao(app, "vpd_extra", seed_data["vpd_orgao_id"])
    monkeypatch.setattr(
        "routes.api.project_members.notify_project_invite", FakeNotificadorExplosivo()
    )

    response = _post_lote(
        client_user,
        seed_data["project_id"],
        {"orgao_id": seed_data["vpd_orgao_id"], "papel": "leitor"},
    )

    assert response.status_code == 500
    _assert_fail(response.get_json(), code="server")
    with app.app_context():
        assert ProjectMember.query.count() == 0
        assert AutorizacaoAudit.query.count() == 0
        assert (
            UserNotification.query.filter_by(event_type="projeto_convite").count() == 0
        )
