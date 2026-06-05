"""Regressão: ``product_link`` na allow-list de ``apply_project_inline_changes``.

O campo "Produto" do Detalhe de Projeto passa pelo mesmo fluxo inline (fonte
única) de SEI/GitHub/Documentação. Antes não estava na allow-list, então o POST
era silenciosamente ignorado. Estes testes fixam o contrato: valor não vazio é
gravado; ``""``/``None`` viram ``None``; ausência da chave não altera o campo.

Opera direto sobre ``apply_project_inline_changes`` (fonte única dos dois fluxos
Jinja+SPA) usando o projeto semeado por ``seed_data``. O ramo de ``product_link``
não toca ``g.user``, então não exige sessão.
"""

from __future__ import annotations

from models import Project, db
from routes.projects.ajax import apply_project_inline_changes


def test_product_link_value_is_persisted(app, seed_data):
    with app.app_context():
        project = db.session.get(Project, seed_data["project_id"])

        apply_project_inline_changes(project, {"product_link": "https://produto.rj"})

        assert project.product_link == "https://produto.rj"


def test_product_link_empty_string_becomes_none(app, seed_data):
    with app.app_context():
        project = db.session.get(Project, seed_data["project_id"])
        project.product_link = "https://antigo.rj"

        apply_project_inline_changes(project, {"product_link": ""})

        assert project.product_link is None


def test_product_link_explicit_none_becomes_none(app, seed_data):
    with app.app_context():
        project = db.session.get(Project, seed_data["project_id"])
        project.product_link = "https://antigo.rj"

        apply_project_inline_changes(project, {"product_link": None})

        assert project.product_link is None


def test_product_link_absent_key_leaves_field_untouched(app, seed_data):
    with app.app_context():
        project = db.session.get(Project, seed_data["project_id"])
        project.product_link = "https://mantido.rj"

        apply_project_inline_changes(project, {"observacao": "outro campo"})

        assert project.product_link == "https://mantido.rj"
