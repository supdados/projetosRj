"""Contrato do parcial templates/partials/app_topnav.html.

Esse parcial é incluído em todas as páginas logadas e contém a navegação
global (home, projetos, tarefas, pendentes, calendário) + seletor global
de órgão + dropdown de conta + busca global. JS de navegação/notificações
depende dos hooks data-* listados abaixo; um refactor que os renomeie
quebraria silenciosamente a top-nav.

Apos a migração SPA + corte de /profile/change-password (Passo 1b), nenhuma
rota viva renderiza o topnav autenticado; estes contratos só morrem no Passo 6
da faxina, então o parcial é renderizado direto (base.html + context
processors reais) via render_authenticated_shell.
"""

from pathlib import Path

from tests.routes.render_shell import render_authenticated_shell


def _topnav_html(app, seed_data):
    return render_authenticated_shell(app, seed_data, user_key="admin_id")


def test_topnav_has_brand_and_nav_icons(app, seed_data):
    html = _topnav_html(app, seed_data)

    # Marca + navegação principal.
    assert 'class="navbar navbar-expand-lg app-topnav"' in html
    assert 'class="navbar-brand app-brand"' in html
    assert "app-brand-logo" in html
    assert 'class="app-nav-icons"' in html

    # Hooks de navegação para preservar o filtro global de órgão.
    assert html.count("data-area-nav") >= 5
    assert html.count("data-orgao-nav") >= 5


def test_topnav_renders_primary_nav_icons(app, seed_data):
    html = _topnav_html(app, seed_data)
    # Ícones FontAwesome dos links principais devem estar todos presentes
    # (estado 'active' não é testado aqui: nenhuma página de auth ativa um
    # item da nav principal).
    assert "fas fa-home" in html
    assert "fas fa-folder-open" in html
    assert "fas fa-tasks" in html
    assert "fas fa-exclamation-triangle" in html
    assert "fas fa-calendar-alt" in html


def test_topnav_renders_global_search_form_hooks(app, seed_data):
    html = _topnav_html(app, seed_data)

    assert 'id="appGlobalSearchForm"' in html
    assert 'id="appGlobalSearchInput"' in html
    assert 'id="appGlobalSearchDropdown"' in html
    assert "data-global-search" in html
    assert "data-search-url" in html
    assert 'name="q"' in html


def test_topnav_global_search_preserves_selected_orgao(app, seed_data):
    html = render_authenticated_shell(
        app,
        seed_data,
        user_key="admin_id",
        path=f"/dashboard?orgao={seed_data['vpd_orgao_id']}",
    )

    assert 'name="orgao"' in html
    assert f'value="{seed_data["vpd_orgao_id"]}"' in html


def test_topnav_renders_notifications_dropdown_hooks(app, seed_data):
    html = _topnav_html(app, seed_data)

    assert 'id="appNotificationsDesktop"' in html
    assert 'id="appNotificationsBadge"' in html
    assert 'id="appNotificationsList"' in html
    assert 'id="appNotificationsState"' in html
    assert 'id="appNotificationsUnreadCount"' in html


def test_topnav_admin_dropdown_has_admin_entries(app, seed_data):
    html = _topnav_html(app, seed_data)

    assert "Gerenciar Usuários" in html
    assert "Hierarquia de Órgãos" in html
    assert "Modelos de Etapas" in html
    assert "Meu Perfil (Admin)" in html
    assert "Alterar Senha" in html


def test_topnav_user_dropdown_hides_admin_entries(app, seed_data):
    html = render_authenticated_shell(app, seed_data, user_key="user_id")

    assert "Gerenciar Usuários" not in html
    assert "Hierarquia de Órgãos" not in html
    assert "Modelos de Etapas" not in html
    # Usuário comum vê apenas "Gerenciar Conta" + Sair.
    assert "Gerenciar Conta" in html


def test_topnav_theme_toggle_markup_is_preserved_in_source():
    """Markup do toggle segue no FONTE do parcial para reativação.

    O toggle não renderiza hoje ({% if False %} até o modo escuro ser
    finalizado), então o contrato do theme.js (input #appThemeToggle checkbox
    role="switch" + wrapper .app-theme-switch) é verificado no template.
    """
    topnav_path = (
        Path(__file__).resolve().parents[2]
        / "templates"
        / "partials"
        / "app_topnav.html"
    )
    topnav_source = topnav_path.read_text(encoding="utf-8")

    assert 'id="appThemeToggle"' in topnav_source
    assert 'class="app-theme-switch' in topnav_source
    assert 'aria-label="Alternar tema claro/escuro"' in topnav_source


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


def test_topnav_orgao_dropdown_is_rendered(app, seed_data):
    html = _topnav_html(app, seed_data)
    # O topo global voltou a renderizar o seletor de órgão.
    assert (
        "data-area-select" in html
        or "app-area-single-link" in html
        or "app-area-empty" in html
    )
    assert "data-orgao-select" in html
    assert "Todos os órgãos" in html


def test_topnav_logout_link_present(app, seed_data):
    html = _topnav_html(app, seed_data)
    assert 'href="/logout"' in html
    assert "app-dropdown-item-danger" in html
