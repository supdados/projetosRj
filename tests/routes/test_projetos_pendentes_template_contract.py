def test_projetos_pendentes_template_uses_short_done_toast(client_user):
    response = client_user.get('/projetos_pendentes')

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert "showToast('Etapa concluída', 'info');" in html
    assert 'removida da triagem' not in html
