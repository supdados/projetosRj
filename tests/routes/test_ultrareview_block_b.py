"""Regressões para os achados #5 e #6 do ultrareview (bloco B).

#5 — get_visible_orgao_tree filtrava ancestrais por ativo=True, derrubando o
    pai quando desativado e deixando o filho órfão no build_nested_orgao_tree.
    Hoje ancestrais ficam FORA da árvore de não-admin (o vínculo vira raiz),
    então ancestral inativo não é mais um problema — o teste vira guarda da
    regra nova.
#6 — selected_orgao_sigla no task hub usava g.get("ORGAOS_DISPONIVEIS") mas o
    valor é injetado no contexto do template (context processor), não em g.

(#7 — sentinel de órgãos do form Jinja admin — foi removido junto com a rota
``/admin/users/edit`` na migração SPA; o contrato equivalente vive na API
``/api/admin/usuarios/<id>`` e em ``tests/routes/test_api_admin_users_contract.py``.)
"""

from models import OrgaoUnidade, User, db
from routes.orgao_scope import build_nested_orgao_tree, get_visible_orgao_tree

# --- #5 --------------------------------------------------------------------


def test_get_visible_orgao_tree_omite_ancestral_e_promove_vinculo_a_raiz(
    app, seed_data
):
    # O seed cria Auditoria como filho de SETD. SETD (ancestral, mesmo
    # inativo) fica fora da árvore do usuário de Auditoria; Auditoria vira
    # raiz no build_nested_orgao_tree — sem nó órfão.
    with app.app_context():
        setd = OrgaoUnidade.query.filter_by(sigla="SETD").first()
        assert setd is not None
        setd.ativo = False
        db.session.commit()

        user = db.session.get(User, seed_data["user_id"])
        tree = get_visible_orgao_tree(user)
        by_id = {node["id"]: node for node in tree}
        assert setd.id not in by_id
        auditoria = OrgaoUnidade.query.filter_by(sigla="Auditoria").first()
        assert auditoria.id in by_id
        assert by_id[auditoria.id]["is_inactive"] is False
        roots = build_nested_orgao_tree(tree)
        assert auditoria.id in {root["id"] for root in roots}


# --- #6 --------------------------------------------------------------------


def test_task_hub_accepts_selected_orgao_filter(client_user, seed_data, app):
    # Apos o cut-over /tarefas serve a shell da SPA; o filtro de orgao e aplicado
    # server-side em GET /api/tarefas (mesma fonte build_task_hub_context). Um
    # orgao valido para o usuario corrente devolve 200 com o filtro aplicado.
    with app.app_context():
        auditoria = OrgaoUnidade.query.filter_by(sigla="Auditoria").first()
        auditoria_id = auditoria.id

    payload = client_user.get(f"/api/tarefas?orgao={auditoria_id}").get_json()
    assert payload["ok"] is True
    assert payload["data"]["filters"]["selected_orgao"] == auditoria_id
