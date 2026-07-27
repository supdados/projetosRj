"""Fluxo ponta a ponta do convite por projeto (S4/F3-15..F3-18).

Cobre o ciclo de vida da linha ÚNICA de ``project_member``: criar, revogar,
reativar, expirar e renovar — com a trilha de auditoria acumulando um evento por
transição — e o efeito no acesso de leitura do convidado.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from models import AutorizacaoAudit, Project, ProjectMember, User, db
from services.authorization import (
    PAPEL_LEITOR,
    area_project_rank,
    can_assign_project_to_orgao,
    effective_project_rank,
)
from time_utils import utc_now


@pytest.fixture
def convites_ligados(app):
    app.config["CONVITES_HABILITADOS"] = True
    yield app
    app.config["CONVITES_HABILITADOS"] = False


def _convidar(client, project_id: int, user_id: int, **extra) -> dict:
    response = client.post(
        f"/api/projetos/{project_id}/membros",
        json={"user_id": user_id, "papel": "leitor", **extra},
    )
    assert response.status_code == 200, response.get_json()
    return response.get_json()["data"]


def _eventos(app) -> list[str]:
    with app.app_context():
        return [
            linha.evento
            for linha in AutorizacaoAudit.query.order_by(AutorizacaoAudit.id).all()
        ]


def test_revogar_e_reativar_mantem_uma_linha_e_tres_eventos(
    app, convites_ligados, client_user, seed_data
):
    project_id = seed_data["project_id"]
    membro = _convidar(client_user, project_id, seed_data["outsider_id"])

    revogacao = client_user.delete(f"/api/projetos/{project_id}/membros/{membro['id']}")
    reativado = _convidar(client_user, project_id, seed_data["outsider_id"])

    assert revogacao.status_code == 200
    assert reativado["id"] == membro["id"]
    assert reativado["status"] == "ativo"
    assert _eventos(app) == ["convite_criado", "convite_revogado", "convite_reativado"]
    with app.app_context():
        linha = ProjectMember.query.one()
        assert linha.revoked_at is None
        assert linha.revoked_by_id is None


def test_convite_expirado_aparece_como_expirado_e_e_renovavel(
    app, convites_ligados, client_user, seed_data
):
    project_id = seed_data["project_id"]
    with app.app_context():
        vencido = ProjectMember(
            project_id=project_id,
            user_id=seed_data["outsider_id"],
            papel=PAPEL_LEITOR,
            granted_by_id=seed_data["user_id"],
            expires_at=utc_now() - timedelta(days=1),
        )
        db.session.add(vencido)
        db.session.commit()
        member_id = vencido.id

    listagem = client_user.get(f"/api/projetos/{project_id}/membros")
    renovacao = client_user.put(
        f"/api/projetos/{project_id}/membros/{member_id}",
        json={"expires_at": "2099-01-01"},
    )

    assert listagem.get_json()["data"]["diretos"][0]["status"] == "expirado"
    assert renovacao.status_code == 200
    assert renovacao.get_json()["data"]["status"] == "ativo"


def test_convite_concede_leitura_e_revogacao_a_retira(
    app, convites_ligados, client_user, client_outsider, seed_data
):
    project_id = seed_data["project_id"]
    antes = client_outsider.get(f"/api/projetos/{project_id}/detalhe")

    membro = _convidar(client_user, project_id, seed_data["outsider_id"])
    durante = client_outsider.get(f"/api/projetos/{project_id}/detalhe")

    client_user.delete(f"/api/projetos/{project_id}/membros/{membro['id']}")
    depois = client_outsider.get(f"/api/projetos/{project_id}/detalhe")

    assert antes.status_code == 403
    assert durante.status_code == 200
    assert depois.status_code == 403


def test_convite_nao_cria_rank_de_area_nem_habilita_reatribuicao(
    app, convites_ligados, client_user, seed_data
):
    project_id = seed_data["project_id"]
    _convidar(client_user, project_id, seed_data["outsider_id"])

    with app.app_context():
        convidado = db.session.get(User, seed_data["outsider_id"])
        project = db.session.get(Project, project_id)
        assert effective_project_rank(convidado, project) > 0
        assert area_project_rank(convidado, project) == 0
        assert (
            can_assign_project_to_orgao(convidado, seed_data["auditoria_orgao_id"])
            is False
        )


def test_convidado_soft_deletado_perde_o_acesso(
    app, convites_ligados, client_user, client_outsider, seed_data
):
    project_id = seed_data["project_id"]
    _convidar(client_user, project_id, seed_data["outsider_id"])
    assert client_outsider.get(f"/api/projetos/{project_id}/detalhe").status_code == 200

    with app.app_context():
        convidado = db.session.get(User, seed_data["outsider_id"])
        convidado.deleted_at = utc_now()
        db.session.commit()

    # Soft-delete invalida a sessão (app.py:87) ANTES do gate de projeto; o
    # convite também some do mapa, então o rank cai a zero para qualquer caminho.
    assert client_outsider.get(f"/api/projetos/{project_id}/detalhe").status_code == 401
    with app.app_context():
        convidado = db.session.get(User, seed_data["outsider_id"])
        project = db.session.get(Project, project_id)
        assert effective_project_rank(convidado, project) == 0
