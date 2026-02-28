import re


def test_project_detail_template_contains_stage_table_hooks(client_user, seed_data):
    response = client_user.get(f"/project/{seed_data['project_id']}")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    required_hooks = [
        'id="etapas-tbody"',
        'etapa-draggable-row',
        'etapa-drag-handle',
        'editable-field',
        'toggle-iniciada',
        'toggle-done',
        'btn-comment-data',
        'data-etapa-delete-form',
        'data-etapa-delete-btn',
        "form[data-etapa-delete-form]",
        'data-etapa-id="',
        'data-field="',
        'data-original-value="',
        'data-empty-display="Sem data"',
        'id="date-context-menu"',
    ]

    for hook in required_hooks:
        assert hook in html


def test_project_detail_template_contains_inline_add_stage_contract(client_user, seed_data):
    response = client_user.get(f"/project/{seed_data['project_id']}")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    inline_hooks = [
        'id="btnImportModel"',
        'id="btnOpenInlineEtapaAdd"',
        'id="etapaInlineAddEntryRow"',
        'id="etapaInlineAddFormRow"',
        'id="etapaInlineAddForm"',
        'id="btnSubmitInlineEtapaAdd"',
        'id="btnCancelInlineEtapaAdd"',
        'id="reactivate-project-confirm-modal"',
        'id="reactivate-project-confirm-btn"',
        'id="reactivate-project-cancel-btn"',
        'etapa-inline-cell etapa-inline-cell-actions',
        'etapa-inline-date-wrap',
        'id="etapa_inline_iniciada"',
        'id="etapa_inline_done"',
        'inline-status-toggle',
        'etapa-status-toggle',
        'etapa-inline-form-row',
    ]

    for hook in inline_hooks:
        assert hook in html

    assert 'id="etapa_inline_comentarios"' not in html

    inline_row_match = re.search(
        r'<tr id="etapaInlineAddFormRow"[\s\S]*?</tr>',
        html,
    )
    assert inline_row_match is not None
    assert inline_row_match.group(0).count('<td') == 9
    assert 'type="checkbox"' in inline_row_match.group(0)
    assert 'role="switch"' not in inline_row_match.group(0)
