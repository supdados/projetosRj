"""Custo de query de "Projetos Pendentes": zero N+1 em ``Etapa.responsaveis``.

Regressão: ``serialize_etapa_card`` chama ``etapa_tem_responsavel(etapa)``, que
toca ``Etapa.responsaveis`` (``lazy="select"``). Sem o ``selectinload`` na query
de etapas de ``build_projetos_pendentes_context`` sai 1 SELECT em
``etapa_responsavel`` por etapa serializada (centenas por request).
"""

import datetime
import uuid

import pytest
from flask import g
from sqlalchemy import event

from models import Etapa, OrgaoUnidade, Project, User, db
from models.etapa import EtapaResponsavel
from routes.api.serializers import serialize_pending_project_row
from routes.projects.views import build_projetos_pendentes_context


class ContadorDeSelectDeResponsavel:
    """Conta somente os SELECT que leem a tabela ``etapa_responsavel``.

    O contador genérico não serve: o alias de coluna de ``Etapa.responsavel``
    aparece como ``etapa_responsavel`` no SQL e contaria falsos positivos.
    """

    def __init__(self, engine) -> None:
        self.engine = engine
        self.total = 0

    def _on_execute(self, conn, cursor, statement, parameters, context, many) -> None:
        if "FROM etapa_responsavel" in statement:
            self.total += 1

    def __enter__(self) -> "ContadorDeSelectDeResponsavel":
        event.listen(self.engine, "before_cursor_execute", self._on_execute)
        return self

    def __exit__(self, *_exc) -> None:
        event.remove(self.engine, "before_cursor_execute", self._on_execute)


def _semeia_pendentes(qtd_projetos: int, etapas_por_projeto: int) -> int:
    """Cria projetos vigentes com etapas atrasadas, todas com área responsável."""
    # Sufixo único: o mesmo banco pode receber mais de uma semeadura.
    sufixo = uuid.uuid4().hex[:8]
    orgao = OrgaoUnidade(sigla=f"SETD{sufixo}", nome="SETD", tipo="Secretaria", ordem=0)
    db.session.add(orgao)
    db.session.flush()

    admin = User(username=f"admin_{sufixo}", name="Admin", orgao="SETD", is_admin=True)
    admin.set_password("senha123")
    db.session.add(admin)
    db.session.flush()

    atrasada = datetime.date.today() - datetime.timedelta(days=5)
    for indice_projeto in range(qtd_projetos):
        projeto = Project(
            titulo=f"Projeto {indice_projeto}",
            orgao_id=orgao.id,
            orgao="SETD",
            prioridade="alta",
            status="Vigente",
            objetivo_id=1,
            resultado_esperado_id=1,
        )
        db.session.add(projeto)
        db.session.flush()
        for ordem in range(etapas_por_projeto):
            etapa = Etapa(
                descricao=f"Etapa {indice_projeto}-{ordem}",
                data_inicio=atrasada,
                data_fim=atrasada + datetime.timedelta(days=1),
                iniciada=False,
                done=False,
                project_id=projeto.id,
                ordem=ordem,
            )
            db.session.add(etapa)
            db.session.flush()
            db.session.add(
                EtapaResponsavel(
                    etapa_id=etapa.id, area_id=orgao.id, label="SETD", ordem=0
                )
            )
    db.session.commit()
    return admin.id


def _custo_de_responsaveis(app, qtd_projetos: int, etapas_por_projeto: int) -> int:
    with app.app_context():
        admin_id = _semeia_pendentes(qtd_projetos, etapas_por_projeto)
    with app.test_request_context("/api/projetos-pendentes"):
        g.user = db.session.get(User, admin_id)
        with ContadorDeSelectDeResponsavel(db.engine) as contador:
            context = build_projetos_pendentes_context(None)
            linhas = [
                serialize_pending_project_row(row)
                for row in context["projetos_com_etapas"]
            ]
        etapas_serializadas = sum(
            len(linha["etapas_visiveis"]) + len(linha["etapas_outras"])
            for linha in linhas
        )
        assert etapas_serializadas == qtd_projetos * etapas_por_projeto
        assert all(
            card["tem_responsavel"] is True
            for linha in linhas
            for card in linha["etapas_visiveis"]
        )
        return contador.total


def test_responsaveis_das_etapas_nao_geram_um_select_por_etapa(app):
    """1 SELECT (selectinload) independente de quantas etapas entram nos cards."""
    assert _custo_de_responsaveis(app, qtd_projetos=6, etapas_por_projeto=8) <= 1


@pytest.mark.parametrize("etapas_por_projeto", [1, 8])
def test_custo_de_responsaveis_nao_cresce_com_o_numero_de_etapas(
    app, etapas_por_projeto
):
    assert (
        _custo_de_responsaveis(
            app, qtd_projetos=4, etapas_por_projeto=etapas_por_projeto
        )
        <= 1
    )
