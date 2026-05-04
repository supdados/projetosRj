from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "static/js/modules/kanban/drawer-anexos.js"
)


def _module_source():
    return MODULE_PATH.read_text(encoding="utf-8")


def _function_body(source, function_name):
    start_marker = f"function {function_name}("
    start = source.index(start_marker)
    brace_start = source.index("{", start)
    depth = 0
    for index in range(brace_start, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[brace_start + 1:index]
    raise AssertionError(f"Function body not found for {function_name}")


def test_drawer_attachment_renderer_uses_dom_apis_for_untrusted_metadata():
    source = _module_source()
    body = _function_body(source, "renderDrawerAnexoItem")

    assert "el.innerHTML" not in body
    assert "document.createElement('a')" in body
    assert "link.setAttribute('data-filename', anexo.filename || '')" in body
    assert "link.setAttribute('data-content-type', anexo.content_type || '')" in body
    assert "nameSpan.textContent = anexo.filename || ''" in body

    unsafe_patterns = [
        'data-filename="\' + escapeAnexoHtml(anexo.filename)',
        'data-content-type="\' + escapeAnexoHtml(anexo.content_type',
        '<span class="task-item-drawer-anexo-name">\' + escapeAnexoHtml(anexo.filename)',
    ]
    for pattern in unsafe_patterns:
        assert pattern not in source
