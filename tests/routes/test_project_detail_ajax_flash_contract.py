from pathlib import Path


def _read(path):
    return path.read_text(encoding='utf-8')


def test_project_detail_ajax_flash_stack_is_limited_to_three():
    file_path = Path(__file__).resolve().parents[2] / 'templates' / 'project_detail.html'
    content = _read(file_path)

    assert 'const MAX_NOTIFICATIONS = 3;' in content
    assert 'const MAX_NOTIFICATIONS = 5;' not in content


def test_project_detail_ajax_flash_uses_compact_app_flash_markup():
    template_path = Path(__file__).resolve().parents[2] / 'templates' / 'project_detail.html'
    css_path = Path(__file__).resolve().parents[2] / 'static' / 'pages' / 'project-detail.css'

    template_content = _read(template_path)
    css_content = _read(css_path)

    assert 'app-flash-alert app-flash-alert-compact' in template_content
    assert 'app-flash-icon' in template_content
    assert '.app-flash-alert-compact' in css_content
