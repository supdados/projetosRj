import re
from pathlib import Path


def _read(path):
    return path.read_text(encoding='utf-8')


def _selector_body(content, selector):
    match = re.search(rf'(^|\n){re.escape(selector)}\s*\{{(?P<body>.*?)\n\}}', content, re.DOTALL)
    assert match is not None, f'Seletor não encontrado: {selector}'
    return match.group('body')


def test_caderno_cards_keep_visual_shell_aligned_with_grid_slot():
    file_path = Path(__file__).resolve().parents[2] / 'static' / 'css' / 'caderno' / 'caderno.css'
    content = _read(file_path)

    block_body = _selector_body(content, '.caderno-block')
    widget_body = _selector_body(content, '.caderno-widget')
    note_body = _selector_body(content, '.caderno-nota-card')
    ref_body = _selector_body(content, '.caderno-ref-card')
    null_body = _selector_body(content, '.caderno-ref-null')

    assert 'outline: none;' in block_body
    assert 'min-height: 100%;' in widget_body
    assert 'height: 100%;' in note_body
    assert 'min-height: 100%;' in ref_body
    assert 'min-height: 100%;' in null_body
    assert 'padding-right: 3.85rem;' not in content
    assert 'padding-bottom: 3.7rem;' not in content


def test_caderno_drag_measurement_avoids_extra_buffer_rows():
    file_path = Path(__file__).resolve().parents[2] / 'static' / 'js' / 'pages' / 'caderno.js'
    content = _read(file_path)

    assert "function shouldAutoMeasureBlock(block) {" in content
    assert "return !!block && block.block_type === 'text';" in content
    assert "const measureRoot = blockEl.querySelector('.caderno-text-editor');" in content
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


def test_caderno_slash_menu_anchors_to_caret_and_hides_empty_toolbar():
    css_path = Path(__file__).resolve().parents[2] / 'static' / 'css' / 'caderno' / 'caderno.css'
    css_content = _read(css_path)

    js_path = Path(__file__).resolve().parents[2] / 'static' / 'js' / 'pages' / 'caderno.js'
    js_content = _read(js_path)

    assert 'getEditorCaretRect' in js_content
    assert 'positionSlashMenu(editorEl);' in js_content
    assert 'window.scrollY' not in js_content
    assert 'window.scrollX' not in js_content
    assert 'syncSlashMenuState()' in js_content
    assert '.caderno-block.is-active:not(.is-editor-empty):not(.is-slash-trigger):not(.is-slash-menu-open) .caderno-block-resize-handle' in css_content
    assert '.slash-menu[data-side="top"]' in css_content


def test_caderno_composer_toolbar_is_the_primary_add_flow():
    js_path = Path(__file__).resolve().parents[2] / 'static' / 'js' / 'pages' / 'caderno.js'
    js_content = _read(js_path)
    html_path = Path(__file__).resolve().parents[2] / 'templates' / 'caderno' / 'index.html'
    html_content = _read(html_path)
    css_path = Path(__file__).resolve().parents[2] / 'static' / 'css' / 'caderno' / 'caderno.css'
    css_content = _read(css_path)

    assert 'id="cadernoComposer"' in html_content
    assert 'data-create-type="text"' in html_content
    assert 'data-create-type="project"' in html_content
    assert '.caderno-composer {' in css_content
    assert '.caderno-compose-btn {' in css_content
    assert 'function findReusableDraftTextBlock() {' in js_content
    assert 'function createTextBlockFromComposer() {' in js_content
    assert 'function onComposerActionClick(event) {' in js_content
    assert "composer.querySelectorAll('[data-create-type]')" in js_content
    assert "btn.addEventListener('click', onComposerActionClick);" in js_content
    assert 'openSearchModal(type, null);' in js_content
    assert 'onCanvasInteract(event)' not in js_content
    assert 'createTextBlockAtPoint(clientX, clientY)' not in js_content


def test_caderno_text_blocks_hide_toolbar_and_visual_cards_gain_resize_handles():
    js_path = Path(__file__).resolve().parents[2] / 'static' / 'js' / 'pages' / 'caderno.js'
    js_content = _read(js_path)
    css_path = Path(__file__).resolve().parents[2] / 'static' / 'css' / 'caderno' / 'caderno.css'
    css_content = _read(css_path)

    assert "function canMoveBlock(block) {" in js_content
    assert "function shouldRenderToolbar(block) {" in js_content
    assert "function canResizeBlock(block) {" in js_content
    assert "return block.block_type !== 'text';" in js_content
    assert "function canDeleteBlock(block) {" in js_content
    assert "if (!shouldRenderToolbar(block)) return '';" in js_content
    assert "${canMoveBlock(block) ? `" not in js_content
    assert 'function renderResizeHandles(block) {' in js_content
    assert 'data-resize-direction="east"' in js_content
    assert 'data-resize-direction="south"' in js_content
    assert 'data-resize-direction="southeast"' in js_content
    assert "${canDeleteBlock(block) ? `" in js_content
    assert '.caderno-block-toolbar-delete {' in css_content
    assert '.caderno-block-resize-handle {' in css_content
    assert '.caderno-block.is-active .caderno-nota-card,' in css_content
    assert '.caderno-block-resize-handle--corner {' in css_content


def test_caderno_reference_cards_drag_from_surface_and_link_only_on_title():
    js_path = Path(__file__).resolve().parents[2] / 'static' / 'js' / 'pages' / 'caderno.js'
    js_content = _read(js_path)
    css_path = Path(__file__).resolve().parents[2] / 'static' / 'css' / 'caderno' / 'caderno.css'
    css_content = _read(css_path)

    assert 'function onDragSurfacePointerDown(event) {' in js_content
    assert "if (event.target.closest('a, button, [contenteditable], input, textarea, select')) return;" in js_content
    assert "blocksContainer.querySelectorAll('[data-drag-surface]').forEach(surface => {" in js_content
    assert 'data-drag-surface="reference"' in js_content
    assert 'data-drag-surface="note"' in js_content
    assert 'class="caderno-ref-card-title-link"' in js_content
    assert 'caderno-ref-card-link-hint' not in js_content
    assert '.caderno-ref-card-body {' in css_content
    assert 'overflow: auto;' in _selector_body(css_content, '.caderno-ref-card-body')
    assert 'white-space: normal;' in _selector_body(css_content, '.caderno-ref-card-title-link')
    assert 'align-self: flex-start;' in _selector_body(css_content, '.caderno-ref-card-title-link')
    assert 'cursor: grab;' in _selector_body(css_content, '.caderno-ref-card')
    assert 'cursor: pointer;' in _selector_body(css_content, '.caderno-ref-card-title-link')


def test_caderno_click_outside_clears_selection_and_delete_uses_hover():
    js_path = Path(__file__).resolve().parents[2] / 'static' / 'js' / 'pages' / 'caderno.js'
    js_content = _read(js_path)
    css_path = Path(__file__).resolve().parents[2] / 'static' / 'css' / 'caderno' / 'caderno.css'
    css_content = _read(css_path)

    assert "if (!event.target.closest('.caderno-block')) {" in js_content
    assert 'setActiveBlock(null);' in js_content
    assert '.caderno-block:hover .caderno-block-toolbar-delete,' in css_content
    assert '.caderno-block.is-active:not(.is-editor-empty):not(.is-slash-trigger):not(.is-slash-menu-open) .caderno-block-toolbar-delete' not in css_content


def test_caderno_existing_pages_reset_expand_state_and_compact_overflow():
    js_path = Path(__file__).resolve().parents[2] / 'static' / 'js' / 'pages' / 'caderno.js'
    js_content = _read(js_path)

    assert 'function compactLayout(sourceBlocks) {' in js_content
    assert 'function hasLayoutOverflowForCurrentSheet(sourceBlocks) {' in js_content
    assert 'const shouldResetSheetSize = persistedSheet.expand_steps > 0;' in js_content
    assert 'expand_steps: 0,' in js_content
    assert 'await saveSheetExpandSteps(0);' in js_content
    assert 'compactLayout(incomingBlocks)' in js_content
