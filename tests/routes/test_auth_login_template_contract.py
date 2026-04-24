"""Contrato do template de /login.

Verifica os hooks DOM esperados pelo JS inline (lpLocalForm, lpToggleBtn,
lpPwToggle) e a conditional do botão "Entrar com GOV.BR" em função de
`govbr_login_enabled`. Um refactor silencioso que renomeasse esses IDs ou
removesse o botão gov.br quebraria a experiência de login sem pytest se não
fosse por este contrato.
"""


def _fetch_login(client):
    response = client.get("/login")
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_login_page_renders_local_form_hooks(client):
    html = _fetch_login(client)

    # Form alvo do JS inline e endpoint para POST.
    assert 'id="lpLocalForm"' in html
    assert 'action="/login"' in html
    assert 'method="POST"' in html

    # Campos obrigatórios preservam os "name" que o backend consome.
    assert 'name="username"' in html
    assert 'name="password"' in html
    assert 'name="next"' in html

    # Toggles e ícones usados pelo <script> no final do template.
    assert 'id="lp-username"' in html
    assert 'id="lp-password"' in html
    assert 'id="lpPwToggle"' in html
    assert 'id="lpPwIcon"' in html


def test_login_page_defaults_to_hidden_govbr_integration(client):
    """Sem gov.br configurado, não renderiza botão nem toggle entre modos."""
    html = _fetch_login(client)
    assert "lp-govbr-btn" not in html
    assert 'id="lpToggleBtn"' not in html
    assert 'id="lpDivider"' not in html
    # E o form deve aparecer já visível (sem a classe hidden).
    assert "lp-local-form--hidden" not in html


def test_login_page_shows_govbr_button_when_enabled(app, client):
    app.config.update(
        GOVBR_OIDC_ENABLED=True,
        GOVBR_OIDC_BASE_URL="https://idp.example.com",
        GOVBR_OIDC_REALM="my-realm",
        GOVBR_OIDC_CLIENT_ID="my-client",
        GOVBR_OIDC_CLIENT_SECRET="secret",
        GOVBR_OIDC_REDIRECT_URI="https://app.example.com/callback",
    )

    html = _fetch_login(client)
    assert "lp-govbr-btn" in html
    assert 'href="/login/govbr"' in html
    assert 'id="lpToggleBtn"' in html
    assert 'id="lpDivider"' in html
    # Form inicia oculto quando há gov.br e o usuário ainda não expandiu.
    assert "lp-local-form--hidden" in html


def test_login_page_shows_form_after_invalid_credentials(client):
    response = client.post(
        "/login", data={"username": "inexistente", "password": "errado"}
    )
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    # Credenciais inválidas marcam show_local_form=True — form precisa ficar
    # visível e o flash de erro aparece.
    assert 'id="lpLocalForm"' in html
    assert "Credenciais inválidas" in html


def test_login_page_stats_placeholders_are_present(client):
    """Os números das 4 métricas são renderizados mesmo quando são zero."""
    html = _fetch_login(client)
    assert "lp-stat-number" in html
    assert "Projetos Vigentes" in html
    assert "Concluídos" in html
    assert "Tarefas" in html
    assert "Áreas" in html


def test_login_page_preserves_next_param_in_hidden_input(client):
    response = client.get("/login?next=/dashboard")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'value="/dashboard"' in html
