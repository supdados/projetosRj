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


def test_project_header_inline_editors_keep_chip_dimensions():
    root = Path(__file__).resolve().parents[2]
    editor_content = _read(
        root
        / "static"
        / "js"
        / "pages"
        / "projects"
        / "detail"
        / "09-project-inline-editor.js"
    )
    header_css = _read(
        root
        / "static"
        / "css"
        / "projects"
        / "detail"
        / "01-shell-and-header.css"
    )
    dark_css = _read(
        root
        / "static"
        / "css"
        / "projects"
        / "detail"
        / "04-dark-mode.css"
    )

    assert "function prepareHeaderChipEditor(input, sourceEl, field)" in editor_content
    assert "const HEADER_CHIP_EDIT_LABELS" in editor_content
    assert "status: 'Status'" in editor_content
    assert "prioridade: 'Prioridade'" in editor_content
    assert "delivery_type: 'Tipo'" in editor_content
    assert "sourceEl.closest('.project-header-chips')" in editor_content
    assert "project-header-chip-edit-wrap" in editor_content
    assert "project-header-chip-edit-label" in editor_content
    assert "input.classList.add('project-header-chip-editor'" in editor_content
    assert "wrapper.style.setProperty('--ph-editor-width'" in editor_content
    assert "wrapper.style.setProperty('--ph-editor-height'" in editor_content
    assert "const replacement = prepareHeaderChipEditor(input, el, field) || input;" in editor_content

    assert "function resizeProjectHeaderTextEditor(input)" in editor_content
    assert "function measureProjectHeaderTextWidth(input)" in editor_content
    assert "function prepareProjectHeaderTextEditor(input, sourceEl, field)" in editor_content
    assert "input.classList.contains('project-header-text-editor--short-description')" in editor_content
    assert "input.classList.contains('project-header-text-editor--short_description')" in editor_content
    assert "const maxWidth = Number(input.dataset.visualMaxWidth || input.dataset.visualWidth || '0') || 0;" in editor_content
    assert "const measuredWidth = measureProjectHeaderTextWidth(input);" in editor_content
    assert "const minWidth = isDescription ? 72 : 180;" in editor_content
    assert "input.style.setProperty('--ph-text-editor-width', `${nextWidth}px`);" in editor_content
    assert "input.style.setProperty('--ph-text-editor-max-width', maxWidth ? `${maxWidth}px` : '100%');" in editor_content
    assert "const verticalPadding = parseFloat(style.paddingTop || '0') + parseFloat(style.paddingBottom || '0');" in editor_content
    assert "const lineHeight = parseFloat(style.lineHeight || '0') || (parseFloat(style.fontSize || '0') * 1.2) || 18;" in editor_content
    assert "const contentHeight = input.scrollHeight - verticalPadding;" in editor_content
    assert "input.style.height = `${Math.max(contentHeight, lineHeight)}px`;" in editor_content
    assert "context.measureText(text).width" in editor_content
    assert "const sourceWidth = Math.ceil(sourceEl.getBoundingClientRect().width || 0);" in editor_content
    assert "const sourceContainer = sourceEl.closest('.project-header-main-content');" in editor_content
    assert "const sourceStyle = window.getComputedStyle(sourceEl);" in editor_content
    assert "replace(/[^a-z0-9]+/gi, '-').toLowerCase()" in editor_content
    assert "input.dataset.visualWidth = String(sourceWidth);" in editor_content
    assert "input.dataset.visualMaxWidth = String(maxWidth);" in editor_content
    assert "input.style.setProperty('--ph-text-editor-font-family', sourceStyle.fontFamily);" in editor_content
    assert "input.style.setProperty('--ph-text-editor-font-size', sourceStyle.fontSize);" in editor_content
    assert "input.style.setProperty('--ph-text-editor-font-weight', sourceStyle.fontWeight);" in editor_content
    assert "input.style.setProperty('--ph-text-editor-line-height', sourceStyle.lineHeight);" in editor_content
    assert "input.style.setProperty('--ph-text-editor-letter-spacing', sourceStyle.letterSpacing);" in editor_content
    assert "input.style.height = 'auto';" in editor_content
    assert "input.addEventListener('input', function ()" in editor_content
    assert "project-header-text-editor" in editor_content
    assert "input = document.createElement('textarea');\n                    input.rows = 1;\n                    input.className = 'form-control form-control-sm project-inline-input project-inline-input-title';" in editor_content
    assert "input.className = 'form-control form-control-sm project-inline-input project-inline-input-description';\n                    input.rows = 1;" in editor_content
    assert "project-additional-link-editor" in editor_content
    assert "project-observacao-editor" in editor_content
    assert "function resizeHeaderChipSelect(select)" in editor_content
    assert "input.addEventListener('change', function ()" in editor_content

    assert ".project-header-chips .project-header-chip-editor.form-select" in header_css
    assert ".project-header-chip-edit-label" in header_css
    assert "margin-bottom: 0.12rem !important;" in header_css
    assert ".project-header .project-header-text-editor.form-control" in header_css
    assert "box-sizing: content-box;" in header_css
    assert "width: var(--ph-text-editor-width, 100%);" in header_css
    assert "max-width: var(--ph-text-editor-max-width, 100%);" in header_css
    assert "min-width: 0;" in header_css
    assert "font-family: var(--ph-text-editor-font-family, inherit);" in header_css
    assert "font-size: var(--ph-text-editor-font-size, inherit);" in header_css
    assert "font-weight: var(--ph-text-editor-font-weight, inherit);" in header_css
    assert "line-height: var(--ph-text-editor-line-height, inherit);" in header_css
    assert "letter-spacing: var(--ph-text-editor-letter-spacing, 0);" in header_css
    assert ".project-header .project-header-text-editor--short_description.form-control" in header_css
    assert "margin: 0 0 0.35rem;" in header_css
    assert "margin-bottom: 0.18rem;" in header_css
    assert "padding: 0.14rem 0.32rem;" in header_css
    assert "padding: 0.12rem 0.28rem;" in header_css
    assert "min-height: 0 !important;" in header_css
    assert "-webkit-line-clamp: 5;" in header_css
    assert ".project-header .project-header-description" in header_css
    assert "-webkit-line-clamp: 15;" in header_css
    assert "width: var(--ph-editor-width);" in header_css
    assert "height: var(--ph-editor-height, 1.74rem);" in header_css
    assert "min-width: var(--ph-editor-width);" in header_css
    assert "max-width: var(--ph-editor-width);" in header_css
    assert "font-family: var(--ds-font-family-heading);" in header_css
    assert "font-size: var(--ds-font-size-xl);" in header_css
    assert "font-weight: var(--ds-font-weight-bold);" in header_css
    assert "input.form-control[data-field]:not(.project-header-text-editor):not(.project-header-chip-editor)" in header_css
    assert "select.form-select[data-field]:not(.project-header-chip-editor)" in header_css
    assert "textarea.form-control[data-field]:not(.project-header-text-editor)" in header_css
    assert ".project-detail-abep-combobox[data-field] .project-detail-abep-input.form-control" in header_css
    assert "font-family: var(--ds-font-family-body);" in header_css
    assert "font-size: var(--ds-font-size-sm);" in header_css
    assert "font-weight: var(--ds-font-weight-regular);" in header_css
    assert ".additional-info-box .project-additional-link-editor.form-control" in header_css
    assert "display: inline-block;" in header_css
    assert "width: min(60%, 38rem);" in header_css
    assert "max-width: calc(100% - 8rem);" in header_css
    assert "margin-left: 0.35rem;" in header_css
    assert ".additional-info-box .project-observacao-editor.form-control" in header_css
    assert "width: 70%;" in header_css
    assert "border: 1px solid #e5e7eb;" in header_css
    assert "html:not([data-theme=\"dark\"]) input.form-control[data-field]:not(.project-header-text-editor):not(.project-header-chip-editor)" in header_css
    assert "html:not([data-theme=\"dark\"]) select.form-select[data-field]:not(.project-header-chip-editor)" in header_css
    assert "html:not([data-theme=\"dark\"]) textarea.form-control[data-field]:not(.project-header-text-editor)" in header_css
    assert "html:not([data-theme=\"dark\"]) .project-detail-abep-combobox[data-field] .project-detail-abep-input.form-control" in header_css
    assert "html:not([data-theme=\"dark\"]) .additional-info-box .project-additional-link-editor.form-control" in header_css
    assert "html:not([data-theme=\"dark\"]) .additional-info-box .project-observacao-editor.form-control" in header_css
    assert "border: 1px solid #e5e7eb !important;" in header_css
    assert "border-color: #d6dbe2 !important;" in header_css
    assert "box-shadow: 0 0 0 0.14rem rgba(31, 41, 55, 0.06) !important;" in header_css

    assert (
        "html[data-theme=\"dark\"] body.is-authenticated "
        ".project-header-chips .project-header-chip-editor.form-select"
    ) in dark_css
    assert (
        "html[data-theme=\"dark\"] body.is-authenticated "
        ".project-header .project-header-chip-edit-wrap,\n"
        "html[data-theme=\"dark\"] body.is-authenticated "
        ".project-header .project-header-chip-edit-label"
    ) in dark_css
    assert (
        "html[data-theme=\"dark\"] body.is-authenticated "
        ".project-header .project-header-text-editor.form-control"
    ) in dark_css
    assert "background-color: transparent !important;" in dark_css
    assert "box-shadow: none !important;" in dark_css


def test_project_header_description_line_clamp_survives_later_css_import():
    css_file = (
        Path(__file__).resolve().parents[2]
        / "static"
        / "css"
        / "projects"
        / "detail"
        / "03-stages-and-interactions.css"
    )
    content = _read(css_file)

    assert ".project-header-description" in content
    assert "-webkit-line-clamp: 15;" in content
    assert "white-space: pre-line;" in content
    assert "overflow-wrap: anywhere;" in content


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
