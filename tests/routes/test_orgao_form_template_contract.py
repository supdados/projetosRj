"""Contrato do template do formulário de órgão.

Garante que o combobox de "Órgão pai" exponha os atributos necessários para o
JS filtrar por rank do tipo e por busca textual. Um eventual refactor que
remova data-rank/data-tipo/data-label quebraria silenciosamente o filtro no
cliente — este contrato trava a forma do DOM.
"""


def _get_form_html(client_admin, seed_data):
    response = client_admin.get(f'/admin/orgaos/{seed_data["orgao_child_id"]}/edit')
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_orgao_form_has_searchable_pai_combobox(client_admin, seed_data):
    html = _get_form_html(client_admin, seed_data)

    assert 'id="paiCombo"' in html
    assert 'id="pai_id_input"' in html
    assert 'id="paiComboDropdown"' in html
    # Input de texto com role-appropriate attributes.
    assert 'role="listbox"' in html
    assert 'aria-haspopup="listbox"' in html
    # Campo oculto que vai no POST mantém o name esperado pelo backend.
    assert 'name="pai_id"' in html


def test_orgao_form_options_expose_rank_tipo_and_label(client_admin, seed_data):
    html = _get_form_html(client_admin, seed_data)

    # Para editar a Secretaria filha, o único candidato válido a pai é o
    # Estado raiz (sigla ERJ). A opção deve expor todos os data-* usados pelo
    # JS de filtro.
    assert 'class="pai-combo-option"' in html
    assert 'data-value="' in html
    assert 'data-rank="' in html
    assert 'data-tipo="' in html
    assert 'data-label="' in html
    # O Estado raiz tem rank 0 e deve estar disponível como candidato.
    assert 'data-tipo="Estado"' in html
    assert 'data-rank="0"' in html


def test_orgao_form_new_renders_combobox(client_admin, seed_data):
    response = client_admin.get("/admin/orgaos/new")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'id="paiCombo"' in html
    # Sem órgão pré-selecionado ao criar novo.
    assert 'id="pai_id_input"' in html
