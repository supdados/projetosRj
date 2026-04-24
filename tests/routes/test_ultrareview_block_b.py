"""Regressões para os achados #5, #6 e #7 do ultrareview (bloco B).

#5 — get_visible_orgao_tree filtrava ancestrais por ativo=True, derrubando o
    pai quando desativado e deixando o filho órfão no build_nested_orgao_tree.
#6 — selected_orgao_sigla no task hub usava g.get("ORGAOS_DISPONIVEIS") mas o
    valor é injetado no contexto do template (context processor), não em g.
#7 — admin_users.edit_user usava `"orgaos_responsavel" in request.form` para
    saber se o form foi submetido, então desmarcar todos os checkboxes fazia
    o backend manter a lista atual em vez de limpar.
"""

from models import OrgaoUnidade, User, UserOrgao, db
from routes.orgao_scope import get_visible_orgao_tree

# --- #5 --------------------------------------------------------------------


def test_get_visible_orgao_tree_keeps_inactive_ancestor(app, seed_data):
    # O seed cria Auditoria como filho de SETD. Desativamos SETD (ancestral)
    # e garantimos que ele continua aparecendo na árvore do usuário de
    # Auditoria — caso contrário, Auditoria ficaria órfã.
    with app.app_context():
        setd = OrgaoUnidade.query.filter_by(sigla="SETD").first()
        assert setd is not None
        setd.ativo = False
        db.session.commit()

        user = db.session.get(User, seed_data["user_id"])
        tree = get_visible_orgao_tree(user)
        by_id = {node["id"]: node for node in tree}
        assert setd.id in by_id, "ancestral inativo foi derrubado — árvore quebra"
        assert by_id[setd.id]["is_inactive"] is True
        # Órgão do usuário segue presente.
        auditoria = OrgaoUnidade.query.filter_by(sigla="Auditoria").first()
        assert auditoria.id in by_id
        assert by_id[auditoria.id]["is_inactive"] is False


# --- #6 --------------------------------------------------------------------


def test_task_hub_fills_selected_orgao_sigla(client_user, seed_data, app):
    with app.app_context():
        auditoria = OrgaoUnidade.query.filter_by(sigla="Auditoria").first()
        auditoria_id = auditoria.id

    response = client_user.get(f"/tarefas?orgao={auditoria_id}")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    # Antes do fix, `selected_orgao_sigla` era sempre "" porque
    # g.get("ORGAOS_DISPONIVEIS") devolvia None. Agora a sigla aparece no HTML.
    assert "Auditoria" in html


# --- #7 --------------------------------------------------------------------


def test_admin_can_clear_all_orgao_links_from_user(app, client_admin, seed_data):
    target_user_id = seed_data["user_id"]
    with app.app_context():
        user = db.session.get(User, target_user_id)
        initial_links = [uo.orgao_id for uo in user.orgaos]
        assert initial_links, "teste precisa de ao menos 1 vínculo pré-existente"

    # Submete o form de edição sem nenhum checkbox marcado, mas com o sentinel
    # que o template passou a enviar. Backend deve LIMPAR — não preservar.
    response = client_admin.post(
        f"/admin/users/edit/{target_user_id}",
        data={
            "name": "Usuario Auditoria",
            "orgaos_responsavel_submitted": "1",
            # "orgaos_responsavel" propositalmente ausente (desmarcou todos)
        },
        follow_redirects=False,
    )
    # Admin redireciona ao terminar com sucesso.
    assert response.status_code in (302, 200), response.status_code

    with app.app_context():
        remaining = UserOrgao.query.filter_by(user_id=target_user_id).count()
        assert remaining == 0, f"esperava 0 vínculos, restou {remaining}"


def test_admin_edit_without_orgaos_fields_preserves_existing_links(
    app, client_admin, seed_data
):
    """Contrato oposto ao test acima: sem sentinel e sem checkbox, o backend
    deve entender como "esse form não mexeu em órgãos" e preservar o atual.
    Isso protege fluxos administrativos legados (scripts, APIs) que só editam
    outros campos.
    """
    target_user_id = seed_data["user_id"]
    with app.app_context():
        user = db.session.get(User, target_user_id)
        before = sorted(uo.orgao_id for uo in user.orgaos)

    response = client_admin.post(
        f"/admin/users/edit/{target_user_id}",
        data={"name": "Usuario Auditoria"},
        follow_redirects=False,
    )
    assert response.status_code in (302, 200)

    with app.app_context():
        user = db.session.get(User, target_user_id)
        after = sorted(uo.orgao_id for uo in user.orgaos)
        assert before == after
