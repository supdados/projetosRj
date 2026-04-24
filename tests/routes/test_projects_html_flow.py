from html import unescape

from models import Project, ProjectHistory, db
from tests._orgao_helpers import ensure_orgao


def _follow_redirect_and_get_html(client, response):
    location = response.headers['Location']
    followed = client.get(location)
    assert followed.status_code == 200
    return unescape(followed.get_data(as_text=True))


def test_edit_project_form_renders_full_html_contract_for_single_area_user(client_user, seed_data):
    response = client_user.get(f"/project/{seed_data['project_id']}/edit")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    required_hooks = [
        'Editar Projeto:',
        f'action="/project/{seed_data["project_id"]}/edit"',
        'id="project_titulo"',
        'value="Projeto Auditoria"',
        'id="project_orgao_id"',
        'name="project_orgao_id"',
        'id="project_orgao"',
        'value="Orgao A"',
        'id="project_special_project"',
        'id="project_sei_process"',
        'id="project_delivery_type"',
        'id="project_abep_indicator_search"',
        'id="project_abep_indicator"',
        'id="project_objetivo"',
        'id="project_resultado"',
        'id="indicadores-container"',
        'id="project_github_link"',
        'id="project_documentation_link"',
        'id="project_product_link"',
        'id="project_observacao"',
        f'href="/project/{seed_data["project_id"]}"',
        'Salvar Alterações',
    ]

    for hook in required_hooks:
        assert hook in html

    assert 'name="project_orgao_id" required' in html
    assert '<option value="Vigente" selected>Vigente</option>' in html


def test_delete_project_html_redirects_with_flash_and_removes_project(app, client_user):
    with app.app_context():
        project = Project(
            titulo='Projeto Para Excluir HTML',
            orgao_id=ensure_orgao('Auditoria').id,
            orgao='Orgao Delete',
            prioridade='baixa',
            status='Vigente',
            objetivo_id=1,
            resultado_esperado_id=1,
        )
        db.session.add(project)
        db.session.commit()
        project_id = project.id

    response = client_user.post(f'/project/{project_id}/delete', follow_redirects=False)

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/projects')

    html = _follow_redirect_and_get_html(client_user, response)
    assert 'Projeto "Projeto Para Excluir HTML" e suas etapas foram excluídos.' in html

    with app.app_context():
        assert db.session.get(Project, project_id) is None


def test_concluir_project_html_redirects_back_with_warning_flash_when_incomplete(app, client_user, seed_data):
    response = client_user.post(
        f"/project/{seed_data['project_id']}/concluir",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers['Location'].endswith(f"/project/{seed_data['project_id']}")

    html = _follow_redirect_and_get_html(client_user, response)
    assert 'Todas as etapas devem estar iniciadas e concluídas para finalizar o projeto.' in html

    with app.app_context():
        project = db.session.get(Project, seed_data['project_id'])
        assert project is not None
        assert project.status == 'Vigente'


def test_concluir_project_html_redirects_back_with_success_flash_and_finalizes_project(app, client_user, seed_data):
    response = client_user.post(
        f"/project/{seed_data['project_complete_id']}/concluir",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers['Location'].endswith(f"/project/{seed_data['project_complete_id']}")

    html = _follow_redirect_and_get_html(client_user, response)
    assert 'Projeto "Projeto Concluivel" foi concluído com sucesso!' in html

    with app.app_context():
        project = db.session.get(Project, seed_data['project_complete_id'])
        assert project is not None
        assert project.status == 'Finalizado'

        history = (
            ProjectHistory.query
            .filter_by(project_id=project.id, action_type='finalize')
            .order_by(ProjectHistory.id.desc())
            .first()
        )
        assert history is not None
        assert 'Concluiu o projeto' in history.action_description
