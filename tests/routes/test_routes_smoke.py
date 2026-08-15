import pytest
import time

from tests.routes.request_payloads import resolve_request
from tests.routes.route_cases import ROUTE_CASES


def _login(client, user_id):
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["login_at"] = time.time()


def _build_client(case, app, seed_data):
    client = app.test_client()
    role = case["role"]
    if role == "anon":
        return client
    if role == "user":
        _login(client, seed_data["user_id"])
        return client
    if role == "admin":
        _login(client, seed_data["admin_id"])
        return client
    if role == "outsider":
        _login(client, seed_data["outsider_id"])
        return client
    raise ValueError(f'Role nao suportado no caso {case["id"]}: {role}')


def _allowed_statuses(expected_status):
    if isinstance(expected_status, int):
        return {expected_status}
    return set(expected_status)


def _assert_expected_status(response, expected_status):
    assert response.status_code in _allowed_statuses(expected_status)


def _assert_no_unhandled_server_error(response, expected_status):
    """5xx só passa se o caso o declarar — o guard caça crash, não resposta de projeto."""
    assert response.status_code < 500 or response.status_code in _allowed_statuses(
        expected_status
    )


@pytest.mark.parametrize("case", ROUTE_CASES, ids=[case["id"] for case in ROUTE_CASES])
def test_routes_smoke(case, app, seed_data):
    http_client = _build_client(case, app, seed_data)
    path, request_kwargs = resolve_request(case, seed_data)

    response = http_client.open(
        path,
        method=case["method"],
        follow_redirects=False,
        **request_kwargs,
    )

    _assert_expected_status(response, case["expected_status"])
    _assert_no_unhandled_server_error(response, case["expected_status"])
