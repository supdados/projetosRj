import pytest

from tests.routes.route_cases import ADMIN_REQUIRED_CASES, LOGIN_REQUIRED_CASES


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


@pytest.mark.parametrize('case', LOGIN_REQUIRED_CASES, ids=[case['id'] for case in LOGIN_REQUIRED_CASES])
def test_login_required_routes_redirect_when_anonymous(case, client, seed_data):
    path, request_kwargs = _resolve_request(case, seed_data)
    response = client.open(path, method=case['method'], follow_redirects=False, **request_kwargs)

    assert response.status_code == 302
    assert '/login' in (response.headers.get('Location') or '')


@pytest.mark.parametrize('case', ADMIN_REQUIRED_CASES, ids=[case['id'] for case in ADMIN_REQUIRED_CASES])
def test_admin_routes_redirect_for_non_admin(case, client_user, seed_data):
    path, request_kwargs = _resolve_request(case, seed_data)
    response = client_user.open(path, method=case['method'], follow_redirects=False, **request_kwargs)

    assert response.status_code == 302
    assert '/dashboard' in (response.headers.get('Location') or '')


AREA_PROTECTED_CASES = [
    {
        'id': 'outsider_project_detail',
        'method': 'GET',
        'path': '/project/{project_id}',
        'expected_status': 302,
        'redirect_contains': '/projects',
    },
    {
        'id': 'outsider_project_edit_data',
        'method': 'GET',
        'path': '/project/{project_id}/edit_data',
        'expected_status': 403,
    },
    {
        'id': 'outsider_project_update_inline',
        'method': 'POST',
        'path': '/project/{project_id}/update_inline',
        'json': {'titulo': 'Nao pode editar'},
        'expected_status': 403,
    },
    {
        'id': 'outsider_project_delete',
        'method': 'POST',
        'path': '/project/{project_id}/delete',
        'expected_status': 302,
        'redirect_contains': '/projects',
    },
    {
        'id': 'outsider_project_history',
        'method': 'GET',
        'path': '/project/{project_id}/history',
        'expected_status': 302,
        'redirect_contains': '/projects',
    },
    {
        'id': 'outsider_etapas_reorder',
        'method': 'POST',
        'path': '/project/{project_id}/etapas/reordenar',
        'json': {'etapa_ids': ['{etapa_id}']},
        'expected_status': 403,
    },
    {
        'id': 'outsider_etapa_toggle_iniciada',
        'method': 'POST',
        'path': '/etapa/{etapa_id}/toggle_iniciada',
        'expected_status': 403,
    },
    {
        'id': 'outsider_etapa_update_field',
        'method': 'POST',
        'path': '/etapa/{etapa_id}/update_field',
        'json': {'field': 'descricao', 'value': 'Bloqueado'},
        'expected_status': 403,
    },
    {
        'id': 'outsider_project_cascade_update',
        'method': 'POST',
        'path': '/project/{project_id}/cascade_update',
        'json': {'etapa_id': '{etapa_id}', 'days_diff': 1},
        'expected_status': 403,
    },
    {
        'id': 'outsider_task_detail',
        'method': 'GET',
        'path': '/tarefas/{task_id}',
        'expected_status': 302,
        'redirect_contains': '/tarefas',
    },
    {
        'id': 'outsider_task_edit',
        'method': 'POST',
        'path': '/tarefas/{task_id}/edit',
        'data': {'titulo': 'Bloqueado', 'project_id': '{project_id}'},
        'expected_status': 403,
    },
    {
        'id': 'outsider_task_update_status',
        'method': 'POST',
        'path': '/tarefas/{task_id}/update_status',
        'json': {'status': 'em_andamento'},
        'expected_status': 403,
    },
    {
        'id': 'outsider_task_update_prioridade',
        'method': 'POST',
        'path': '/tarefas/{task_id}/update_prioridade',
        'json': {'prioridade': 'alta'},
        'expected_status': 403,
    },
    {
        'id': 'outsider_task_update_tipo',
        'method': 'POST',
        'path': '/tarefas/{task_id}/update_tipo',
        'json': {'tipo_pedido': 'bug'},
        'expected_status': 403,
    },
    {
        'id': 'outsider_task_item_add',
        'method': 'POST',
        'path': '/tarefas/{task_id}/itens/add',
        'headers': {'X-Requested-With': 'XMLHttpRequest'},
        'data': {'descricao': 'Item bloqueado'},
        'expected_status': 403,
    },
    {
        'id': 'outsider_task_item_global_add',
        'method': 'POST',
        'path': '/tarefas/itens/add',
        'headers': {'X-Requested-With': 'XMLHttpRequest'},
        'data': {'project': '{project_id}', 'descricao': 'Item bloqueado'},
        'expected_status': 403,
    },
    {
        'id': 'outsider_task_suggestions',
        'method': 'GET',
        'path': '/tarefas/{task_id}/sugestoes-responsavel',
        'expected_status': 403,
    },
    {
        'id': 'outsider_task_comment_add_canonical',
        'method': 'POST',
        'path': '/tarefas/{task_id}/comentarios/add',
        'headers': {'X-Requested-With': 'XMLHttpRequest'},
        'data': {'content': 'Comentario sem permissao'},
        'expected_status': 403,
    },
    {
        'id': 'outsider_task_anexos_list_canonical',
        'method': 'GET',
        'path': '/tarefas/{task_id}/anexos',
        'expected_status': 403,
    },
    {
        'id': 'outsider_task_anexo_add_canonical',
        'method': 'POST',
        'path': '/tarefas/{task_id}/anexos/add',
        'expected_status': 403,
    },
    {
        'id': 'outsider_task_hub_suggestions',
        'method': 'GET',
        'path': '/tarefas/sugestoes-responsavel',
        'query_string': {'project': '{project_id}'},
        'expected_status': 403,
    },
    {
        'id': 'outsider_task_finalize',
        'method': 'POST',
        'path': '/tarefas/{task_id}/finalizar',
        'expected_status': 302,
        'redirect_contains': '/tarefas',
    },
    {
        'id': 'outsider_task_reactivate',
        'method': 'POST',
        'path': '/tarefas/{task_id}/reativar',
        'expected_status': 403,
    },
    {
        'id': 'outsider_task_desarquivar',
        'method': 'POST',
        'path': '/tarefas/{task_id}/desarquivar',
        'expected_status': 403,
    },
]


@pytest.mark.parametrize('case', AREA_PROTECTED_CASES, ids=[case['id'] for case in AREA_PROTECTED_CASES])
def test_area_protected_routes_block_outsider(case, client_outsider, seed_data):
    path, request_kwargs = _resolve_request(case, seed_data)
    response = client_outsider.open(path, method=case['method'], follow_redirects=False, **request_kwargs)

    assert response.status_code == case['expected_status']
    if response.status_code == 302 and case.get('redirect_contains'):
        assert case['redirect_contains'] in (response.headers.get('Location') or '')
