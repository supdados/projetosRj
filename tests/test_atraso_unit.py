"""Critério único de atraso (services/atraso.py): definição + 1 relógio.

DECISÃO DE PRODUTO: projeto atrasado = existe etapa de workflow NÃO concluída
com ``data_fim < hoje`` (hoje = ``utc_now().date()``, UTC). A fronteira
``data_fim == hoje`` NÃO é atraso e ``data_inicio`` não participa. Os quatro
consumidores (Lista, Pendentes, Dashboard, Coleções) devem concordar.
"""

import datetime

from flask import g

from models import Etapa, Project, ProjectCollection, ProjectCollectionItem, User, db
from routes.dashboard import build_dashboard_context
from routes.projects.views import (
    build_projects_list_context,
    build_projetos_pendentes_context,
)
from services.atraso import (
    etapa_esta_vencida,
    hoje_utc,
    projeto_atrasado_criterion,
    projeto_esta_atrasado,
)
from services.project_collections import colecao_project_rows

HOJE_FIXO = datetime.date(2026, 8, 15)


def _novo_projeto(titulo: str, status: str = "Vigente") -> Project:
    projeto = Project(titulo=titulo, status=status)
    db.session.add(projeto)
    db.session.flush()
    return projeto


def _nova_etapa(
    project_id: int,
    *,
    data_fim: datetime.date | None,
    done: bool = False,
    entry_type: str = "manual",
) -> Etapa:
    etapa = Etapa(
        descricao="Etapa atraso",
        data_fim=data_fim,
        done=done,
        iniciada=done,
        project_id=project_id,
        ordem=0,
        entry_type=entry_type,
    )
    db.session.add(etapa)
    db.session.flush()
    return etapa


def _ids_atrasados(hoje: datetime.date) -> set[int]:
    rows = Project.query.filter(projeto_atrasado_criterion(hoje)).all()
    return {projeto.id for projeto in rows}


def test_criterion_projeto_com_etapa_vencida_e_atrasado(app):
    with app.app_context():
        projeto = _novo_projeto("Vencido")
        _nova_etapa(projeto.id, data_fim=HOJE_FIXO - datetime.timedelta(days=1))
        db.session.commit()

        assert _ids_atrasados(HOJE_FIXO) == {projeto.id}
        assert projeto_esta_atrasado(projeto.id, HOJE_FIXO) is True


def test_criterion_data_fim_futura_nao_e_atraso(app):
    with app.app_context():
        projeto = _novo_projeto("Futuro")
        _nova_etapa(projeto.id, data_fim=HOJE_FIXO + datetime.timedelta(days=1))
        db.session.commit()

        assert _ids_atrasados(HOJE_FIXO) == set()
        assert projeto_esta_atrasado(projeto.id, HOJE_FIXO) is False


def test_criterion_etapa_vencida_concluida_nao_e_atraso(app):
    with app.app_context():
        projeto = _novo_projeto("Concluido")
        _nova_etapa(
            projeto.id, data_fim=HOJE_FIXO - datetime.timedelta(days=10), done=True
        )
        db.session.commit()

        assert _ids_atrasados(HOJE_FIXO) == set()


def test_criterion_projeto_sem_etapas_nao_e_atraso(app):
    with app.app_context():
        _novo_projeto("Sem etapas")
        db.session.commit()

        assert _ids_atrasados(HOJE_FIXO) == set()


def test_criterion_fronteira_data_fim_igual_hoje_nao_e_atraso(app):
    with app.app_context():
        projeto = _novo_projeto("Fronteira")
        _nova_etapa(projeto.id, data_fim=HOJE_FIXO)
        db.session.commit()

        assert _ids_atrasados(HOJE_FIXO) == set()
        assert projeto_esta_atrasado(projeto.id, HOJE_FIXO) is False


def test_criterion_ignora_reuniao_google_e_data_fim_nula(app):
    with app.app_context():
        projeto = _novo_projeto("Reuniao e sem data")
        _nova_etapa(
            projeto.id,
            data_fim=HOJE_FIXO - datetime.timedelta(days=3),
            entry_type="google_meeting",
        )
        _nova_etapa(projeto.id, data_fim=None)
        db.session.commit()

        assert _ids_atrasados(HOJE_FIXO) == set()


def test_espelho_python_concorda_com_o_criterion_sql(app):
    with app.app_context():
        projeto = _novo_projeto("Paridade")
        etapas = [
            _nova_etapa(projeto.id, data_fim=HOJE_FIXO - datetime.timedelta(days=1)),
            _nova_etapa(projeto.id, data_fim=HOJE_FIXO),
            _nova_etapa(projeto.id, data_fim=None),
            _nova_etapa(
                projeto.id, data_fim=HOJE_FIXO - datetime.timedelta(days=1), done=True
            ),
            _nova_etapa(
                projeto.id,
                data_fim=HOJE_FIXO - datetime.timedelta(days=1),
                entry_type="google_meeting",
            ),
        ]
        db.session.commit()

        assert [etapa_esta_vencida(etapa, HOJE_FIXO) for etapa in etapas] == [
            True,
            False,
            False,
            False,
            False,
        ]


# ── Os 4 consumidores concordam ───────────────────────────────────────────────


def _semeia_consumidores() -> dict[str, int]:
    """Admin + projeto atrasado (data_fim ontem) + projeto na fronteira (hoje)."""
    admin = User(username="admin_atraso", name="Admin Atraso", is_admin=True)
    admin.set_password("senha123")
    db.session.add(admin)
    db.session.flush()

    atrasado = _novo_projeto("Projeto Atrasado")
    _nova_etapa(atrasado.id, data_fim=hoje_utc() - datetime.timedelta(days=2))
    no_prazo = _novo_projeto("Projeto Fronteira")
    _nova_etapa(no_prazo.id, data_fim=hoje_utc())

    colecao = ProjectCollection(owner_user_id=admin.id, nome="Colecao Atraso")
    db.session.add(colecao)
    db.session.flush()
    for ordem, projeto in enumerate([atrasado, no_prazo]):
        db.session.add(
            ProjectCollectionItem(
                collection_id=colecao.id, project_id=projeto.id, ordem=ordem
            )
        )
    db.session.commit()
    return {
        "admin_id": admin.id,
        "atrasado_id": atrasado.id,
        "no_prazo_id": no_prazo.id,
        "colecao_id": colecao.id,
    }


def test_os_quatro_consumidores_concordam_sobre_o_mesmo_projeto(app):
    with app.app_context():
        ids = _semeia_consumidores()
    with app.test_request_context("/"):
        g.user = db.session.get(User, ids["admin_id"])

        lista_atrasados = build_projects_list_context(
            selected_status="", selected_atraso="atrasado"
        )
        assert {p.id for p in lista_atrasados["projects"]} == {ids["atrasado_id"]}

        lista_no_prazo = build_projects_list_context(
            selected_status="", selected_atraso="no_prazo"
        )
        assert {p.id for p in lista_no_prazo["projects"]} == {ids["no_prazo_id"]}

        pendentes = build_projetos_pendentes_context(None)
        assert {item["projeto"].id for item in pendentes["projetos_com_etapas"]} == {
            ids["atrasado_id"]
        }

        dashboard = build_dashboard_context(None)
        assert dashboard["projetos_em_atraso"] == 1

        colecao = db.session.get(ProjectCollection, ids["colecao_id"])
        flags = {
            linha["id"]: linha["atrasado"]
            for linha in colecao_project_rows(colecao, g.user)
        }
        assert flags == {ids["atrasado_id"]: True, ids["no_prazo_id"]: False}
