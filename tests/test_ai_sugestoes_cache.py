"""Testes de integração do cache de sugestões de coleção por IA (Fase 2 §6).

Exercita as rotas reais pelo test client: GET do cache (vazio, cheio e
desatualizado), POST (geração + persistência, dedupe de 60s e ``forcar``),
descarte persistente (próprio, alheio, inexistente) e o aceite via
``POST /api/colecoes`` com ``sugestao_id``.

O provedor nunca é tocado: ``FakeWatsonxClient`` implementa ``ClienteChatIA`` e
entra por monkeypatch de ``sugerir_colecoes`` no namespace da rota — a rota
constrói o cliente real sozinha, então a injeção precisa ser no nome importado.
"""

import json

import pytest

from models import ColecaoSugestaoIA, OrgaoUnidade, Project, User, UserOrgao, db
from models.colecao_sugestao import (
    STATUS_SUGESTAO_ACEITA,
    STATUS_SUGESTAO_DESCARTADA,
    STATUS_SUGESTAO_PENDENTE,
)
from routes.api import collection_suggestions as sugestoes_api
from services.ai import sugerir_colecoes
from services.orgao_tree import rebuild_orgao_closure

ROTA_SUGESTOES = "/api/colecoes/sugestoes"
ROTA_COLECOES = "/api/colecoes"

NOME_SAUDE = "Saúde digital"
NOME_MOBILIDADE = "Mobilidade urbana"

_TITULOS_SEMEADOS = (
    "Prontuário Eletrônico Estadual",
    "Telemedicina na Baixada",
    "Corredor de BRT da Zona Norte",
    "Bilhetagem Única Intermunicipal",
)


# ── Fake nomeado do provedor ──────────────────────────────────────────────────


class FakeWatsonxClient:
    """Cliente de chat falso: devolve sempre a mesma resposta e conta chamadas."""

    def __init__(self, resposta: str) -> None:
        self.resposta = resposta
        self.chamadas: list[tuple[str, str]] = []

    def invocar(self, system_prompt: str, user_prompt: str) -> str:
        self.chamadas.append((system_prompt, user_prompt))
        return self.resposta


# ── Helpers de cenário ────────────────────────────────────────────────────────


def _add_orgao(sigla: str) -> int:
    orgao = OrgaoUnidade(
        sigla=sigla, nome=sigla, tipo="Secretaria", ordem=0, ativo=True
    )
    db.session.add(orgao)
    db.session.flush()
    return orgao.id


def _add_user(username: str, orgao_id: int) -> int:
    user = User(username=username, name=username.upper(), password_hash="x")
    db.session.add(user)
    db.session.flush()
    db.session.add(UserOrgao(user_id=user.id, orgao_id=orgao_id, papel="gestor"))
    db.session.flush()
    return user.id


def _add_project(titulo: str, orgao_id: int) -> int:
    projeto = Project(titulo=titulo, orgao_id=orgao_id, status="Vigente")
    db.session.add(projeto)
    db.session.flush()
    return projeto.id


def _resposta_de_duas_colecoes(projeto_ids: list[int]) -> str:
    """Resposta crua do LLM com dois conjuntos DISJUNTOS (assinaturas distintas)."""
    return json.dumps(
        {
            "sugestoes": [
                {
                    "nome": NOME_SAUDE,
                    "descricao": "Prontuário eletrônico e telemedicina",
                    "justificativa": "Os dois projetos digitalizam serviços de saúde.",
                    "project_ids": projeto_ids[:2],
                    "criterio_palavras": ["prontuário", "telemedicina"],
                },
                {
                    "nome": NOME_MOBILIDADE,
                    "descricao": None,
                    "justificativa": "Os dois projetos tratam de transporte público.",
                    "project_ids": projeto_ids[2:],
                    "criterio_palavras": ["brt", "bilhetagem"],
                },
            ]
        },
        ensure_ascii=False,
    )


@pytest.fixture
def cenario_cache(app):
    """Dono e vizinho na mesma área enxergam os 4 projetos candidatos."""
    with app.app_context():
        area = _add_orgao("AREACACHE")
        rebuild_orgao_closure()
        cenario = {
            "dono_id": _add_user("dono_cache", area),
            "vizinho_id": _add_user("vizinho_cache", area),
            "projeto_ids": [_add_project(titulo, area) for titulo in _TITULOS_SEMEADOS],
        }
        db.session.commit()
        return cenario


def _client_logado(app, user_id: int):
    cliente = app.test_client()
    with cliente.session_transaction() as sessao:
        sessao["user_id"] = user_id
    return cliente


@pytest.fixture
def client_dono(app, cenario_cache):
    return _client_logado(app, cenario_cache["dono_id"])


@pytest.fixture
def client_vizinho(app, cenario_cache):
    return _client_logado(app, cenario_cache["vizinho_id"])


@pytest.fixture
def provedor_fake(monkeypatch, cenario_cache):
    """Liga o gate de IA e injeta o fake no ``sugerir_colecoes`` que a rota usa."""
    monkeypatch.setenv("WATSONX_API_KEY", "chave-de-teste")
    monkeypatch.setenv("WATSONX_PROJECT_ID", "projeto-de-teste")
    fake = FakeWatsonxClient(_resposta_de_duas_colecoes(cenario_cache["projeto_ids"]))

    def _sugerir_com_fake(user: User):
        return sugerir_colecoes(user, client=fake)

    monkeypatch.setattr(sugestoes_api, "sugerir_colecoes", _sugerir_com_fake)
    return fake


# ── Helpers de asserção ───────────────────────────────────────────────────────


def _dados(resposta) -> dict:
    corpo = resposta.get_json()
    assert resposta.status_code == 200, corpo
    assert corpo["ok"] is True, corpo
    return corpo["data"]


def _linhas_persistidas(app, user_id: int) -> list[dict]:
    """Snapshot JSON-safe das linhas do usuário (evita instância destacada)."""
    with app.app_context():
        linhas = (
            db.session.query(ColecaoSugestaoIA)
            .filter_by(user_id=user_id)
            .order_by(ColecaoSugestaoIA.ordem)
            .all()
        )
        return [
            {
                "id": linha.id,
                "nome": linha.nome,
                "status": linha.status,
                "colecao_id": linha.colecao_id,
                "assinatura": linha.assinatura,
            }
            for linha in linhas
        ]


def _status_por_nome(app, user_id: int) -> dict[str, str]:
    return {
        linha["nome"]: linha["status"] for linha in _linhas_persistidas(app, user_id)
    }


def _renomear_projeto(app, project_id: int, titulo: str) -> None:
    with app.app_context():
        db.session.get(Project, project_id).titulo = titulo
        db.session.commit()


def _nomes(dados: dict) -> list[str]:
    return [sugestao["nome"] for sugestao in dados["sugestoes"]]


def _descartar(cliente, sugestao_id: int):
    return cliente.post(f"{ROTA_SUGESTOES}/{sugestao_id}/descartar")


# ── GET: cache vazio ──────────────────────────────────────────────────────────


def test_get_sem_cache_devolve_lote_vazio_e_nao_chama_a_ia(client_dono, provedor_fake):
    dados = _dados(client_dono.get(ROTA_SUGESTOES))
    assert dados["sugestoes"] == []
    assert dados["desatualizado"] is False
    assert dados["gerado_em"] is None
    assert dados["lote_id"] is None
    assert provedor_fake.chamadas == []


def test_get_sem_cache_ja_devolve_os_projetos_candidatos(client_dono, provedor_fake):
    dados = _dados(client_dono.get(ROTA_SUGESTOES))
    assert sorted(projeto["titulo"] for projeto in dados["projetos"]) == sorted(
        _TITULOS_SEMEADOS
    )


# ── POST: geração e persistência ──────────────────────────────────────────────


def test_post_gera_lote_e_persiste_as_linhas(
    app, client_dono, provedor_fake, cenario_cache
):
    dados = _dados(client_dono.post(ROTA_SUGESTOES))
    assert _nomes(dados) == [NOME_SAUDE, NOME_MOBILIDADE]
    assert len(provedor_fake.chamadas) == 1
    assert _status_por_nome(app, cenario_cache["dono_id"]) == {
        NOME_SAUDE: STATUS_SUGESTAO_PENDENTE,
        NOME_MOBILIDADE: STATUS_SUGESTAO_PENDENTE,
    }


def test_post_responde_com_lote_identificado_e_fresco(client_dono, provedor_fake):
    dados = _dados(client_dono.post(ROTA_SUGESTOES))
    assert dados["desatualizado"] is False
    assert dados["lote_id"]
    assert dados["gerado_em"]
    assert all(sugestao["id"] for sugestao in dados["sugestoes"])


def test_get_apos_post_devolve_o_lote_do_cache(client_dono, provedor_fake):
    gerado = _dados(client_dono.post(ROTA_SUGESTOES))
    lido = _dados(client_dono.get(ROTA_SUGESTOES))
    assert lido["lote_id"] == gerado["lote_id"]
    assert lido["gerado_em"] == gerado["gerado_em"]
    assert lido["sugestoes"] == gerado["sugestoes"]
    assert lido["desatualizado"] is False
    assert len(provedor_fake.chamadas) == 1


# ── GET: staleness por mudança na carteira ────────────────────────────────────


def test_get_marca_desatualizado_apos_renomear_projeto(
    app, client_dono, provedor_fake, cenario_cache
):
    client_dono.post(ROTA_SUGESTOES)
    _renomear_projeto(app, cenario_cache["projeto_ids"][0], "Prontuário Eletrônico 2.0")
    dados = _dados(client_dono.get(ROTA_SUGESTOES))
    assert dados["desatualizado"] is True


def test_get_desatualizado_ainda_serve_as_sugestoes_antigas(
    app, client_dono, provedor_fake, cenario_cache
):
    client_dono.post(ROTA_SUGESTOES)
    _renomear_projeto(app, cenario_cache["projeto_ids"][0], "Prontuário Eletrônico 2.0")
    dados = _dados(client_dono.get(ROTA_SUGESTOES))
    assert _nomes(dados) == [NOME_SAUDE, NOME_MOBILIDADE]
    assert len(provedor_fake.chamadas) == 1


# ── POST: dedupe de 60s e escape hatch ────────────────────────────────────────


def test_post_repetido_na_janela_reusa_o_lote_sem_chamar_a_ia(
    client_dono, provedor_fake
):
    primeiro = _dados(client_dono.post(ROTA_SUGESTOES))
    segundo = _dados(client_dono.post(ROTA_SUGESTOES))
    assert segundo["lote_id"] == primeiro["lote_id"]
    assert segundo["sugestoes"] == primeiro["sugestoes"]
    assert len(provedor_fake.chamadas) == 1


def test_post_com_forcar_regenera_dentro_da_janela(
    app, client_dono, provedor_fake, cenario_cache
):
    primeiro = _dados(client_dono.post(ROTA_SUGESTOES))
    segundo = _dados(client_dono.post(ROTA_SUGESTOES, json={"forcar": True}))
    assert segundo["lote_id"] != primeiro["lote_id"]
    assert len(provedor_fake.chamadas) == 2
    assert len(_linhas_persistidas(app, cenario_cache["dono_id"])) == 2


# ── Descarte persistente ──────────────────────────────────────────────────────


def test_descartar_tira_a_sugestao_do_get(
    app, client_dono, provedor_fake, cenario_cache
):
    gerado = _dados(client_dono.post(ROTA_SUGESTOES))
    assert _descartar(client_dono, gerado["sugestoes"][0]["id"]).status_code == 200
    assert _nomes(_dados(client_dono.get(ROTA_SUGESTOES))) == [NOME_MOBILIDADE]
    assert _status_por_nome(app, cenario_cache["dono_id"]) == {
        NOME_SAUDE: STATUS_SUGESTAO_DESCARTADA,
        NOME_MOBILIDADE: STATUS_SUGESTAO_PENDENTE,
    }


def test_nova_geracao_nao_re_sugere_conjunto_descartado(client_dono, provedor_fake):
    gerado = _dados(client_dono.post(ROTA_SUGESTOES))
    _descartar(client_dono, gerado["sugestoes"][0]["id"])
    novo = _dados(client_dono.post(ROTA_SUGESTOES, json={"forcar": True}))
    assert _nomes(novo) == [NOME_MOBILIDADE]
    assert len(provedor_fake.chamadas) == 2


def test_descartar_sugestao_alheia_responde_404(
    app, client_dono, client_vizinho, provedor_fake, cenario_cache
):
    gerado = _dados(client_dono.post(ROTA_SUGESTOES))
    resposta = _descartar(client_vizinho, gerado["sugestoes"][0]["id"])
    assert resposta.status_code == 404
    assert resposta.get_json()["error"]["code"] == "not_found"
    assert set(_status_por_nome(app, cenario_cache["dono_id"]).values()) == {
        STATUS_SUGESTAO_PENDENTE
    }


def test_descartar_sugestao_inexistente_responde_404(client_dono):
    resposta = _descartar(client_dono, 999999)
    assert resposta.status_code == 404
    assert resposta.get_json()["error"]["code"] == "not_found"


# ── Aceite via POST /api/colecoes ─────────────────────────────────────────────


def test_aceite_com_sugestao_id_marca_a_linha_e_vincula_a_colecao(
    app, client_dono, provedor_fake, cenario_cache
):
    sugestao = _dados(client_dono.post(ROTA_SUGESTOES))["sugestoes"][0]
    criada = _dados(
        client_dono.post(
            ROTA_COLECOES,
            json={
                "nome": "Saúde digital 2026",
                "project_ids": sugestao["project_ids"],
                "sugestao_id": sugestao["id"],
            },
        )
    )["colecao"]
    aceita = _linha_por_id(app, cenario_cache["dono_id"], sugestao["id"])
    assert aceita["status"] == STATUS_SUGESTAO_ACEITA
    assert aceita["colecao_id"] == criada["id"]


def test_aceite_nao_decide_as_demais_sugestoes_do_lote(
    app, client_dono, provedor_fake, cenario_cache
):
    sugestoes = _dados(client_dono.post(ROTA_SUGESTOES))["sugestoes"]
    client_dono.post(
        ROTA_COLECOES,
        json={
            "nome": "Saúde digital 2026",
            "project_ids": sugestoes[0]["project_ids"],
            "sugestao_id": sugestoes[0]["id"],
        },
    )
    outra = _linha_por_id(app, cenario_cache["dono_id"], sugestoes[1]["id"])
    assert outra["status"] == STATUS_SUGESTAO_PENDENTE


def _linha_por_id(app, user_id: int, sugestao_id: int) -> dict:
    linhas = _linhas_persistidas(app, user_id)
    return next(linha for linha in linhas if linha["id"] == sugestao_id)
