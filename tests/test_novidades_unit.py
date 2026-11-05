"""Regras de ``services.novidades``: quem vê o quê, idempotência e gestão do admin."""

from datetime import datetime

import pytest

from models import Novidade, NovidadeVista, db
from services.novidades import (
    NovidadeInexistente,
    definir_ativa,
    listar_para_admin,
    marcar_vista,
    mostrar_de_novo,
    novidades_ativas_para,
)


def _novidade(slug: str, *, ativa: bool = True, dia: int = 1) -> Novidade:
    novidade = Novidade(
        slug=slug,
        titulo=slug.title(),
        ativa=ativa,
        publicada_em=datetime(2026, 11, dia),
    )
    db.session.add(novidade)
    db.session.flush()
    return novidade


def test_ativas_vem_da_mais_recente_e_sem_as_desligadas(app, seed_data):
    with app.app_context():
        _novidade("antiga", dia=1)
        _novidade("recente", dia=5)
        _novidade("desligada", ativa=False, dia=9)
        slugs = [item["slug"] for item in novidades_ativas_para(seed_data["user_id"])]
    assert slugs == ["recente", "antiga"]


def test_vista_e_por_pessoa(app, seed_data):
    with app.app_context():
        _novidade("colecoes")
        marcar_vista(seed_data["user_id"], "colecoes", concluida=False)
        db.session.commit()
        do_user = novidades_ativas_para(seed_data["user_id"])
        do_admin = novidades_ativas_para(seed_data["admin_id"])
    assert [item["vista"] for item in do_user] == [True]
    assert [item["vista"] for item in do_admin] == [False]


def test_marcar_vista_e_idempotente_e_so_promove_a_concluida(app, seed_data):
    with app.app_context():
        _novidade("colecoes")
        marcar_vista(seed_data["user_id"], "colecoes", concluida=False)
        marcar_vista(seed_data["user_id"], "colecoes", concluida=True)
        marcar_vista(seed_data["user_id"], "colecoes", concluida=False)
        db.session.commit()
        vistas = NovidadeVista.query.all()
    assert len(vistas) == 1
    assert vistas[0].concluida is True


@pytest.mark.parametrize("slug,ativa", [("inexistente", True), ("desligada", False)])
def test_marcar_vista_recusa_inexistente_ou_desligada(app, seed_data, slug, ativa):
    with app.app_context():
        _novidade("desligada", ativa=ativa)
        with pytest.raises(NovidadeInexistente):
            marcar_vista(seed_data["user_id"], slug, concluida=True)


def test_admin_ve_todas_com_alcance(app, seed_data):
    with app.app_context():
        _novidade("colecoes", dia=5)
        _novidade("rascunho", ativa=False, dia=1)
        marcar_vista(seed_data["user_id"], "colecoes", concluida=True)
        marcar_vista(seed_data["admin_id"], "colecoes", concluida=False)
        db.session.commit()
        itens = {item["slug"]: item for item in listar_para_admin()}
    assert (itens["colecoes"]["vistas"], itens["colecoes"]["concluidas"]) == (2, 1)
    assert (itens["rascunho"]["vistas"], itens["rascunho"]["ativa"]) == (0, False)


def test_desligar_tira_da_lista_e_religar_devolve(app, seed_data):
    with app.app_context():
        _novidade("colecoes")
        definir_ativa("colecoes", False)
        assert novidades_ativas_para(seed_data["user_id"]) == []
        definir_ativa("colecoes", True)
        assert [i["slug"] for i in novidades_ativas_para(seed_data["user_id"])] == [
            "colecoes"
        ]


def test_mostrar_de_novo_apaga_as_vistas(app, seed_data):
    with app.app_context():
        _novidade("colecoes")
        marcar_vista(seed_data["user_id"], "colecoes", concluida=True)
        db.session.commit()
        assert mostrar_de_novo("colecoes") == 1
        db.session.commit()
        assert [i["vista"] for i in novidades_ativas_para(seed_data["user_id"])] == [
            False
        ]


def test_gestao_com_slug_inexistente_erra(app, seed_data):
    with app.app_context():
        with pytest.raises(NovidadeInexistente):
            definir_ativa("nao-existe", True)
        with pytest.raises(NovidadeInexistente):
            mostrar_de_novo("nao-existe")
