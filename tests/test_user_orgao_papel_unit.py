"""Testes unitários do papel por vínculo de área (`user_orgao.papel`).

Cobrem a validação da taxonomia (`leitor|editor|gestor`) no modelo e as duas
assinaturas de gravação de vínculos: `set_orgaos_com_papeis` (pares) e o wrapper
de compat `set_orgaos` (lista de ids, todos `gestor`).
"""

import pytest

from models import OrgaoUnidade, User, UserOrgao, db


def _criar_orgao(sigla: str) -> OrgaoUnidade:
    orgao = OrgaoUnidade(sigla=sigla, nome=sigla, tipo="Subsecretaria", ordem=0)
    db.session.add(orgao)
    db.session.flush()
    return orgao


def _criar_usuario(username: str = "vinculado") -> User:
    user = User(username=username, name="Usuário Vinculado")
    user.set_password("senha123")
    db.session.add(user)
    db.session.flush()
    return user


def _papel_por_sigla(user: User) -> dict[str, str]:
    db.session.commit()
    return {uo.orgao.sigla: uo.papel for uo in user.orgaos}


def test_set_orgaos_grava_todos_os_vinculos_como_gestor(app):
    with app.app_context():
        supdados = _criar_orgao("SUPDADOS")
        supest = _criar_orgao("SUPEST")
        user = _criar_usuario()

        user.set_orgaos([supdados.id, supest.id])

        assert _papel_por_sigla(user) == {"SUPDADOS": "gestor", "SUPEST": "gestor"}


def test_set_orgaos_com_papeis_grava_papeis_distintos(app):
    with app.app_context():
        supdados = _criar_orgao("SUPDADOS")
        supest = _criar_orgao("SUPEST")
        user = _criar_usuario()

        user.set_orgaos_com_papeis([(supdados.id, "editor"), (supest.id, "leitor")])

        assert _papel_por_sigla(user) == {"SUPDADOS": "editor", "SUPEST": "leitor"}


def test_set_orgaos_com_papeis_deduplica_por_orgao_id(app):
    with app.app_context():
        supdados = _criar_orgao("SUPDADOS")
        user = _criar_usuario()

        user.set_orgaos_com_papeis([(supdados.id, "editor"), (supdados.id, "leitor")])

        assert _papel_por_sigla(user) == {"SUPDADOS": "editor"}


def test_set_orgaos_substitui_os_vinculos_anteriores(app):
    with app.app_context():
        supdados = _criar_orgao("SUPDADOS")
        supest = _criar_orgao("SUPEST")
        user = _criar_usuario()
        user.set_orgaos_com_papeis([(supdados.id, "leitor")])
        db.session.commit()

        user.set_orgaos([supest.id])

        assert _papel_por_sigla(user) == {"SUPEST": "gestor"}


def test_vinculo_sem_papel_explicito_nasce_gestor(app):
    with app.app_context():
        supdados = _criar_orgao("SUPDADOS")
        user = _criar_usuario()

        db.session.add(UserOrgao(user_id=user.id, orgao_id=supdados.id))

        assert _papel_por_sigla(user) == {"SUPDADOS": "gestor"}


def test_papel_invalido_cita_valor_recebido_e_esperados(app):
    with app.app_context():
        supdados = _criar_orgao("SUPDADOS")
        user = _criar_usuario()

        with pytest.raises(ValueError) as exc:
            UserOrgao(user_id=user.id, orgao_id=supdados.id, papel="chefe")

        assert "chefe" in str(exc.value)
        assert "leitor|editor|gestor" in str(exc.value)
