"""Regressões para os achados #3 e #4 do ultrareview.

#3: `_resolve_orgao_from_form` deixava admin criar/editar projetos apontando para
    OrgaoUnidade inativo. O fix rejeita inativos — exceto quando o valor
    submetido coincide com o `orgao_id` atual do projeto (preserva vínculo
    legado durante edição).

#4: O form de edição filtrava `ORGAOS_DISPONIVEIS` por `ativo=True`, então um
    projeto vinculado a órgão inativo perdia a option correta — o admin não
    conseguia salvar. O template passou a incluir o órgão atual mesmo inativo
    como option extra com sufixo "(inativo)".
"""

from models import OrgaoUnidade, Project, db


def _get_orgao(app, sigla):
    with app.app_context():
        return OrgaoUnidade.query.filter_by(sigla=sigla).first()


def _deactivate_orgao(app, orgao_id):
    with app.app_context():
        orgao = db.session.get(OrgaoUnidade, orgao_id)
        orgao.ativo = False
        db.session.commit()


def test_add_project_rejects_inactive_orgao(app, client_admin, seed_data):
    with app.app_context():
        inactive = OrgaoUnidade(
            sigla="INATIVO_ADD",
            nome="Órgão Desativado",
            tipo="Subsecretaria",
            ativo=False,
            ordem=0,
        )
        db.session.add(inactive)
        db.session.commit()
        inactive_id = inactive.id

    response = client_admin.post(
        "/add_project",
        data={
            "project_titulo": "Projeto em Órgão Morto",
            "project_orgao_id": str(inactive_id),
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    with app.app_context():
        assert Project.query.filter_by(titulo="Projeto em Órgão Morto").first() is None


def test_edit_project_preserves_inactive_orgao_link(app, client_admin, seed_data):
    project_id = seed_data["project_id"]
    with app.app_context():
        project = db.session.get(Project, project_id)
        orgao_id = project.orgao_id

    _deactivate_orgao(app, orgao_id)

    # GET deve renderizar o órgão inativo como option selected com sufixo.
    response_get = client_admin.get(f"/project/{project_id}/edit")
    assert response_get.status_code == 200
    html = response_get.get_data(as_text=True)
    assert f'value="{orgao_id}"' in html
    assert "(inativo)" in html

    # POST mantendo o mesmo orgao_id inativo deve salvar com sucesso.
    response_post = client_admin.post(
        f"/project/{project_id}/edit",
        data={
            "project_titulo": "Projeto Auditoria (renomeado)",
            "project_orgao_id": str(orgao_id),
            "project_orgao": "Auditoria",
            "project_prioridade": "alta",
            "project_status": "Vigente",
        },
        follow_redirects=False,
    )
    assert response_post.status_code == 302
    with app.app_context():
        project = db.session.get(Project, project_id)
        assert project.titulo == "Projeto Auditoria (renomeado)"
        assert project.orgao_id == orgao_id


def test_edit_project_rejects_switching_to_different_inactive_orgao(
    app, client_admin, seed_data
):
    project_id = seed_data["project_id"]
    with app.app_context():
        other = OrgaoUnidade(
            sigla="OUTRO_INATIVO",
            nome="Outro Órgão Desativado",
            tipo="Subsecretaria",
            ativo=False,
            ordem=0,
        )
        db.session.add(other)
        db.session.commit()
        other_id = other.id
        project = db.session.get(Project, project_id)
        original_orgao_id = project.orgao_id

    response = client_admin.post(
        f"/project/{project_id}/edit",
        data={
            "project_titulo": "Mudando para órgão inativo",
            "project_orgao_id": str(other_id),
            "project_orgao": "Auditoria",
            "project_prioridade": "alta",
            "project_status": "Vigente",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    with app.app_context():
        project = db.session.get(Project, project_id)
        # Projeto mantém o vínculo original — o fix bloqueou a troca.
        assert project.orgao_id == original_orgao_id
