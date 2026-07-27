"""Contrato dos errorhandlers JSON de ``/api/*`` (B1).

Garante que erros sob ``/api/*`` respondem o envelope canônico
``{"ok": false, "error": {"code", "message"}}`` em JSON — NUNCA HTML — para que o
cliente SPA (``client.ts``) consiga desempacotar sem quebrar ("Unrecognized token
'<'"). Cobre 500 (exceção não tratada), 404 (rota inexistente) e 405 (método não
permitido), e confirma que rotas Jinja (fora de ``/api/``) seguem em HTML.

Cobre também o contrato anti-enumeração da S5 (F4-2b): recurso invisível e
recurso inexistente devolvem envelope IDÊNTICO — mesmo status, ``code`` e
``message`` —, indistinguíveis inclusive do 404 do roteador.

Handlers exercitados: ``routes/api/errors.py``, ``routes/api/envelope.py``.
"""

import pytest


def _assert_fail_envelope(response, *, status, code):
    """Asserta que a resposta é JSON no envelope ``fail`` com ``status``/``code``.

    Args:
        response: A resposta do test client.
        status: Código HTTP esperado.
        code: Código de erro canônico esperado em ``error.code``.
    """
    assert response.status_code == status
    assert response.is_json, f"esperava JSON, veio {response.content_type!r}"
    body = response.get_json()
    assert body["ok"] is False
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]


def test_unhandled_exception_under_api_returns_json_500_envelope(
    client_user, monkeypatch
):
    """Exceção não tratada numa view ``/api/*`` vira 500 JSON, não HTML 500."""

    def _boom(_objetivo_id):
        raise RuntimeError("falha simulada na view /api")

    # A view get_resultados chama get_resultados_for_objetivo; forçamos o estouro
    # DEPOIS da checagem de id (objetivo 1 existe no catálogo semeado).
    monkeypatch.setattr("routes.api.legacy.get_resultados_for_objetivo", _boom)

    response = client_user.get("/api/resultados/1")

    _assert_fail_envelope(response, status=500, code="server")


def test_unknown_api_path_returns_json_404_envelope(client_user):
    """GET de rota ``/api/<inexistente>`` responde 404 JSON, não HTML 404."""
    response = client_user.get("/api/rota-que-nao-existe-12345")

    _assert_fail_envelope(response, status=404, code="not_found")


def test_wrong_method_under_api_returns_json_405_envelope(client_user):
    """Método não aceito numa rota ``/api/*`` responde 405 JSON (``validation``)."""
    # /api/resultados/<id> só aceita GET; POST deve cair no 405 envelopado.
    response = client_user.post("/api/resultados/1")

    _assert_fail_envelope(response, status=405, code="validation")


def test_projeto_invisivel_e_projeto_inexistente_tem_envelope_identico(
    client_outsider, seed_data
):
    """F4-2b: "existe mas nao vejo" e "nao existe" sao INDISTINGUIVEIS.

    ``user_vpd`` tem rank 0 no projeto da Auditoria. O envelope da negativa tem
    de bater byte a byte com o de um id que nunca existiu — status, ``code`` e
    ``message`` — senao o 404 nao cumpre a funcao anti-enumeracao.
    """
    fora_do_escopo = client_outsider.get(
        f"/api/projetos/{seed_data['project_id']}/detalhe"
    )
    inexistente = client_outsider.get("/api/projetos/999999/detalhe")

    _assert_fail_envelope(fora_do_escopo, status=404, code="not_found")
    _assert_fail_envelope(inexistente, status=404, code="not_found")
    assert fora_do_escopo.get_json() == inexistente.get_json()


def test_projeto_invisivel_bate_com_o_404_do_roteador(client_outsider, seed_data):
    """O 404 de autorizacao e o mesmo do roteador (rota inexistente sob /api/)."""
    fora_do_escopo = client_outsider.get(
        f"/api/projetos/{seed_data['project_id']}/detalhe"
    )
    rota_inexistente = client_outsider.get("/api/rota-que-nao-existe-12345")

    assert fora_do_escopo.get_json() == rota_inexistente.get_json()


def test_tarefa_invisivel_e_tarefa_inexistente_tem_envelope_identico(
    client_outsider, seed_data
):
    """Mesma indistinguibilidade no dominio de TAREFAS (helper task_access_verdict)."""
    fora_do_escopo = client_outsider.get(f"/api/tarefas/{seed_data['task_id']}/detalhe")
    inexistente = client_outsider.get("/api/tarefas/999999/detalhe")

    _assert_fail_envelope(fora_do_escopo, status=404, code="not_found")
    assert fora_do_escopo.get_json() == inexistente.get_json()


def test_jinja_route_404_stays_html_not_json(client_user):
    """Fora de ``/api/``, o 404 permanece HTML (telas Jinja preservadas)."""
    response = client_user.get("/pagina-jinja-inexistente-98765")

    assert response.status_code == 404
    assert not response.is_json
    assert response.get_json(silent=True) is None
