from pathlib import Path


def _read(path):
    return path.read_text(encoding='utf-8')


def test_project_detail_ajax_flash_stack_is_limited_to_three():
    main_js_path = Path(__file__).resolve().parents[2] / 'static' / 'js' / 'pages' / 'project-detail' / '01-main.js'
    content = _read(main_js_path)

    assert 'const MAX_NOTIFICATIONS = 3;' in content
    assert 'const MAX_NOTIFICATIONS = 5;' not in content


def test_project_detail_ajax_flash_uses_compact_app_flash_markup():
    template_path = Path(__file__).resolve().parents[2] / 'templates' / 'project_detail.html'
    main_js_path = Path(__file__).resolve().parents[2] / 'static' / 'js' / 'pages' / 'project-detail' / '01-main.js'
    pages_root = Path(__file__).resolve().parents[2] / 'static' / 'pages'
    css_bundle_paths = [
        pages_root / 'project-detail.css',
        *sorted((pages_root / 'project-detail').glob('*.css')),
    ]

    template_content = _read(template_path)
    main_js_content = _read(main_js_path)
    css_content = '\n'.join(_read(path) for path in css_bundle_paths)

    assert "js/pages/project-detail/01-main.js" in template_content
    assert 'app-flash-alert app-flash-alert-compact' in main_js_content
    assert 'app-flash-text' in main_js_content
    assert 'app-flash-icon' not in main_js_content
    assert '.app-flash-alert-compact' in css_content
