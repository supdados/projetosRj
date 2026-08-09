import pytest
import time

from models import User, UserOrgao, db
from routes.api.envelope import NOT_FOUND_MESSAGE
from services.authorization import PAPEL_LEITOR
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


def _assert_fail_envelope(response, *, status, code):
    """Envelope canonico da negativa, nas DUAS superficies (S5/F4-2).

    ``/api/*`` fala ``{"ok": false, "error": {"code", "message"}}``; as rotas
    legadas falam ``{"success": false, "message"}``. O 404 anti-enumeracao
    (F4-2b) exige a MESMA mensagem do id inexistente nos dois formatos — por
    isso ela e comparada literalmente aqui.
    """
    assert response.status_code == status
    assert response.is_json, f"esperava JSON, veio {response.content_type!r}"
    body = response.get_json()
    if "ok" in body:
        assert body["ok"] is False
        assert body["error"]["code"] == code
        message = body["error"]["message"]
    else:
        assert body["success"] is False
        message = body["message"]
    assert isinstance(message, str) and message
    if code == "not_found":
        assert message == NOT_FOUND_MESSAGE


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


# Contrato S5/F4-2: quem tem rank 0 no projeto recebe 404 `not_found` com o
# MESMO corpo do id inexistente (anti-enumeracao). Os 302 que sobraram sao rotas
# hibridas fora do modo ajax — negam por flash+redirect, nunca por 403.
AREA_PROTECTED_CASES = [
    # /project/<id> virou redirect cego (302 -> /projetos/<id>); o controle de
    # acesso ao detalhe vive agora na API da SPA (/api/projetos/<id>), coberto
    # em test_api_*_contract. Por isso não há mais caso "outsider" para ele aqui.
    # edit_data/update_inline/delete (Jinja) foram cortados na migração; o
    # controle de acesso de edição/exclusão vive na API (/api/projetos/<id>*),
    # coberto em test_api_*_contract.
    {
        "id": "outsider_etapas_reorder",
        "method": "POST",
        "path": "/project/{project_id}/etapas/reordenar",
        "json": {"etapa_ids": ["{etapa_id}"]},
        "expected_status": 404,
    },
    {
        "id": "outsider_etapa_toggle_iniciada",
        "method": "POST",
        "path": "/etapa/{etapa_id}/toggle_iniciada",
        "expected_status": 404,
    },
    {
        "id": "outsider_etapa_update_field",
        "method": "POST",
        "path": "/etapa/{etapa_id}/update_field",
        "json": {"field": "descricao", "value": "Bloqueado"},
        "expected_status": 404,
    },
    {
        "id": "outsider_project_cascade_update",
        "method": "POST",
        "path": "/project/{project_id}/cascade_update",
        "json": {"etapa_id": "{etapa_id}", "days_diff": 1},
        "expected_status": 404,
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
        "expected_status": 404,
    },
    {
        "id": "outsider_task_update_status",
        "method": "POST",
        "path": "/tarefas/{task_id}/update_status",
        "json": {"status": "em_andamento"},
        "expected_status": 404,
    },
    {
        "id": "outsider_task_update_prioridade",
        "method": "POST",
        "path": "/tarefas/{task_id}/update_prioridade",
        "json": {"prioridade": "alta"},
        "expected_status": 404,
    },
    {
        "id": "outsider_task_update_tipo",
        "method": "POST",
        "path": "/tarefas/{task_id}/update_tipo",
        "json": {"tipo_pedido": "bug"},
        "expected_status": 404,
    },
    {
        "id": "outsider_task_global_add",
        "method": "POST",
        "path": "/tarefas/add",
        "headers": {"X-Requested-With": "XMLHttpRequest"},
        "data": {"project": "{project_id}", "descricao": "Item bloqueado"},
        "expected_status": 404,
    },
    {
        "id": "outsider_task_suggestions",
        "method": "GET",
        "path": "/tarefas/{task_id}/sugestoes-responsavel",
        "expected_status": 404,
    },
    {
        "id": "outsider_task_comment_add_canonical",
        "method": "POST",
        "path": "/tarefas/{task_id}/comentarios/add",
        "headers": {"X-Requested-With": "XMLHttpRequest"},
        "data": {"content": "Comentario sem permissao"},
        "expected_status": 404,
    },
    {
        "id": "outsider_task_anexos_list_canonical",
        "method": "GET",
        "path": "/tarefas/{task_id}/anexos",
        "expected_status": 404,
    },
    {
        "id": "outsider_task_anexo_add_canonical",
        "method": "POST",
        "path": "/tarefas/{task_id}/anexos/add",
        "expected_status": 404,
    },
    {
        "id": "outsider_task_hub_suggestions",
        "method": "GET",
        "path": "/tarefas/sugestoes-responsavel",
        "query_string": {"project": "{project_id}"},
        "expected_status": 404,
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
        "expected_status": 404,
    },
    {
        "id": "outsider_task_desarquivar",
        "method": "POST",
        "path": "/tarefas/{task_id}/desarquivar",
        "expected_status": 404,
    },
]


@pytest.mark.parametrize(
    "case", AREA_PROTECTED_CASES, ids=[case["id"] for case in AREA_PROTECTED_CASES]
)
def test_area_protected_routes_block_outsider(case, client_outsider, seed_data):
    """Rank 0 no projeto: 404 anti-enumeracao (ou redirect nas rotas hibridas)."""
    path, request_kwargs = _resolve_request(case, seed_data)
    response = client_outsider.open(
        path, method=case["method"], follow_redirects=False, **request_kwargs
    )

    assert response.status_code == case["expected_status"]
    assert response.status_code != 403, "rank 0 nunca recebe 403 (S5/F4-2)"
    if response.status_code == 302 and case.get("redirect_contains"):
        assert case["redirect_contains"] in (response.headers.get("Location") or "")
        return
    if response.status_code == 404:
        _assert_fail_envelope(response, status=404, code="not_found")


# Par obrigatorio do contrato (§6.1, F4-4): a MESMA rota que devolve 404 para
# rank 0 devolve 403 para quem ja ve o projeto mas nao alcanca o rank da acao.
LEITOR_FORBIDDEN_CASES = [
    {
        "id": "leitor_etapas_reorder",
        "method": "POST",
        "path": "/project/{project_id}/etapas/reordenar",
        "json": {"etapa_ids": ["{etapa_id}"]},
    },
    {
        "id": "leitor_etapa_toggle_iniciada",
        "method": "POST",
        "path": "/etapa/{etapa_id}/toggle_iniciada",
    },
    {
        "id": "leitor_etapa_update_field",
        "method": "POST",
        "path": "/etapa/{etapa_id}/update_field",
        "json": {"field": "descricao", "value": "Bloqueado"},
    },
    {
        "id": "leitor_project_cascade_update",
        "method": "POST",
        "path": "/project/{project_id}/cascade_update",
        "json": {"etapa_id": "{etapa_id}", "days_diff": 1},
    },
    {
        "id": "leitor_task_edit",
        "method": "POST",
        "path": "/tarefas/{task_id}/edit",
        "data": {"titulo": "Bloqueado", "project_id": "{project_id}"},
    },
    {
        "id": "leitor_task_update_status",
        "method": "POST",
        "path": "/tarefas/{task_id}/update_status",
        "json": {"status": "em_andamento"},
    },
    {
        "id": "leitor_task_update_prioridade",
        "method": "POST",
        "path": "/tarefas/{task_id}/update_prioridade",
        "json": {"prioridade": "alta"},
    },
    {
        "id": "leitor_task_update_tipo",
        "method": "POST",
        "path": "/tarefas/{task_id}/update_tipo",
        "json": {"tipo_pedido": "bug"},
    },
    {
        "id": "leitor_task_global_add",
        "method": "POST",
        "path": "/tarefas/add",
        "headers": {"X-Requested-With": "XMLHttpRequest"},
        "data": {"project": "{project_id}", "descricao": "Item bloqueado"},
    },
    {
        "id": "leitor_task_anexo_add",
        "method": "POST",
        "path": "/tarefas/{task_id}/anexos/add",
    },
    {
        "id": "leitor_task_desarquivar",
        "method": "POST",
        "path": "/tarefas/{task_id}/desarquivar",
    },
]


@pytest.fixture
def client_leitor(app, seed_data):
    """Usuario com vinculo LEITOR no orgao dono do projeto semeado.

    Ve o projeto (logo nunca recebe 404 por autorizacao) mas nao alcanca o rank
    editor exigido pelas escritas — e o outro lado do par 404/403 da S5.
    """
    with app.app_context():
        leitor = User(
            username="leitor_contrato", name="Leitor Contrato", orgao="Orgao Teste"
        )
        leitor.set_password("senha123")
        db.session.add(leitor)
        db.session.flush()
        db.session.add(
            UserOrgao(
                user_id=leitor.id,
                orgao_id=seed_data["auditoria_orgao_id"],
                papel=PAPEL_LEITOR,
            )
        )
        db.session.commit()
        leitor_id = leitor.id

    http_client = app.test_client()
    with http_client.session_transaction() as session:
        session["user_id"] = leitor_id
        session["login_at"] = time.time()
    return http_client


@pytest.mark.parametrize(
    "case",
    LEITOR_FORBIDDEN_CASES,
    ids=[case["id"] for case in LEITOR_FORBIDDEN_CASES],
)
def test_area_protected_routes_forbid_leitor(case, client_leitor, seed_data):
    """Rank >= leitor com acao acima do rank: 403 `forbidden`, nunca 404."""
    path, request_kwargs = _resolve_request(case, seed_data)
    response = client_leitor.open(
        path, method=case["method"], follow_redirects=False, **request_kwargs
    )

    _assert_fail_envelope(response, status=403, code="forbidden")
