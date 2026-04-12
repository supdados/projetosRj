import re
from pathlib import Path


def _read(path):
    return path.read_text(encoding='utf-8')


def _selector_body(content, selector):
    match = re.search(rf'{re.escape(selector)}\s*\{{(?P<body>.*?)\n\}}', content, re.DOTALL)
    assert match is not None, f'Seletor não encontrado: {selector}'
    return match.group('body')


def test_caderno_cards_keep_visual_shell_aligned_with_grid_slot():
    file_path = Path(__file__).resolve().parents[2] / 'static' / 'css' / 'caderno' / 'caderno.css'
    content = _read(file_path)

    widget_body = _selector_body(content, '.caderno-widget')
    note_body = _selector_body(content, '.caderno-nota-card')
    ref_body = _selector_body(content, '.caderno-ref-card')
    null_body = _selector_body(content, '.caderno-ref-null')

    assert 'min-height: 100%;' in widget_body
    assert 'height: 100%;' in note_body
    assert 'min-height: 100%;' in ref_body
    assert 'min-height: 100%;' in null_body


def test_caderno_drag_measurement_avoids_extra_buffer_rows():
    file_path = Path(__file__).resolve().parents[2] / 'static' / 'js' / 'pages' / 'caderno.js'
    content = _read(file_path)

    assert 'measureRoot ? measureRoot.scrollHeight : 0' in content
    assert 'measureRoot ? measureRoot.getBoundingClientRect().height : blockEl.getBoundingClientRect().height' in content
    assert 'scrollHeight) + 8' not in content


def test_caderno_sheet_starts_with_compact_viewport_bound_height():
    css_path = Path(__file__).resolve().parents[2] / 'static' / 'css' / 'caderno' / 'caderno.css'
    css_content = _read(css_path)
    canvas_body = _selector_body(css_content, '.caderno-canvas-wrap')

    js_path = Path(__file__).resolve().parents[2] / 'static' / 'js' / 'pages' / 'caderno.js'
    js_content = _read(js_path)

    assert 'clamp(420px, 54vh, 560px);' in canvas_body
    assert 'function getBaseCanvasMinHeight() {' in js_content
    assert 'DESKTOP_BASE_CANVAS_MIN_HEIGHT' in js_content
    assert 'MOBILE_BASE_CANVAS_MIN_HEIGHT' in js_content
    assert 'BASE_CANVAS_MIN_HEIGHT = 760' not in js_content
