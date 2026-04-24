from models import Etapa, Project, Task, TaskItem, TaskItemComment, User
from scripts.seed_fake_data import SEED_ORGAO_SIGLAS, seed_fake_data


def test_seed_fake_data_creates_expected_volume(app):
    summary = seed_fake_data(
        app,
        reset=True,
        projects=5,
        stages_per_project=3,
        tasks_per_project=2,
        items_per_task=2,
        comments_per_item=1,
        orphan_tasks=2,
        rng_seed=7,
    )

    expected_project_tasks = 5 * 2
    expected_total_tasks = expected_project_tasks + 2
    expected_items = expected_total_tasks * 2
    expected_comments = expected_items * 1
    expected_stages = 5 * 3
    expected_users = len(SEED_ORGAO_SIGLAS) + 1

    assert summary['projects'] == 5
    assert summary['stages'] == expected_stages
    assert summary['project_tasks'] == expected_project_tasks
    assert summary['orphan_tasks'] == 2
    assert summary['task_items'] == expected_items
    assert summary['task_item_comments'] == expected_comments
    assert summary['users'] == expected_users
    assert summary['projects_total_in_db'] == 5
    assert summary['tasks_total_in_db'] == expected_total_tasks
    assert summary['task_items_total_in_db'] == expected_items
    assert summary['task_item_comments_total_in_db'] == expected_comments

    with app.app_context():
        assert User.query.count() == expected_users
        assert Project.query.count() == 5
        assert Etapa.query.count() == expected_stages
        assert Task.query.count() == expected_total_tasks
        assert TaskItem.query.count() == expected_items
        assert TaskItemComment.query.count() == expected_comments


def test_seed_fake_data_reset_replaces_previous_data(app):
    seed_fake_data(
        app,
        reset=True,
        projects=3,
        stages_per_project=2,
        tasks_per_project=1,
        items_per_task=2,
        comments_per_item=1,
        orphan_tasks=1,
        rng_seed=1,
    )

    second_summary = seed_fake_data(
        app,
        reset=True,
        projects=2,
        stages_per_project=1,
        tasks_per_project=1,
        items_per_task=1,
        comments_per_item=0,
        orphan_tasks=1,
        rng_seed=2,
    )

    assert second_summary['projects_total_in_db'] == 2
    assert second_summary['project_tasks'] == 2
    assert second_summary['orphan_tasks'] == 1
    assert second_summary['tasks_total_in_db'] == 3
    assert second_summary['task_items_total_in_db'] == 3
    assert second_summary['task_item_comments_total_in_db'] == 0

    with app.app_context():
        assert Project.query.count() == 2
        assert Etapa.query.count() == 2
        assert Task.query.count() == 3
        assert TaskItem.query.count() == 3
        assert TaskItemComment.query.count() == 0
