"""Regressão para o loop de redirect com `?area=<inválido>` (achado #2 do ultrareview).

`_read_task_filter_values` aceita tanto `?orgao=` quanto `?area=` (alias legado).
Quando o id é inválido, a view chama `redirect_to_current_route_without_orgao()`.
Antes do fix, esse helper removia só `orgao` e deixava `area` na URL — o cliente
seguia o redirect, o sanitizer rejeitava de novo e o loop se fechava.

O teste confirma que um `?area=<inválido>` é limpo no redirect (sem loop) e que
uma requisição posterior sem o parâmetro responde 200.
"""


def _extract_location(response):
    assert response.status_code == 302, response.status_code
    return response.headers["Location"]


def test_tarefas_redirect_drops_invalid_area_param(client_user):
    response = client_user.get("/tarefas?area=999999")
    location = _extract_location(response)
    assert "area=" not in location
    assert "orgao=" not in location


def test_tarefas_redirect_drops_invalid_orgao_param(client_user):
    response = client_user.get("/tarefas?orgao=999999")
    location = _extract_location(response)
    assert "area=" not in location
    assert "orgao=" not in location


def test_tarefas_redirect_preserves_other_query_params(client_user):
    response = client_user.get("/tarefas?area=999999&status=em_andamento")
    location = _extract_location(response)
    assert "area=" not in location
    assert "orgao=" not in location
    assert "status=em_andamento" in location


def test_tarefas_follow_redirect_does_not_loop(client_user):
    # follow_redirects resolve até o 200 final. Se o loop existisse, o cliente
    # de teste do Flask estouraria com "too many redirects".
    response = client_user.get("/tarefas?area=999999", follow_redirects=True)
    assert response.status_code == 200
