from models import AreaCatalog, Project, UserArea, db


def test_admin_can_create_area(client_admin, app):
    response = client_admin.post(
        '/admin/areas/new',
        data={'name': 'Nova Area Admin'},
        follow_redirects=False,
    )

    assert response.status_code == 302

    with app.app_context():
        created = AreaCatalog.query.filter_by(name='Nova Area Admin').first()
        assert created is not None


def test_admin_area_create_rejects_duplicate_name(client_admin, app):
    response = client_admin.post(
        '/admin/areas/new',
        data={'name': 'auditoria'},
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Já existe uma área com esse nome.' in html

    with app.app_context():
        assert AreaCatalog.query.filter_by(name='Auditoria').count() == 1


def test_admin_area_create_rejects_empty_name(client_admin):
    response = client_admin.post(
        '/admin/areas/new',
        data={'name': '   '},
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'O nome da área é obrigatório.' in html


def test_admin_area_edit_renames_and_propagates_to_projects_and_user_links(client_admin, app, seed_data):
    response = client_admin.post(
        f'/admin/areas/{seed_data["auditoria_area_id"]}/edit',
        data={'name': 'Auditoria Estratégica'},
        follow_redirects=False,
    )

    assert response.status_code == 302

    with app.app_context():
        area = AreaCatalog.query.filter_by(id=seed_data['auditoria_area_id']).first()
        assert area is not None
        assert area.name == 'Auditoria Estratégica'

        project = db.session.get(Project, seed_data['project_id'])
        assert project is not None
        assert project.area_responsavel == 'Auditoria Estratégica'

        project_complete = db.session.get(Project, seed_data['project_complete_id'])
        assert project_complete is not None
        assert project_complete.area_responsavel == 'Auditoria Estratégica'

        linked_areas = {
            row.area
            for row in UserArea.query.filter(
                UserArea.user_id.in_([seed_data['admin_id'], seed_data['user_id']])
            ).all()
        }
        assert 'Auditoria Estratégica' in linked_areas
        assert 'Auditoria' not in linked_areas


def test_admin_area_delete_is_blocked_when_projects_are_associated(client_admin, app, seed_data):
    response = client_admin.post(
        f'/admin/areas/{seed_data["auditoria_area_id"]}/delete',
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Não é possível excluir a área' in html

    with app.app_context():
        area = db.session.get(AreaCatalog, seed_data['auditoria_area_id'])
        assert area is not None


def test_admin_area_delete_without_projects_removes_user_links(client_admin, app, seed_data):
    with app.app_context():
        area = AreaCatalog(name='Area Sem Projeto')
        db.session.add(area)
        db.session.flush()
        db.session.add(UserArea(user_id=seed_data['deletable_user_id'], area='Area Sem Projeto'))
        db.session.commit()
        area_id = area.id

    response = client_admin.post(f'/admin/areas/{area_id}/delete', follow_redirects=False)
    assert response.status_code == 302

    with app.app_context():
        deleted_area = db.session.get(AreaCatalog, area_id)
        assert deleted_area is None
        remaining_links = UserArea.query.filter_by(
            user_id=seed_data['deletable_user_id'],
            area='Area Sem Projeto',
        ).count()
        assert remaining_links == 0
