from tests.routes.route_cases import ROUTE_CASES


def test_route_matrix_covers_all_registered_routes(app):
    expected_routes = set()
    for rule in app.url_map.iter_rules():
        if rule.endpoint == 'static':
            continue
        for method in sorted(rule.methods):
            if method in {'HEAD', 'OPTIONS'}:
                continue
            expected_routes.add((method, rule.rule))

    covered_routes = {(case['method'], case['rule']) for case in ROUTE_CASES}

    missing = expected_routes - covered_routes
    extra = covered_routes - expected_routes

    assert not missing, f'Rotas sem cobertura na matriz: {sorted(missing)}'
    assert not extra, f'Casos na matriz sem rota registrada: {sorted(extra)}'
    assert len(covered_routes) == 136
