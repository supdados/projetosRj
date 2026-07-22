"""Regressão do bug 2.8: busca deve casar o órgão ATUAL, não o texto legado.

``Project.orgao`` (texto livre) dessincroniza de ``Project.orgao_id`` — a SPA
grava só ``orgao_id`` ao trocar a Área Responsável, deixando o texto stale/None.
Os três filtros de busca (lista de projetos, projetos pendentes e busca global)
devem achar o projeto pela sigla/nome do órgão ATUAL e NÃO pelo texto stale;
projetos legados SEM ``orgao_id`` seguem encontráveis pelo texto legado.
"""

import datetime

from models import Etapa, OrgaoUnidade, Project, db


def _make_orgao(sigla, nome):
    setd = OrgaoUnidade.query.filter_by(sigla="SETD").first()
    orgao = OrgaoUnidade(
        sigla=sigla,
        nome=nome,
        tipo="Subsecretaria",
        pai_id=setd.id if setd else None,
        ordem=0,
        ativo=True,
    )
    db.session.add(orgao)
    db.session.flush()
    return orgao


def _project_ids(payload_data):
    return {p["id"] for p in payload_data["projetos"]}


def test_projetos_list_search_matches_current_orgao_not_stale_text(
    app, client_admin, seed_data
):
    with app.app_context():
        orgao = _make_orgao("ZZSIGLANOVA", "Orgao Sigla Nova")
        synced = Project(
            titulo="Projeto Sync Lista",
            orgao_id=orgao.id,
            orgao="ZZTEXTOSTALE",
            prioridade="media",
            status="Vigente",
            objetivo_id=1,
            resultado_esperado_id=1,
        )
        db.session.add(synced)
        db.session.commit()
        synced_id = synced.id

    by_current = client_admin.get("/api/projetos", query_string={"q": "ZZSIGLANOVA"})
    assert by_current.status_code == 200
    assert synced_id in _project_ids(by_current.get_json()["data"])

    by_stale = client_admin.get("/api/projetos", query_string={"q": "ZZTEXTOSTALE"})
    assert by_stale.status_code == 200
    assert synced_id not in _project_ids(by_stale.get_json()["data"])


def test_projetos_list_search_matches_legacy_text_when_no_orgao_id(
    app, client_admin, seed_data
):
    with app.app_context():
        legacy = Project(
            titulo="Projeto Legado Lista",
            orgao_id=None,
            orgao="ZZLEGADOTEXTO",
            prioridade="media",
            status="Vigente",
            objetivo_id=1,
            resultado_esperado_id=1,
        )
        db.session.add(legacy)
        db.session.commit()
        legacy_id = legacy.id

    response = client_admin.get("/api/projetos", query_string={"q": "ZZLEGADOTEXTO"})
    assert response.status_code == 200
    assert legacy_id in _project_ids(response.get_json()["data"])


def test_projetos_pendentes_search_matches_current_orgao_not_stale_text(
    app, client_admin, seed_data
):
    with app.app_context():
        orgao = _make_orgao("ZZPENDSIGLA", "Orgao Pendente Novo")
        synced = Project(
            titulo="Projeto Sync Pendente",
            orgao_id=orgao.id,
            orgao="ZZPENDSTALE",
            prioridade="media",
            status="Vigente",
            objetivo_id=1,
            resultado_esperado_id=1,
        )
        db.session.add(synced)
        db.session.flush()
        # Pendentes só considera projetos com etapa aberta atrasada.
        db.session.add(
            Etapa(
                descricao="Etapa Pendente Sync",
                data_inicio=datetime.date(2000, 1, 1),
                data_fim=datetime.date(2000, 1, 2),
                iniciada=True,
                done=False,
                project_id=synced.id,
                ordem=0,
            )
        )
        db.session.commit()
        synced_id = synced.id

    def pending_ids(query):
        response = client_admin.get("/api/projetos-pendentes", query_string=query)
        assert response.status_code == 200
        data = response.get_json()["data"]
        return {item["project"]["id"] for item in data["projetos"]}

    assert synced_id in pending_ids({"q": "ZZPENDSIGLA", "periodo": "atrasados"})
    assert synced_id not in pending_ids({"q": "ZZPENDSTALE", "periodo": "atrasados"})


def test_global_search_matches_current_orgao_not_stale_text(
    app, client_admin, seed_data
):
    with app.app_context():
        orgao = _make_orgao("ZZGLOBSIGLA", "Orgao Global Novo")
        synced = Project(
            titulo="Projeto Sync Global",
            orgao_id=orgao.id,
            orgao="ZZGLOBSTALE",
            prioridade="media",
            status="Vigente",
            objetivo_id=1,
            resultado_esperado_id=1,
        )
        db.session.add(synced)
        db.session.commit()

    def global_titles(term):
        response = client_admin.get("/api/busca-global", query_string={"q": term})
        assert response.status_code == 200
        return {p["title"] for p in response.get_json()["results"]["projects"]}

    assert "Projeto Sync Global" in global_titles("ZZGLOBSIGLA")
    assert "Projeto Sync Global" not in global_titles("ZZGLOBSTALE")
