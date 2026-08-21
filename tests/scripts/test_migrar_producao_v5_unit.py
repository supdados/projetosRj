"""Orquestrador da migração v5.0: portão por reexecução, travas e ensaio."""

import json
from argparse import Namespace
from pathlib import Path

import pytest

from scripts.migrations import migrar_producao_v5 as orquestrador
from scripts.migrations.auditoria_role_map import (
    EstadoColapso,
    ancestrais_de,
    auditar,
    cobertura_da_poda,
    conferir_keep,
    desserializar_mapas,
    desserializar_vinculos,
    keep_esperado,
    motivo_da_reprovacao,
    pares_de_vinculo,
    perdas_de_alcance,
    resumo,
    serializar_mapas,
    serializar_vinculos,
)
from scripts.migrations.migrar_producao_v5 import (
    ORDEM,
    Contexto,
    StageAbortado,
    _classes_de_aborto,
    _ensaio_em_uma_transacao,
    _rodar,
    _stages_pedidos,
    exigir_role_map_pre,
    exigir_vinculos_pre,
    recusar_sobrescrever_a_base,
    stage_colapso,
    stage_organograma,
)
from scripts.migrations.verificacao_schema import REVISAO_ESPERADA_PRE, mensagem_schema
from services.user_orgao_collapse import calcular_colapso, rank_do_papel

# Árvore de ensaio: 1=GOVRJ (raiz genérica) -> 2=SETD (genérica) -> 10 -> 12,
# 11; e 1 -> 9=PRODERJ (genérica) -> 20.
DESCENDENTES = {
    1: {1, 2, 9, 10, 11, 12, 20},
    2: {2, 10, 11, 12},
    9: {9, 20},
    10: {10, 12},
    11: {11},
    12: {12},
    20: {20},
}
ANCESTRAIS = ancestrais_de(DESCENDENTES)
GENERICOS = frozenset({1, 2, 9})
GESTOR = "gestor"


def _keep(vinculos_pre) -> set[tuple[int, int, str]]:
    return keep_esperado(
        vinculos_pre, GENERICOS, ANCESTRAIS, calcular_colapso, rank_do_papel
    )


def _conferencia(vinculos_pre, vinculos_pos):
    return conferir_keep(_keep(vinculos_pre), pares_de_vinculo(vinculos_pos))


def _estado(**ajustes) -> EstadoColapso:
    base = {
        "role_map_pre": {},
        "role_map_pos": {},
        "vinculos_pre": {},
        "vinculos_pos": {},
        "genericos": GENERICOS,
        "descendentes": DESCENDENTES,
        "ancestrais": ANCESTRAIS,
        "usernames": {7: "feu", 17: "proderj"},
    }
    return EstadoColapso(**{**base, **ajustes})


def _auditar(**ajustes):
    estado = _estado(**ajustes)
    return auditar(estado, _conferencia(estado.vinculos_pre, estado.vinculos_pos))


def _relatorio(tmp_path: Path, **conteudo) -> Path:
    caminho = tmp_path / "migracao.json"
    caminho.write_text(json.dumps(conteudo), encoding="utf-8")
    return caminho


class SessaoFalsa:
    """Conta commit/rollback/flush no lugar de um Session do SQLAlchemy."""

    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.flushes = 0

    def __call__(self) -> "SessaoFalsa":
        return self

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def flush(self) -> None:
        self.flushes += 1


class BancoFalso:
    """Só o que os stages usam de `db`: `db.session` e `db.session()`."""

    def __init__(self, sessao: SessaoFalsa) -> None:
        self.session = sessao


# portão por reexecução (E2) ---


def test_keep_esperado_poda_generico_e_absorve_descendente():
    keep = _keep({7: [(2, GESTOR), (10, GESTOR), (12, GESTOR), (11, GESTOR)]})
    assert keep == {(7, 10, GESTOR), (7, 11, GESTOR)}


def test_keep_esperado_preserva_quem_so_tinha_generico():
    assert _keep({17: [(9, GESTOR)]}) == {(17, 9, GESTOR)}


def test_keep_esperado_nao_absorve_descendente_de_rank_maior():
    keep = _keep({7: [(10, "leitor"), (12, GESTOR)]})
    assert keep == {(7, 10, "leitor"), (7, 12, GESTOR)}


def test_portao_aprova_o_estado_que_o_colapso_produz():
    conferencia = _conferencia(
        {7: [(2, GESTOR), (10, GESTOR), (11, GESTOR)]},
        {7: [(10, GESTOR), (11, GESTOR)]},
    )
    assert conferencia.aprovada
    assert (conferencia.faltando, conferencia.sobrando) == ((), ())


def test_portao_reprova_vinculo_apagado_a_mao_dentro_da_subarvore_podada():
    # É o ponto cego da heurística antiga: 11 está dentro de SETD, que foi
    # podada, então a perda passava como "explicada".
    auditoria = _auditar(
        role_map_pre={7: {2: 30, 10: 30, 11: 30}},
        role_map_pos={7: {10: 30}},
        vinculos_pre={7: [(2, GESTOR), (10, GESTOR), (11, GESTOR)]},
        vinculos_pos={7: [(10, GESTOR)]},
    )
    assert auditoria.perdas[0].nao_explicados == ()
    assert auditoria.conferencia.faltando == ((7, 11, GESTOR),)
    assert not auditoria.aprovada
    assert "diverge do colapso recalculado" in motivo_da_reprovacao(auditoria)


def test_portao_reprova_vinculo_acrescentado_a_mao():
    conferencia = _conferencia(
        {7: [(2, GESTOR), (10, GESTOR)]}, {7: [(10, GESTOR), (20, GESTOR)]}
    )
    assert conferencia.sobrando == ((7, 20, GESTOR),)
    assert not conferencia.aprovada


def test_portao_reprova_papel_trocado_a_mao():
    conferencia = _conferencia({7: [(10, GESTOR)]}, {7: [(10, "leitor")]})
    assert conferencia.faltando == ((7, 10, GESTOR),)
    assert conferencia.sobrando == ((7, 10, "leitor"),)


def test_portao_reprova_absorvido_que_ficou_no_banco():
    conferencia = _conferencia(
        {7: [(10, GESTOR), (12, GESTOR)]}, {7: [(10, GESTOR), (12, GESTOR)]}
    )
    assert conferencia.sobrando == ((7, 12, GESTOR),)


def test_resumo_traz_o_veredito_antes_do_relato_de_perda():
    auditoria = _auditar(
        role_map_pre={7: {2: 30, 10: 30, 11: 30}},
        role_map_pos={7: {10: 30}},
        vinculos_pre={7: [(2, GESTOR), (10, GESTOR), (11, GESTOR)]},
        vinculos_pos={7: [(10, GESTOR)]},
    )
    dados = resumo(auditoria)
    assert dados["keep_confere"] is False
    assert dados["pares_faltando"] == 1
    assert dados["divergencias"] == [[7, 11, GESTOR]]
    assert dados["usuarios_com_perda"] == 1


def test_linhas_marcam_a_divergencia_com_o_username():
    auditoria = _auditar(
        vinculos_pre={7: [(10, GESTOR)]}, vinculos_pos={7: [(11, GESTOR)]}
    )
    linhas = " | ".join(auditoria.linhas())
    assert "FALTANDO em user_orgao: feu" in linhas
    assert "SOBRANDO em user_orgao: feu" in linhas


# relato informativo de perda de alcance ---


def test_perdas_pega_queda_de_rank_e_orgao_sumido():
    assert perdas_de_alcance({1: 30, 2: 30, 3: 10}, {1: 30, 2: 10}) == {
        2: (30, 10),
        3: (10, 0),
    }


def test_perdas_ignora_ganho_de_alcance():
    assert perdas_de_alcance({1: 10}, {1: 30, 2: 30}) == {}


def test_cobertura_da_poda_e_so_o_que_o_vinculo_mantido_nao_alcanca():
    assert cobertura_da_poda([2, 10], [10], GENERICOS, DESCENDENTES) == {2, 11}


def test_cobertura_da_poda_da_raiz_nao_engole_o_ramo_preservado():
    assert 20 not in cobertura_da_poda([1, 20], [20], GENERICOS, DESCENDENTES)


def test_usuario_que_ficou_sem_nenhum_vinculo_reprova_a_auditoria():
    auditoria = _auditar(
        role_map_pre={17: {9: 30, 20: 30}},
        role_map_pos={17: {}},
        vinculos_pre={17: [(9, GESTOR)]},
        vinculos_pos={},
    )
    zerado = auditoria.sem_nenhum_vinculo[0]
    assert (zerado.user_id, zerado.username, zerado.vinculos_antes) == (
        17,
        "proderj",
        1,
    )
    assert auditoria.sem_nenhum_alcance[0].user_id == 17
    assert not auditoria.aprovada
    assert resumo(auditoria)["usuarios_sem_nenhum_vinculo"][0]["username"] == "proderj"


def test_usuario_sem_vinculo_antes_e_depois_nao_e_zerado():
    auditoria = _auditar(vinculos_pre={17: []}, vinculos_pos={})
    assert auditoria.sem_nenhum_vinculo == ()
    assert auditoria.aprovada


def test_auditoria_omite_usuario_sem_perda():
    auditoria = _auditar(
        role_map_pre={7: {10: 30}},
        role_map_pos={7: {10: 30, 11: 30}},
        vinculos_pre={7: [(10, GESTOR)]},
        vinculos_pos={7: [(10, GESTOR)]},
    )
    assert auditoria.perdas == ()
    assert auditoria.aprovada


# linha de base no relatório (E3) ---


def test_snapshot_recusa_sobrescrever_uma_base_ja_aplicada(tmp_path):
    caminho = _relatorio(
        tmp_path,
        role_map_pre={"7": {"10": 30}},
        vinculos_pre={"7": [[10, GESTOR], [11, GESTOR]]},
        role_map_pre_aplicado=True,
    )
    with pytest.raises(StageAbortado, match="1 usuários, 2 vínculos"):
        recusar_sobrescrever_a_base(Contexto(apply=True, relatorio=caminho))


def test_snapshot_pode_regravar_base_de_ensaio_e_relatorio_novo(tmp_path):
    ensaio = _relatorio(
        tmp_path, role_map_pre={"7": {"10": 30}}, role_map_pre_aplicado=False
    )
    assert recusar_sobrescrever_a_base(Contexto(apply=True, relatorio=ensaio)) is None
    novo = Contexto(apply=True, relatorio=tmp_path / "outro.json")
    assert recusar_sobrescrever_a_base(novo) is None


def test_colapso_aborta_antes_de_escrever_quando_falta_a_linha_de_base(tmp_path):
    ctx = Contexto(apply=True, relatorio=tmp_path / "inexistente.json")
    with pytest.raises(StageAbortado, match="snapshot_role_map"):
        stage_colapso(ctx)


def test_snapshot_de_ensaio_nao_serve_de_base_para_o_colapso_real(tmp_path):
    caminho = _relatorio(
        tmp_path, role_map_pre={"7": {"10": 30}}, role_map_pre_aplicado=False
    )
    with pytest.raises(StageAbortado, match="dry-run"):
        exigir_role_map_pre(Contexto(apply=True, relatorio=caminho))
    assert exigir_role_map_pre(Contexto(apply=False, relatorio=caminho))


def test_vinculos_pre_no_formato_antigo_sem_papel_aborta(tmp_path):
    caminho = _relatorio(tmp_path, vinculos_pre={"7": [10, 11]})
    with pytest.raises(StageAbortado, match="orgao_id, papel"):
        exigir_vinculos_pre(Contexto(apply=True, relatorio=caminho))


def test_vinculos_sobrevivem_ao_json_com_o_papel():
    vinculos = {7: [(10, GESTOR), (11, "leitor")]}
    bruto = json.loads(json.dumps(serializar_vinculos(vinculos)))
    assert desserializar_vinculos(bruto) == vinculos


def test_role_map_sobrevive_ao_json():
    mapas = {7: {1: 30, 2: 10}}
    assert desserializar_mapas(serializar_mapas(mapas)) == mapas


# runner ---


def test_stages_pedidos_respeita_a_ordem_canonica():
    args = Namespace(all=False, stage=["colapso", "snapshot"])
    assert _stages_pedidos(args) == ["snapshot", "colapso"]


def test_stages_pedidos_com_all_roda_tudo():
    assert _stages_pedidos(Namespace(all=True, stage=None)) == list(ORDEM)


def test_mensagem_de_schema_incompleto_ensina_o_stamp_purge():
    mensagem = mensagem_schema(["orgao_tipo"], {}, {})
    assert f"stamp --purge {REVISAO_ESPERADA_PRE}" in mensagem
    assert "orgao_tipo" in mensagem


def test_organograma_aborta_citando_o_csv_ausente(tmp_path, monkeypatch):
    ausente = tmp_path / "estrutura_setd_proderj.csv"
    monkeypatch.setattr(
        "scripts.catalog.organograma_siorg.CSV_PADRAO", ausente, raising=True
    )
    with pytest.raises(StageAbortado, match=str(ausente)):
        stage_organograma(Contexto(apply=False, relatorio=tmp_path / "r.json"))


def test_colapso_ja_aplicado_sai_como_abort_limpo(tmp_path, monkeypatch, capsys):
    from scripts.migrations.backfill_orgaos import ColapsoJaAplicado

    def recusar(ctx: Contexto) -> dict[str, object]:
        raise ColapsoJaAplicado("o colapso de vinculos ja rodou neste banco")

    assert ColapsoJaAplicado in _classes_de_aborto()
    monkeypatch.setitem(orquestrador.STAGES, "backfill_orgaos", recusar)
    monkeypatch.setattr(orquestrador, "db", BancoFalso(SessaoFalsa()))
    ctx = Contexto(apply=True, relatorio=tmp_path / "r.json")
    assert _rodar(["backfill_orgaos"], ctx) == 1
    erro = capsys.readouterr().err
    assert "ColapsoJaAplicado" in erro
    assert "ja rodou neste banco" in erro


def test_erro_de_verdade_continua_estourando(tmp_path, monkeypatch):
    def quebrar(ctx: Contexto) -> dict[str, object]:
        raise ValueError("bug de verdade")

    monkeypatch.setitem(orquestrador.STAGES, "snapshot", quebrar)
    monkeypatch.setattr(orquestrador, "db", BancoFalso(SessaoFalsa()))
    with pytest.raises(ValueError, match="bug de verdade"):
        _rodar(["snapshot"], Contexto(apply=True, relatorio=tmp_path / "r.json"))


def test_ensaio_em_dry_run_troca_commit_por_flush_e_desfaz_no_fim(monkeypatch):
    sessao = SessaoFalsa()
    monkeypatch.setattr(orquestrador, "db", BancoFalso(sessao))
    with _ensaio_em_uma_transacao(Contexto(apply=False, relatorio=Path("r.json"))):
        sessao.commit()
        sessao.rollback()
    assert (sessao.commits, sessao.flushes, sessao.rollbacks) == (0, 1, 1)
    sessao.commit()
    assert sessao.commits == 1


def test_ensaio_com_apply_nao_toca_na_sessao(monkeypatch):
    sessao = SessaoFalsa()
    monkeypatch.setattr(orquestrador, "db", BancoFalso(sessao))
    with _ensaio_em_uma_transacao(Contexto(apply=True, relatorio=Path("r.json"))):
        sessao.commit()
    assert (sessao.commits, sessao.rollbacks) == (1, 0)
