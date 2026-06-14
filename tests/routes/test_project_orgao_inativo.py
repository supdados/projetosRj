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
