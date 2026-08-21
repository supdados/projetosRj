"""Importação do organograma real do SIORG-RJ (scripts/catalog/organograma_siorg.py)."""

import pytest

from models import OrgaoClosure, OrgaoTipo, OrgaoUnidade, db
from scripts.catalog.organograma_siorg import (
    ALIAS_SIGLA_LEGADA,
    CSV_PADRAO,
    VINCULOS_DUPLOS,
    importar_estrutura,
    ler_estrutura,
    resolver_orgao_id_por_codigo,
)

SIGLAS_AREA_CATALOG_LEGADO = frozenset(
    {
        "Auditoria",
        "CHEGAB",
        "SUPDADOS",
        "SUBDGD",
        "SUPEST",
        "SUPIM",
        "SUPPAE",
        "PRODERJ",
        "ASSESP",
        "ECENTRAL",
        "SUBEDD",
        "VPD",
        "VPE",
        "VPT",
        "EPERJ",
        "SETD",
        "DIRPE",
        "DIRGN",
        "GERGD",
        "SUBEXE",
        "Ouvidoria",
        "ASSTEC",
        "EGPE",
        "DIRIT",
        "DIRSS",
        "DIRSI",
        "RH-PRODERJ",
        "DIRPL",
        "GAR",
        "GFS",
        "GAR/GFS",
        "GERS",
        "GERRC",
        "GDB",
        "GSS/GFS",
        "GSS",
        "GERII",
        "VPG",
    }
)


@pytest.fixture
def organograma(app):
    """Organograma do SIORG importado uma vez, dentro de um app context."""
    with app.app_context():
        importar_estrutura(dry_run=False)
        yield


def _por_sigla_e_codigo() -> dict[tuple[str, str], OrgaoUnidade]:
    return {
        (linha.sigla, linha.codigo_externo): linha for linha in OrgaoUnidade.query.all()
    }


def _cadeia_de_siglas(unidade: OrgaoUnidade) -> list[str]:
    cadeia = []
    atual = unidade
    while atual is not None:
        cadeia.append(atual.sigla)
        atual = db.session.get(OrgaoUnidade, atual.pai_id) if atual.pai_id else None
    return cadeia


def test_csv_do_repo_cobre_a_estrutura_e_o_complemento_legado():
    unidades = ler_estrutura(CSV_PADRAO)
    assert len(unidades) == 100
    assert {u.codigo for u in unidades if u.sigla == "ECENTRAL"} == {99}
    assert {u.codigo for u in unidades if u.sigla == "VPG"} == {100}
    assert {u.tipo for u in unidades} == {"ENTE", "ORGAO", "ENTIDADE", "UA", "UC"}


def test_alias_e_vinculos_duplos_cobrem_as_38_siglas_do_area_catalog():
    cobertas = set(ALIAS_SIGLA_LEGADA) | set(VINCULOS_DUPLOS)
    assert cobertas == SIGLAS_AREA_CATALOG_LEGADO
    assert len(ALIAS_SIGLA_LEGADA) == 36
    assert len(VINCULOS_DUPLOS) == 2


def test_todas_as_siglas_legadas_resolvem_para_um_no_existente(app, organograma):
    with app.app_context():
        por_codigo = resolver_orgao_id_por_codigo()
        codigos = set(ALIAS_SIGLA_LEGADA.values())
        for par in VINCULOS_DUPLOS.values():
            codigos.update(par)
        ausentes = sorted(codigo for codigo in codigos if codigo not in por_codigo)
        assert ausentes == []


def test_import_repetido_nao_duplica_unidades(app, organograma):
    with app.app_context():
        segundo = importar_estrutura(dry_run=False)
        assert segundo.criadas == []
        assert segundo.atualizadas == []
        assert segundo.inalteradas == 100
        assert segundo.pais_religados == 0
        assert segundo.tipos_criados == []
        assert OrgaoUnidade.query.count() == 100
        assert OrgaoTipo.query.filter(OrgaoTipo.nome == "UA").count() == 1


def test_dry_run_nao_grava_nada(app):
    with app.app_context():
        relatorio = importar_estrutura(dry_run=True)
        assert len(relatorio.criadas) == 100
        assert OrgaoUnidade.query.count() == 0
        assert OrgaoClosure.query.count() == 0


def test_as_duas_chegab_coexistem_e_a_legada_e_a_da_setd(app, organograma):
    with app.app_context():
        chegabs = OrgaoUnidade.query.filter_by(sigla="CHEGAB").all()
        assert {linha.codigo_externo for linha in chegabs} == {"4", "36"}

        legada = db.session.get(
            OrgaoUnidade, resolver_orgao_id_por_codigo()[ALIAS_SIGLA_LEGADA["CHEGAB"]]
        )
        assert legada.codigo_externo == "4"
        assert "SETD" in _cadeia_de_siglas(legada)
        assert "PRODERJ" not in _cadeia_de_siglas(legada)


def test_siglas_repetidas_nao_colidem_no_upsert(app, organograma):
    with app.app_context():
        for sigla in ("CHEGAB", "ASSJUR", "ASSCOM", "CORREG", "OUVI"):
            assert OrgaoUnidade.query.filter_by(sigla=sigla).count() == 2
        assert len(_por_sigla_e_codigo()) == 100


def test_tipos_do_siorg_replicam_o_perfil_do_organograma_de_dev(app, organograma):
    with app.app_context():
        perfis = {
            tipo.nome: (tipo.nivel, tipo.permite_raiz, tipo.slug)
            for tipo in OrgaoTipo.query.all()
        }
        assert perfis["ENTE"] == (0, True, "ente")
        assert perfis["ORGAO"] == (0, True, "orgao")
        assert perfis["ENTIDADE"] == (99, False, "entidade")
        assert perfis["UA"] == (99, False, "ua")
        assert perfis["UC"] == (99, False, "uc")


def test_tipo_id_aponta_para_o_tipo_com_o_mesmo_nome(app, organograma):
    with app.app_context():
        tipos = {tipo.id: tipo.nome for tipo in OrgaoTipo.query.all()}
        divergentes = [
            linha.sigla
            for linha in OrgaoUnidade.query.all()
            if tipos.get(linha.tipo_id) != linha.tipo
        ]
        assert divergentes == []


def test_closure_bate_com_pai_id_depois_do_import(app, organograma):
    with app.app_context():
        pais = {linha.id: linha.pai_id for linha in OrgaoUnidade.query.all()}
        esperado = set()
        for node_id in pais:
            esperado.add((node_id, node_id, 0))
            atual, depth = pais[node_id], 1
            while atual is not None:
                esperado.add((atual, node_id, depth))
                atual, depth = pais[atual], depth + 1
        gravado = {
            (linha.ancestor_id, linha.descendant_id, linha.depth)
            for linha in OrgaoClosure.query.all()
        }
        assert gravado == esperado


def test_arvore_comeca_na_raiz_govrj_e_indenta_os_filhos(app, organograma):
    with app.app_context():
        relatorio = importar_estrutura(dry_run=True)
    assert relatorio.arvore[0].startswith("GOVRJ — Governo do Estado do Rio de Janeiro")
    assert relatorio.arvore[1].startswith("  SETD — ")
    assert len(relatorio.arvore) == 100
