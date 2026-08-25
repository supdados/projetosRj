"""Contrato do modo ``?apenas_orgao=1`` (filtro de órgão SEM descendentes).

Cobre as telas que expõem o chip "Apenas esta área": Lista de Projetos,
Projetos Pendentes, Hub de Tarefas (lista + board) e o export CSV — todas
compartilham ``expand_orgao_filter_ids(..., incluir_descendentes=False)``.
"""

from __future__ import annotations

import datetime

from models import Etapa, OrgaoUnidade, Project, db


def _criar_pai_filho_com_projetos(app):
    """Órgão pai e filho, cada um com 1 projeto Vigente com etapa atrasada."""
    with app.app_context():
        pai = OrgaoUnidade(
            sigla="PAIX",
            nome="PAIX",
            tipo="Secretaria",
            pai_id=None,
            ordem=0,
            ativo=True,
        )
        db.session.add(pai)
        db.session.flush()
        filho = OrgaoUnidade(
            sigla="FILHOX",
            nome="FILHOX",
            tipo="Subsecretaria",
            pai_id=pai.id,
            ordem=0,
            ativo=True,
        )
        db.session.add(filho)
        db.session.flush()
        ontem = datetime.date.today() - datetime.timedelta(days=1)
        for titulo, orgao_id in (
            ("Projeto do Pai", pai.id),
            ("Projeto do Filho", filho.id),
        ):
            project = Project(titulo=titulo, orgao_id=orgao_id, status="Vigente")
            db.session.add(project)
            db.session.flush()
            db.session.add(
                Etapa(
                    descricao=f"Etapa atrasada de {titulo}",
                    data_fim=ontem,
                    done=False,
                    project_id=project.id,
                    ordem=0,
                )
            )
        db.session.commit()
        return pai.id, filho.id


def _titulos(payload):
    return {p["titulo"] for p in payload["data"]["projetos"]}


def test_api_projetos_apenas_orgao_exclui_descendentes(app, client_admin):
    pai_id, _ = _criar_pai_filho_com_projetos(app)

    hierarquico = client_admin.get(f"/api/projetos?orgao={pai_id}").get_json()
    assert {"Projeto do Pai", "Projeto do Filho"} <= _titulos(hierarquico)

    apenas = client_admin.get(f"/api/projetos?orgao={pai_id}&apenas_orgao=1").get_json()
    assert "Projeto do Pai" in _titulos(apenas)
    assert "Projeto do Filho" not in _titulos(apenas)


def test_api_projetos_export_apenas_orgao(app, client_admin):
    pai_id, _ = _criar_pai_filho_com_projetos(app)

    resposta = client_admin.get(
        f"/api/projetos/exportar?colunas=titulo&orgao={pai_id}&apenas_orgao=1"
    )
    assert resposta.status_code == 200
    corpo = resposta.get_data(as_text=True)
    assert "Projeto do Pai" in corpo
    assert "Projeto do Filho" not in corpo


def test_api_projetos_pendentes_apenas_orgao(app, client_admin):
    pai_id, _ = _criar_pai_filho_com_projetos(app)

    hierarquico = client_admin.get(f"/api/projetos-pendentes?orgao={pai_id}").get_json()
    apenas = client_admin.get(
        f"/api/projetos-pendentes?orgao={pai_id}&apenas_orgao=1"
    ).get_json()
    assert hierarquico["ok"] is True and apenas["ok"] is True
    total_hierarquico = hierarquico["data"]["summary_counts"]["total_projects"]
    total_apenas = apenas["data"]["summary_counts"]["total_projects"]
    assert total_apenas == total_hierarquico - 1


def test_api_tarefas_apenas_orgao_restringe_opcoes_de_projeto(app, client_admin):
    pai_id, _ = _criar_pai_filho_com_projetos(app)

    hierarquico = client_admin.get(f"/api/tarefas?orgao={pai_id}").get_json()
    apenas = client_admin.get(f"/api/tarefas?orgao={pai_id}&apenas_orgao=1").get_json()
    assert hierarquico["ok"] is True and apenas["ok"] is True

    def rotulos(payload):
        return {o["label"] for o in payload["data"]["project_options"]}

    assert {"Projeto do Pai", "Projeto do Filho"} <= rotulos(hierarquico)
    assert "Projeto do Pai" in rotulos(apenas)
    assert "Projeto do Filho" not in rotulos(apenas)


def test_api_board_aceita_apenas_orgao(app, client_admin):
    pai_id, _ = _criar_pai_filho_com_projetos(app)

    resposta = client_admin.get(f"/api/tarefas/board?orgao={pai_id}&apenas_orgao=1")
    assert resposta.status_code == 200
    assert resposta.get_json()["ok"] is True
