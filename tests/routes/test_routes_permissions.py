import pytest

from tests.routes.route_cases import ADMIN_REQUIRED_CASES, LOGIN_REQUIRED_CASES


class _DummyIdContext(dict):
    """Contexto de format() que devolve um id ficticio para chaves ausentes.

    A negacao a anonimo/nao-admin nao depende do id concreto na URL (o guard
    rejeita ANTES de qualquer lookup), entao um placeholder e suficiente quando
    o ``seed_data`` nao expoe a chave (ex.: ``anexo_id`` vive em outra lane de
    seed). Mantem o teste de permissao auto-suficiente sem tocar o seed.
    """

    def __missing__(self, key):
        return "1"


def _format_payload(value, context):
    if isinstance(value, str):
        return value.format_map(context)
    if isinstance(value, list):
        return [_format_payload(item, context) for item in value]
    if isinstance(value, tuple):
        return tuple(_format_payload(item, context) for item in value)
    if isinstance(value, dict):
        return {key: _format_payload(item, context) for key, item in value.items()}
    return value


def _resolve_request(case, seed_data):
    context = _DummyIdContext(seed_data)
    path = case["path"].format_map(context)
    request_kwargs = {}
    for key in ("data", "json", "headers", "query_string"):
        if key in case:
            request_kwargs[key] = _format_payload(case[key], context)
    return path, request_kwargs


def _is_api_rule(case):
    """Rotas /api/* falam o contrato JSON canonico (401/403)."""
    return case["rule"].startswith("/api/")


def _assert_canonical_unauthenticated(response):
    """Fixa o envelope canonico 401 JSON (sem Location), detectando 404/500/2xx."""
    assert response.status_code == 401
    assert response.is_json
    body = response.get_json()
    assert body["ok"] is False
    assert body["error"]["code"] == "unauthenticated"
    assert not (response.headers.get("Location") or "")


@pytest.mark.parametrize(
    "case", LOGIN_REQUIRED_CASES, ids=[case["id"] for case in LOGIN_REQUIRED_CASES]
)
def test_login_required_routes_deny_anonymous(case, client, seed_data):
    """Toda rota login-required NEGA acesso a anonimo.

    Intencao preservada da forma antiga ("rota protegida nega anonimo"). Por
    contrato:
      - Jinja: 302 + "/login" no Location.
      - /api/* canonico (SPA): 401 JSON {ok:false, error.code:"unauthenticated"}.
      - /api/* legado (area ainda Jinja, ex.: /api/templates, /api/chatbot-token):
        302 + "/login" (guard ``login_required`` legado, ver legacy.py).
      - /api/* mutativo: 401 (harness CSRF OFF) ou 400 (CSRF ON em prod).
    Nunca 2xx/404/500 — a negacao tem que ser efetiva e a rota tem que existir.
    """
    path, request_kwargs = _resolve_request(case, seed_data)
    response = client.open(
        path, method=case["method"], follow_redirects=False, **request_kwargs
    )
    location = response.headers.get("Location") or ""

    # (A) Jinja: redireciona para /login.
    if not _is_api_rule(case):
        assert response.status_code == 302
        assert "/login" in location
        return

    # Cobertura explicita: download binario de anexo a anonimo devolve 401 JSON
    # canonico (envelope), NUNCA o octet-stream.
    if case["id"] == "api_anexo_download_get":
        _assert_canonical_unauthenticated(response)
        assert "application/octet-stream" not in (response.content_type or "")
        return

    # (C) /api/* mutativo (POST/PUT/PATCH/DELETE): 401 no harness (CSRF OFF),
    # 400 em producao (CSRF ON roda antes do guard) ou 302/login no legado.
    # Nunca 2xx.
    if case["method"] != "GET":
        if response.status_code == 302:
            assert "/login" in location  # POST legado sob guard Jinja
            return
        assert response.status_code in (400, 401)
        assert not (200 <= response.status_code < 300)
        assert not location
        return

    # (B) /api/* GET: contrato canonico 401 JSON; rotas legadas ainda nao
    # migradas usam o guard Jinja (302 -> /login). Ambos negam de fato; nenhum
    # serve 2xx/404/500.
    if response.status_code == 302:
        assert "/login" in location
        return
    _assert_canonical_unauthenticated(response)


@pytest.mark.parametrize(
    "case", ADMIN_REQUIRED_CASES, ids=[case["id"] for case in ADMIN_REQUIRED_CASES]
)
def test_admin_routes_deny_non_admin(case, client_user, seed_data):
    """Toda rota admin NEGA acesso a usuario autenticado nao-admin.

    Intencao preservada (302 + /dashboard no Jinja); para /api/* o novo contrato
    e 403 JSON com code "forbidden".
    """
    path, request_kwargs = _resolve_request(case, seed_data)
    response = client_user.open(
        path, method=case["method"], follow_redirects=False, **request_kwargs
    )

    # (B) /api/*: 403 JSON com envelope canonico.
    if _is_api_rule(case):
        assert response.status_code == 403
        assert response.is_json
        body = response.get_json()
        assert body["ok"] is False
        assert body["error"]["code"] == "forbidden"
        return

    # (A) Jinja: redireciona para /dashboard.
    assert response.status_code == 302
    assert "/dashboard" in (response.headers.get("Location") or "")


AREA_PROTECTED_CASES = [
    {
        "id": "outsider_project_detail",
        "method": "GET",
        "path": "/project/{project_id}",
        "expected_status": 302,
        "redirect_contains": "/projects",
    },
    {
        "id": "outsider_project_edit_data",
        "method": "GET",
        "path": "/project/{project_id}/edit_data",
        "expected_status": 403,
    },
    {
        "id": "outsider_project_update_inline",
        "method": "POST",
        "path": "/project/{project_id}/update_inline",
        "json": {"titulo": "Nao pode editar"},
        "expected_status": 403,
    },
    {
        "id": "outsider_project_delete",
        "method": "POST",
        "path": "/project/{project_id}/delete",
        "expected_status": 302,
        "redirect_contains": "/projects",
    },
    {
        "id": "outsider_etapas_reorder",
        "method": "POST",
        "path": "/project/{project_id}/etapas/reordenar",
        "json": {"etapa_ids": ["{etapa_id}"]},
        "expected_status": 403,
    },
    {
        "id": "outsider_etapa_toggle_iniciada",
        "method": "POST",
        "path": "/etapa/{etapa_id}/toggle_iniciada",
        "expected_status": 403,
    },
    {
        "id": "outsider_etapa_update_field",
        "method": "POST",
        "path": "/etapa/{etapa_id}/update_field",
        "json": {"field": "descricao", "value": "Bloqueado"},
        "expected_status": 403,
    },
    {
        "id": "outsider_project_cascade_update",
        "method": "POST",
        "path": "/project/{project_id}/cascade_update",
        "json": {"etapa_id": "{etapa_id}", "days_diff": 1},
        "expected_status": 403,
    },
    {
        "id": "outsider_task_detail",
        "method": "GET",
        "path": "/tarefas/{task_id}",
        "expected_status": 302,
        "redirect_contains": "/tarefas",
    },
    {
        "id": "outsider_task_edit",
        "method": "POST",
        "path": "/tarefas/{task_id}/edit",
        "data": {"titulo": "Bloqueado", "project_id": "{project_id}"},
        "expected_status": 403,
    },
    {
        "id": "outsider_task_update_status",
        "method": "POST",
        "path": "/tarefas/{task_id}/update_status",
        "json": {"status": "em_andamento"},
        "expected_status": 403,
    },
    {
        "id": "outsider_task_update_prioridade",
        "method": "POST",
        "path": "/tarefas/{task_id}/update_prioridade",
        "json": {"prioridade": "alta"},
        "expected_status": 403,
    },
    {
        "id": "outsider_task_update_tipo",
        "method": "POST",
        "path": "/tarefas/{task_id}/update_tipo",
        "json": {"tipo_pedido": "bug"},
        "expected_status": 403,
    },
    {
        "id": "outsider_task_global_add",
        "method": "POST",
        "path": "/tarefas/add",
        "headers": {"X-Requested-With": "XMLHttpRequest"},
        "data": {"project": "{project_id}", "descricao": "Item bloqueado"},
        "expected_status": 403,
    },
    {
        "id": "outsider_task_suggestions",
        "method": "GET",
        "path": "/tarefas/{task_id}/sugestoes-responsavel",
        "expected_status": 403,
    },
    {
        "id": "outsider_task_comment_add_canonical",
        "method": "POST",
        "path": "/tarefas/{task_id}/comentarios/add",
        "headers": {"X-Requested-With": "XMLHttpRequest"},
        "data": {"content": "Comentario sem permissao"},
        "expected_status": 403,
    },
    {
        "id": "outsider_task_anexos_list_canonical",
        "method": "GET",
        "path": "/tarefas/{task_id}/anexos",
        "expected_status": 403,
    },
    {
        "id": "outsider_task_anexo_add_canonical",
        "method": "POST",
        "path": "/tarefas/{task_id}/anexos/add",
        "expected_status": 403,
    },
    {
        "id": "outsider_task_hub_suggestions",
        "method": "GET",
        "path": "/tarefas/sugestoes-responsavel",
        "query_string": {"project": "{project_id}"},
        "expected_status": 403,
    },
    {
        "id": "outsider_task_finalize",
        "method": "POST",
        "path": "/tarefas/{task_id}/finalizar",
        "expected_status": 302,
        "redirect_contains": "/tarefas",
    },
    {
        "id": "outsider_task_reactivate",
        "method": "POST",
        "path": "/tarefas/{task_id}/reativar",
        "expected_status": 403,
    },
    {
        "id": "outsider_task_desarquivar",
        "method": "POST",
        "path": "/tarefas/{task_id}/desarquivar",
        "expected_status": 403,
    },
]


@pytest.mark.parametrize(
    "case", AREA_PROTECTED_CASES, ids=[case["id"] for case in AREA_PROTECTED_CASES]
)
def test_area_protected_routes_block_outsider(case, client_outsider, seed_data):
    path, request_kwargs = _resolve_request(case, seed_data)
    response = client_outsider.open(
        path, method=case["method"], follow_redirects=False, **request_kwargs
    )

    assert response.status_code == case["expected_status"]
    if response.status_code == 302 and case.get("redirect_contains"):
        assert case["redirect_contains"] in (response.headers.get("Location") or "")
