"""Regressão: `task_comment.mentions` na sequência canônica de migração.

Antes do fix a coluna só nascia em `startup.ensure_task_comment_mentions_column`;
o runner nunca a criava e o caminho de REBUILD de tarefas recriava `task_comment`
sem ela, apagando os spans já gravados.
"""

from sqlalchemy import inspect, text

from models import Task, TaskComment, User, db
from scripts.migrations.run_migrations import (
    TASK_COMMENT_INCREMENTAL_COLUMNS,
    _add_task_comment_columns,
    ensure_task_schema,
)

SPAN = [{"user_id": 1, "name": "Maria Silva", "start": 0, "length": 6}]


def _colunas_task_comment() -> set[str]:
    return {c["name"] for c in inspect(db.engine).get_columns("task_comment")}


def _derrubar_coluna_mentions() -> None:
    """Volta `task_comment` ao formato anterior ao recurso de menções."""
    db.session.execute(text("ALTER TABLE task_comment DROP COLUMN mentions"))
    db.session.commit()


def _forcar_rebuild_de_task() -> None:
    """Remove coluna exigida por TASK_REQUIRED_COLUMNS para disparar o rebuild."""
    db.session.execute(text("ALTER TABLE task DROP COLUMN tipo_pedido"))
    db.session.commit()


def _criar_comentario_com_mencao() -> int:
    autor = User(username="autor_mencao", name="Autor Menção")
    autor.set_password("senha123")
    db.session.add(autor)
    db.session.flush()

    tarefa = Task(
        descricao="Tarefa com menção",
        status="nao_iniciada",
        created_by_id=autor.id,
    )
    db.session.add(tarefa)
    db.session.flush()

    comentario = TaskComment(
        content="@Maria olha isso",
        user_id=autor.id,
        task_id=tarefa.id,
        mentions=SPAN,
    )
    db.session.add(comentario)
    db.session.commit()
    return comentario.id


def test_mentions_esta_na_lista_de_colunas_incrementais():
    assert TASK_COMMENT_INCREMENTAL_COLUMNS == [("mentions", "JSON")]


def test_add_task_comment_columns_recria_mentions_e_e_idempotente(app):
    with app.app_context():
        _derrubar_coluna_mentions()
        assert "mentions" not in _colunas_task_comment()

        assert _add_task_comment_columns() == ["task_comment.mentions"]
        assert "mentions" in _colunas_task_comment()

        assert _add_task_comment_columns() == []


def test_ensure_task_schema_cria_mentions_em_banco_legado(app):
    with app.app_context():
        _derrubar_coluna_mentions()

        resultado = ensure_task_schema(emit_output=False)

        assert resultado["success"] is True
        assert "task_comment.mentions" in resultado["changes"]
        assert "mentions" in _colunas_task_comment()


def test_rebuild_de_task_preserva_spans_de_mentions(app):
    with app.app_context():
        comentario_id = _criar_comentario_com_mencao()
        _forcar_rebuild_de_task()

        resultado = ensure_task_schema(emit_output=False)

        assert resultado["success"] is True
        assert "task.rebuilt_task_only" in resultado["changes"]
        assert "mentions" in _colunas_task_comment()
        assert db.session.get(TaskComment, comentario_id).mentions == SPAN


def test_rebuild_em_banco_sem_mentions_gera_coluna_nula(app):
    with app.app_context():
        comentario_id = _criar_comentario_com_mencao()
        _derrubar_coluna_mentions()
        _forcar_rebuild_de_task()

        resultado = ensure_task_schema(emit_output=False)

        assert resultado["success"] is True
        assert "task.rebuilt_task_only" in resultado["changes"]
        assert "mentions" in _colunas_task_comment()
        assert db.session.get(TaskComment, comentario_id).mentions is None
