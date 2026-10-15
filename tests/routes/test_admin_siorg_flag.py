"""`SIORG_ENABLED=0` desliga o SIORG mesmo com `SIORG_API_KEY` preenchida."""

from __future__ import annotations


def test_status_reporta_desligado_quando_flag_zero(app, client_admin):
    app.config.update(SIORG_API_KEY="token-de-teste", SIORG_ENABLED="0")

    resposta = client_admin.get("/api/admin/siorg/status")

    assert resposta.status_code == 200
    assert resposta.get_json()["configurado"] is False


def test_status_reporta_ligado_com_chave_e_flag_ausente(app, client_admin):
    app.config.update(SIORG_API_KEY="token-de-teste", SIORG_ENABLED="")

    resposta = client_admin.get("/api/admin/siorg/status")

    assert resposta.get_json()["configurado"] is True


def test_sync_recusa_com_503_quando_flag_zero(app, client_admin):
    app.config.update(SIORG_API_KEY="token-de-teste", SIORG_ENABLED="0")

    resposta = client_admin.post("/api/admin/siorg/sync")

    assert resposta.status_code == 503
    assert "SIORG_ENABLED=0" in resposta.get_json()["error"]
