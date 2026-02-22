import re
from pathlib import Path


def _read(path):
    return path.read_text(encoding='utf-8')


def test_project_detail_has_no_light_inline_editor_styles():
    file_path = Path(__file__).resolve().parents[2] / 'templates' / 'project_detail.html'
    content = _read(file_path)

    forbidden_patterns = [
        r'input\.style\.cssText',
        r'backgroundColor\s*=\s*[\'"]rgba\(255,\s*255,\s*255',
        r'borderColor\s*=\s*[\'"]rgba\(255,\s*255,\s*255',
        r'style\s*=\s*[\'"][^\'"]*color\s*:\s*#',
        r'style\s*=\s*[\'"][^\'"]*background-color\s*:\s*#',
    ]

    for pattern in forbidden_patterns:
        assert re.search(pattern, content, re.IGNORECASE) is None, (
            f'Padrão inline proibido encontrado em project_detail.html: {pattern}'
        )


def test_project_add_form_js_has_no_inline_color_hints():
    file_path = Path(__file__).resolve().parents[2] / 'templates' / 'project_add_form_js.html'
    content = _read(file_path)

    forbidden_patterns = [
        r'<span\s+style=',
        r'style\s*=\s*[\'"][^\'"]*color\s*:\s*#',
    ]

    for pattern in forbidden_patterns:
        assert re.search(pattern, content, re.IGNORECASE) is None, (
            f'Padrão inline proibido encontrado em project_add_form_js.html: {pattern}'
        )
