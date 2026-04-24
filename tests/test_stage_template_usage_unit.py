"""Testes do rastreamento de uso de modelos de etapas.

Cobre os dois caminhos de registro:
- StageTemplateUsage(source='creation') quando o projeto é criado com modelo.
- StageTemplateUsage(source='post_import') quando o modelo é importado em projeto existente.
"""

from models import StageTemplate, StageTemplateUsage, db
from sqlalchemy import func


def _create_project_from_template(client, seed_data, template_id, titulo):
    return client.post(
        "/add_project",
        data={
            "project_titulo": titulo,
            "project_orgao_id": str(seed_data["auditoria_orgao_id"]),
            "project_orgao": "Orgao A",
            "project_prioridade": "media",
            "project_objetivo_id": "1",
            "project_resultado_esperado_id": "1",
            "project_template_id": str(template_id),
            "etapa_descricao": ["Planejamento", "Execucao"],
            "etapa_duration": ["2", "3"],
        },
        follow_redirects=False,
    )


def test_creation_with_template_registers_usage(app, client_admin, seed_data):
    template_id = seed_data["template_id"]

    response = _create_project_from_template(
        client_admin, seed_data, template_id, "Projeto Rastreado"
    )
    assert response.status_code == 302

    with app.app_context():
        usages = StageTemplateUsage.query.filter_by(template_id=template_id).all()
        creation_usages = [u for u in usages if u.source == "creation"]
        assert len(creation_usages) == 1
        assert creation_usages[0].project_id is not None


def test_creation_without_template_does_not_register_usage(
    app, client_admin, seed_data
):
    response = client_admin.post(
        "/add_project",
        data={
            "project_titulo": "Projeto Sem Modelo",
            "project_orgao_id": str(seed_data["auditoria_orgao_id"]),
            "project_orgao": "Orgao A",
            "project_prioridade": "media",
            "project_objetivo_id": "1",
            "project_resultado_esperado_id": "1",
            "etapa_descricao": ["Etapa livre"],
            "etapa_duration": ["1"],
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        assert StageTemplateUsage.query.count() == 0


def test_creation_with_invalid_template_id_does_not_register(
    app, client_admin, seed_data
):
    response = client_admin.post(
        "/add_project",
        data={
            "project_titulo": "Projeto Template Invalido",
            "project_orgao_id": str(seed_data["auditoria_orgao_id"]),
            "project_orgao": "Orgao A",
            "project_prioridade": "media",
            "project_objetivo_id": "1",
            "project_resultado_esperado_id": "1",
            "project_template_id": "999999",
            "etapa_descricao": ["Etapa"],
            "etapa_duration": ["1"],
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        assert StageTemplateUsage.query.count() == 0


def test_import_model_after_creation_registers_post_import(
    app, client_admin, seed_data
):
    project_id = seed_data["project_id"]
    template_id = seed_data["template_id"]

    response = client_admin.post(
        f"/project/{project_id}/import_model",
        data={
            "template_id": str(template_id),
            "start_date": "2026-05-01",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        usages = StageTemplateUsage.query.filter_by(
            template_id=template_id, project_id=project_id
        ).all()
        post_import_usages = [u for u in usages if u.source == "post_import"]
        assert len(post_import_usages) == 1


def test_distinct_project_count_matches_expectation(app, client_admin, seed_data):
    template_id = seed_data["template_id"]
    project_id = seed_data["project_id"]

    # Primeiro uso: import pós-criação no project_id
    client_admin.post(
        f"/project/{project_id}/import_model",
        data={"template_id": str(template_id), "start_date": "2026-05-01"},
    )
    # Segundo uso: novo projeto criado a partir do modelo
    _create_project_from_template(
        client_admin, seed_data, template_id, "Projeto Contagem"
    )
    # Terceiro uso: import novamente no mesmo project_id (não deve inflar distinct)
    client_admin.post(
        f"/project/{project_id}/import_model",
        data={"template_id": str(template_id), "start_date": "2026-06-01"},
    )

    with app.app_context():
        distinct_projects = (
            db.session.query(func.count(func.distinct(StageTemplateUsage.project_id)))
            .filter(StageTemplateUsage.template_id == template_id)
            .scalar()
        )
        assert distinct_projects == 2


def test_template_audit_fields_on_create(app, client_admin, seed_data):
    response = client_admin.post(
        "/admin/templates/new",
        data={
            "name": "Modelo Auditoria",
            "description": "Teste de auditoria",
            "stage_name": ["Etapa A"],
            "stage_duration": ["1"],
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        template = StageTemplate.query.filter_by(name="Modelo Auditoria").first()
        assert template is not None
        assert template.created_at is not None
        assert template.updated_at is not None
        assert template.created_by_id == seed_data["admin_id"]
        assert template.updated_by_id == seed_data["admin_id"]


def test_template_updated_by_changes_on_edit(app, client_admin, seed_data):
    template_id = seed_data["template_id"]

    response = client_admin.post(
        f"/admin/templates/{template_id}/edit",
        data={
            "name": "Modelo Editado",
            "description": "Auditoria update",
            "stage_name": ["Nova"],
            "stage_duration": ["2"],
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        template = db.session.get(StageTemplate, template_id)
        assert template.updated_by_id == seed_data["admin_id"]
