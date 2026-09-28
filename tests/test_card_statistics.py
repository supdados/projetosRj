from datetime import date

from sqlalchemy.orm import raiseload

from models import Etapa, Project, Task, TaskAnexo, TaskComment, db
from routes.api.serializers import serialize_project_card, serialize_task_card
from services.card_statistics import (
    project_card_statistics,
    task_card_counts,
    task_card_load_options,
)
from tests.sql_query_counter import SqlQueryCounter


def test_project_statistics_match_properties_without_loading_stages(
    app, seed_data
) -> None:
    with app.app_context():
        project = db.session.get(Project, seed_data["project_id"])
        db.session.add(
            Etapa(
                project_id=project.id,
                descricao="Reunião",
                entry_type="google_meeting",
                data_inicio=date(2025, 1, 1),
                data_fim=date(2027, 1, 1),
                done=True,
                iniciada=True,
            )
        )
        db.session.commit()
        expected = serialize_project_card(project)
        project_id = project.id
        db.session.expunge_all()
        loaded = (
            Project.query.options(raiseload(Project.etapas))
            .filter_by(id=project_id)
            .one()
        )
        stats = project_card_statistics([project_id])[project_id]
        assert serialize_project_card(loaded, statistics=stats) == expected


def test_task_counts_match_relationships_without_loading_content(
    app, seed_data
) -> None:
    with app.app_context():
        task = db.session.get(Task, seed_data["task_id"])
        db.session.add_all(
            [
                TaskComment(
                    task_id=task.id, user_id=seed_data["user_id"], content="texto"
                )
                for _ in range(3)
            ]
        )
        db.session.add(
            TaskAnexo(
                task_id=task.id,
                uploaded_by_id=seed_data["user_id"],
                filename="x.txt",
                stored_filename="sintetico.txt",
            )
        )
        db.session.commit()
        expected = serialize_task_card(task)
        task_id = task.id
        db.session.expunge_all()
        loaded = (
            Task.query.options(
                *task_card_load_options(),
                raiseload(Task.comments),
                raiseload(Task.anexos)
            )
            .filter_by(id=task_id)
            .one()
        )
        counts = task_card_counts([task_id])[task_id]
        assert serialize_task_card(loaded, counts=counts) == expected


def test_statistics_are_batched_and_empty_inputs_make_no_queries(app) -> None:
    with app.app_context():
        with SqlQueryCounter(db.engine) as queries:
            assert project_card_statistics([]) == {}
            assert task_card_counts([]) == {}
        assert queries.total == 0
        with SqlQueryCounter(db.engine) as queries:
            counts = task_card_counts(range(1, 502))
        assert len(counts) == 501
        assert queries.total == 4
        assert all(row.comments == row.attachments == 0 for row in counts.values())
