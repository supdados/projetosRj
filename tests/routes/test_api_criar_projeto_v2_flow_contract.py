"""Contrato dos endpoints consumidos pelo CriarProjetoModal v2 (criação em 2 tempos).

O modal v2 cria o projeto ao fim da fase essencial (3 passos) e depois salva cada
seção complementar como um UPDATE no projeto já existente. Isso reusa endpoints
que já existiam, mas em uma combinação NOVA de payloads — estes testes travam
exatamente essa combinação para que uma futura mudança de backend não quebre o
modal em silêncio:

    1. ``POST /api/projetos``                        — só as 4 chaves essenciais.
    2. ``POST /api/projetos/<id>/inline``            — seção 1 (objetivos).
    3. ``POST /api/projetos/<id>/inline``            — seção 2 (detalhes).
    4. ``POST /api/projetos/<id>/inline``            — seção 3 (links).
    5. ``POST /api/projetos/<id>/importar-modelo``   — seção 4 (etapas).
    6. ``POST /api/projetos/<id>/inline``            — reedição dos essenciais.

Cobre também as 4 notas de contrato que o front precisa respeitar: ``start_date``
obrigatório no import, import ACRESCENTA etapas (guard anti-duplicação no
cliente), etapas em dias ÚTEIS e save de seção AUTORITATIVO (vazio limpa).

Reutiliza as fixtures de ``tests/conftest.py`` (``client_user`` = usuário de
Auditoria, ``seed_data``). Sem mocks de rede.
"""

from __future__ import annotations

from typing import Any


def _ok(response: Any) -> dict[str, Any]:
    payload = response.get_json()
    assert payload["ok"] is True, payload
    return payload["data"]


def _fail(response: Any, *, code: str) -> None:
    payload = response.get_json()
    assert payload["ok"] is False, payload
    assert payload["error"]["code"] == code


def _criar_projeto_essencial(client, seed_data, titulo="Projeto v2") -> int:
    """Executa o passo 3 do modal v2: cria o projeto com as 4 chaves essenciais."""
    response = client.post(
        "/api/projetos",
        json={
            "titulo": titulo,
            "orgao_id": str(seed_data["auditoria_orgao_id"]),
            "prioridade": "alta",
            "short_description": "Resumo do projeto v2",
        },
    )
    assert response.status_code == 200, response.get_json()
    return _ok(response)["id"]


def _detalhe(client, project_id: int) -> dict[str, Any]:
    response = client.get(f"/api/projetos/{project_id}/detalhe")
    assert response.status_code == 200
    return _ok(response)["project"]


# ── Fase essencial (passos 1-3) ───────────────────────────────────────────────


def test_fase_essencial_cria_projeto_com_apenas_4_chaves(client_user, seed_data):
    """O POST de criação do v2 não manda mais nada além do que os 3 passos coletam."""
    response = client_user.post(
        "/api/projetos",
        json={
            "titulo": "Projeto Essencial",
            "orgao_id": str(seed_data["auditoria_orgao_id"]),
            "prioridade": "urgente",
            "short_description": "Descrição do passo 2",
        },
    )

    assert response.status_code == 200
    data = _ok(response)
    project = data["project"]
    assert project["titulo"] == "Projeto Essencial"
    assert project["prioridade"] == "urgente"
    assert project["short_description"] == "Descrição do passo 2"
    assert project["orgao_id"] == seed_data["auditoria_orgao_id"]
    # O projeto nasce completo e válido — o hub só faz UPDATE a partir daqui.
    assert project["status"] == "Vigente"
    assert data["redirect_to"] == f"/projetos/{data['id']}"


# ── Seção 1 — Objetivos e indicadores ─────────────────────────────────────────


def test_secao_objetivos_persiste_cascata_completa(client_user, seed_data):
    project_id = _criar_projeto_essencial(client_user, seed_data)

    response = client_user.post(
        f"/api/projetos/{project_id}/inline",
        json={
            "objetivo_id": 1,
            "resultado_esperado_id": 2,
            "indicadores_ids": [2, 3],
            "abep_indicator": "",
        },
    )

    assert response.status_code == 200
    project = _ok(response)["project"]
    assert project["objetivo_id"] == 1
    assert project["resultado_esperado_id"] == 2
    assert sorted(project["indicadores_ids"]) == [2, 3]
    assert project["abep_indicator"] is None


def test_secao_objetivos_com_nulos_limpa_a_cascata(client_user, seed_data):
    """Reabrir a seção e desmarcar tudo precisa apagar objetivo/resultado/indicadores."""
    project_id = _criar_projeto_essencial(client_user, seed_data)
    client_user.post(
        f"/api/projetos/{project_id}/inline",
        json={
            "objetivo_id": 1,
            "resultado_esperado_id": 2,
            "indicadores_ids": [2, 3],
            "abep_indicator": "",
        },
    )

    response = client_user.post(
        f"/api/projetos/{project_id}/inline",
        json={
            "objetivo_id": None,
            "resultado_esperado_id": None,
            "indicadores_ids": [],
            "abep_indicator": "",
        },
    )

    assert response.status_code == 200
    project = _ok(response)["project"]
    assert project["objetivo_id"] is None
    assert project["resultado_esperado_id"] is None
    assert project["indicadores_ids"] == []


def test_secao_objetivos_rejeita_indicador_de_outro_resultado(client_user, seed_data):
    project_id = _criar_projeto_essencial(client_user, seed_data)

    response = client_user.post(
        f"/api/projetos/{project_id}/inline",
        json={
            "objetivo_id": 1,
            "resultado_esperado_id": 2,
            "indicadores_ids": [6],
            "abep_indicator": "",
        },
    )

    assert response.status_code == 422
    _fail(response, code="validation")


# ── Seção 2 — Detalhes ────────────────────────────────────────────────────────


def test_secao_detalhes_persiste_todas_as_chaves(client_user, seed_data):
    project_id = _criar_projeto_essencial(client_user, seed_data)

    response = client_user.post(
        f"/api/projetos/{project_id}/inline",
        json={
            "orgao": "Subsecretaria de Testes",
            "delivery_type": "Painel",
            "special_project": "ABEP",
            "sei_processes": ["380001/000664/2026", "380001/000665/2026"],
            "observacao": "Observação da seção 2",
        },
    )

    assert response.status_code == 200
    project = _ok(response)["project"]
    assert project["orgao"] == "Subsecretaria de Testes"
    assert project["delivery_type"] == "Painel"
    assert project["special_project"] == "ABEP"
    assert project["sei_processes"] == [
        "SEI-380001/000664/2026",
        "SEI-380001/000665/2026",
    ]
    assert project["observacao"] == "Observação da seção 2"


def test_secao_detalhes_e_autoritativa_e_limpa_com_vazios(client_user, seed_data):
    """Nota de contrato 4: a seção manda TODAS as suas chaves; vazio limpa o campo."""
    project_id = _criar_projeto_essencial(client_user, seed_data)
    client_user.post(
        f"/api/projetos/{project_id}/inline",
        json={
            "orgao": "Subsecretaria de Testes",
            "delivery_type": "Painel",
            "special_project": "ABEP",
            "sei_processes": ["380001/000664/2026"],
            "observacao": "Some depois",
        },
    )

    response = client_user.post(
        f"/api/projetos/{project_id}/inline",
        json={
            "orgao": "",
            "delivery_type": "",
            "special_project": "",
            "sei_processes": [],
            "observacao": "",
        },
    )

    assert response.status_code == 200
    project = _ok(response)["project"]
    assert project["orgao"] is None
    assert project["delivery_type"] is None
    assert project["special_project"] is None
    assert project["sei_processes"] == []
    assert project["observacao"] is None


def test_secao_detalhes_ignora_processo_sei_em_branco(client_user, seed_data):
    """Uma linha de SEI aberta e vazia não pode derrubar o save da seção inteira."""
    project_id = _criar_projeto_essencial(client_user, seed_data)

    response = client_user.post(
        f"/api/projetos/{project_id}/inline",
        json={
            "orgao": "",
            "delivery_type": "",
            "special_project": "",
            "sei_processes": ["380001/000664/2026", "", "   "],
            "observacao": "",
        },
    )

    assert response.status_code == 200
    assert _ok(response)["project"]["sei_processes"] == ["SEI-380001/000664/2026"]


# ── Seção 3 — Links ───────────────────────────────────────────────────────────


def test_secao_links_persiste_fixos_e_personalizados(client_user, seed_data):
    project_id = _criar_projeto_essencial(client_user, seed_data)

    response = client_user.post(
        f"/api/projetos/{project_id}/inline",
        json={
            "github_link": "github.com/rj/projeto",
            "documentation_link": "https://docs.rj.gov.br/projeto",
            "product_link": "https://app.rj.gov.br/projeto",
            "custom_links": [
                {"label": "Painel BI", "url": "https://bi.rj.gov.br/p"},
                {"label": "Ata", "url": "https://sei.rj.gov.br/ata"},
            ],
        },
    )

    assert response.status_code == 200
    project = _ok(response)["project"]
    # URL sem scheme é normalizada para https:// pelo backend.
    assert project["github_link"] == "https://github.com/rj/projeto"
    assert project["documentation_link"] == "https://docs.rj.gov.br/projeto"
    assert project["product_link"] == "https://app.rj.gov.br/projeto"
    assert project["custom_links"] == [
        {"label": "Painel BI", "url": "https://bi.rj.gov.br/p"},
        {"label": "Ata", "url": "https://sei.rj.gov.br/ata"},
    ]


def test_secao_links_e_autoritativa_e_limpa_com_vazios(client_user, seed_data):
    project_id = _criar_projeto_essencial(client_user, seed_data)
    client_user.post(
        f"/api/projetos/{project_id}/inline",
        json={
            "github_link": "https://github.com/rj/projeto",
            "documentation_link": "",
            "product_link": "",
            "custom_links": [{"label": "Painel BI", "url": "https://bi.rj.gov.br/p"}],
        },
    )

    response = client_user.post(
        f"/api/projetos/{project_id}/inline",
        json={
            "github_link": "",
            "documentation_link": "",
            "product_link": "",
            "custom_links": [],
        },
    )

    assert response.status_code == 200
    project = _ok(response)["project"]
    assert project["github_link"] is None
    assert project["custom_links"] == []


def test_secao_links_rejeita_mais_de_tres_personalizados(client_user, seed_data):
    project_id = _criar_projeto_essencial(client_user, seed_data)

    response = client_user.post(
        f"/api/projetos/{project_id}/inline",
        json={
            "github_link": "",
            "documentation_link": "",
            "product_link": "",
            "custom_links": [
                {"label": f"Link {i}", "url": f"https://rj.gov.br/{i}"}
                for i in range(4)
            ],
        },
    )

    assert response.status_code == 422
    _fail(response, code="validation")


# ── Seção 4 — Etapas (importar modelo) ────────────────────────────────────────


def test_secao_etapas_exige_start_date(client_user, seed_data):
    """Nota de contrato 1: sem ``start_date`` o import é 422 — o front preenche com hoje."""
    project_id = _criar_projeto_essencial(client_user, seed_data)

    response = client_user.post(
        f"/api/projetos/{project_id}/importar-modelo",
        json={"template_id": seed_data["template_id"]},
    )

    assert response.status_code == 422
    _fail(response, code="validation")


def test_secao_etapas_cria_etapas_em_dias_uteis(client_user, seed_data):
    """Nota de contrato 3: a duração do modelo é contada em dias ÚTEIS.

    Modelo semeado: Planejamento (2 dias) + Execucao (3 dias). Começando numa
    sexta (2026-01-09), o fim da 1ª etapa cai na segunda (12) — não no sábado
    (10), como seria em dias corridos.
    """
    project_id = _criar_projeto_essencial(client_user, seed_data)

    response = client_user.post(
        f"/api/projetos/{project_id}/importar-modelo",
        json={"template_id": seed_data["template_id"], "start_date": "2026-01-09"},
    )

    assert response.status_code == 200
    data = _ok(response)
    assert data["etapas_criadas"] == 2
    etapas = data["etapas"]
    assert etapas[0]["descricao"] == "Planejamento"
    assert etapas[0]["data_inicio"] == "2026-01-09"
    assert etapas[0]["data_fim"] == "2026-01-12"
    assert etapas[1]["descricao"] == "Execucao"
    assert etapas[1]["data_inicio"] == "2026-01-13"
    assert etapas[1]["data_fim"] == "2026-01-15"


def test_secao_etapas_normaliza_start_date_de_fim_de_semana(client_user, seed_data):
    project_id = _criar_projeto_essencial(client_user, seed_data)

    response = client_user.post(
        f"/api/projetos/{project_id}/importar-modelo",
        json={"template_id": seed_data["template_id"], "start_date": "2026-01-10"},
    )

    assert response.status_code == 200
    assert _ok(response)["etapas"][0]["data_inicio"] == "2026-01-12"


def test_secao_etapas_importar_duas_vezes_acrescenta(client_user, seed_data):
    """Nota de contrato 2: o import ACRESCENTA — por isso o front trava o 2º POST."""
    project_id = _criar_projeto_essencial(client_user, seed_data)
    payload = {
        "template_id": seed_data["template_id"],
        "start_date": "2026-01-09",
    }
    client_user.post(f"/api/projetos/{project_id}/importar-modelo", json=payload)

    response = client_user.post(
        f"/api/projetos/{project_id}/importar-modelo", json=payload
    )

    assert response.status_code == 200
    data = _ok(response)
    assert data["etapas_criadas"] == 2
    # 4 etapas no total: o backend não deduplica, o guard é do cliente.
    assert len(data["etapas"]) == 4
    assert [etapa["ordem"] for etapa in data["etapas"]] == [0, 1, 2, 3]


# ── Reedição dos essenciais (lápis do hub) ────────────────────────────────────


def test_reeditar_essenciais_apos_criacao(client_user, seed_data):
    project_id = _criar_projeto_essencial(client_user, seed_data)

    response = client_user.post(
        f"/api/projetos/{project_id}/inline",
        json={
            "titulo": "Projeto v2 Renomeado",
            "short_description": "Resumo revisado",
            "prioridade": "baixa",
            "orgao_id": seed_data["auditoria_orgao_id"],
        },
    )

    assert response.status_code == 200
    project = _ok(response)["project"]
    assert project["titulo"] == "Projeto v2 Renomeado"
    assert project["short_description"] == "Resumo revisado"
    assert project["prioridade"] == "baixa"
    assert project["orgao_id"] == seed_data["auditoria_orgao_id"]


def test_reeditar_essenciais_para_orgao_fora_do_escopo_retorna_403(
    client_user, seed_data
):
    project_id = _criar_projeto_essencial(client_user, seed_data)

    response = client_user.post(
        f"/api/projetos/{project_id}/inline",
        json={
            "titulo": "Projeto v2",
            "short_description": "",
            "prioridade": "alta",
            "orgao_id": seed_data["vpd_orgao_id"],
        },
    )

    assert response.status_code == 403
    _fail(response, code="forbidden")


# ── Fluxo completo ────────────────────────────────────────────────────────────


def test_fluxo_completo_v2_preserva_todos_os_campos(client_user, seed_data):
    """Passo 3 → 4 seções: nenhum campo se perde entre um save e o seguinte."""
    project_id = _criar_projeto_essencial(client_user, seed_data, titulo="Projeto Hub")

    client_user.post(
        f"/api/projetos/{project_id}/inline",
        json={
            "objetivo_id": 1,
            "resultado_esperado_id": 2,
            "indicadores_ids": [2, 3],
            "abep_indicator": "",
        },
    )
    client_user.post(
        f"/api/projetos/{project_id}/inline",
        json={
            "orgao": "Subsecretaria de Testes",
            "delivery_type": "Sistema",
            "special_project": "TCE",
            "sei_processes": ["380001/000664/2026"],
            "observacao": "Observação final",
        },
    )
    client_user.post(
        f"/api/projetos/{project_id}/inline",
        json={
            "github_link": "https://github.com/rj/hub",
            "documentation_link": "",
            "product_link": "",
            "custom_links": [{"label": "Painel", "url": "https://bi.rj.gov.br/hub"}],
        },
    )
    client_user.post(
        f"/api/projetos/{project_id}/importar-modelo",
        json={"template_id": seed_data["template_id"], "start_date": "2026-01-09"},
    )

    project = _detalhe(client_user, project_id)
    assert project["titulo"] == "Projeto Hub"
    assert project["short_description"] == "Resumo do projeto v2"
    assert project["prioridade"] == "alta"
    assert project["objetivo_id"] == 1
    assert sorted(project["indicadores_ids"]) == [2, 3]
    assert project["delivery_type"] == "Sistema"
    assert project["special_project"] == "TCE"
    assert project["sei_processes"] == ["SEI-380001/000664/2026"]
    assert project["observacao"] == "Observação final"
    assert project["github_link"] == "https://github.com/rj/hub"
    assert project["custom_links"] == [
        {"label": "Painel", "url": "https://bi.rj.gov.br/hub"}
    ]
    assert project["total_workflow_etapas"] == 2
