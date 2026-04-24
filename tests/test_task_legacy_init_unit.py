"""Testes unitários do __init__ legado de Task/TaskItem e das queries de escopo.

Cobre:
  * Task.__init__ com kwargs legados `titulo=` e `task_id=`: mapeamento para
    `descricao`, herança de project_id/legacy_parent_task_id/created_by_id a
    partir do anchor e cálculo automático de `ordem` (MAX + 1).
  * Task.task_id setter com ids inválidos.
  * TaskQuery.count() (escopo root) e TaskItemQuery.count() (escopo child):
    ignoram escopo em queries com where e contam corretamente em queries planas.
"""

from models import Project, Task, TaskItem, User, db
from tests._orgao_helpers import ensure_orgao, link_user_to_orgao


def _user(username="tk_user"):
    user = User(username=username, name="Test", orgao="Orgao Teste", is_admin=False)
    user.set_password("senha123")
    db.session.add(user)
    db.session.flush()
    link_user_to_orgao(user.id, "Auditoria")
    return user


def _project(titulo="Projeto TK"):
    orgao = ensure_orgao("Auditoria")
    project = Project(
        titulo=titulo,
        orgao_id=orgao.id,
        orgao="Orgao A",
        prioridade="media",
        status="Vigente",
        objetivo_id=1,
        resultado_esperado_id=1,
    )
    db.session.add(project)
    db.session.flush()
    return project


# ---------------------------------------------------------------------------
# Task.__init__ legacy kwargs
# ---------------------------------------------------------------------------


def test_task_legacy_titulo_maps_to_descricao(app):
    with app.app_context():
        user = _user()
        db.session.commit()

        task = Task(titulo="Legacy Titulo", created_by_id=user.id, project_id=None)
        assert task.descricao == "Legacy Titulo"


def test_task_explicit_descricao_wins_over_legacy_titulo(app):
    with app.app_context():
        user = _user()
        db.session.commit()

        task = Task(
            titulo="Legacy",
            descricao="Descricao explicita",
            created_by_id=user.id,
        )
        assert task.descricao == "Descricao explicita"


def test_task_task_id_inherits_anchor_fields_and_computes_ordem(app):
    with app.app_context():
        user = _user()
        project = _project()

        anchor = Task(
            descricao="Anchor",
            created_by_id=user.id,
            project_id=project.id,
            ordem=5,
        )
        db.session.add(anchor)
        db.session.commit()

        child = Task(titulo="Child", task_id=anchor.id)
        db.session.add(child)
        db.session.commit()

        assert child.descricao == "Child"
        assert child.project_id == project.id
        assert child.legacy_parent_task_id == anchor.id
        assert child.created_by_id == anchor.created_by_id
        # Ordem = MAX(ordem) + 1 = 5 + 1 = 6.
        assert child.ordem == 6


def test_task_task_id_ignores_archived_when_computing_ordem(app):
    with app.app_context():
        user = _user()
        project = _project()

        anchor = Task(
            descricao="Anchor", created_by_id=user.id, project_id=project.id, ordem=2
        )
        archived = Task(
            descricao="Archived",
            created_by_id=user.id,
            project_id=project.id,
            ordem=99,
            is_archived=True,
        )
        db.session.add_all([anchor, archived])
        db.session.commit()

        child = Task(titulo="Child", task_id=anchor.id)
        db.session.add(child)
        db.session.commit()

        # Ignora ordem=99 do arquivado e usa 2+1=3.
        assert child.ordem == 3


def test_task_task_id_invalid_integer_is_ignored(app):
    with app.app_context():
        user = _user()
        db.session.commit()

        task = Task(titulo="X", task_id="nao-numerico", created_by_id=user.id)
        assert task.legacy_parent_task_id is None
        assert task.descricao == "X"


def test_task_task_id_missing_anchor_leaves_fields_untouched(app):
    with app.app_context():
        user = _user()
        db.session.commit()

        task = Task(titulo="X", task_id=99999, created_by_id=user.id)
        assert task.legacy_parent_task_id is None


def test_task_task_id_setter_after_construction(app):
    with app.app_context():
        user = _user()
        project = _project()

        anchor = Task(
            descricao="Anchor",
            created_by_id=user.id,
            project_id=project.id,
        )
        db.session.add(anchor)
        db.session.commit()

        fresh = Task(descricao="Fresh", created_by_id=user.id)
        fresh.task_id = anchor.id

        assert fresh.project_id == project.id
        assert fresh.legacy_parent_task_id == anchor.id


def test_task_task_id_setter_with_invalid_value_is_noop(app):
    with app.app_context():
        user = _user()
        db.session.commit()

        fresh = Task(descricao="Fresh", created_by_id=user.id)
        fresh.task_id = "bogus"
        assert fresh.legacy_parent_task_id is None


def test_task_properties_aliases(app):
    """Garantia das propriedades de compatibilidade (titulo/finalized/items)."""
    with app.app_context():
        user = _user()
        db.session.commit()

        task = Task(descricao="Descricao", created_by_id=user.id)
        db.session.add(task)
        db.session.flush()  # aplica default=False de is_archived via SQLAlchemy
        assert task.titulo == "Descricao"
        task.titulo = "Novo"
        assert task.descricao == "Novo"
        assert task.is_finalized is False
        task.is_finalized = True
        assert task.is_archived is True
        assert task.finalized_at is task.archived_at
        assert task.items == [task]
        assert task.task is task


# ---------------------------------------------------------------------------
# TaskItem.__init__ (mesma semântica do Task)
# ---------------------------------------------------------------------------


def test_task_item_legacy_kwargs_populate_from_anchor(app):
    with app.app_context():
        user = _user()
        project = _project()

        anchor = Task(descricao="Anchor", created_by_id=user.id, project_id=project.id)
        db.session.add(anchor)
        db.session.commit()

        item = TaskItem(titulo="Sub", task_id=anchor.id)
        db.session.add(item)
        db.session.commit()

        assert item.descricao == "Sub"
        assert item.project_id == project.id
        assert item.legacy_parent_task_id == anchor.id


# ---------------------------------------------------------------------------
# Query classes — escopo root x child via count()
# ---------------------------------------------------------------------------


def test_task_query_count_restricts_to_root_rows(app):
    """Task.query.count() deve ignorar filhas (legacy_parent_task_id != NULL)."""
    with app.app_context():
        user = _user()
        project = _project()

        root_a = Task(descricao="A", created_by_id=user.id, project_id=project.id)
        root_b = Task(descricao="B", created_by_id=user.id, project_id=project.id)
        db.session.add_all([root_a, root_b])
        db.session.commit()

        # Adiciona filha (TaskItem) do root_a.
        item = TaskItem(titulo="Filha", task_id=root_a.id)
        db.session.add(item)
        db.session.commit()

        assert Task.query.count() == 2  # só raízes
        assert TaskItem.query.count() == 1  # só filhas


def test_task_query_count_with_filter_ignores_scope(app):
    """Quando já há where, _LegacyTaskScopeQuery fala pro super (sem escopo)."""
    with app.app_context():
        user = _user()
        project = _project()

        root = Task(descricao="X", created_by_id=user.id, project_id=project.id)
        db.session.add(root)
        db.session.commit()

        item = TaskItem(titulo="Filha", task_id=root.id)
        db.session.add(item)
        db.session.commit()

        filtered = Task.query.filter(Task.project_id == project.id).count()
        # Com where, conta raízes + filhas (2 linhas na tabela).
        assert filtered == 2


def test_task_item_query_count_with_filter_ignores_scope(app):
    """O mesmo comportamento vale para TaskItemQuery."""
    with app.app_context():
        user = _user()
        project = _project()

        root = Task(descricao="X", created_by_id=user.id, project_id=project.id)
        db.session.add(root)
        db.session.commit()

        item = TaskItem(titulo="Filha", task_id=root.id)
        db.session.add(item)
        db.session.commit()

        filtered = TaskItem.query.filter(TaskItem.descricao == "X").count()
        # With where: retorna só a raiz (não escopa em filha).
        assert filtered == 1
