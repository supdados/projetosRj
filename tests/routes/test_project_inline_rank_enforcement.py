"""Enforcement de rank na edição inline de projeto (S3/F2-3).

Cobre ``routes/projects/ajax.py::apply_project_inline_changes`` pelo endpoint que
o consome (``POST /api/projetos/<id>/inline``) e, quando o cenário não é
alcançável pela rota (rank 0 no projeto), direto na função.

Os dois lados exigidos pela sprint:

- **equivalência gestor**: todo vínculo do seed nasce ``gestor`` (backfill S2),
  então admin e gestor mantêm exatamente o comportamento de hoje — inclusive os
  400/422 de órgão inexistente/inativo, que continuam vindo antes do 403;
- **restrição nova**: ``leitor`` perde toda escrita inline e ``editor`` perde a
  reatribuição de Área Responsável para fora da própria subárvore (§5.4).

As duas variantes de escalação da §5.4 estão em
``test_editor_nao_move_projeto_para_orgao_fora_da_subarvore`` (destino arbitrário)
e ``test_rank_zero_no_projeto_nao_captura_projeto_para_a_propria_area``
(condição (b): rank alto no destino não basta).
"""

from __future__ import annotations

import pytest
from flask import g

from models import OrgaoUnidade, Project, User, UserOrgao, db
from routes.projects.ajax import ProjectInlineError, apply_project_inline_changes
from services.authorization import (
    can_assign_project_to_orgao,
    user_can_reassign_project_to_orgao,
)


def _criar_usuario_com_papel(username: str, orgao_id: int, papel: str) -> int:
    """Cria usuário com um único vínculo de área no papel pedido."""
    user = User(username=username, name=username, orgao="Orgao Teste", is_admin=False)
    user.set_password("senha123")
    db.session.add(user)
    db.session.flush()
    db.session.add(UserOrgao(user_id=user.id, orgao_id=orgao_id, papel=papel))
    db.session.commit()
    return user.id


def _criar_suborgao(sigla: str, pai_id: int) -> int:
    orgao = OrgaoUnidade(
        sigla=sigla, nome=sigla, tipo="Subsecretaria", pai_id=pai_id, ordem=0
    )
    db.session.add(orgao)
    db.session.commit()
    return orgao.id


def _cliente_logado(app, user_id: int):
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = user_id
    return client


def _cliente_com_papel(app, seed_data, papel: str):
    """Cliente autenticado como usuário com ``papel`` na área dona do projeto."""
    with app.app_context():
        user_id = _criar_usuario_com_papel(
            f"user_{papel}", seed_data["auditoria_orgao_id"], papel
        )
    return _cliente_logado(app, user_id)


def _titulo(app, project_id: int) -> str:
    with app.app_context():
        return db.session.get(Project, project_id).titulo


def _orgao_id(app, project_id: int) -> int:
    with app.app_context():
        return db.session.get(Project, project_id).orgao_id


# ── Escrita inline: limiar editor ────────────────────────────────────────────


def test_gestor_edita_inline_como_hoje(app, client_user, seed_data):
    """Equivalência gestor: vínculo do backfill continua editando tudo."""
    project_id = seed_data["project_id"]

    response = client_user.post(
        f"/api/projetos/{project_id}/inline", json={"titulo": "Editado por gestor"}
    )

    assert response.status_code == 200
    assert _titulo(app, project_id) == "Editado por gestor"


def test_admin_edita_inline_como_hoje(app, client_admin, seed_data):
    project_id = seed_data["project_id"]

    response = client_admin.post(
        f"/api/projetos/{project_id}/inline", json={"titulo": "Editado por admin"}
    )

    assert response.status_code == 200
    assert _titulo(app, project_id) == "Editado por admin"


def test_editor_edita_inline(app, seed_data):
    project_id = seed_data["project_id"]
    titulo_antes = _titulo(app, project_id)
    client = _cliente_com_papel(app, seed_data, "editor")

    response = client.post(
        f"/api/projetos/{project_id}/inline", json={"titulo": "Editado por editor"}
    )

    assert response.status_code == 200
    assert _titulo(app, project_id) == "Editado por editor" != titulo_antes


def test_leitor_perde_a_escrita_inline(app, seed_data):
    project_id = seed_data["project_id"]
    titulo_antes = _titulo(app, project_id)
    client = _cliente_com_papel(app, seed_data, "leitor")

    response = client.post(
        f"/api/projetos/{project_id}/inline", json={"titulo": "Editado por leitor"}
    )

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "forbidden"
    assert _titulo(app, project_id) == titulo_antes


def test_leitor_tambem_perde_a_reabertura_de_projeto_finalizado(app, seed_data):
    project_id = seed_data["project_complete_id"]
    client = _cliente_com_papel(app, seed_data, "leitor")

    response = client.post(
        f"/api/projetos/{project_id}/inline", json={"status": "Vigente"}
    )

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "forbidden"


# ── Reatribuição de Área Responsável: regra dupla da §5.4 ────────────────────


def test_gestor_move_projeto_dentro_da_propria_subarvore(app, client_user, seed_data):
    """Equivalência gestor: mover dentro da subárvore continua 200."""
    project_id = seed_data["project_id"]
    with app.app_context():
        destino_id = _criar_suborgao("AUDSUB", seed_data["auditoria_orgao_id"])

    response = client_user.post(
        f"/api/projetos/{project_id}/inline", json={"orgao_id": destino_id}
    )

    assert response.status_code == 200
    assert _orgao_id(app, project_id) == destino_id


def test_editor_move_projeto_dentro_da_propria_subarvore(app, seed_data):
    project_id = seed_data["project_id"]
    with app.app_context():
        destino_id = _criar_suborgao("AUDSUB2", seed_data["auditoria_orgao_id"])
    client = _cliente_com_papel(app, seed_data, "editor")

    response = client.post(
        f"/api/projetos/{project_id}/inline", json={"orgao_id": destino_id}
    )

    assert response.status_code == 200
    assert _orgao_id(app, project_id) == destino_id


def test_editor_nao_move_projeto_para_orgao_fora_da_subarvore(app, seed_data):
    """Variante 1 da escalação: destino arbitrário é negado pela condição (a)."""
    project_id = seed_data["project_id"]
    orgao_antes = _orgao_id(app, project_id)
    client = _cliente_com_papel(app, seed_data, "editor")

    response = client.post(
        f"/api/projetos/{project_id}/inline",
        json={"orgao_id": seed_data["vpd_orgao_id"]},
    )

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "forbidden"
    assert _orgao_id(app, project_id) == orgao_antes


def test_leitor_da_area_dona_nao_move_projeto(app, seed_data):
    project_id = seed_data["project_id"]
    orgao_antes = _orgao_id(app, project_id)
    client = _cliente_com_papel(app, seed_data, "leitor")

    response = client.post(
        f"/api/projetos/{project_id}/inline", json={"orgao_id": orgao_antes}
    )

    assert response.status_code == 403
    assert _orgao_id(app, project_id) == orgao_antes


def test_rank_zero_no_projeto_nao_captura_projeto_para_a_propria_area(app, seed_data):
    """Variante 2 da escalação (condição (b)): editor no DESTINO não basta.

    Exercitado na função porque a rota nem chega lá — rank 0 no projeto para no
    404 anti-enumeração (S5/F4-2). Reproduz o convidado-editor da S4.
    """
    project_id = seed_data["project_id"]
    with app.test_request_context():
        capturador_id = _criar_usuario_com_papel(
            "capturador", seed_data["vpd_orgao_id"], "editor"
        )
        g.user = db.session.get(User, capturador_id)
        project = db.session.get(Project, project_id)

        # Condição (a) satisfeita no destino, (b) reprovada no projeto.
        assert can_assign_project_to_orgao(g.user, seed_data["vpd_orgao_id"]) is True
        assert (
            user_can_reassign_project_to_orgao(
                g.user, project, seed_data["vpd_orgao_id"]
            )
            is False
        )

        with pytest.raises(ProjectInlineError) as excinfo:
            apply_project_inline_changes(
                project, {"orgao_id": seed_data["vpd_orgao_id"]}
            )

        assert excinfo.value.status == 403
        db.session.rollback()

    assert _orgao_id(app, project_id) == seed_data["auditoria_orgao_id"]


def test_editor_no_destino_e_leitor_no_projeto_nao_move(app, seed_data):
    """Condição (b) com acesso de leitura: leitor na área dona não reatribui."""
    project_id = seed_data["project_id"]
    with app.app_context():
        leitor_id = _criar_usuario_com_papel(
            "leitor_auditoria_editor_vpd", seed_data["auditoria_orgao_id"], "leitor"
        )
        db.session.add(
            UserOrgao(
                user_id=leitor_id, orgao_id=seed_data["vpd_orgao_id"], papel="editor"
            )
        )
        db.session.commit()
    client = _cliente_logado(app, leitor_id)

    response = client.post(
        f"/api/projetos/{project_id}/inline",
        json={"orgao_id": seed_data["vpd_orgao_id"]},
    )

    assert response.status_code == 403
    assert _orgao_id(app, project_id) == seed_data["auditoria_orgao_id"]


# ── Contrato preservado: 400/422 de órgão continua antes do 403 ──────────────


def test_gestor_recebe_422_para_orgao_inexistente(app, client_user, seed_data):
    project_id = seed_data["project_id"]

    response = client_user.post(
        f"/api/projetos/{project_id}/inline", json={"orgao_id": 999999}
    )

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "validation"


def test_gestor_recebe_422_para_orgao_inativo(app, client_user, seed_data):
    project_id = seed_data["project_id"]
    with app.app_context():
        inativo = OrgaoUnidade(
            sigla="AUDOFF",
            nome="AUDOFF",
            tipo="Subsecretaria",
            pai_id=seed_data["auditoria_orgao_id"],
            ordem=0,
            ativo=False,
        )
        db.session.add(inativo)
        db.session.commit()
        inativo_id = inativo.id

    response = client_user.post(
        f"/api/projetos/{project_id}/inline", json={"orgao_id": inativo_id}
    )

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "validation"
