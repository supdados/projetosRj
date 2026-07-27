"""Testes do backfill de responsáveis legados (texto -> task_assignee).

Regressão do bug (2026-06-10) em que lista/kanban exibiam o texto livre
``Task.responsavel`` enquanto o drawer mostrava a relação ``task_assignee``
vazia. O passo de migração ``backfill_task_assignees`` converte os nomes do
texto em linhas de ``task_assignee`` e remove do texto os nomes convertidos
(idempotência entre boots: atribuições removidas na UI não ressuscitam).
"""

import pytest

from models import Task, TaskAssignee, User, db
from scripts.migrations.backfill_task_assignees import backfill_task_assignees
from time_utils import utc_now


@pytest.fixture
def backfill_setup(app):
    """Dois usuários ativos com nomes distintos, para casar os textos legados.

    Commita e fecha o contexto antes do yield: cada teste abre o próprio
    app_context (= outra sessão/conexão no SQLite de arquivo), e uma transação
    de escrita aberta aqui travaria a escrita do teste ("database is locked").
    """
    with app.app_context():
        jose = User(username="jhudson", name="Jose Hudson", orgao="SETD")
        jose.set_password("senha123")
        sandra = User(username="sbaldine", name="Sandra Baldine", orgao="SETD")
        sandra.set_password("senha123")
        db.session.add_all([jose, sandra])
        db.session.commit()
        ids = {"jose_id": jose.id, "sandra_id": sandra.id}
    return ids


def _add_task(descricao, responsavel, created_by_id):
    task = Task(
        descricao=descricao,
        status="nao_iniciada",
        responsavel=responsavel,
        created_by_id=created_by_id,
    )
    db.session.add(task)
    db.session.flush()
    return task.id


def test_backfill_converts_matched_name_and_clears_text(app, backfill_setup):
    with app.app_context():
        task_id = _add_task(
            "Publicar métricas", "Jose Hudson", backfill_setup["jose_id"]
        )

        result = backfill_task_assignees(emit_output=False)

        assert result["success"] is True
        assert result["assignees_created"] == 1
        task = db.session.get(Task, task_id)
        assert [a.user_id for a in task.assignees] == [backfill_setup["jose_id"]]
        assert task.responsavel is None


def test_backfill_keeps_unmatched_names_in_text(app, backfill_setup):
    with app.app_context():
        task_id = _add_task(
            "Contato SEBRAE",
            "Jose Hudson, Fulano Inexistente",
            backfill_setup["jose_id"],
        )

        backfill_task_assignees(emit_output=False)

        task = db.session.get(Task, task_id)
        assert [a.user_id for a in task.assignees] == [backfill_setup["jose_id"]]
        assert task.responsavel == "Fulano Inexistente"


def test_backfill_matches_username_when_text_stored_login_alias(app, backfill_setup):
    """O texto legado também guardou apelidos de login (ex.: "Lucas" p/ ``lucas``)."""
    with app.app_context():
        task_id = _add_task("Apelido de login", "JHUDSON", backfill_setup["jose_id"])

        backfill_task_assignees(emit_output=False)

        task = db.session.get(Task, task_id)
        assert [a.user_id for a in task.assignees] == [backfill_setup["jose_id"]]
        assert task.responsavel is None


def test_backfill_matches_name_case_and_spacing_insensitive(app, backfill_setup):
    with app.app_context():
        task_id = _add_task(
            "Levantamento", "  sandra   BALDINE ", backfill_setup["jose_id"]
        )

        backfill_task_assignees(emit_output=False)

        task = db.session.get(Task, task_id)
        assert [a.user_id for a in task.assignees] == [backfill_setup["sandra_id"]]


def test_backfill_is_idempotent_after_ui_removal(app, backfill_setup):
    """Rodar de novo (boot seguinte) não ressuscita atribuição removida na UI."""
    with app.app_context():
        task_id = _add_task("Tarefa editada", "Jose Hudson", backfill_setup["jose_id"])
        backfill_task_assignees(emit_output=False)

        task = db.session.get(Task, task_id)
        task.assignees.remove(task.assignees[0])
        db.session.commit()

        rerun = backfill_task_assignees(emit_output=False)

        assert rerun["assignees_created"] == 0
        assert db.session.get(Task, task_id).assignees == []


def test_backfill_skips_ambiguous_and_deleted_users(app, backfill_setup):
    with app.app_context():
        homonimo = User(username="jhudson2", name="Jose Hudson", orgao="VPD")
        homonimo.set_password("senha123")
        deleted = User(
            username="apagado", name="Carlos Sumido", orgao="SETD", deleted_at=utc_now()
        )
        deleted.set_password("senha123")
        db.session.add_all([homonimo, deleted])
        db.session.flush()
        task_id = _add_task(
            "Caso ambíguo", "Jose Hudson, Carlos Sumido", backfill_setup["jose_id"]
        )

        result = backfill_task_assignees(emit_output=False)

        assert result["assignees_created"] == 0
        task = db.session.get(Task, task_id)
        assert task.assignees == []
        assert task.responsavel == "Jose Hudson, Carlos Sumido"


def test_backfill_merges_with_existing_assignees_without_duplicating(
    app, backfill_setup
):
    with app.app_context():
        task_id = _add_task(
            "Já tinha assignee",
            "Jose Hudson, Sandra Baldine",
            backfill_setup["jose_id"],
        )
        db.session.add(TaskAssignee(task_id=task_id, user_id=backfill_setup["jose_id"]))
        db.session.flush()

        result = backfill_task_assignees(emit_output=False)

        assert result["assignees_created"] == 1
        task = db.session.get(Task, task_id)
        assert sorted(a.user_id for a in task.assignees) == sorted(
            [backfill_setup["jose_id"], backfill_setup["sandra_id"]]
        )
        assert task.responsavel is None
