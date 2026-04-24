import json

from models import Project, StageTemplate, StageTemplateItem, db
from tests._orgao_helpers import ensure_orgao


def _client_for_user(app, user_id):
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = user_id
    return client


def test_api_resultados_and_indicadores_return_canonical_payload(client_user):
    resultados_response = client_user.get("/api/resultados/1")
    assert resultados_response.status_code == 200
    resultados_payload = resultados_response.get_json()
    assert isinstance(resultados_payload, list)
    assert resultados_payload
    assert resultados_payload[0] == {
        "id": 1,
        "descricao": "Gestao e governanca da politica de governo digital estadual qualificadas",
    }

    indicadores_response = client_user.get("/api/indicadores/1")
    assert indicadores_response.status_code == 200
    indicadores_payload = indicadores_response.get_json()
    assert isinstance(indicadores_payload, list)
    assert indicadores_payload == [
        {
            "id": 1,
            "descricao": "N de orgaos/entidades com pontos focais de governo digital indicados",
        }
    ]


def test_api_goal_endpoints_return_404_with_error_payload_for_invalid_ids(client_user):
    resultados_response = client_user.get("/api/resultados/999")
    assert resultados_response.status_code == 404
    assert resultados_response.get_json() == {"error": "Objetivo não encontrado"}

    indicadores_response = client_user.get("/api/indicadores/999")
    assert indicadores_response.status_code == 404
    assert indicadores_response.get_json() == {
        "error": "Resultado esperado não encontrado"
    }


def test_api_templates_and_template_stages_return_sorted_shape(
    app, client_user, seed_data
):
    with app.app_context():
        template = StageTemplate(name="AAA Template", description="Template adicional")
        db.session.add(template)
        db.session.flush()
        db.session.add_all(
            [
                StageTemplateItem(
                    name="Descoberta", duration_days=5, order=0, templateId=template.id
                ),
                StageTemplateItem(
                    name="Entrega", duration_days=2, order=1, templateId=template.id
                ),
            ]
        )
        db.session.commit()
        template_id = template.id

    templates_response = client_user.get("/api/templates")
    assert templates_response.status_code == 200
    templates_payload = templates_response.get_json()
    assert templates_payload[0] == {
        "id": template_id,
        "name": "AAA Template",
        "stage_count": 2,
        "total_duration_days": 7,
    }
    assert any(
        item
        == {
            "id": seed_data["template_id"],
            "name": "Template Base",
            "stage_count": 2,
            "total_duration_days": 5,
        }
        for item in templates_payload
    )

    stages_response = client_user.get(f"/api/templates/{template_id}")
    assert stages_response.status_code == 200
    assert stages_response.get_json() == [
        {"name": "Descoberta", "order": 0, "duration": 5},
        {"name": "Entrega", "order": 1, "duration": 2},
    ]


def test_api_user_projects_respects_user_scope_and_admin_sees_all(app, seed_data):
    with app.app_context():
        db.session.add(
            Project(
                titulo="Projeto Adicional Auditoria",
                orgao_id=ensure_orgao("Auditoria").id,
                orgao="Orgao A",
                prioridade="media",
                status="Vigente",
                objetivo_id=1,
                resultado_esperado_id=1,
            )
        )
        db.session.commit()

    user_client = _client_for_user(app, seed_data["user_id"])
    admin_client = _client_for_user(app, seed_data["admin_id"])

    user_response = user_client.get("/api/projetos_usuario")
    assert user_response.status_code == 200
    user_payload = user_response.get_json()
    user_titles = [item["titulo"] for item in user_payload]
    assert "Projeto Auditoria" in user_titles
    assert "Projeto Adicional Auditoria" in user_titles
    assert "Projeto VPD" not in user_titles
    assert all(item["orgao_sigla"] == "Auditoria" for item in user_payload)

    admin_response = admin_client.get("/api/projetos_usuario")
    assert admin_response.status_code == 200
    admin_payload = admin_response.get_json()
    admin_titles = [item["titulo"] for item in admin_payload]
    assert "Projeto Auditoria" in admin_titles
    assert "Projeto VPD" in admin_titles


def test_api_chatbot_token_returns_upstream_token_payload(app, seed_data, monkeypatch):
    app.config.update(
        CHATBOT_ENABLED=True,
        CHATBOT_BASE_URL="https://chatbot.proderj.rj.gov.br",
        CHATBOT_PORTAL_API_KEY="portal-secret",
        CHATBOT_TIMEOUT_SECONDS=7,
        SERVER_NAME="projetos.proderj.rj.gov.br",
    )

    captured = {}

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"token": "jwt-teste", "expires_in": 900}).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["api_key"] = request.headers.get("X-portal-api-key")
        captured["portal_origin"] = request.headers.get("X-portal-origin")
        return _FakeResponse()

    monkeypatch.setattr("routes.api.urlopen", fake_urlopen)

    user_client = _client_for_user(app, seed_data["user_id"])
    response = user_client.get(
        "/api/chatbot-token",
        environ_overrides={
            "wsgi.url_scheme": "https",
        },
    )

    assert response.status_code == 200
    assert response.get_json() == {"token": "jwt-teste", "expires_in": 900}
    assert captured == {
        "url": "https://chatbot.proderj.rj.gov.br/api/token",
        "timeout": 7,
        "api_key": "portal-secret",
        "portal_origin": "https://projetos.proderj.rj.gov.br",
    }


def test_api_chatbot_token_returns_404_when_feature_is_disabled(client_user):
    response = client_user.get("/api/chatbot-token")

    assert response.status_code == 404
    assert response.get_json() == {"error": "Chatbot desabilitado"}
