"""Testes unitários de services/siorg_sync.py (executar_sync_siorg).

Usa FakeSiorgClient com payloads fixture (árvore de 5 nós em 2 níveis) e o
banco SQLite da fixture ``app`` — sem HTTP real. NÃO valida a UI: cobre
upsert por codigo_externo, desativação de ausentes, legado intocado, no-op
por manifesto e o lock anti-concorrência.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from models import OrgaoClosure, OrgaoUnidade, SiorgSyncLog, db
from services.siorg_client import SiorgApiError
from services.siorg_sync import SiorgSyncEmAndamento, executar_sync_siorg
from time_utils import utc_now

# ── Fakes e fixtures de payload ───────────────────────────────────────────────


class FakeSiorgClient:
    """Client fake: devolve manifesto/árvore fixos e conta as chamadas."""

    def __init__(self, manifesto: dict[str, Any], arvore: list[dict[str, Any]]):
        self.manifesto = manifesto
        self.arvore = arvore
        self.chamadas_arvore = 0

    def obter_manifesto(self) -> dict[str, Any]:
        return dict(self.manifesto)

    def obter_arvore(self, codigo_raiz: int) -> list[dict[str, Any]]:
        self.chamadas_arvore += 1
        return self.arvore


def _no(
    codigo: int,
    sigla: str,
    *,
    tipo: str = "UA",
    codigo_pai: int | None = None,
    ativo: bool = True,
    ordenacao: int = 0,
    filhos: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": 1000 + codigo,
        "codigo": str(codigo),
        "codigo_pai": str(codigo_pai) if codigo_pai is not None else None,
        "sigla": sigla,
        "nome": f"Nome {sigla}",
        "tipo": tipo,
        "area_atuacao": None,
        "ativo": ativo,
        "ordenacao": ordenacao,
        "filhos": filhos or [],
    }


MANIFESTO = {
    "versao_global": 7,
    "gerado_em": "2026-07-14T12:00:00Z",
    "total_unidades": 5,
    "hash": "abc123",
    "contrato": "v1",
}

# 5 nós, 2 níveis: SETD (raiz do escopo; pai "1" fora do payload) + 4 filhos.
ARVORE = [
    _no(
        2,
        "SETD",
        tipo="ORGAO",
        codigo_pai=1,
        filhos=[
            _no(4, "GABSEC", codigo_pai=2, ordenacao=1),
            _no(8, "AUD", codigo_pai=2, ordenacao=2),
            _no(10, "OUVI", codigo_pai=2, ordenacao=3),
            _no(36, "PRESI", codigo_pai=2, ordenacao=4, ativo=False),
        ],
    )
]


class FakeSiorgClientArvoreQuebrada(FakeSiorgClient):
    """Client fake que falha ao baixar a árvore (SIORG caiu no meio do sync)."""

    def obter_arvore(self, codigo_raiz: int) -> list[dict[str, Any]]:
        raise SiorgApiError("SIORG respondeu HTTP 500 em /unidades/2/arvore")


def _client() -> FakeSiorgClient:
    return FakeSiorgClient(MANIFESTO, ARVORE)


def _por_codigo(codigo: str) -> OrgaoUnidade | None:
    return OrgaoUnidade.query.filter_by(codigo_externo=codigo).first()


# ── Criação ───────────────────────────────────────────────────────────────────


def test_sync_cria_unidades_novas_com_pai_e_closure(app):
    with app.app_context():
        log = executar_sync_siorg(_client(), None, codigo_raiz=2)

        assert log.status == "sucesso"
        assert log.criadas == 5
        assert log.atualizadas == 0
        assert log.desativadas == 0
        assert log.versao_global == "7"
        assert log.hash_manifesto == "abc123"
        assert log.finalizado_em is not None

        setd = _por_codigo("2")
        gabsec = _por_codigo("4")
        assert setd is not None and gabsec is not None
        assert setd.pai_id is None  # codigo_pai "1" fora do payload
        assert gabsec.pai_id == setd.id
        assert gabsec.tipo == "UA"
        assert gabsec.tipo_id is None
        assert gabsec.ordem == 1
        assert _por_codigo("36").ativo is False  # respeita "ativo" do nó
        assert OrgaoClosure.query.count() > 0


# ── Atualização in-place por codigo_externo ──────────────────────────────────


def test_sync_atualiza_in_place_por_codigo_externo_preservando_id(app):
    with app.app_context():
        local = OrgaoUnidade(
            nome="GABSEC antigo",
            sigla="GABVELHO",
            tipo="Subsecretaria",
            codigo_externo="4",
            ativo=True,
        )
        db.session.add(local)
        db.session.commit()
        local_id = local.id

        log = executar_sync_siorg(_client(), None, codigo_raiz=2)

        assert log.criadas == 4
        assert log.atualizadas == 1
        atualizado = _por_codigo("4")
        assert atualizado.id == local_id
        assert atualizado.nome == "Nome GABSEC"
        assert atualizado.sigla == "GABSEC"
        assert atualizado.tipo == "UA"
        assert atualizado.tipo_id is None


# ── Desativação de ausentes ───────────────────────────────────────────────────


def test_sync_desativa_unidade_com_codigo_externo_ausente_do_payload(app):
    with app.app_context():
        sumida = OrgaoUnidade(
            nome="Extinta",
            sigla="EXT",
            tipo="Subsecretaria",
            codigo_externo="999",
            ativo=True,
        )
        db.session.add(sumida)
        db.session.commit()

        log = executar_sync_siorg(_client(), None, codigo_raiz=2)

        assert log.desativadas == 1
        assert _por_codigo("999").ativo is False


# ── Legado sem codigo_externo intocado ────────────────────────────────────────


def test_sync_nao_toca_unidade_legada_sem_codigo_externo(app):
    with app.app_context():
        legado = OrgaoUnidade(
            nome="Escritorio Central",
            sigla="ECENTRAL",
            tipo="Subsecretaria",
            codigo_externo=None,
            ativo=True,
        )
        db.session.add(legado)
        db.session.commit()

        log = executar_sync_siorg(_client(), None, codigo_raiz=2)

        recarregado = OrgaoUnidade.query.filter_by(sigla="ECENTRAL").one()
        assert recarregado.ativo is True
        assert recarregado.nome == "Escritorio Central"
        assert recarregado.codigo_externo is None
        assert log.desativadas == 0


# ── Caminho de erro (falha da API no meio do sync) ───────────────────────────


def test_sync_fecha_log_como_erro_sem_criar_unidades_quando_arvore_falha(app):
    with app.app_context():
        client = FakeSiorgClientArvoreQuebrada(MANIFESTO, ARVORE)

        with pytest.raises(SiorgApiError):
            executar_sync_siorg(client, None, codigo_raiz=2)

        log = SiorgSyncLog.query.order_by(SiorgSyncLog.id.desc()).first()
        assert log.status == "erro"
        assert log.erro
        assert OrgaoUnidade.query.count() == 0  # rollback: nada persistido


# ── Payload com codigo duplicado ──────────────────────────────────────────────


def test_sync_nao_duplica_unidade_quando_payload_repete_codigo(app):
    with app.app_context():
        arvore = [ARVORE[0], _no(4, "GABSEC", codigo_pai=2, ordenacao=1)]
        log = executar_sync_siorg(FakeSiorgClient(MANIFESTO, arvore), None)

        assert log.status == "sucesso"
        assert log.criadas == 5
        assert OrgaoUnidade.query.filter_by(codigo_externo="4").count() == 1


# ── No-op por manifesto igual ─────────────────────────────────────────────────


def test_sync_finaliza_noop_quando_manifesto_igual_ao_ultimo_sucesso(app):
    with app.app_context():
        primeiro = executar_sync_siorg(_client(), None, codigo_raiz=2)
        assert primeiro.criadas == 5

        client = _client()
        segundo = executar_sync_siorg(client, None, codigo_raiz=2)

        assert segundo.status == "sucesso"
        assert (segundo.criadas, segundo.atualizadas, segundo.desativadas) == (0, 0, 0)
        assert client.chamadas_arvore == 0  # nem baixa a árvore


def test_sync_reprocessa_quando_hash_muda_mesmo_com_versao_global_igual(app):
    with app.app_context():
        executar_sync_siorg(_client(), None, codigo_raiz=2)

        client = FakeSiorgClient(dict(MANIFESTO, hash="def456"), ARVORE)
        log = executar_sync_siorg(client, None, codigo_raiz=2)

        assert log.status == "sucesso"
        assert client.chamadas_arvore == 1  # hash decide sozinho; versao é fallback


def test_sync_reprocessa_quando_raiz_muda_mesmo_com_manifesto_igual(app):
    with app.app_context():
        executar_sync_siorg(_client(), None, codigo_raiz=2)

        client = _client()
        log = executar_sync_siorg(client, None, codigo_raiz=1)

        assert log.status == "sucesso"
        assert log.codigo_raiz == 1
        assert client.chamadas_arvore == 1  # manifesto é global; raiz nova re-sync


# ── Lock anti-concorrência ────────────────────────────────────────────────────


def test_sync_aborta_quando_ja_existe_em_andamento_recente(app):
    with app.app_context():
        db.session.add(SiorgSyncLog(status="em_andamento", iniciado_em=utc_now()))
        db.session.commit()

        with pytest.raises(SiorgSyncEmAndamento):
            executar_sync_siorg(_client(), None, codigo_raiz=2)


def test_sync_marca_lock_morto_como_erro_e_prossegue(app):
    with app.app_context():
        morto = SiorgSyncLog(
            status="em_andamento",
            iniciado_em=utc_now() - timedelta(minutes=30),
        )
        db.session.add(morto)
        db.session.commit()

        log = executar_sync_siorg(_client(), None, codigo_raiz=2)

        assert log.status == "sucesso"
        assert log.criadas == 5
        assert morto.status == "erro"
        assert morto.erro is not None
