"""Busca global casa o responsável da etapa pela N:N, não só pelo espelho legado."""

from models import Etapa, EtapaResponsavel, db


def _add_etapa(project_id: int, descricao: str, mirror: str | None, labels: list[str]):
    etapa = Etapa(
        descricao=descricao, project_id=project_id, ordem=90, responsavel=mirror
    )
    etapa.responsaveis = [
        EtapaResponsavel(area_id=None, label=label, ordem=index)
        for index, label in enumerate(labels)
    ]
    db.session.add(etapa)
    db.session.commit()
    return etapa.id


def _stage_titles(client, term: str) -> list[str]:
    response = client.get("/api/busca-global", query_string={"q": term, "limit": 20})
    assert response.status_code == 200
    return [item["title"] for item in response.get_json()["results"]["stages"]]


def test_busca_encontra_etapa_por_responsavel_so_na_n_n(app, client_user, seed_data):
    with app.app_context():
        _add_etapa(
            seed_data["project_id"],
            "Etapa Espelho Vazio",
            None,
            ["COOZETAUM", "COOZETADOIS"],
        )

    assert _stage_titles(client_user, "COOZETADOIS") == ["Etapa Espelho Vazio"]


def test_busca_ignora_espelho_divergente_quando_ha_n_n(app, client_user, seed_data):
    with app.app_context():
        _add_etapa(
            seed_data["project_id"],
            "Etapa Espelho Truncado",
            "COOZETAOBSOLETA",
            ["COOZETAUM", "COOZETATRES"],
        )

    assert _stage_titles(client_user, "COOZETATRES") == ["Etapa Espelho Truncado"]
    assert _stage_titles(client_user, "COOZETAOBSOLETA") == []


def test_busca_mantem_fallback_no_espelho_sem_linhas_n_n(app, client_user, seed_data):
    with app.app_context():
        _add_etapa(seed_data["project_id"], "Etapa Legada", "COOZETAQUATRO", [])

    assert _stage_titles(client_user, "COOZETAQUATRO") == ["Etapa Legada"]
