from models import LegacyTaskRedirect, db


def test_task_detail_route_redirects_to_project_board_with_focus_task(
    client_user, seed_data
):
    response = client_user.get(
        f"/tarefas/{seed_data['task_id']}", follow_redirects=False
    )

    assert response.status_code == 302
    location = response.headers.get("Location") or ""
    assert f"/projeto/{seed_data['project_id']}/tarefas" in location
    assert f"focus_task={seed_data['task_id']}" in location


def test_task_detail_route_redirects_to_hub_for_sem_projeto_with_focus_task(
    client_user, seed_data
):
    response = client_user.get(
        f"/tarefas/{seed_data['orphan_task_id']}", follow_redirects=False
    )

    assert response.status_code == 302
    location = response.headers.get("Location") or ""
    assert "/tarefas?focus_task=" in location
    assert f"focus_task={seed_data['orphan_task_id']}" in location


def test_legacy_task_redirect_hides_cross_area_project_ids(app, client_user, seed_data):
    legacy_id = 987654
    with app.app_context():
        db.session.add(
            LegacyTaskRedirect(
                legacy_task_id=legacy_id,
                project_id=seed_data["foreign_project_id"],
                sample_task_id=seed_data["foreign_task_id"],
            )
        )
        db.session.commit()

    response = client_user.get(f"/tarefas/{legacy_id}", follow_redirects=False)

    assert response.status_code == 302
    location = response.headers.get("Location") or ""
    assert location.endswith("/tarefas")
    assert f"/projeto/{seed_data['foreign_project_id']}/tarefas" not in location
    assert f"focus_task={seed_data['foreign_task_id']}" not in location


def test_legacy_task_redirect_keeps_authorized_project_focus(
    app, client_user, seed_data
):
    legacy_id = 987655
    with app.app_context():
        db.session.add(
            LegacyTaskRedirect(
                legacy_task_id=legacy_id,
                project_id=seed_data["project_id"],
                sample_task_id=seed_data["task_id"],
            )
        )
        db.session.commit()

    response = client_user.get(f"/tarefas/{legacy_id}", follow_redirects=False)

    assert response.status_code == 302
    location = response.headers.get("Location") or ""
    assert f"/projeto/{seed_data['project_id']}/tarefas" in location
    assert f"focus_task={seed_data['task_id']}" in location
