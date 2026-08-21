"""Testes de services/ai/suggestion_store (cache persistido, Fase 2 do plano).

Cobre a assinatura de conjunto, a substituição do lote pendente (sem tocar nas
linhas já decididas), a leitura ordenada e as transições de decisão
(descartar/aceitar) com o contrato próprio × alheio.
"""

import pytest

from models import ColecaoSugestaoIA, ProjectCollection, User, db
from models.colecao_sugestao import (
    STATUS_SUGESTAO_ACEITA,
    STATUS_SUGESTAO_DESCARTADA,
    STATUS_SUGESTAO_PENDENTE,
)
from services.ai import (
    ColecaoSugerida,
    SugestoesGeradas,
    assinatura_do_conjunto,
    assinaturas_bloqueadas,
    descartar_sugestao,
    lote_pendente,
    marcar_aceita,
    persistir_lote,
)

INPUT_HASH_TESTE = "f" * 64
MODELO_TESTE = "modelo-fixo/teste-v1"


def _add_user(username: str) -> int:
    user = User(username=username, name=username.upper(), password_hash="x")
    db.session.add(user)
    db.session.flush()
    return user.id


def _sugerida(nome: str, project_ids: list[int]) -> ColecaoSugerida:
    return ColecaoSugerida(
        nome=nome,
        descricao=None,
        justificativa="agrupamento temático",
        project_ids=project_ids,
        criterio_palavras=["tema"],
    )


def _resultado(*sugestoes: ColecaoSugerida) -> SugestoesGeradas:
    return SugestoesGeradas(
        sugestoes=list(sugestoes),
        projetos_analisados=[],
        input_hash=INPUT_HASH_TESTE,
        modelo_id=MODELO_TESTE,
    )


def _semear_linha(user_id: int, *, status: str, ordem: int = 0) -> int:
    linha = ColecaoSugestaoIA(
        user_id=user_id,
        lote_id="a" * 32,
        input_hash="h" * 64,
        ordem=ordem,
        nome=f"Linha {ordem}",
        justificativa="registro anterior",
        project_ids=[1, 2],
        assinatura=assinatura_do_conjunto([1, 2]),
        status=status,
    )
    db.session.add(linha)
    db.session.commit()
    return linha.id


@pytest.fixture
def dono_id(app):
    with app.app_context():
        user_id = _add_user("dono_store")
        db.session.commit()
        yield user_id


# ── assinatura_do_conjunto ────────────────────────────────────────────────────


def test_assinatura_do_conjunto_ignora_ordem():
    assert assinatura_do_conjunto([7, 3, 12]) == assinatura_do_conjunto([12, 7, 3])


def test_assinatura_do_conjunto_distingue_conjuntos():
    assert assinatura_do_conjunto([3, 7]) != assinatura_do_conjunto([3, 7, 12])


# ── assinaturas_bloqueadas ────────────────────────────────────────────────────


def test_assinaturas_bloqueadas_traz_descartadas_e_aceitas(app, dono_id):
    with app.app_context():
        _semear_linha(dono_id, status=STATUS_SUGESTAO_DESCARTADA)
        _semear_linha(dono_id, status=STATUS_SUGESTAO_ACEITA, ordem=1)
        _semear_linha(dono_id, status=STATUS_SUGESTAO_PENDENTE, ordem=2)
        assert assinaturas_bloqueadas(dono_id) == {assinatura_do_conjunto([1, 2])}


def test_assinaturas_bloqueadas_ignora_outros_usuarios(app, dono_id):
    with app.app_context():
        outro_id = _add_user("outro_store")
        _semear_linha(outro_id, status=STATUS_SUGESTAO_DESCARTADA)
        assert assinaturas_bloqueadas(dono_id) == set()


# ── persistir_lote ────────────────────────────────────────────────────────────


def test_persistir_lote_insere_linhas_com_lote_e_ordem(app, dono_id):
    resultado = _resultado(_sugerida("Obras", [3, 7]), _sugerida("Saúde", [2, 9]))
    with app.app_context():
        linhas = persistir_lote(dono_id, resultado)
        db.session.commit()
        assert [linha.ordem for linha in linhas] == [0, 1]
        assert len({linha.lote_id for linha in linhas}) == 1
        assert {linha.status for linha in linhas} == {STATUS_SUGESTAO_PENDENTE}
        assert linhas[0].input_hash == INPUT_HASH_TESTE
        assert linhas[0].modelo_id == MODELO_TESTE
        assert linhas[0].assinatura == assinatura_do_conjunto([3, 7])


def test_persistir_lote_nao_commita(app, dono_id):
    with app.app_context():
        linhas = persistir_lote(dono_id, _resultado(_sugerida("Obras", [3, 7])))
        assert [linha.id for linha in linhas] == [None]
        db.session.commit()
        assert linhas[0].id is not None


def test_persistir_lote_substitui_pendentes_anteriores(app, dono_id):
    # A substituição é asserida pelo CONTEÚDO (nome/lote), não pelo id: o
    # SQLite sem AUTOINCREMENT reutiliza o id apagado na mesma transação,
    # então a linha nova pode herdar o id da antiga.
    with app.app_context():
        _semear_linha(dono_id, status=STATUS_SUGESTAO_PENDENTE)
        persistir_lote(dono_id, _resultado(_sugerida("Nova", [3, 7])))
        db.session.commit()
        restantes = ColecaoSugestaoIA.query.filter_by(user_id=dono_id).all()
        assert [linha.nome for linha in restantes] == ["Nova"]
        assert restantes[0].lote_id != "a" * 32
        assert [linha.nome for linha in lote_pendente(dono_id)] == ["Nova"]


def test_persistir_lote_preserva_linhas_ja_decididas(app, dono_id):
    with app.app_context():
        descartada_id = _semear_linha(dono_id, status=STATUS_SUGESTAO_DESCARTADA)
        aceita_id = _semear_linha(dono_id, status=STATUS_SUGESTAO_ACEITA, ordem=1)
        persistir_lote(dono_id, _resultado(_sugerida("Nova", [3, 7])))
        db.session.commit()
        assert db.session.get(ColecaoSugestaoIA, descartada_id) is not None
        assert db.session.get(ColecaoSugestaoIA, aceita_id) is not None


def test_persistir_lote_nao_apaga_pendentes_de_outro_usuario(app, dono_id):
    with app.app_context():
        outro_id = _add_user("outro_store")
        alheia_id = _semear_linha(outro_id, status=STATUS_SUGESTAO_PENDENTE)
        persistir_lote(dono_id, _resultado(_sugerida("Nova", [3, 7])))
        db.session.commit()
        assert db.session.get(ColecaoSugestaoIA, alheia_id) is not None


# ── lote_pendente ─────────────────────────────────────────────────────────────


def test_lote_pendente_ordena_pela_ordem_da_geracao(app, dono_id):
    with app.app_context():
        _semear_linha(dono_id, status=STATUS_SUGESTAO_PENDENTE, ordem=1)
        _semear_linha(dono_id, status=STATUS_SUGESTAO_PENDENTE, ordem=0)
        assert [linha.ordem for linha in lote_pendente(dono_id)] == [0, 1]


def test_lote_pendente_ignora_linhas_decididas(app, dono_id):
    with app.app_context():
        _semear_linha(dono_id, status=STATUS_SUGESTAO_DESCARTADA)
        assert lote_pendente(dono_id) == []


# ── descartar_sugestao ────────────────────────────────────────────────────────


def test_descartar_sugestao_propria_marca_status_e_decidido_em(app, dono_id):
    with app.app_context():
        sugestao_id = _semear_linha(dono_id, status=STATUS_SUGESTAO_PENDENTE)
        assert descartar_sugestao(dono_id, sugestao_id) is True
        db.session.commit()
        linha = db.session.get(ColecaoSugestaoIA, sugestao_id)
        assert linha.status == STATUS_SUGESTAO_DESCARTADA
        assert linha.decidido_em is not None


def test_descartar_sugestao_alheia_devolve_false_sem_mudar_nada(app, dono_id):
    with app.app_context():
        outro_id = _add_user("outro_store")
        sugestao_id = _semear_linha(outro_id, status=STATUS_SUGESTAO_PENDENTE)
        assert descartar_sugestao(dono_id, sugestao_id) is False
        linha = db.session.get(ColecaoSugestaoIA, sugestao_id)
        assert linha.status == STATUS_SUGESTAO_PENDENTE


def test_descartar_sugestao_inexistente_devolve_false(app, dono_id):
    with app.app_context():
        assert descartar_sugestao(dono_id, 999_999) is False


# ── marcar_aceita ─────────────────────────────────────────────────────────────


def _add_colecao(owner_id: int) -> int:
    colecao = ProjectCollection(owner_user_id=owner_id, nome="Criada pela IA")
    db.session.add(colecao)
    db.session.flush()
    return colecao.id


def test_marcar_aceita_propria_vincula_colecao(app, dono_id):
    with app.app_context():
        sugestao_id = _semear_linha(dono_id, status=STATUS_SUGESTAO_PENDENTE)
        colecao_id = _add_colecao(dono_id)
        assert marcar_aceita(dono_id, sugestao_id, colecao_id) is True
        db.session.commit()
        linha = db.session.get(ColecaoSugestaoIA, sugestao_id)
        assert linha.status == STATUS_SUGESTAO_ACEITA
        assert linha.colecao_id == colecao_id
        assert linha.decidido_em is not None


def test_marcar_aceita_alheia_devolve_false_sem_derrubar(app, dono_id):
    with app.app_context():
        outro_id = _add_user("outro_store")
        sugestao_id = _semear_linha(outro_id, status=STATUS_SUGESTAO_PENDENTE)
        colecao_id = _add_colecao(dono_id)
        assert marcar_aceita(dono_id, sugestao_id, colecao_id) is False
        linha = db.session.get(ColecaoSugestaoIA, sugestao_id)
        assert linha.status == STATUS_SUGESTAO_PENDENTE
        assert linha.colecao_id is None


def test_marcar_aceita_inexistente_devolve_false(app, dono_id):
    with app.app_context():
        assert marcar_aceita(dono_id, 999_999, 1) is False
