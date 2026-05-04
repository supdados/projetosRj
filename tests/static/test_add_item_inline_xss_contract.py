from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "static/js/modules/add-item-inline/dom-factories.js"
)


def _module_source():
    return MODULE_PATH.read_text(encoding="utf-8")


def test_add_item_inline_uses_attribute_encoder_for_dynamic_data_attributes():
    source = _module_source()

    assert "function escapeAttr(value)" in source
    assert '.replace(/"/g, \'&quot;\')' in source
    assert ".replace(/'/g, '&#39;')" in source

    unsafe_attribute_patterns = [
        'data-task-titulo="\' + escapeHtml(taskTitulo)',
        'data-project-titulo="\' + escapeHtml(projectInfo.label)',
        'data-project-value="\' + escapeHtml(projectInfo.value)',
        'data-item-prioridade="\' + escapeHtml(prioridade)',
        'data-item-tipo="\' + escapeHtml(tipoPedido)',
    ]
    for pattern in unsafe_attribute_patterns:
        assert pattern not in source

    safe_attribute_patterns = [
        'data-task-titulo="\' + escapeAttr(taskTitulo)',
        'data-project-titulo="\' + escapeAttr(projectInfo.label)',
        'data-project-value="\' + escapeAttr(projectInfo.value)',
        'data-item-prioridade="\' + escapeAttr(prioridade)',
        'data-item-tipo="\' + escapeAttr(tipoPedido)',
    ]
    for pattern in safe_attribute_patterns:
        assert pattern in source
