"""Regressão: ``product_link`` na allow-list de ``apply_project_inline_changes``.

O campo "Produto" do Detalhe de Projeto passa pelo mesmo fluxo inline (fonte
única) de SEI/GitHub/Documentação. Antes não estava na allow-list, então o POST
era silenciosamente ignorado. Estes testes fixam o contrato: valor não vazio é
gravado; ``""``/``None`` viram ``None``; ausência da chave não altera o campo.

Opera direto sobre ``apply_project_inline_changes`` (fonte única dos dois fluxos
Jinja+SPA) usando o projeto semeado por ``seed_data``. Desde S3/F2-3 a função
exige rank ``editor`` no projeto, então cada teste publica em ``g.user`` o
gestor da área dona (``user_auditoria``, vínculo `gestor` do backfill).
"""

from __future__ import annotations

import pytest
from flask import g

from models import Project, User, db
from routes.projects.ajax import apply_project_inline_changes


@pytest.fixture
def projeto_com_gestor_logado(app, seed_data):
    """Cede ``(project, )`` já dentro de um contexto com ``g.user`` = gestor."""
    with app.test_request_context():
        g.user = db.session.get(User, seed_data["user_id"])
        yield db.session.get(Project, seed_data["project_id"])


def test_product_link_value_is_persisted(projeto_com_gestor_logado):
    project = projeto_com_gestor_logado

    apply_project_inline_changes(project, {"product_link": "https://produto.rj"})

    assert project.product_link == "https://produto.rj"


def test_product_link_empty_string_becomes_none(projeto_com_gestor_logado):
    project = projeto_com_gestor_logado
    project.product_link = "https://antigo.rj"

    apply_project_inline_changes(project, {"product_link": ""})

    assert project.product_link is None


def test_product_link_explicit_none_becomes_none(projeto_com_gestor_logado):
    project = projeto_com_gestor_logado
    project.product_link = "https://antigo.rj"

    apply_project_inline_changes(project, {"product_link": None})

    assert project.product_link is None


def test_product_link_absent_key_leaves_field_untouched(projeto_com_gestor_logado):
    project = projeto_com_gestor_logado
    project.product_link = "https://mantido.rj"

    apply_project_inline_changes(project, {"observacao": "outro campo"})

    assert project.product_link == "https://mantido.rj"
