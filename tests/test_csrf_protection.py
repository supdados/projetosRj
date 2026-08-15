"""Testes de proteção CSRF global nos endpoints POST da API da SPA.

Contexto do bug original (era no JS do kanban legado, hoje cortado):
  Flask-WTF 1.2.2 NÃO isenta requests com Content-Type: application/json — CSRF é
  exigido para todo POST. Endpoints chamados sem X-CSRFToken eram bloqueados com 400.
  A propriedade continua valendo para a superfície /api/* consumida pela SPA
  (nenhum blueprint de API é csrf.exempt; só o webhook de calendário é).

O que esses testes verificam:
  1. POST sem token (form-urlencoded) → rejeitado com 400.
  2. POST com Content-Type: application/json mas sem token → ainda 400 (JSON não isenta CSRF).
  3. POST com X-CSRFToken válido no header → CSRF superado (fix correto).

Por que o conftest padrão não cobre:
  O fixture `app` do conftest define WTF_CSRF_ENABLED=False. Esses testes usam um
  fixture próprio com CSRF ativo, que é o comportamento real de produção.
"""

import pytest
from sqlalchemy.pool import NullPool

from app import create_app
from catalogs.objectives import sync_goal_catalog_to_db
from models import db

# ── Fixture com CSRF ativo ────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def csrf_app(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("csrf") / "csrf_test.sqlite"
    flask_app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "csrf-test-secret-key",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "SQLALCHEMY_ENGINE_OPTIONS": {"poolclass": NullPool},
            "SKIP_STARTUP_DB_INIT": True,
            "WTF_CSRF_ENABLED": True,
        }
    )
    with flask_app.app_context():
        db.drop_all()
        db.create_all()
        sync_goal_catalog_to_db(commit=True)
    yield flask_app
    with flask_app.app_context():
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


@pytest.fixture
def csrf_client(csrf_app):
    return csrf_app.test_client()


def _csrf_token_for_client(csrf_app, csrf_client) -> str:
    """Gera token CSRF válido e injeta a sessão correspondente no cliente de teste.

    Flask-WTF armazena um valor base na sessão e retorna um HMAC assinado.
    Para validar, a sessão do cliente deve conter esse valor base.
    """
    from flask_wtf.csrf import generate_csrf

    token = None
    session_data = {}

    with csrf_app.test_request_context("/"):
        from flask import session

        token = generate_csrf()
        session_data = dict(session)

    with csrf_client.session_transaction() as sess:
        sess.update(session_data)

    return token


# ── Helpers ───────────────────────────────────────────────────────────────────


def _is_csrf_error(response) -> bool:
    """True se a resposta é rejeição de CSRF (400 com mensagem do Flask-WTF)."""
    if response.status_code != 400:
        return False
    body = response.get_data(as_text=True)
    return "CSRF" in body or "csrf" in body


# ── Endpoints com o padrão que tinha o bug ────────────────────────────────────
#
# POSTs de exclusão que o front pode disparar sem corpo JSON (sem content-type).

_ENDPOINTS_SEM_JSON = [
    "/api/tarefas/1/excluir",
    "/api/comentarios/1/delete",
    "/api/anexos/1/delete",
]

# Endpoints que sempre recebem Content-Type: application/json (referência)
_ENDPOINTS_SEMPRE_JSON = [
    "/api/tarefas/board/reordenar",
    "/api/tarefas/1/status",
    "/api/tarefas/1/campos",
    "/api/tarefas/1/finalizar",
    "/api/tarefas/1/desarquivar",
    "/api/tarefas/1/reativar",
    "/api/tarefas/arquivar-finalizadas",
    "/api/tarefas",
]


# ── 1. Rejeição: POST sem JSON e sem token deve falhar com CSRF 400 ───────────


@pytest.mark.parametrize("url", _ENDPOINTS_SEM_JSON)
def test_post_sem_json_e_sem_csrf_retorna_400(csrf_client, url):
    """POST sem Content-Type application/json e sem token CSRF deve ser rejeitado."""
    resp = csrf_client.post(url, headers={"Accept": "application/json"})
    assert _is_csrf_error(resp), (
        f"Esperava erro CSRF (400), mas obteve {resp.status_code} em {url}. "
        f"Corpo: {resp.get_data(as_text=True)[:200]}"
    )


# ── 2. JSON não isenta CSRF: POST application/json sem token ainda deve falhar ──
#
# Flask-WTF 1.2.2 NÃO isenta Content-Type: application/json. Todo POST sem
# X-CSRFToken válido é rejeitado com 400, independentemente do content-type.


@pytest.mark.parametrize("url", _ENDPOINTS_SEM_JSON + _ENDPOINTS_SEMPRE_JSON)
def test_post_com_content_type_json_sem_token_retorna_400(csrf_client, url):
    """POST application/json sem X-CSRFToken deve ser rejeitado com 400.

    Flask-WTF 1.2.2 não concede isenção automática para Content-Type: application/json.
    Todo POST sem token válido falha — o fix correto é enviar X-CSRFToken no header,
    não apenas mudar o content-type.
    """
    resp = csrf_client.post(
        url,
        content_type="application/json",
        data="{}",
    )
    assert _is_csrf_error(resp), (
        f"Esperava erro CSRF (400) em {url}, mas obteve {resp.status_code}. "
        f"Flask-WTF 1.2.2 não isenta JSON — token ausente deve ser rejeitado. "
        f"Corpo: {resp.get_data(as_text=True)[:200]}"
    )


# ── 3. Bypass via header: X-CSRFToken válido passa a verificação ──────────────


@pytest.mark.parametrize("url", _ENDPOINTS_SEM_JSON)
def test_post_com_csrf_header_valido_passa_csrf(csrf_app, csrf_client, url):
    """POST com X-CSRFToken válido não deve ser bloqueado — simula o fetch da SPA.

    Gera token via Flask-WTF e injeta a sessão correspondente no cliente, replicando
    o que o browser faz após ler a meta[name=csrf-token] do shell da SPA.
    """
    token = _csrf_token_for_client(csrf_app, csrf_client)

    resp = csrf_client.post(
        url,
        headers={
            "Accept": "application/json",
            "X-CSRFToken": token,
        },
    )
    assert not _is_csrf_error(resp), (
        f"X-CSRFToken válido foi rejeitado em {url}. "
        f"O fetch da SPA injeta esse header — deveria passar do CSRF. "
        f"Corpo: {resp.get_data(as_text=True)[:200]}"
    )
