def test_admin_templates_list_has_clickable_rows_and_no_edit_button(client_admin):
    response = client_admin.get('/admin/templates')

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'btn-edit-clean' not in html
    assert 'template-item-clickable' in html
    assert 'data-template-url="/admin/templates/' in html
    assert 'role="link"' in html
    assert 'data-stop-row-click="1"' in html
    assert 'btn-delete-clean' in html
