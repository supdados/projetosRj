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
        'data-etapa-id="',
        'data-field="',
        'data-original-value="',
    ]

    for hook in required_hooks:
        assert hook in html


def test_project_detail_template_contains_add_stage_modal_contract(client_user, seed_data):
    response = client_user.get(f"/project/{seed_data['project_id']}")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    modal_hooks = [
        'id="addEtapaModal"',
        'id="addEtapaForm"',
        'id="etapa_descricao_modal"',
        'id="etapa_comentarios_modal"',
        'id="etapa_data_inicio_modal"',
        'id="etapa_data_fim_modal"',
        'id="etapa_responsavel_modal"',
        'id="etapa_iniciada_modal"',
        'id="etapa_done_modal"',
    ]

    for hook in modal_hooks:
        assert hook in html
