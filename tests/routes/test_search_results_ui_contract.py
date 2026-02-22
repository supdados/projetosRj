def test_search_results_items_use_square_contract_class(client_user):
    response = client_user.get('/busca?q=Auditoria')

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'class="search-result-item search-result-item-square"' in html
