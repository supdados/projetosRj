from models import StageTemplate, StageTemplateItem, db


def test_admin_can_create_template_and_api_reflects_items(app, client_admin):
    response = client_admin.post(
        "/admin/templates/new",
        data={
            "name": "Template Operacional",
            "description": "Fluxo operacional",
            "stage_name": ["Diagnóstico", "", "Entrega"],
            "stage_duration": ["2", "", "4"],
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/admin/templates" in response.headers["Location"]

    with app.app_context():
        template = StageTemplate.query.filter_by(name="Template Operacional").first()
        assert template is not None
        assert template.description == "Fluxo operacional"
        items = (
            StageTemplateItem.query.filter_by(templateId=template.id)
            .order_by(StageTemplateItem.order.asc())
            .all()
        )
        assert [(item.name, item.duration_days, item.order) for item in items] == [
            ("Diagnóstico", 2, 0),
            ("Entrega", 4, 2),
        ]
        template_id = template.id

    list_response = client_admin.get("/api/templates")
    assert list_response.status_code == 200
    payload = list_response.get_json()
    entry = next((item for item in payload if item["id"] == template_id), None)
    assert entry is not None
    assert entry["name"] == "Template Operacional"
    assert entry["stage_count"] == 2
    assert entry["total_duration_days"] == 6

    detail_response = client_admin.get(f"/api/templates/{template_id}")
    assert detail_response.status_code == 200
    assert detail_response.get_json() == [
        {"name": "Diagnóstico", "order": 0, "duration": 2},
        {"name": "Entrega", "order": 2, "duration": 4},
    ]


def test_admin_template_create_validates_missing_name_and_stages(app, client_admin):
    response = client_admin.post(
        "/admin/templates/new",
        data={
            "name": "",
            "description": "Inválido",
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert (
        "O nome do modelo e pelo menos uma etapa são obrigatórios."
        in response.get_data(as_text=True)
    )

    with app.app_context():
        assert StageTemplate.query.filter_by(description="Inválido").first() is None


def test_admin_can_edit_template_and_replace_items(app, client_admin, seed_data):
    response = client_admin.post(
        f"/admin/templates/{seed_data['template_id']}/edit",
        data={
            "name": "Template Base Ajustado",
            "description": "Descrição ajustada",
            "stage_name": ["Nova Etapa 1", "Nova Etapa 2"],
            "stage_duration": ["5", "1"],
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/admin/templates" in response.headers["Location"]

    with app.app_context():
        template = db.session.get(StageTemplate, seed_data["template_id"])
        assert template is not None
        assert template.name == "Template Base Ajustado"
        assert template.description == "Descrição ajustada"
        items = (
            StageTemplateItem.query.filter_by(templateId=template.id)
            .order_by(StageTemplateItem.order.asc())
            .all()
        )
        assert [(item.name, item.duration_days, item.order) for item in items] == [
            ("Nova Etapa 1", 5, 0),
            ("Nova Etapa 2", 1, 1),
        ]

    api_response = client_admin.get(f"/api/templates/{seed_data['template_id']}")
    assert api_response.status_code == 200
    assert api_response.get_json() == [
        {"name": "Nova Etapa 1", "order": 0, "duration": 5},
        {"name": "Nova Etapa 2", "order": 1, "duration": 1},
    ]


def test_admin_can_delete_template_and_it_disappears_from_api(
    app, client_admin, seed_data
):
    response = client_admin.post(
        f"/admin/templates/{seed_data['template_id']}/delete",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/admin/templates" in response.headers["Location"]

    with app.app_context():
        assert db.session.get(StageTemplate, seed_data["template_id"]) is None
        assert (
            StageTemplateItem.query.filter_by(
                templateId=seed_data["template_id"]
            ).count()
            == 0
        )

    api_response = client_admin.get("/api/templates")
    assert api_response.status_code == 200
    api_ids = [item["id"] for item in api_response.get_json()]
    assert seed_data["template_id"] not in api_ids


def test_api_templates_exposes_stage_count_and_total_duration(app, client_admin):
    with app.app_context():
        tpl = StageTemplate(name="API Stats Modelo")
        db.session.add(tpl)
        db.session.flush()
        db.session.add(
            StageTemplateItem(name="A", duration_days=3, order=0, templateId=tpl.id)
        )
        db.session.add(
            StageTemplateItem(name="B", duration_days=5, order=1, templateId=tpl.id)
        )
        db.session.add(
            StageTemplateItem(name="C", duration_days=2, order=2, templateId=tpl.id)
        )
        db.session.commit()
        tpl_id = tpl.id

    response = client_admin.get("/api/templates")
    assert response.status_code == 200
    payload = response.get_json()
    entry = next((item for item in payload if item["id"] == tpl_id), None)
    assert entry == {
        "id": tpl_id,
        "name": "API Stats Modelo",
        "stage_count": 3,
        "total_duration_days": 10,
    }


def test_admin_can_duplicate_template(app, client_admin, seed_data):
    original_id = seed_data["template_id"]

    response = client_admin.post(
        f"/admin/templates/{original_id}/duplicate",
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/admin/templates" in response.headers["Location"]

    with app.app_context():
        original = db.session.get(StageTemplate, original_id)
        copy = StageTemplate.query.filter(
            StageTemplate.name == f"{original.name} (cópia)"
        ).first()
        assert copy is not None
        assert copy.id != original_id
        original_items = (
            StageTemplateItem.query.filter_by(templateId=original_id)
            .order_by(StageTemplateItem.order)
            .all()
        )
        copy_items = (
            StageTemplateItem.query.filter_by(templateId=copy.id)
            .order_by(StageTemplateItem.order)
            .all()
        )
        assert [(i.name, i.duration_days, i.order) for i in copy_items] == [
            (i.name, i.duration_days, i.order) for i in original_items
        ]


def test_admin_template_edit_preserves_getlist_order_with_five_stages(
    app, client_admin, seed_data
):
    stage_names = ["Alpha", "Bravo", "Charlie", "Delta", "Echo"]
    stage_durations = ["1", "2", "3", "4", "5"]
    response = client_admin.post(
        f"/admin/templates/{seed_data['template_id']}/edit",
        data={
            "name": "Ordering Check",
            "description": "",
            "stage_name": stage_names,
            "stage_duration": stage_durations,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        items = (
            StageTemplateItem.query.filter_by(templateId=seed_data["template_id"])
            .order_by(StageTemplateItem.order.asc())
            .all()
        )
        assert [(i.name, i.duration_days, i.order) for i in items] == [
            ("Alpha", 1, 0),
            ("Bravo", 2, 1),
            ("Charlie", 3, 2),
            ("Delta", 4, 3),
            ("Echo", 5, 4),
        ]


def test_admin_templates_list_filters_by_query(client_admin, app):
    with app.app_context():
        db.session.add(
            StageTemplate(name="Aquisição Direta", description="Para compras rápidas")
        )
        db.session.add(
            StageTemplateItem(
                name="Etapa Única",
                duration_days=1,
                order=0,
                templateId=StageTemplate.query.filter_by(name="Aquisição Direta")
                .first()
                .id,
            )
        )
        db.session.commit()

    response = client_admin.get("/admin/templates?q=Aquisição")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Aquisição Direta" in html
    assert "Template Base" not in html


def test_admin_templates_list_order_nome_respects_alphabetical(client_admin, app):
    with app.app_context():
        db.session.add(StageTemplate(name="Zeta Modelo"))
        db.session.add(StageTemplate(name="Alfa Modelo"))
        db.session.commit()

    response = client_admin.get("/admin/templates?order=nome")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    pos_alfa = html.find("Alfa Modelo")
    pos_zeta = html.find("Zeta Modelo")
    assert pos_alfa != -1 and pos_zeta != -1
    assert pos_alfa < pos_zeta


def test_admin_templates_list_paginates_at_page_size(client_admin, app):
    with app.app_context():
        # seed_data já criou 1; cria mais 10 para forçar pagina 2
        for i in range(10):
            tpl = StageTemplate(name=f"Modelo Extra {i:02d}")
            db.session.add(tpl)
            db.session.flush()
            db.session.add(
                StageTemplateItem(
                    name="X",
                    duration_days=1,
                    order=0,
                    templateId=tpl.id,
                )
            )
        db.session.commit()

    page1 = client_admin.get("/admin/templates?order=nome")
    assert page1.status_code == 200
    assert "Modelo Extra 00" in page1.get_data(as_text=True)

    page2 = client_admin.get("/admin/templates?order=nome&page=2")
    assert page2.status_code == 200
    html2 = page2.get_data(as_text=True)
    # Na página 2 o 11º por ordem alfabética deve aparecer
    assert "tpl-pagination" in html2 or "Template Base" in html2
