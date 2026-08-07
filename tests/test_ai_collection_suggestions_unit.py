"""Testes de services/ai/* (sugestão de coleções por IA, Fase 1 do plano).

Cobre as três camadas que a rota não pode reimplementar: parse do texto do LLM,
validação estrutural/semântica (id alucinado, nome já usado, "Favoritos") e a
orquestração com retry. O provedor nunca é tocado: ``FakeWatsonxClient``
implementa ``ClienteChatIA`` com fila de respostas.

Os testes que passam pelo banco rodam em ``app.test_request_context`` porque
``apply_project_visibility`` usa cache de request.
"""

import json

import pytest

from models import (
    ColecaoSugestaoIA,
    OrgaoUnidade,
    Project,
    ProjectCollection,
    ProjectCollectionItem,
    ProjectCollectionShare,
    User,
    UserOrgao,
    db,
)
from models.colecao_sugestao import (
    STATUS_SUGESTAO_ACEITA,
    STATUS_SUGESTAO_DESCARTADA,
    STATUS_SUGESTAO_PENDENTE,
)
from models.project_collection import PAPEL_SHARE_VIEWER
from services.ai import (
    ColecaoSugerida,
    ProjetoCandidato,
    SugestaoIndisponivel,
    SugestoesInvalidas,
    assinatura_do_conjunto,
    calcular_input_hash,
    coletar_projetos_candidatos,
    extrair_json,
    modelo_sugestoes_configurado,
    montar_prompt,
    sugerir_colecoes,
    validar_sugestoes,
)
from services.ai.collection_suggestions import DESCRICAO_MAX_PROMPT
from services.authorization import apply_project_visibility
from services.orgao_tree import rebuild_orgao_closure
from services.project_collections import DESCRICAO_MAX_COLECAO, NOME_MAX_COLECAO

# ── Fake nomeado do provedor ──────────────────────────────────────────────────


class FakeWatsonxClient:
    """Cliente de chat falso: entrega ``respostas`` em ordem e grava os prompts.

    Um item ``Exception`` na fila é levantado no lugar de devolver texto.
    """

    def __init__(self, respostas: list[str | Exception]) -> None:
        self.respostas: list[str | Exception] = list(respostas)
        self.chamadas: list[tuple[str, str]] = []

    def invocar(self, system_prompt: str, user_prompt: str) -> str:
        self.chamadas.append((system_prompt, user_prompt))
        if not self.respostas:
            raise AssertionError("FakeWatsonxClient chamado mais vezes que o previsto")
        proxima = self.respostas.pop(0)
        if isinstance(proxima, Exception):
            raise proxima
        return proxima


# ── Helpers ───────────────────────────────────────────────────────────────────


def _sugestao(**overrides: object) -> dict[str, object]:
    bruta: dict[str, object] = {
        "nome": "Saúde digital",
        "descricao": "Prontuário eletrônico e telemedicina",
        "justificativa": "Os projetos digitalizam serviços de saúde.",
        "project_ids": [1, 2],
        "criterio_palavras": ["portal", "prontuário"],
    }
    bruta.update(overrides)
    return bruta


def _resposta(*sugestoes: dict[str, object]) -> str:
    return json.dumps({"sugestoes": list(sugestoes)}, ensure_ascii=False)


def _candidato(**overrides: object) -> ProjetoCandidato:
    campos: dict[str, object] = {
        "id": 1,
        "titulo": "Portal do Cidadão",
        "descricao": "Serviços digitais unificados",
        "orgao_sigla": "SETD",
        "status": "Vigente",
    }
    campos.update(overrides)
    return ProjetoCandidato(**campos)  # type: ignore[arg-type]


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


def _add_project(titulo: str, orgao_id: int, **campos: object) -> Project:
    projeto = Project(titulo=titulo, orgao_id=orgao_id, status="Vigente", **campos)
    db.session.add(projeto)
    db.session.flush()
    return projeto


def _usuario(user_id: int) -> User:
    return db.session.get(User, user_id)


def _semear_projeto(titulo: str, **campos: object) -> int:
    """Cria um projeto da AREAIA na sessão corrente e devolve o id já commitado."""
    area_id = db.session.query(OrgaoUnidade.id).filter_by(sigla="AREAIA").scalar()
    projeto = _add_project(titulo, area_id, **campos)
    projeto_id = projeto.id
    db.session.commit()
    return projeto_id


@pytest.fixture
def cenario_ia(app):
    """Dono enxerga 2 projetos da AREAIA; o da AREAIB fica fora do escopo."""
    with app.app_context():
        area_a = _add_orgao("AREAIA")
        area_b = _add_orgao("AREAIB")
        rebuild_orgao_closure()
        dono = _add_user("dono_ia", orgao_id=area_a)
        sem_area = _add_user("sem_area_ia")
        alfa = _add_project("Portal do Cidadão", area_a)
        beta = _add_project("Prontuário Eletrônico", area_a)
        oculto = _add_project("Projeto de Outra Área", area_b)
        db.session.commit()
        yield {
            "dono_id": dono.id,
            "sem_area_id": sem_area.id,
            "alfa_id": alfa.id,
            "beta_id": beta.id,
            "oculto_id": oculto.id,
        }


# ── extrair_json ──────────────────────────────────────────────────────────────


def test_extrair_json_aceita_json_puro():
    assert extrair_json('{"sugestoes": []}') == {"sugestoes": []}


def test_extrair_json_aceita_json_embrulhado_em_prosa():
    texto = 'Claro! Segue:\n```json\n{"sugestoes": [{"nome": "Obras"}]}\n```\nEspero ajudar.'
    assert extrair_json(texto) == {"sugestoes": [{"nome": "Obras"}]}


def test_extrair_json_devolve_none_para_texto_sem_json():
    assert extrair_json("não consegui agrupar os projetos") is None


def test_extrair_json_devolve_none_para_json_quebrado():
    assert extrair_json('{"sugestoes": [') is None


def test_extrair_json_devolve_none_para_json_que_nao_e_objeto():
    assert extrair_json("[1, 2, 3]") is None


# ── validar_sugestoes: estrutura ──────────────────────────────────────────────


def test_validar_aceita_sugestao_completa():
    validas = validar_sugestoes(
        {"sugestoes": [_sugestao()]},
        ids_permitidos={1, 2},
        nomes_indisponiveis=set(),
    )
    assert validas == [
        ColecaoSugerida(
            nome="Saúde digital",
            descricao="Prontuário eletrônico e telemedicina",
            justificativa="Os projetos digitalizam serviços de saúde.",
            project_ids=[1, 2],
            criterio_palavras=["portal", "prontuário"],
        )
    ]


def test_validar_recusa_nome_acima_do_limite():
    with pytest.raises(SugestoesInvalidas) as erro:
        validar_sugestoes(
            {"sugestoes": [_sugestao(nome="a" * (NOME_MAX_COLECAO + 1))]},
            ids_permitidos={1, 2},
            nomes_indisponiveis=set(),
        )
    assert erro.value.erros == ["sugestoes[0].nome: 101 caracteres; máximo 100"]


def test_validar_recusa_descricao_acima_do_limite():
    with pytest.raises(SugestoesInvalidas) as erro:
        validar_sugestoes(
            {"sugestoes": [_sugestao(descricao="d" * (DESCRICAO_MAX_COLECAO + 1))]},
            ids_permitidos={1, 2},
            nomes_indisponiveis=set(),
        )
    assert "descricao" in erro.value.erros[0]


def test_validar_aceita_descricao_nula():
    validas = validar_sugestoes(
        {"sugestoes": [_sugestao(descricao=None)]},
        ids_permitidos={1, 2},
        nomes_indisponiveis=set(),
    )
    assert validas[0].descricao is None


@pytest.mark.parametrize("justificativa", ["", "   ", None, 42])
def test_validar_recusa_justificativa_vazia(justificativa):
    with pytest.raises(SugestoesInvalidas) as erro:
        validar_sugestoes(
            {"sugestoes": [_sugestao(justificativa=justificativa)]},
            ids_permitidos={1, 2},
            nomes_indisponiveis=set(),
        )
    assert "justificativa" in erro.value.erros[0]


@pytest.mark.parametrize("project_ids", [[], [7], [7, 7], "7,8", [7, "8"], [7, True]])
def test_validar_recusa_menos_de_dois_project_ids(project_ids):
    with pytest.raises(SugestoesInvalidas) as erro:
        validar_sugestoes(
            {"sugestoes": [_sugestao(project_ids=project_ids)]},
            ids_permitidos={7, 8},
            nomes_indisponiveis=set(),
        )
    assert "project_ids" in erro.value.erros[0]


def test_validar_deduplica_project_ids_repetidos():
    validas = validar_sugestoes(
        {"sugestoes": [_sugestao(project_ids=[1, 2, 1])]},
        ids_permitidos={1, 2},
        nomes_indisponiveis=set(),
    )
    assert validas[0].project_ids == [1, 2]


def test_validar_recusa_payload_ausente():
    with pytest.raises(SugestoesInvalidas) as erro:
        validar_sugestoes(None, ids_permitidos={1, 2}, nomes_indisponiveis=set())
    assert erro.value.erros == ["resposta não é um objeto JSON válido"]


@pytest.mark.parametrize("payload", [{}, {"sugestoes": []}, {"sugestoes": "Obras"}])
def test_validar_recusa_lista_de_sugestoes_ausente_ou_vazia(payload):
    with pytest.raises(SugestoesInvalidas) as erro:
        validar_sugestoes(payload, ids_permitidos={1, 2}, nomes_indisponiveis=set())
    assert "sugestoes" in erro.value.erros[0]


def test_validar_acumula_erros_de_varias_sugestoes_para_o_retry():
    with pytest.raises(SugestoesInvalidas) as erro:
        validar_sugestoes(
            {
                "sugestoes": [
                    _sugestao(justificativa=""),
                    _sugestao(project_ids=[1]),
                    "não é objeto",
                ]
            },
            ids_permitidos={1, 2},
            nomes_indisponiveis=set(),
        )
    assert len(erro.value.erros) == 3


# ── validar_sugestoes: semântica ──────────────────────────────────────────────


def test_validar_descarta_ids_alucinados_mantendo_o_subconjunto():
    validas = validar_sugestoes(
        {"sugestoes": [_sugestao(project_ids=[1, 999, 2, 1000])]},
        ids_permitidos={1, 2},
        nomes_indisponiveis=set(),
    )
    assert validas[0].project_ids == [1, 2]


def test_validar_derruba_colecao_que_fica_com_menos_de_dois_ids_validos():
    validas = validar_sugestoes(
        {
            "sugestoes": [
                _sugestao(nome="Alucinada", project_ids=[1, 999]),
                _sugestao(nome="Real", project_ids=[1, 2]),
            ]
        },
        ids_permitidos={1, 2},
        nomes_indisponiveis=set(),
    )
    assert [sugestao.nome for sugestao in validas] == ["Real"]


def test_validar_descarta_nome_que_colide_com_colecao_existente_casefold():
    validas = validar_sugestoes(
        {
            "sugestoes": [
                _sugestao(nome="obras VIÁRIAS"),
                _sugestao(nome="Saúde digital"),
            ]
        },
        ids_permitidos={1, 2},
        nomes_indisponiveis={"Obras Viárias"},
    )
    assert [sugestao.nome for sugestao in validas] == ["Saúde digital"]


@pytest.mark.parametrize("nome", ["Favoritos", "favoritos", "FAVORITOS"])
def test_validar_descarta_nome_reservado_favoritos(nome):
    with pytest.raises(SugestoesInvalidas) as erro:
        validar_sugestoes(
            {"sugestoes": [_sugestao(nome=nome)]},
            ids_permitidos={1, 2},
            nomes_indisponiveis=set(),
        )
    assert "nenhuma sugestão restou" in erro.value.erros[0]


def test_validar_levanta_quando_nenhuma_sugestao_sobrevive_ao_filtro():
    with pytest.raises(SugestoesInvalidas):
        validar_sugestoes(
            {"sugestoes": [_sugestao(project_ids=[41, 42])]},
            ids_permitidos={1, 2},
            nomes_indisponiveis=set(),
        )


# ── coletar_projetos_candidatos: escopo e sanitização (LGPD) ──────────────────


def test_coletar_candidatos_traz_so_projetos_visiveis(app, cenario_ia):
    with app.test_request_context("/"):
        candidatos = coletar_projetos_candidatos(_usuario(cenario_ia["dono_id"]))
    ids = {candidato.id for candidato in candidatos}
    assert ids == {cenario_ia["alfa_id"], cenario_ia["beta_id"]}


def _compartilhar_oculto_com_dono(cenario_ia: dict[str, int]) -> None:
    """Coleção do sem_area contendo o projeto oculto, compartilhada com o dono."""
    colecao = ProjectCollection(
        owner_user_id=cenario_ia["sem_area_id"], nome="Compartilhada"
    )
    db.session.add(colecao)
    db.session.flush()
    db.session.add(
        ProjectCollectionItem(
            collection_id=colecao.id, project_id=cenario_ia["oculto_id"], ordem=0
        )
    )
    db.session.add(
        ProjectCollectionShare(
            collection_id=colecao.id,
            user_id=cenario_ia["dono_id"],
            papel=PAPEL_SHARE_VIEWER,
            created_by_user_id=cenario_ia["sem_area_id"],
        )
    )
    db.session.commit()


def test_coletar_candidatos_ignora_projeto_visivel_so_via_share_de_colecao(
    app, cenario_ia
):
    """Regressão: candidato via share de coleção quebraria o aceite, que valida
    com include_collections=False (ProjetoForaDoEscopo)."""
    with app.test_request_context("/"):
        _compartilhar_oculto_com_dono(cenario_ia)
        dono = _usuario(cenario_ia["dono_id"])
        visiveis = {p.id for p in apply_project_visibility(Project.query, dono).all()}
        assert cenario_ia["oculto_id"] in visiveis
        candidatos = coletar_projetos_candidatos(dono)
    assert cenario_ia["oculto_id"] not in {candidato.id for candidato in candidatos}


def test_coletar_candidatos_remove_cpf_do_titulo(app, cenario_ia):
    with app.test_request_context("/"):
        alvo_id = _semear_projeto("Cadastro de 123.456.789-00 no portal")
        candidatos = coletar_projetos_candidatos(_usuario(cenario_ia["dono_id"]))
        titulo = next(c.titulo for c in candidatos if c.id == alvo_id)
        assert titulo == "Cadastro de [cpf removido] no portal"


def test_coletar_candidatos_remove_numero_sei_da_descricao(app, cenario_ia):
    with app.test_request_context("/"):
        alvo_id = _semear_projeto(
            "Contratação",
            short_description="Processo SEI-260002/001234/2026 em análise",
        )
        candidatos = coletar_projetos_candidatos(_usuario(cenario_ia["dono_id"]))
        descricao = next(c.descricao for c in candidatos if c.id == alvo_id)
        assert descricao == "Processo [sei removido] em análise"


def test_coletar_candidatos_trunca_descricao_longa(app, cenario_ia):
    with app.test_request_context("/"):
        alvo_id = _semear_projeto("Descrição longa", short_description="d" * 400)
        candidatos = coletar_projetos_candidatos(_usuario(cenario_ia["dono_id"]))
        descricao = next(c.descricao for c in candidatos if c.id == alvo_id)
        assert len(descricao) == DESCRICAO_MAX_PROMPT


# ── montar_prompt ─────────────────────────────────────────────────────────────


def test_montar_prompt_lista_id_e_campos_de_cada_projeto():
    _, user_prompt = montar_prompt(
        [_candidato(id=3), _candidato(id=7, titulo="Telemedicina", orgao_sigla="SES")],
        [],
    )
    linha = "3 | Portal do Cidadão | Serviços digitais unificados | SETD | Vigente"
    assert linha in user_prompt
    assert "7 | Telemedicina" in user_prompt


def test_montar_prompt_traz_as_regras_inviolaveis():
    system_prompt, _ = montar_prompt([_candidato()], [])
    assert "SOMENTE os ids" in system_prompt
    assert "mínimo 2 projetos" in system_prompt
    assert "APENAS com JSON válido" in system_prompt


def test_montar_prompt_delimita_os_dados_como_dado_e_nao_instrucao():
    system_prompt, user_prompt = montar_prompt([_candidato()], [])
    assert "<<<DADOS" in user_prompt and "DADOS>>>" in user_prompt
    assert "não instrução" in system_prompt


def test_montar_prompt_informa_colecoes_existentes():
    _, user_prompt = montar_prompt([_candidato()], ["Obras", "Saúde"])
    assert "Obras, Saúde" in user_prompt


def test_montar_prompt_sem_colecoes_existentes_diz_nenhuma():
    _, user_prompt = montar_prompt([_candidato()], [])
    assert "(nenhuma)" in user_prompt


def test_montar_prompt_nao_expoe_campos_proibidos(app, cenario_ia):
    with app.test_request_context("/"):
        _semear_projeto(
            "Modernização",
            observacao="Despacho do servidor Fulano de Tal",
            sei_process="SEI-260002/000999/2026",
            github_link="https://git.interno.rj.gov.br/segredo",
        )
        candidatos = coletar_projetos_candidatos(_usuario(cenario_ia["dono_id"]))
    _, user_prompt = montar_prompt(candidatos, [])
    assert "Fulano" not in user_prompt
    assert "000999" not in user_prompt
    assert "git.interno" not in user_prompt


# ── sugerir_colecoes ──────────────────────────────────────────────────────────


def test_sugerir_colecoes_devolve_sugestoes_da_primeira_resposta(app, cenario_ia):
    ids = [cenario_ia["alfa_id"], cenario_ia["beta_id"]]
    cliente = FakeWatsonxClient([_resposta(_sugestao(project_ids=ids))])
    with app.test_request_context("/"):
        resultado = sugerir_colecoes(_usuario(cenario_ia["dono_id"]), cliente)
    sugestoes = resultado.sugestoes
    assert len(cliente.chamadas) == 1
    assert sugestoes[0].nome == "Saúde digital"
    assert sugestoes[0].project_ids == ids


def test_sugerir_colecoes_nao_repassa_projeto_invisivel(app, cenario_ia):
    alucinada = [cenario_ia["alfa_id"], cenario_ia["oculto_id"]]
    validos = [cenario_ia["alfa_id"], cenario_ia["beta_id"]]
    cliente = FakeWatsonxClient(
        [
            _resposta(
                _sugestao(nome="Vazamento", project_ids=alucinada),
                _sugestao(nome="Legítima", project_ids=validos),
            )
        ]
    )
    with app.test_request_context("/"):
        resultado = sugerir_colecoes(_usuario(cenario_ia["dono_id"]), cliente)
    assert [sugestao.nome for sugestao in resultado.sugestoes] == ["Legítima"]


def test_sugerir_colecoes_refaz_o_pedido_apos_json_invalido(app, cenario_ia):
    ids = [cenario_ia["alfa_id"], cenario_ia["beta_id"]]
    cliente = FakeWatsonxClient(
        ["desculpe, não consegui", _resposta(_sugestao(project_ids=ids))]
    )
    with app.test_request_context("/"):
        resultado = sugerir_colecoes(_usuario(cenario_ia["dono_id"]), cliente)
    assert len(cliente.chamadas) == 2
    assert "Sua resposta anterior foi rejeitada" in cliente.chamadas[1][1]
    assert len(resultado.sugestoes) == 1


def test_sugerir_colecoes_reenvia_os_erros_da_validacao(app, cenario_ia):
    ids = [cenario_ia["alfa_id"], cenario_ia["beta_id"]]
    cliente = FakeWatsonxClient(
        [
            _resposta(_sugestao(justificativa="")),
            _resposta(_sugestao(project_ids=ids)),
        ]
    )
    with app.test_request_context("/"):
        sugerir_colecoes(_usuario(cenario_ia["dono_id"]), cliente)
    assert "sugestoes[0].justificativa" in cliente.chamadas[1][1]


def test_sugerir_colecoes_desiste_apos_a_segunda_resposta_invalida(app, cenario_ia):
    cliente = FakeWatsonxClient(["prosa sem json", '{"sugestoes": []}'])
    with app.test_request_context("/"):
        with pytest.raises(SugestaoIndisponivel, match="após retry"):
            sugerir_colecoes(_usuario(cenario_ia["dono_id"]), cliente)
    assert len(cliente.chamadas) == 2


def test_sugerir_colecoes_propaga_indisponibilidade_do_provedor(app, cenario_ia):
    cliente = FakeWatsonxClient([SugestaoIndisponivel("provedor watsonx falhou")])
    with app.test_request_context("/"):
        with pytest.raises(SugestaoIndisponivel, match="provedor watsonx falhou"):
            sugerir_colecoes(_usuario(cenario_ia["dono_id"]), cliente)


def test_sugerir_colecoes_exige_dois_projetos_visiveis(app, cenario_ia):
    cliente = FakeWatsonxClient([])
    with app.test_request_context("/"):
        with pytest.raises(SugestaoIndisponivel, match="insuficientes"):
            sugerir_colecoes(_usuario(cenario_ia["sem_area_id"]), cliente)
    assert cliente.chamadas == []


def test_sugerir_colecoes_descarta_nome_de_colecao_ja_existente(app, cenario_ia):
    ids = [cenario_ia["alfa_id"], cenario_ia["beta_id"]]
    cliente = FakeWatsonxClient(
        [
            _resposta(
                _sugestao(nome="obras", project_ids=ids),
                _sugestao(nome="Saúde digital", project_ids=ids),
            )
        ]
    )
    with app.test_request_context("/"):
        db.session.add(
            ProjectCollection(owner_user_id=cenario_ia["dono_id"], nome="Obras")
        )
        db.session.commit()
        resultado = sugerir_colecoes(_usuario(cenario_ia["dono_id"]), cliente)
    assert [sugestao.nome for sugestao in resultado.sugestoes] == ["Saúde digital"]
    assert "Obras" in cliente.chamadas[0][1]


def test_sugerir_colecoes_devolve_projetos_analisados(app, cenario_ia):
    ids = [cenario_ia["alfa_id"], cenario_ia["beta_id"]]
    cliente = FakeWatsonxClient([_resposta(_sugestao(project_ids=ids))])
    with app.test_request_context("/"):
        resultado = sugerir_colecoes(_usuario(cenario_ia["dono_id"]), cliente)
    analisados = {projeto.id for projeto in resultado.projetos_analisados}
    assert set(ids) <= analisados


# ── grupos candidatos por nome ────────────────────────────────────────────────


def test_montar_prompt_inclui_grupos_candidatos_por_palavra_do_titulo():
    projetos = [
        _candidato(id=1, titulo="Migração SEI Fazenda"),
        _candidato(id=2, titulo="SEI digital"),
        _candidato(id=3, titulo="Integração do SEI"),
        _candidato(id=4, titulo="Capacitação de servidores"),
    ]
    _, user_prompt = montar_prompt(projetos, [])
    assert "<<<GRUPOS_CANDIDATOS" in user_prompt
    assert "sei: 1, 2, 3" in user_prompt


def test_montar_prompt_omite_grupos_com_menos_de_tres_projetos():
    projetos = [
        _candidato(id=1, titulo="Migração SEI Fazenda"),
        _candidato(id=2, titulo="SEI digital"),
        _candidato(id=3, titulo="Capacitação de servidores"),
    ]
    _, user_prompt = montar_prompt(projetos, [])
    assert "<<<GRUPOS_CANDIDATOS" not in user_prompt


def test_grupos_por_nome_ignora_stopwords_de_titulo():
    projetos = [
        _candidato(id=1, titulo="Sistema de Obras Norte"),
        _candidato(id=2, titulo="Sistema de Saúde"),
        _candidato(id=3, titulo="Sistema Tributário"),
    ]
    _, user_prompt = montar_prompt(projetos, [])
    assert "<<<GRUPOS_CANDIDATOS" not in user_prompt


# ── calcular_input_hash ───────────────────────────────────────────────────────

# Blindagem do risco #1 do plano Fase 2: mudança silenciosa nos campos do hash
# quebra este digest e obriga o bump de HASH_VERSION.
DIGEST_FIXO_V3 = "684851040f666f5b4954331629671efdb968bc63c7bcea4342c25099ae32bc56"
MODELO_FIXO = "modelo-fixo/teste-v1"


def _candidatos_fixos() -> list[ProjetoCandidato]:
    return [
        _candidato(id=7, titulo="Telemedicina", descricao=None, orgao_sigla="SES"),
        _candidato(id=3),
    ]


def test_calcular_input_hash_digest_fixo():
    assert calcular_input_hash(_candidatos_fixos(), MODELO_FIXO) == DIGEST_FIXO_V3


def test_calcular_input_hash_independe_da_ordem_da_lista():
    invertidos = list(reversed(_candidatos_fixos()))
    assert calcular_input_hash(invertidos, MODELO_FIXO) == DIGEST_FIXO_V3


def test_calcular_input_hash_muda_com_o_modelo():
    assert calcular_input_hash(_candidatos_fixos(), "outro/modelo") != DIGEST_FIXO_V3


def test_calcular_input_hash_muda_com_o_conteudo():
    editados = [_candidato(id=7, titulo="Telessaúde"), _candidato(id=3)]
    assert calcular_input_hash(editados, MODELO_FIXO) != DIGEST_FIXO_V3


# ── supressão de assinaturas já decididas ─────────────────────────────────────


def _semear_sugestao(user_id: int, project_ids: list[int], status: str) -> None:
    db.session.add(
        ColecaoSugestaoIA(
            user_id=user_id,
            lote_id="a" * 32,
            input_hash="h" * 64,
            ordem=0,
            nome="Lote antigo",
            justificativa="registro anterior",
            project_ids=project_ids,
            assinatura=assinatura_do_conjunto(project_ids),
            status=status,
        )
    )
    db.session.commit()


@pytest.mark.parametrize("status", [STATUS_SUGESTAO_DESCARTADA, STATUS_SUGESTAO_ACEITA])
def test_sugerir_colecoes_suprime_conjunto_ja_decidido(app, cenario_ia, status):
    ids = [cenario_ia["alfa_id"], cenario_ia["beta_id"]]
    cliente = FakeWatsonxClient([_resposta(_sugestao(project_ids=ids))])
    with app.test_request_context("/"):
        _semear_sugestao(cenario_ia["dono_id"], list(reversed(ids)), status)
        resultado = sugerir_colecoes(_usuario(cenario_ia["dono_id"]), cliente)
    assert resultado.sugestoes == []


def test_sugerir_colecoes_nao_suprime_conjunto_apenas_pendente(app, cenario_ia):
    ids = [cenario_ia["alfa_id"], cenario_ia["beta_id"]]
    cliente = FakeWatsonxClient([_resposta(_sugestao(project_ids=ids))])
    with app.test_request_context("/"):
        _semear_sugestao(cenario_ia["dono_id"], ids, STATUS_SUGESTAO_PENDENTE)
        resultado = sugerir_colecoes(_usuario(cenario_ia["dono_id"]), cliente)
    assert len(resultado.sugestoes) == 1


def test_sugerir_colecoes_nao_suprime_decisao_de_outro_usuario(app, cenario_ia):
    ids = [cenario_ia["alfa_id"], cenario_ia["beta_id"]]
    cliente = FakeWatsonxClient([_resposta(_sugestao(project_ids=ids))])
    with app.test_request_context("/"):
        _semear_sugestao(cenario_ia["sem_area_id"], ids, STATUS_SUGESTAO_DESCARTADA)
        resultado = sugerir_colecoes(_usuario(cenario_ia["dono_id"]), cliente)
    assert len(resultado.sugestoes) == 1


def test_sugerir_colecoes_preenche_input_hash_e_modelo(app, cenario_ia):
    ids = [cenario_ia["alfa_id"], cenario_ia["beta_id"]]
    cliente = FakeWatsonxClient([_resposta(_sugestao(project_ids=ids))])
    with app.test_request_context("/"):
        resultado = sugerir_colecoes(_usuario(cenario_ia["dono_id"]), cliente)
    assert resultado.modelo_id == modelo_sugestoes_configurado()
    assert resultado.input_hash == calcular_input_hash(
        resultado.projetos_analisados, resultado.modelo_id
    )


def test_erro_de_deadline_detecta_context_deadline():
    from services.ai.watsonx_client import _erro_de_deadline

    assert _erro_de_deadline(Exception("Downstream vllm ... context deadline exceeded"))
    assert _erro_de_deadline(Exception("Time Limit atingido"))
    assert not _erro_de_deadline(Exception("connection reset by peer"))


# ── filtro de evidência (criterio_palavras) ──────────────────────────────────


def _sugerida_com_criterio(ids: list[int], palavras: list[str]) -> ColecaoSugerida:
    return ColecaoSugerida(
        nome="Grupo",
        descricao=None,
        justificativa="agrupamento",
        project_ids=ids,
        criterio_palavras=palavras,
    )


def test_filtro_de_evidencia_remove_id_sem_palavra_do_criterio():
    from services.ai.collection_suggestions import _filtrar_por_evidencia

    projetos = [
        _candidato(id=1, titulo="Hospital Regional", descricao=None),
        _candidato(id=2, titulo="Telemedicina RJ", descricao=None),
        _candidato(id=3, titulo="Contratação de estagiários", descricao=None),
    ]
    aprovadas = _filtrar_por_evidencia(
        [_sugerida_com_criterio([1, 2, 3], ["hospital", "telemedicina"])], projetos
    )
    assert aprovadas[0].project_ids == [1, 2]


def test_filtro_de_evidencia_ignora_acentos():
    from services.ai.collection_suggestions import _filtrar_por_evidencia

    projetos = [
        _candidato(id=1, titulo="Saude Digital", descricao=None),
        _candidato(id=2, titulo="Posto de Saúde Móvel", descricao=None),
    ]
    aprovadas = _filtrar_por_evidencia(
        [_sugerida_com_criterio([1, 2], ["saúde"])], projetos
    )
    assert aprovadas[0].project_ids == [1, 2]


def test_filtro_de_evidencia_exige_palavra_inteira():
    from services.ai.collection_suggestions import _filtrar_por_evidencia
    from services.ai.suggestion_schema import SugestoesInvalidas

    projetos = [
        _candidato(id=1, titulo="Capacitação de servidores", descricao=None),
        _candidato(id=2, titulo="Rapidez no atendimento", descricao=None),
    ]
    with pytest.raises(SugestoesInvalidas, match="verificação de evidência"):
        _filtrar_por_evidencia([_sugerida_com_criterio([1, 2], ["api"])], projetos)


def test_filtro_de_evidencia_derruba_colecao_com_menos_de_dois_ids():
    from services.ai.collection_suggestions import _filtrar_por_evidencia

    projetos = [
        _candidato(id=1, titulo="API de Dados Abertos", descricao=None),
        _candidato(id=2, titulo="Contratação de estagiários", descricao=None),
        _candidato(id=3, titulo="API de Promoções", descricao=None),
        _candidato(id=4, titulo="Portal de Turismo", descricao=None),
    ]
    sobreviventes = _filtrar_por_evidencia(
        [
            _sugerida_com_criterio([1, 3], ["api"]),
            _sugerida_com_criterio([2, 4], ["saúde"]),
        ],
        projetos,
    )
    assert [s.project_ids for s in sobreviventes] == [[1, 3]]


def test_filtro_de_evidencia_completa_com_candidatos_que_contem_as_palavras():
    from services.ai.collection_suggestions import _filtrar_por_evidencia

    projetos = [
        _candidato(id=1, titulo="Site Drupal da Fazenda", descricao=None),
        _candidato(id=2, titulo="Migração Drupal Educação", descricao=None),
        _candidato(id=3, titulo="Portal Drupal do Turismo", descricao=None),
        _candidato(id=4, titulo="Contratação de estagiários", descricao=None),
    ]
    aprovadas = _filtrar_por_evidencia(
        [_sugerida_com_criterio([1, 2], ["drupal"])], projetos
    )
    assert aprovadas[0].project_ids == [1, 2, 3]


def test_expansao_usa_so_a_palavra_ancora_e_ignora_termo_generico():
    from services.ai.collection_suggestions import _filtrar_por_evidencia

    projetos = [
        _candidato(id=1, titulo="Portal do Turismo RJ", descricao=None),
        _candidato(id=2, titulo="Turismo Rural", descricao=None),
        _candidato(id=3, titulo="Site da Fazenda", descricao=None),
        _candidato(id=4, titulo="Rota do Turismo de Aventura", descricao=None),
    ]
    aprovadas = _filtrar_por_evidencia(
        [_sugerida_com_criterio([1, 2], ["turismo", "site"])], projetos
    )
    assert aprovadas[0].project_ids == [1, 2, 4]
