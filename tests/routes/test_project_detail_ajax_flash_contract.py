from pathlib import Path


def _read(path):
    return path.read_text(encoding='utf-8')


def test_project_detail_ajax_flash_stack_is_limited_to_three_in_app_shell():
    app_shell_js_path = Path(__file__).resolve().parents[2] / 'static' / 'js' / 'app-shell.js'
    content = _read(app_shell_js_path)

    assert 'while (stack.children.length >= 3)' in content
    assert 'while (stack.children.length >= 5)' not in content


def test_project_detail_ajax_flash_uses_global_app_flash_system():
    detail_template_path = Path(__file__).resolve().parents[2] / 'templates' / 'projects' / 'detail.html'
    base_template_path = Path(__file__).resolve().parents[2] / 'templates' / 'base.html'
    detail_main_js_path = Path(__file__).resolve().parents[2] / 'static' / 'js' / 'pages' / 'projects' / 'detail' / '01-main.js'
    app_shell_js_path = Path(__file__).resolve().parents[2] / 'static' / 'js' / 'app-shell.js'
    flash_css_path = Path(__file__).resolve().parents[2] / 'static' / 'css' / 'partials' / 'flash.css'

    detail_template_content = _read(detail_template_path)
    base_template_content = _read(base_template_path)
    detail_main_js_content = _read(detail_main_js_path)
    app_shell_js_content = _read(app_shell_js_path)
    flash_css_content = _read(flash_css_path)

    assert "js/pages/projects/detail/01-main.js" in detail_template_content
    assert "css/partials/flash.css" in base_template_content
    assert "js/app-shell.js" in base_template_content
    assert "typeof window.showFlash === 'function'" in detail_main_js_content
    assert "window.showFlash(message, type || 'info');" in detail_main_js_content
    assert "stack.className = 'app-flash-stack';" in app_shell_js_content
    assert "el.className = 'app-flash-alert alert-' + t;" in app_shell_js_content
    assert '.app-flash-stack' in flash_css_content
    assert '.app-flash-alert' in flash_css_content
    assert '.app-flash-alert-compact' not in flash_css_content
