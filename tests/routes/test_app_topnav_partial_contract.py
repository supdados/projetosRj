"""Contrato do parcial templates/partials/app_topnav.html.

Esse parcial é incluído em todas as páginas logadas e contém a navegação
global (home, projetos, tarefas, pendentes, calendário) + seletor global
de órgão + dropdown de conta + busca global. JS de navegação/notificações
depende dos hooks data-* listados abaixo; um refactor que os renomeie
quebraria silenciosamente a top-nav.

Apos a migração SPA, as únicas páginas Jinja que renderizam o topnav são as de
auth. Usamos /profile/change-password (autenticada, extends base.html) para
garantir que o parcial é renderizado no contexto real (usuário autenticado).
"""

from pathlib import Path


def _topnav_html(client_admin):
    response = client_admin.get("/profile/change-password")
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_topnav_has_brand_and_nav_icons(client_admin):
    html = _topnav_html(client_admin)

    # Marca + navegação principal.
    assert 'class="navbar navbar-expand-lg app-topnav"' in html
    assert 'class="navbar-brand app-brand"' in html
    assert "app-brand-logo" in html
    assert 'class="app-nav-icons"' in html

    # Hooks de navegação para preservar o filtro global de órgão.
    assert html.count("data-area-nav") >= 5
    assert html.count("data-orgao-nav") >= 5


def test_topnav_renders_primary_nav_icons(client_admin):
    html = _topnav_html(client_admin)
    # Ícones FontAwesome dos links principais devem estar todos presentes
    # (estado 'active' não é testado aqui: nenhuma página de auth ativa um
    # item da nav principal).
    assert "fas fa-home" in html
    assert "fas fa-folder-open" in html
    assert "fas fa-tasks" in html
    assert "fas fa-exclamation-triangle" in html
    assert "fas fa-calendar-alt" in html


def test_topnav_renders_global_search_form_hooks(client_admin):
    html = _topnav_html(client_admin)

    assert 'id="appGlobalSearchForm"' in html
    assert 'id="appGlobalSearchInput"' in html
    assert 'id="appGlobalSearchDropdown"' in html
    assert "data-global-search" in html
    assert "data-search-url" in html
    assert 'name="q"' in html


def test_topnav_global_search_preserves_selected_orgao(client_admin, seed_data):
    response = client_admin.get(
        "/profile/change-password",
        query_string={"orgao": str(seed_data["vpd_orgao_id"])},
    )
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'name="orgao"' in html
    assert f'value="{seed_data["vpd_orgao_id"]}"' in html


def test_topnav_renders_notifications_dropdown_hooks(client_admin):
    html = _topnav_html(client_admin)

    assert 'id="appNotificationsDesktop"' in html
    assert 'id="appNotificationsBadge"' in html
    assert 'id="appNotificationsList"' in html
    assert 'id="appNotificationsState"' in html
    assert 'id="appNotificationsUnreadCount"' in html


def test_topnav_admin_dropdown_has_admin_entries(client_admin):
    html = _topnav_html(client_admin)

    assert "Gerenciar Usuários" in html
    assert "Hierarquia de Órgãos" in html
    assert "Modelos de Etapas" in html
    assert "Meu Perfil (Admin)" in html
    assert "Alterar Senha" in html


def test_topnav_user_dropdown_hides_admin_entries(client_user):
    response = client_user.get("/profile/change-password")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert "Gerenciar Usuários" not in html
    assert "Hierarquia de Órgãos" not in html
    assert "Modelos de Etapas" not in html
    # Usuário comum vê apenas "Gerenciar Conta" + Sair.
    assert "Gerenciar Conta" in html


def test_topnav_theme_toggle_button_is_rendered(client_admin):
    html = _topnav_html(client_admin)
    # O toggle de tema é um switch: theme.js depende do input #appThemeToggle
    # (checkbox role="switch") e do wrapper .app-theme-switch para o título.
    assert 'id="appThemeToggle"' in html
    assert 'class="app-theme-switch' in html
    assert 'aria-label="Alternar tema claro/escuro"' in html


def test_topnav_icon_buttons_define_pressed_state_contract():
    css_path = (
        Path(__file__).resolve().parents[2]
        / "static"
        / "css"
        / "legacy"
        / "00-foundation.css"
    )
    css = css_path.read_text(encoding="utf-8")

    assert "--bs-btn-active-color: #ffffff;" in css
    assert "--bs-btn-active-bg: rgba(255, 255, 255, 0.18);" in css
    assert ".app-nav-icon-btn:active," in css
    assert ".app-nav-icon-btn.show {" in css


def test_topnav_orgao_dropdown_is_rendered(client_admin):
    html = _topnav_html(client_admin)
    # O topo global voltou a renderizar o seletor de órgão.
    assert (
        "data-area-select" in html
        or "app-area-single-link" in html
        or "app-area-empty" in html
    )
    assert "data-orgao-select" in html
    assert "Todos os órgãos" in html


def test_topnav_logout_link_present(client_admin):
    html = _topnav_html(client_admin)
    assert 'href="/logout"' in html
    assert "app-dropdown-item-danger" in html
