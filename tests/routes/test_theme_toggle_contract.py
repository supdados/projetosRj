from pathlib import Path


def _read(path):
    return path.read_text(encoding='utf-8')


def test_theme_toggle_is_present_on_authenticated_pages(client_user):
    response = client_user.get('/dashboard')

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'id="appThemeToggle"' in html
    assert 'theme-dark.css' in html
    assert 'projetosrj.theme' in html


def test_theme_toggle_is_not_rendered_on_login_page(client):
    response = client.get('/login')

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'id="appThemeToggle"' not in html
    assert 'projetosrj.theme' in html
    assert 'data-skeleton-active="login"' in html
    assert 'data-skeleton-template="login"' in html


def test_login_route_is_mapped_to_login_skeleton_in_app_shell():
    app_shell_path = Path(__file__).resolve().parents[2] / 'static' / 'js' / 'app-shell.js'
    app_shell_content = _read(app_shell_path)

    assert "pathname === '/' || pathname === '/login'" in app_shell_content
    assert "return 'login';" in app_shell_content


def test_theme_toggle_is_after_notifications_and_account(client_user):
    response = client_user.get('/dashboard')

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    notifications_index = html.index('id="appNotificationsDesktop"')
    theme_toggle_index = html.index('id="appThemeToggle"')
    account_index = html.index('id="appAccountMenuDesktop"')

    assert notifications_index < account_index < theme_toggle_index
