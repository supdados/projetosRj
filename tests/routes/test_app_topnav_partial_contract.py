"""Contrato do parcial templates/partials/app_topnav.html.

Esse parcial é incluído em todas as páginas logadas e contém a navegação
global (home, projetos, tarefas, pendentes, calendário) + dropdown de conta
+ busca global. JS de áreas/notificações depende dos hooks data-* listados
abaixo; um refactor que os renomeie quebraria silenciosamente a top-nav.

Usamos a rota /dashboard para garantir que o parcial é renderizado no
contexto real (com endpoint e usuário autenticado).
"""

from pathlib import Path


def _topnav_html(client_admin):
    response = client_admin.get('/dashboard')
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_topnav_has_brand_and_nav_icons(client_admin):
    html = _topnav_html(client_admin)

    # Marca + navegação principal.
    assert 'class="navbar navbar-expand-lg app-topnav"' in html
    assert 'class="navbar-brand app-brand"' in html
    assert 'app-brand-logo' in html
    assert 'class="app-nav-icons"' in html

    # Hooks data-area-nav que o JS inspeciona para injetar a área ativa.
    assert html.count('data-area-nav') >= 5


def test_topnav_marks_dashboard_active_when_on_home(client_admin):
    html = _topnav_html(client_admin)
    # Classe 'active' presente no link do dashboard (endpoint = main.dashboard).
    assert 'app-nav-link app-nav-icon-btn active' in html
    # Fontes awesome esperados dos links principais.
    assert 'fas fa-home' in html
    assert 'fas fa-folder-open' in html
    assert 'fas fa-tasks' in html
    assert 'fas fa-exclamation-triangle' in html
    assert 'fas fa-calendar-alt' in html


def test_topnav_marks_projects_link_active_on_list_projects(client_admin):
    response = client_admin.get('/projects')
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    # O link de "Todos os projetos" deve ter classe 'active'.
    assert 'title="Todos os projetos"' in html
    assert 'aria-label="Todos os projetos"' in html


def test_topnav_renders_global_search_form_hooks(client_admin):
    html = _topnav_html(client_admin)

    assert 'id="appGlobalSearchForm"' in html
    assert 'id="appGlobalSearchInput"' in html
    assert 'id="appGlobalSearchDropdown"' in html
    assert 'data-global-search' in html
    assert 'data-search-url' in html
    assert 'name="q"' in html


def test_topnav_renders_notifications_dropdown_hooks(client_admin):
    html = _topnav_html(client_admin)

    assert 'id="appNotificationsDesktop"' in html
    assert 'id="appNotificationsBadge"' in html
    assert 'id="appNotificationsList"' in html
    assert 'id="appNotificationsState"' in html
    assert 'id="appNotificationsUnreadCount"' in html


def test_topnav_admin_dropdown_has_admin_entries(client_admin):
    html = _topnav_html(client_admin)

    assert 'Gerenciar Usuários' in html
    assert 'Gerenciar Áreas' in html
    assert 'Hierarquia de Órgãos' in html
    assert 'Modelos de Etapas' in html
    assert 'Meu Perfil (Admin)' in html
    assert 'Alterar Senha' in html


def test_topnav_user_dropdown_hides_admin_entries(client_user):
    response = client_user.get('/dashboard')
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'Gerenciar Usuários' not in html
    assert 'Gerenciar Áreas' not in html
    assert 'Hierarquia de Órgãos' not in html
    assert 'Modelos de Etapas' not in html
    # Usuário comum vê apenas "Gerenciar Conta" + Sair.
    assert 'Gerenciar Conta' in html


def test_topnav_theme_toggle_button_is_rendered(client_admin):
    html = _topnav_html(client_admin)
    assert 'id="appThemeToggle"' in html
    assert 'id="appThemeToggleIcon"' in html
    assert 'aria-label="Alternar tema"' in html


def test_topnav_icon_buttons_define_pressed_state_contract():
    css_path = Path(__file__).resolve().parents[2] / 'static' / 'css' / 'legacy' / '00-foundation.css'
    css = css_path.read_text(encoding='utf-8')

    assert '--bs-btn-active-color: #ffffff;' in css
    assert '--bs-btn-active-bg: rgba(255, 255, 255, 0.18);' in css
    assert '.app-nav-icon-btn:active,' in css
    assert '.app-nav-icon-btn.show {' in css


def test_topnav_area_dropdown_includes_user_areas(client_admin):
    html = _topnav_html(client_admin)
    # Admin vê todas as áreas via dropdown; confere que a UI renderiza o widget.
    assert 'data-area-select' in html or 'app-area-single-link' in html or 'app-area-empty' in html


def test_topnav_logout_link_present(client_admin):
    html = _topnav_html(client_admin)
    assert 'href="/logout"' in html
    assert 'app-dropdown-item-danger' in html
