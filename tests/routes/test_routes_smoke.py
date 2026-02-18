import pytest

from tests.routes.route_cases import ROUTE_CASES


def _format_payload(value, context):
    if isinstance(value, str):
        return value.format(**context)
    if isinstance(value, list):
        return [_format_payload(item, context) for item in value]
    if isinstance(value, tuple):
        return tuple(_format_payload(item, context) for item in value)
    if isinstance(value, dict):
        return {key: _format_payload(item, context) for key, item in value.items()}
    return value


def _resolve_request(case, seed_data):
    context = dict(seed_data)
    path = case['path'].format(**context)
    request_kwargs = {}
    for key in ('data', 'json', 'headers', 'query_string'):
        if key in case:
            request_kwargs[key] = _format_payload(case[key], context)
    return path, request_kwargs


def _pick_client(case, *, client, client_user, client_admin, client_outsider):
    role = case['role']
    if role == 'anon':
        return client
    if role == 'user':
        return client_user
    if role == 'admin':
        return client_admin
    if role == 'outsider':
        return client_outsider
    raise ValueError(f'Role nao suportado no caso {case["id"]}: {role}')


def _assert_expected_status(response, expected_status):
    if isinstance(expected_status, int):
        assert response.status_code == expected_status
        return
    assert response.status_code in set(expected_status)


@pytest.mark.parametrize('case', ROUTE_CASES, ids=[case['id'] for case in ROUTE_CASES])
def test_routes_smoke(case, client, client_user, client_admin, client_outsider, seed_data):
    http_client = _pick_client(
        case,
        client=client,
        client_user=client_user,
        client_admin=client_admin,
        client_outsider=client_outsider,
    )
    path, request_kwargs = _resolve_request(case, seed_data)

    response = http_client.open(
        path,
        method=case['method'],
        follow_redirects=False,
        **request_kwargs,
    )

    _assert_expected_status(response, case['expected_status'])
    assert response.status_code < 500
