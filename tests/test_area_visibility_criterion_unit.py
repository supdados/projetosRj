"""``area_visibility_criterion``: SQL de "vejo este projeto PELA ÁREA".

É o conjunto que o picker do EDITOR de coleção lista (``?visibilidade=area``)
e que ``adicionar_projeto`` aceita dele (``area_project_rank >= leitor``). Os
dois lados precisam bater — senão o picker oferece projeto que o backend
recusa no meio do lote, ou esconde projeto que o editor poderia incluir. O
bypass do admin mora no service (gate F0-6), não na rota.
"""

from __future__ import annotations

import pytest

from models import OrgaoUnidade, Project, ProjectMember, User, UserOrgao, db
from services.authorization import (
    PAPEL_LEITOR,
    PAPEL_RANK,
    area_project_rank,
    area_visibility_criterion,
)


def _orgao(sigla: str, pai_id: int | None) -> int:
    orgao = OrgaoUnidade(
        sigla=sigla, nome=sigla, tipo="Secretaria", pai_id=pai_id, ordem=0
    )
    db.session.add(orgao)
    db.session.flush()
    return orgao.id


def _usuario(username: str, *, is_admin: bool = False) -> User:
    usuario = User(username=username, name=username, is_admin=is_admin)
    usuario.set_password("senha123")
    db.session.add(usuario)
    db.session.flush()
    return usuario


def _projeto(titulo: str, orgao_id: int | None) -> int:
    projeto = Project(titulo=titulo, orgao_id=orgao_id, status="Vigente")
    db.session.add(projeto)
    db.session.flush()
    return projeto.id


@pytest.fixture
def cenario_area(app):
    """SEC → SUB e OUTRA; leitor lotado em SEC e convidado só por projeto."""
    with app.app_context():
        sec = _orgao("AVSEC", None)
        sub = _orgao("AVSUB", sec)
        outra = _orgao("AVOUTRA", None)
        projetos = {
            "sec": _projeto("Na raiz", sec),
            "sub": _projeto("No filho", sub),
            "outra": _projeto("Em outra área", outra),
            "sem_orgao": _projeto("Sem órgão", None),
        }
        admin = _usuario("av_admin", is_admin=True)
        leitor = _usuario("av_leitor")
        db.session.add(UserOrgao(user_id=leitor.id, orgao_id=sec, papel=PAPEL_LEITOR))
        convidado = _usuario("av_convidado")
        db.session.add(
            ProjectMember(
                project_id=projetos["outra"],
                user_id=convidado.id,
                papel=PAPEL_LEITOR,
                granted_by_id=admin.id,
            )
        )
        db.session.commit()
        yield {
            "projetos": projetos,
            "admin": admin.id,
            "leitor": leitor.id,
            "convidado": convidado.id,
        }


def _ids_pela_area(user: User | None) -> set[int]:
    query = db.session.query(Project.id).filter(area_visibility_criterion(user))
    return {project_id for (project_id,) in query}


def test_leitor_ve_a_subarvore_e_nada_fora_dela(app, cenario_area):
    projetos = cenario_area["projetos"]
    with app.test_request_context("/"):
        leitor = db.session.get(User, cenario_area["leitor"])
        assert _ids_pela_area(leitor) == {projetos["sec"], projetos["sub"]}


def test_admin_ve_tudo_inclusive_projeto_sem_orgao(app, cenario_area):
    with app.test_request_context("/"):
        admin = db.session.get(User, cenario_area["admin"])
        assert _ids_pela_area(admin) == set(cenario_area["projetos"].values())


def test_convite_de_projeto_nao_conta_como_area(app, cenario_area):
    """Editor que só vê por convite não inclui (decisão 3): o picker esconde."""
    with app.test_request_context("/"):
        convidado = db.session.get(User, cenario_area["convidado"])
        assert _ids_pela_area(convidado) == set()


def test_sem_usuario_nao_ve_nada(app, cenario_area):
    with app.test_request_context("/"):
        assert _ids_pela_area(None) == set()


@pytest.mark.parametrize("quem", ["admin", "leitor", "convidado"])
def test_criterion_equivale_ao_area_project_rank(app, cenario_area, quem):
    """``pid`` no SQL ⇔ ``area_project_rank >= leitor`` — a regra do aceite."""
    with app.test_request_context("/"):
        user = db.session.get(User, cenario_area[quem])
        esperados = {
            projeto.id
            for projeto in Project.query.all()
            if area_project_rank(user, projeto) >= PAPEL_RANK[PAPEL_LEITOR]
        }
        assert _ids_pela_area(user) == esperados
