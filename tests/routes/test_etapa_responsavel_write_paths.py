"""Regressão dos write paths só-espelho de ``Etapa.responsavel`` (auditoria 1.2).

O espelho legado só pode ser reescrito junto da N:N ``etapa_responsavel``: a
edição completa da API traduz o texto recebido para áreas e a edição inline não
aceita mais o campo.
"""

from models import Etapa, EtapaResponsavel, OrgaoUnidade, db
from services.etapa_responsaveis import OUTRAS_LABEL

EDIT_BASE = {
    "descricao": "Etapa editada",
    "comentarios": "Sem comentarios",
    "iniciada": False,
    "done": False,
    "data_inicio": "2026-01-12",
    "data_fim": "2026-01-16",
}


def _error(response):
    payload = response.get_json()
    assert payload["ok"] is False
    return payload["error"]


def _area_id(app, sigla):
    with app.app_context():
        return OrgaoUnidade.query.filter_by(sigla=sigla).one().id


def _set_responsaveis(app, etapa_id, area_id, label):
    with app.app_context():
        etapa = db.session.get(Etapa, etapa_id)
        etapa.responsaveis = [EtapaResponsavel(area_id=area_id, label=label, ordem=0)]
        etapa.responsavel = label
        db.session.commit()


def _estado_responsaveis(app, etapa_id):
    """``(espelho, [(area_id, label), ...])`` — as duas faces que devem casar."""
    with app.app_context():
        etapa = db.session.get(Etapa, etapa_id)
        return etapa.responsavel, [(r.area_id, r.label) for r in etapa.responsaveis]


def test_edit_sem_chave_responsavel_nao_toca_espelho_nem_n_n(
    app, client_user, seed_data
):
    etapa_id = seed_data["etapa_id"]
    _set_responsaveis(app, etapa_id, None, "Outras")

    response = client_user.post(f"/api/etapas/{etapa_id}", json=dict(EDIT_BASE))

    assert response.status_code == 200
    assert _estado_responsaveis(app, etapa_id) == ("Outras", [(None, "Outras")])


def test_edit_com_responsavel_atualiza_n_n_e_espelho(app, client_user, seed_data):
    etapa_id = seed_data["etapa_id"]
    auditoria_id = _area_id(app, "Auditoria")
    _set_responsaveis(app, etapa_id, None, "Outras")

    response = client_user.post(
        f"/api/etapas/{etapa_id}",
        json={**EDIT_BASE, "responsavel": "Auditoria"},
    )

    assert response.status_code == 200
    assert _estado_responsaveis(app, etapa_id) == (
        "Auditoria",
        [(auditoria_id, "Auditoria")],
    )


def test_edit_com_responsavel_desconhecido_vira_outras(app, client_user, seed_data):
    etapa_id = seed_data["etapa_id"]
    _set_responsaveis(app, etapa_id, _area_id(app, "Auditoria"), "Auditoria")

    response = client_user.post(
        f"/api/etapas/{etapa_id}",
        json={**EDIT_BASE, "responsavel": "Equipe Externa"},
    )

    assert response.status_code == 200
    assert _estado_responsaveis(app, etapa_id) == (
        OUTRAS_LABEL,
        [(None, OUTRAS_LABEL)],
    )


def test_edit_com_responsavel_vazio_e_422_e_preserva_estado(
    app, client_user, seed_data
):
    etapa_id = seed_data["etapa_id"]
    auditoria_id = _area_id(app, "Auditoria")
    _set_responsaveis(app, etapa_id, auditoria_id, "Auditoria")

    response = client_user.post(
        f"/api/etapas/{etapa_id}",
        json={**EDIT_BASE, "responsavel": "   "},
    )

    assert response.status_code == 422
    assert _error(response)["code"] == "validation"
    assert _estado_responsaveis(app, etapa_id) == (
        "Auditoria",
        [(auditoria_id, "Auditoria")],
    )


def test_edit_de_etapa_que_continua_concluida_recusa_responsavel(
    app, client_user, seed_data
):
    etapa_id = seed_data["etapa_id"]
    auditoria_id = _area_id(app, "Auditoria")
    _set_responsaveis(app, etapa_id, auditoria_id, "Auditoria")
    with app.app_context():
        etapa = db.session.get(Etapa, etapa_id)
        etapa.iniciada = True
        etapa.done = True
        db.session.commit()

    response = client_user.post(
        f"/api/etapas/{etapa_id}",
        json={**EDIT_BASE, "iniciada": True, "done": True, "responsavel": "VPD"},
    )

    assert response.status_code == 422
    assert _error(response)["code"] == "validation"
    assert _estado_responsaveis(app, etapa_id) == (
        "Auditoria",
        [(auditoria_id, "Auditoria")],
    )


def test_edit_conclui_etapa_e_atualiza_responsavel_na_mesma_chamada(
    app, client_user, seed_data
):
    etapa_id = seed_data["etapa_id"]
    auditoria_id = _area_id(app, "Auditoria")
    _set_responsaveis(app, etapa_id, None, "Outras")

    response = client_user.post(
        f"/api/etapas/{etapa_id}",
        json={**EDIT_BASE, "iniciada": True, "done": True, "responsavel": "Auditoria"},
    )

    assert response.status_code == 200
    with app.app_context():
        assert db.session.get(Etapa, etapa_id).done is True
    assert _estado_responsaveis(app, etapa_id) == (
        "Auditoria",
        [(auditoria_id, "Auditoria")],
    )


def test_update_field_responsavel_e_campo_invalido(app, client_user, seed_data):
    etapa_id = seed_data["etapa_id"]
    auditoria_id = _area_id(app, "Auditoria")
    _set_responsaveis(app, etapa_id, auditoria_id, "Auditoria")

    response = client_user.post(
        f"/api/etapas/{etapa_id}/update-field",
        json={"field": "responsavel", "value": "Outra Coisa"},
    )

    assert response.status_code == 422
    error = _error(response)
    assert error["code"] == "validation"
    assert error["message"] == "Campo inválido."
    assert _estado_responsaveis(app, etapa_id) == (
        "Auditoria",
        [(auditoria_id, "Auditoria")],
    )
