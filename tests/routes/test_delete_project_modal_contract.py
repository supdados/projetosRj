"""Contrato de UI do fluxo de exclusão de projeto em dois passos.

A confirmação por digitação ("APAGAR PROJETO") vive no front-end; a rota
`delete_project` é coberta por test_projects_html_flow / test_projects_core_flow.
Aqui garantimos apenas que os hooks que o JS depende estão renderizados nas duas
telas onde o usuário pode apagar: detalhe (modo edição) e lista geral.
"""

DELETE_MODAL_HOOKS = [
    'id="deleteProjectModal"',
    'data-delete-step="warn"',
    'data-delete-step="confirm"',
    "data-delete-project-name",
    "data-delete-confirm-input",
    "data-delete-advance",
    "data-delete-confirm",
    "data-delete-cancel",
    "APAGAR PROJETO",
    "css/partials/delete-project-modal.css",
    "js/modules/delete-project-modal.js",
]


def test_project_detail_renders_delete_button_and_confirm_modal(client_user, seed_data):
    response = client_user.get(f"/project/{seed_data['project_id']}")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    # Botão vermelho de apagar, escondido até o modo edição (classe ds-hidden).
    assert "btn-delete-project" in html
    assert 'data-delete-url="/project/' in html
    assert f'data-delete-url="/project/{seed_data["project_id"]}/delete"' in html
    # O rótulo segue o ícone (</i>Apagar Projeto) e depois há whitespace antes de
    # </button>, então casa-se o trecho contíguo. "Apagar Projeto" (P maiúsculo) é
    # exclusivo deste botão — o modal usa "Apagar projeto" e "APAGAR PROJETO".
    assert ">Apagar Projeto" in html

    for hook in DELETE_MODAL_HOOKS:
        assert hook in html, f"hook ausente na tela de detalhe: {hook}"


def test_projects_list_renders_delete_form_and_confirm_modal(client_user, seed_data):
    response = client_user.get("/projects")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    # Form de exclusão por linha precisa carregar o nome para o aviso do modal.
    assert "js-delete-project-form" in html
    assert 'data-project-name="Projeto Auditoria"' in html

    for hook in DELETE_MODAL_HOOKS:
        assert hook in html, f"hook ausente na lista de projetos: {hook}"
