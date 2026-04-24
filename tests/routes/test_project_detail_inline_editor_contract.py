from pathlib import Path


def _read(path):
    return path.read_text(encoding="utf-8")


def test_project_detail_inline_js_contains_searchable_abep_combobox():
    bootstrap_path = (
        Path(__file__).resolve().parents[2]
        / "static"
        / "js"
        / "pages"
        / "projects"
        / "detail"
        / "01-main.js"
    )
    editor_path = (
        Path(__file__).resolve().parents[2]
        / "static"
        / "js"
        / "pages"
        / "projects"
        / "detail"
        / "09-project-inline-editor.js"
    )
    bootstrap_content = _read(bootstrap_path)
    editor_content = _read(editor_path)

    required_fragments = [
        "createAbepIndicatorCombobox",
        "project-detail-abep-combobox",
        "Busque por número ou título...",
    ]

    for fragment in required_fragments:
        assert fragment in bootstrap_content

    assert "field === 'abep_indicator'" in editor_content


def test_project_detail_inline_editor_supports_multiline_responsavel():
    js_file = (
        Path(__file__).resolve().parents[2]
        / "static"
        / "js"
        / "pages"
        / "projects"
        / "detail"
        / "07-stage-dnd.js"
    )
    css_file = (
        Path(__file__).resolve().parents[2]
        / "static"
        / "css"
        / "projects"
        / "detail"
        / "03-stages-and-interactions.css"
    )

    js_content = _read(js_file)
    css_content = _read(css_file)

    assert "editable-field-textarea-responsavel" in js_content
    assert ".editable-field-textarea.editable-field-textarea-responsavel" in css_content
    assert "lockInlineEditorToDisplayWidth" in js_content
    assert "if (field === 'responsavel')" in js_content
    assert "min-width: 170px;" in css_content
    assert "box-sizing: border-box;" in css_content


def test_project_detail_inline_stage_composer_avoids_smooth_scroll_hitbox_bug():
    js_file = (
        Path(__file__).resolve().parents[2]
        / "static"
        / "js"
        / "pages"
        / "projects"
        / "detail"
        / "01-main.js"
    )
    js_content = _read(js_file)

    assert "function ensureInlineComposerVisible()" in js_content
    assert "behavior: 'auto'" in js_content
    assert "scrollIntoView({ behavior: 'smooth', block: 'end' });" not in js_content


def test_project_detail_inline_stage_composer_syncs_next_stage_preview_id():
    js_file = (
        Path(__file__).resolve().parents[2]
        / "static"
        / "js"
        / "pages"
        / "projects"
        / "detail"
        / "01-main.js"
    )
    js_content = _read(js_file)

    assert "document.getElementById('etapaInlineOrderPreview')" in js_content
    assert "function syncInlineOrderPreview()" in js_content
    assert "formatEtapaOrder(getEtapaRows().length + 1)" in js_content


def test_task_detail_dark_css_styles_responsavel_picker_more():
    file_path = (
        Path(__file__).resolve().parents[2]
        / "static"
        / "css"
        / "tasks"
        / "detail"
        / "dark.css"
    )
    content = _read(file_path)

    assert ".task-detail-v2 .responsavel-picker-more" in content
    assert ".responsavel-picker-option-checkbox {" in content
    assert ".responsavel-picker-option-checkbox:checked::after {" in content
