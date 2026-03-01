from models import StageTemplate, StageTemplateItem, db


def test_admin_can_create_template_and_api_reflects_items(app, client_admin):
    response = client_admin.post(
        '/admin/templates/new',
        data={
            'name': 'Template Operacional',
            'description': 'Fluxo operacional',
            'stage_name': ['Diagnóstico', '', 'Entrega'],
            'stage_duration': ['2', '', '4'],
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert '/admin/templates' in response.headers['Location']

    with app.app_context():
        template = StageTemplate.query.filter_by(name='Template Operacional').first()
        assert template is not None
        assert template.description == 'Fluxo operacional'
        items = StageTemplateItem.query.filter_by(templateId=template.id).order_by(StageTemplateItem.order.asc()).all()
        assert [(item.name, item.duration_days, item.order) for item in items] == [
            ('Diagnóstico', 2, 0),
            ('Entrega', 4, 2),
        ]
        template_id = template.id

    list_response = client_admin.get('/api/templates')
    assert list_response.status_code == 200
    assert any(item == {'id': template_id, 'name': 'Template Operacional'} for item in list_response.get_json())

    detail_response = client_admin.get(f'/api/templates/{template_id}')
    assert detail_response.status_code == 200
    assert detail_response.get_json() == [
        {'name': 'Diagnóstico', 'order': 0, 'duration': 2},
        {'name': 'Entrega', 'order': 2, 'duration': 4},
    ]


def test_admin_template_create_validates_missing_name_and_stages(app, client_admin):
    response = client_admin.post(
        '/admin/templates/new',
        data={
            'name': '',
            'description': 'Inválido',
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert 'O nome do modelo e pelo menos uma etapa são obrigatórios.' in response.get_data(as_text=True)

    with app.app_context():
        assert StageTemplate.query.filter_by(description='Inválido').first() is None


def test_admin_can_edit_template_and_replace_items(app, client_admin, seed_data):
    response = client_admin.post(
        f"/admin/templates/{seed_data['template_id']}/edit",
        data={
            'name': 'Template Base Ajustado',
            'description': 'Descrição ajustada',
            'stage_name': ['Nova Etapa 1', 'Nova Etapa 2'],
            'stage_duration': ['5', '1'],
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert '/admin/templates' in response.headers['Location']

    with app.app_context():
        template = db.session.get(StageTemplate, seed_data['template_id'])
        assert template is not None
        assert template.name == 'Template Base Ajustado'
        assert template.description == 'Descrição ajustada'
        items = StageTemplateItem.query.filter_by(templateId=template.id).order_by(StageTemplateItem.order.asc()).all()
        assert [(item.name, item.duration_days, item.order) for item in items] == [
            ('Nova Etapa 1', 5, 0),
            ('Nova Etapa 2', 1, 1),
        ]

    api_response = client_admin.get(f"/api/templates/{seed_data['template_id']}")
    assert api_response.status_code == 200
    assert api_response.get_json() == [
        {'name': 'Nova Etapa 1', 'order': 0, 'duration': 5},
        {'name': 'Nova Etapa 2', 'order': 1, 'duration': 1},
    ]


def test_admin_can_delete_template_and_it_disappears_from_api(app, client_admin, seed_data):
    response = client_admin.post(
        f"/admin/templates/{seed_data['template_id']}/delete",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert '/admin/templates' in response.headers['Location']

    with app.app_context():
        assert db.session.get(StageTemplate, seed_data['template_id']) is None
        assert StageTemplateItem.query.filter_by(templateId=seed_data['template_id']).count() == 0

    api_response = client_admin.get('/api/templates')
    assert api_response.status_code == 200
    api_ids = [item['id'] for item in api_response.get_json()]
    assert seed_data['template_id'] not in api_ids
