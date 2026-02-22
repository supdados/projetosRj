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


def test_theme_toggle_is_between_notifications_and_account(client_user):
    response = client_user.get('/dashboard')

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    notifications_index = html.index('id="appNotificationsDesktop"')
    theme_toggle_index = html.index('id="appThemeToggle"')
    account_index = html.index('id="appAccountMenuDesktop"')

    assert notifications_index < theme_toggle_index < account_index
