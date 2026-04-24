"""Contrato da UI do form de criação: import de modelo como preview read-only.

Fase 3 do plano em `docs/plano-modelos-de-etapas.md`. O accordion "Modelo de
Etapas" precisa: enviar `project_template_id` por input hidden, renderizar o
preview read-only, exibir o contador e a dica "Selecione um modelo".
"""


def test_project_add_form_renders_template_import_preview(client_admin):
    response = client_admin.get('/projects')
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    # Hidden input que vincula o projeto ao modelo escolhido
    assert 'name="project_template_id"' in html
    assert 'id="project_template_id"' in html

    # Shell do preview read-only (visível só após seleção)
    assert 'id="tpl-import-preview"' in html
    assert 'id="tpl-import-preview-list"' in html
    assert 'id="tpl-import-stage-count"' in html
    assert 'id="tpl-import-total-duration"' in html
    assert 'id="tpl-import-preview-footer"' in html

    # Empty state quando nenhum modelo está selecionado
    assert 'id="tpl-import-empty"' in html
    assert 'Selecione um modelo' in html

    # Data de início continua sendo opcional
    assert 'id="project_start_date"' in html
    assert 'name="project_start_date"' in html
