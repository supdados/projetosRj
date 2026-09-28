"""P2-16/17: listagens não materializam filhos usados apenas em estatísticas."""

import time

import pytest
from flask.testing import FlaskClient

from models import db
from scripts.benchmarks.review_read_fixtures import seed_read_workload
from tests.model_load_counter import ModelLoadCounter
from tests.sql_query_counter import SqlQueryCounter


@pytest.fixture
def dense_client(app, client) -> FlaskClient:
    with app.app_context():
        viewer_id = seed_read_workload(25)
    with client.session_transaction() as session:
        session["user_id"] = viewer_id
        session["login_at"] = time.time()
    return client


@pytest.mark.parametrize(
    "endpoint",
    ["/api/projetos", "/api/dashboard", "/api/tarefas/board", "/api/tarefas"],
)
def test_cards_use_aggregates_instead_of_loading_stage_comment_attachment_objects(
    dense_client, endpoint
) -> None:
    with ModelLoadCounter() as loaded:
        response = dense_client.get(endpoint)
    assert response.status_code == 200
    assert loaded.counts["TaskComment"] == loaded.counts["TaskAnexo"] == 0
    if (
        endpoint != "/api/tarefas"
    ):  # Lista usa etapas para agrupamento, sem carregar seus filhos.
        assert loaded.counts["Etapa"] == 0


def test_shared_collection_owners_are_loaded_with_the_collection(
    app, dense_client
) -> None:
    with app.app_context():
        engine = db.engine
    with SqlQueryCounter(engine) as queries:
        response = dense_client.get("/api/colecoes")
    assert response.status_code == 200
    shared = [
        row
        for row in response.get_json()["data"]["colecoes"]
        if row["owner"] is not None
    ]
    assert len(shared) == 25
    assert queries.total <= 20
