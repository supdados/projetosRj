"""Testes de services/project_relations.py — vínculo simétrico entre projetos.

Cobre o domínio que a rota não pode reimplementar (canonicalização do par,
duplicata, auto-vínculo, teto de 12 contado só na origem, corrida de INSERT e o
filtro de visibilidade da leitura) e as regressões que a feature obriga: limpeza
dos vínculos antes do delete do projeto, histórico só na origem, zero
notificação e custo de query constante na leitura.

O service não commita: os testes rodam no app context da fixture ``cenario`` e
fazem flush/commit explícitos.
"""

import pytest
from flask import g
from sqlalchemy.exc import IntegrityError

from models import (
    OrgaoUnidade,
    Project,
    ProjectHistory,
    ProjectRelation,
    User,
    UserNotification,
    UserOrgao,
    db,
)
from routes.shared import log_project_action
from services import project_relations
from services.authorization import (
    COLLECTION_RANK_CACHE_ATTR,
    MEMBERSHIP_MAP_CACHE_ATTR,
    ROLE_MAP_CACHE_ATTR,
)
from services.orgao_tree import rebuild_orgao_closure
from services.project_relations import (
    RELATED_MAX_PER_PROJECT,
    RelacaoInvalida,
    desrelacionar_projetos,
    listar_relacionados_payload,
    relacionar_projetos,
    relacoes_do_projeto_ids,
    remover_relacoes_do_projeto,
)
from tests.sql_query_counter import SqlQueryCounter

# ── Helpers de fixture ────────────────────────────────────────────────────────


def _add_orgao(sigla: str) -> int:
    orgao = OrgaoUnidade(
        sigla=sigla, nome=sigla, tipo="Secretaria", ordem=0, ativo=True
    )
    db.session.add(orgao)
    db.session.flush()
    return orgao.id


def _add_user(username: str, *, orgao_id: int | None = None) -> User:
    user = User(username=username, name=username.upper(), password_hash="x")
    db.session.add(user)
    db.session.flush()
    if orgao_id is not None:
        db.session.add(UserOrgao(user_id=user.id, orgao_id=orgao_id, papel="gestor"))
        db.session.flush()
    return user


def _add_project(titulo: str, orgao_id: int) -> Project:
    projeto = Project(titulo=titulo, orgao_id=orgao_id, status="Vigente")
    db.session.add(projeto)
    db.session.flush()
    return projeto


def _add_relacao_bruta(project_id: int, outro_id: int, ator_id: int) -> ProjectRelation:
    """Insere o par direto no banco, sem passar pelas regras do service."""
    relacao = ProjectRelation(
        project_low_id=min(project_id, outro_id),
        project_high_id=max(project_id, outro_id),
        created_by_user_id=ator_id,
    )
    db.session.add(relacao)
    db.session.flush()
    return relacao


def _encher_cota(
    project_id: int, orgao_id: int, ator_id: int, quantidade: int
) -> list[int]:
    outros = [
        _add_project(f"Cota {project_id}-{numero}", orgao_id).id
        for numero in range(quantidade)
    ]
    for outro_id in outros:
        _add_relacao_bruta(project_id, outro_id, ator_id)
    return outros


def _projeto(project_id: int) -> Project:
    return db.session.get(Project, project_id)


def _usuario(user_id: int) -> User:
    return db.session.get(User, user_id)


def _total_de_relacoes(project_id: int) -> int:
    return ProjectRelation.query.filter(
        db.or_(
            ProjectRelation.project_low_id == project_id,
            ProjectRelation.project_high_id == project_id,
        )
    ).count()


def _pares_nao_canonicos() -> int:
    """Invariante do schema: nenhuma linha com ``low >= high`` sobrevive."""
    return ProjectRelation.query.filter(
        ProjectRelation.project_low_id >= ProjectRelation.project_high_id
    ).count()


def _historico(project_id: int, action_type: str) -> int:
    return ProjectHistory.query.filter_by(
        project_id=project_id, action_type=action_type
    ).count()


class RelacaoExistenteCega:
    """Fake de ``_relacao_existente`` que esconde o vencedor da corrida.

    Devolve ``None`` nas ``chamadas_cegas`` primeiras vezes (simulando o SELECT
    que roda antes do INSERT concorrente commitar) e delega ao banco depois.
    """

    def __init__(self, chamadas_cegas: int) -> None:
        self.chamadas_cegas = chamadas_cegas
        self.chamadas = 0

    def __call__(self, low_id: int, high_id: int) -> ProjectRelation | None:
        self.chamadas += 1
        if self.chamadas <= self.chamadas_cegas:
            return None
        return ProjectRelation.query.filter_by(
            project_low_id=low_id, project_high_id=high_id
        ).first()


@pytest.fixture
def cenario(app):
    """AREA com 3 projetos e um gestor; FORA com 1 projeto invisível à AREA."""
    with app.app_context():
        area = _add_orgao("AREA")
        fora = _add_orgao("FORA")
        rebuild_orgao_closure()
        gestor = _add_user("gestor_area", orgao_id=area)
        dono = _add_user("dono_area", orgao_id=area)
        projetos = [_add_project(f"Projeto {letra}", area) for letra in "ABC"]
        de_fora = _add_project("Projeto Fora", fora)
        db.session.commit()
        yield {
            "area": area,
            "fora": fora,
            "gestor_id": gestor.id,
            "dono_id": dono.id,
            "a": projetos[0].id,
            "b": projetos[1].id,
            "c": projetos[2].id,
            "de_fora": de_fora.id,
        }


# ── Canonicalização, duplicata e auto-vínculo ─────────────────────────────────


def test_canonicaliza_o_par_independente_da_ordem_dos_argumentos(app, cenario):
    relacao = relacionar_projetos(
        _projeto(cenario["b"]), _projeto(cenario["a"]), _usuario(cenario["gestor_id"])
    )
    db.session.flush()
    assert relacao.project_low_id == min(cenario["a"], cenario["b"])
    assert relacao.project_high_id == max(cenario["a"], cenario["b"])


def test_relacionar_na_ordem_inversa_cai_na_mesma_linha(app, cenario):
    ator = _usuario(cenario["gestor_id"])
    relacionar_projetos(_projeto(cenario["a"]), _projeto(cenario["b"]), ator)
    db.session.commit()
    with pytest.raises(RelacaoInvalida):
        relacionar_projetos(_projeto(cenario["b"]), _projeto(cenario["a"]), ator)
    assert ProjectRelation.query.count() == 1


def test_duplicata_reporta_os_dois_ids_e_o_formato_esperado(app, cenario):
    ator = _usuario(cenario["gestor_id"])
    _add_relacao_bruta(cenario["a"], cenario["b"], ator.id)
    db.session.commit()
    with pytest.raises(RelacaoInvalida) as erro:
        relacionar_projetos(_projeto(cenario["a"]), _projeto(cenario["b"]), ator)
    mensagem = str(erro.value)
    assert str(min(cenario["a"], cenario["b"])) in mensagem
    assert str(max(cenario["a"], cenario["b"])) in mensagem
    assert "esperado" in mensagem


def test_auto_vinculo_traz_o_id_recebido_na_mensagem(app, cenario):
    projeto = _projeto(cenario["a"])
    with pytest.raises(RelacaoInvalida) as erro:
        relacionar_projetos(projeto, projeto, _usuario(cenario["gestor_id"]))
    assert str(cenario["a"]) in str(erro.value)
    assert ProjectRelation.query.count() == 0


# ── Teto de vínculos ──────────────────────────────────────────────────────────


def test_teto_bloqueia_a_partir_do_projeto_de_origem(app, cenario):
    ator = _usuario(cenario["gestor_id"])
    origem = _projeto(cenario["a"])
    _encher_cota(origem.id, cenario["area"], ator.id, RELATED_MAX_PER_PROJECT)
    db.session.commit()
    with pytest.raises(RelacaoInvalida) as erro:
        relacionar_projetos(origem, _projeto(cenario["b"]), ator)
    assert str(RELATED_MAX_PER_PROJECT) in str(erro.value)
    assert f"id={origem.id}" in str(erro.value)


def test_teto_ignora_os_vinculos_recebidos_pelo_alvo(app, cenario):
    ator = _usuario(cenario["gestor_id"])
    alvo = _projeto(cenario["b"])
    _encher_cota(alvo.id, cenario["area"], ator.id, RELATED_MAX_PER_PROJECT)
    db.session.commit()
    relacao = relacionar_projetos(_projeto(cenario["a"]), alvo, ator)
    db.session.flush()
    assert relacao.id is not None
    assert _total_de_relacoes(alvo.id) == RELATED_MAX_PER_PROJECT + 1


# ── Corrida de INSERT ─────────────────────────────────────────────────────────


def test_corrida_de_insert_responde_como_duplicata(app, cenario, monkeypatch):
    ator = _usuario(cenario["gestor_id"])
    _add_relacao_bruta(cenario["a"], cenario["b"], ator.id)
    db.session.commit()
    fake = RelacaoExistenteCega(chamadas_cegas=1)
    monkeypatch.setattr(project_relations, "_relacao_existente", fake)
    with pytest.raises(RelacaoInvalida):
        relacionar_projetos(_projeto(cenario["a"]), _projeto(cenario["b"]), ator)
    assert fake.chamadas == 2
    assert ProjectRelation.query.count() == 1


def test_corrida_sem_vencedor_relanca_integrity_error(app, cenario, monkeypatch):
    ator = _usuario(cenario["gestor_id"])
    _add_relacao_bruta(cenario["a"], cenario["b"], ator.id)
    db.session.commit()
    monkeypatch.setattr(
        project_relations, "_relacao_existente", RelacaoExistenteCega(chamadas_cegas=9)
    )
    with pytest.raises(IntegrityError):
        relacionar_projetos(_projeto(cenario["a"]), _projeto(cenario["b"]), ator)
    db.session.rollback()
    assert ProjectRelation.query.count() == 1


# ── @validates e invariante do par ────────────────────────────────────────────


def test_validates_aceita_kwargs_nas_duas_ordens(app):
    primeira = ProjectRelation(
        project_low_id=3, project_high_id=9, created_by_user_id=1
    )
    segunda = ProjectRelation(project_high_id=9, project_low_id=3, created_by_user_id=1)
    assert (primeira.project_low_id, primeira.project_high_id) == (3, 9)
    assert (segunda.project_low_id, segunda.project_high_id) == (3, 9)


def test_validates_recusa_par_nao_canonico_nas_duas_ordens(app):
    with pytest.raises(ValueError, match="project_low_id < project_high_id"):
        ProjectRelation(project_low_id=9, project_high_id=3, created_by_user_id=1)
    with pytest.raises(ValueError, match="project_low_id < project_high_id"):
        ProjectRelation(project_high_id=3, project_low_id=9, created_by_user_id=1)


def test_invariante_canonico_apos_sequencia_de_operacoes(app, cenario):
    ator = _usuario(cenario["gestor_id"])
    relacionar_projetos(_projeto(cenario["b"]), _projeto(cenario["a"]), ator)
    relacionar_projetos(_projeto(cenario["c"]), _projeto(cenario["b"]), ator)
    db.session.commit()
    desrelacionar_projetos(_projeto(cenario["b"]), cenario["a"], ator)
    relacionar_projetos(_projeto(cenario["c"]), _projeto(cenario["a"]), ator)
    db.session.commit()
    assert _pares_nao_canonicos() == 0
    assert ProjectRelation.query.count() == 2


# ── Remoção ───────────────────────────────────────────────────────────────────


def test_desrelacionar_par_inexistente_devolve_false(app, cenario):
    assert (
        desrelacionar_projetos(
            _projeto(cenario["a"]), cenario["b"], _usuario(cenario["gestor_id"])
        )
        is False
    )


def test_desrelacionar_apaga_a_linha_uma_unica_vez(app, cenario):
    ator = _usuario(cenario["gestor_id"])
    relacionar_projetos(_projeto(cenario["a"]), _projeto(cenario["b"]), ator)
    db.session.commit()
    assert desrelacionar_projetos(_projeto(cenario["b"]), cenario["a"], ator) is True
    db.session.commit()
    assert ProjectRelation.query.count() == 0
    assert desrelacionar_projetos(_projeto(cenario["b"]), cenario["a"], ator) is False


def test_remover_relacoes_do_projeto_apaga_os_dois_lados(app, cenario):
    ator = _usuario(cenario["gestor_id"])
    _add_relacao_bruta(cenario["a"], cenario["b"], ator.id)
    _add_relacao_bruta(cenario["a"], cenario["c"], ator.id)
    _add_relacao_bruta(cenario["b"], cenario["c"], ator.id)
    db.session.commit()
    assert remover_relacoes_do_projeto(cenario["a"]) == 2
    db.session.commit()
    assert _total_de_relacoes(cenario["a"]) == 0
    assert ProjectRelation.query.count() == 1
    assert remover_relacoes_do_projeto(cenario["a"]) == 0


def test_delete_orm_sozinho_deixa_vinculo_orfao(app, cenario):
    """Regressão: em SQLite o ``ondelete=CASCADE`` não roda — daí a chamada."""
    _add_relacao_bruta(cenario["a"], cenario["b"], cenario["gestor_id"])
    db.session.commit()
    db.session.delete(_projeto(cenario["a"]))
    db.session.commit()
    assert ProjectRelation.query.count() == 1


def test_excluir_projeto_na_ordem_da_rota_nao_deixa_vinculo(app, cenario):
    ator = _usuario(cenario["gestor_id"])
    relacionar_projetos(_projeto(cenario["a"]), _projeto(cenario["b"]), ator)
    db.session.commit()
    remover_relacoes_do_projeto(cenario["a"])
    db.session.delete(_projeto(cenario["a"]))
    db.session.commit()
    assert ProjectRelation.query.count() == 0
    assert listar_relacionados_payload(_projeto(cenario["b"]), ator) == []


# ── Histórico e notificações ──────────────────────────────────────────────────


def test_historico_registra_apenas_no_projeto_de_origem(app, cenario):
    ator = _usuario(cenario["gestor_id"])
    relacionar_projetos(_projeto(cenario["a"]), _projeto(cenario["b"]), ator)
    db.session.commit()
    desrelacionar_projetos(_projeto(cenario["a"]), cenario["b"], ator)
    db.session.commit()
    assert _historico(cenario["a"], "relacionar_projeto") == 1
    assert _historico(cenario["a"], "desrelacionar_projeto") == 1
    assert ProjectHistory.query.filter_by(project_id=cenario["b"]).count() == 0


def test_vinculo_e_desvinculo_nao_geram_notificacao(app, cenario):
    ator = _usuario(cenario["gestor_id"])
    _semear_dono_do_projeto(cenario["a"], cenario["dono_id"])
    relacionar_projetos(_projeto(cenario["a"]), _projeto(cenario["b"]), ator)
    desrelacionar_projetos(_projeto(cenario["a"]), cenario["b"], ator)
    db.session.commit()
    assert UserNotification.query.count() == 0
    # Controle: o mesmo dono recebe notificação de uma ação NÃO ignorada — sem
    # isso a asserção acima passaria mesmo com o notificador quebrado. O
    # request context é necessário para o url_for do target_url da notificação.
    with app.test_request_context():
        log_project_action(
            project_id=cenario["a"],
            action_type="update",
            description="Alterou o título",
            actor_user_id=ator.id,
        )
    db.session.commit()
    assert (
        UserNotification.query.filter_by(recipient_user_id=cenario["dono_id"]).count()
        >= 1
    )


def _semear_dono_do_projeto(project_id: int, user_id: int) -> None:
    """Entrada ``create`` no histórico: é dela que sai o dono notificável."""
    db.session.add(
        ProjectHistory(
            project_id=project_id,
            user_id=user_id,
            action_type="create",
            action_description="Criou o projeto",
        )
    )
    db.session.commit()


# ── Leitura ───────────────────────────────────────────────────────────────────


def test_payload_expoe_apenas_os_campos_do_contrato(app, cenario):
    ator = _usuario(cenario["gestor_id"])
    relacionar_projetos(_projeto(cenario["a"]), _projeto(cenario["b"]), ator)
    db.session.commit()
    (item,) = listar_relacionados_payload(_projeto(cenario["a"]), ator)
    assert set(item) == {"id", "titulo", "status", "prioridade", "orgao_sigla"}
    assert item["id"] == cenario["b"]
    assert item["orgao_sigla"] == "AREA"


def test_status_do_relacionado_muda_so_o_chip_sem_cascata(app, cenario):
    ator = _usuario(cenario["gestor_id"])
    relacionar_projetos(_projeto(cenario["a"]), _projeto(cenario["b"]), ator)
    db.session.commit()
    _projeto(cenario["a"]).status = "Suspenso"
    db.session.commit()
    (item,) = listar_relacionados_payload(_projeto(cenario["b"]), ator)
    assert item["status"] == "Suspenso"
    assert _projeto(cenario["b"]).status == "Vigente"
    assert ProjectHistory.query.filter_by(project_id=cenario["b"]).count() == 0
    assert UserNotification.query.count() == 0


def test_payload_segue_a_ordem_de_criacao_dos_vinculos(app, cenario):
    ator = _usuario(cenario["gestor_id"])
    relacionar_projetos(_projeto(cenario["a"]), _projeto(cenario["c"]), ator)
    relacionar_projetos(_projeto(cenario["a"]), _projeto(cenario["b"]), ator)
    db.session.commit()
    ids = [
        item["id"] for item in listar_relacionados_payload(_projeto(cenario["a"]), ator)
    ]
    assert ids == [cenario["c"], cenario["b"]]


def test_payload_filtra_relacionado_invisivel_ao_viewer(app, cenario):
    _add_relacao_bruta(cenario["a"], cenario["de_fora"], cenario["gestor_id"])
    db.session.commit()
    gestor = _usuario(cenario["gestor_id"])
    assert listar_relacionados_payload(_projeto(cenario["a"]), gestor) == []
    assert listar_relacionados_payload(_projeto(cenario["a"]), None) == []


def test_relacoes_do_projeto_ids_devolve_sempre_o_outro_lado(app, cenario):
    _add_relacao_bruta(cenario["a"], cenario["b"], cenario["gestor_id"])
    _add_relacao_bruta(cenario["c"], cenario["a"], cenario["gestor_id"])
    db.session.commit()
    assert relacoes_do_projeto_ids(cenario["a"]) == {cenario["b"], cenario["c"]}
    assert relacoes_do_projeto_ids(cenario["b"]) == {cenario["a"]}


def _custo_da_leitura(viewer_id: int, project_id: int) -> tuple[int, int]:
    """Statements gastos por ``listar_relacionados_payload`` com cache frio."""
    db.session.expunge_all()
    for atributo in (
        ROLE_MAP_CACHE_ATTR,
        MEMBERSHIP_MAP_CACHE_ATTR,
        COLLECTION_RANK_CACHE_ATTR,
    ):
        g.pop(atributo, None)
    viewer = db.session.get(User, viewer_id)
    projeto = db.session.get(Project, project_id)
    with SqlQueryCounter(db.engine) as contador:
        payload = listar_relacionados_payload(projeto, viewer)
    return contador.total, len(payload)


def test_leitura_dos_relacionados_nao_escala_com_a_quantidade(app, cenario):
    _encher_cota(cenario["a"], cenario["area"], cenario["gestor_id"], 1)
    _encher_cota(cenario["b"], cenario["area"], cenario["gestor_id"], 6)
    db.session.commit()
    custo_um, total_um = _custo_da_leitura(cenario["gestor_id"], cenario["a"])
    custo_seis, total_seis = _custo_da_leitura(cenario["gestor_id"], cenario["b"])
    assert (total_um, total_seis) == (1, 6)
    assert custo_um == custo_seis
