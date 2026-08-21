"""Testes do colapso de vínculos ``user_orgao`` (poda de genéricas + absorção).

A parte pura (``calcular_colapso``) roda contra uma árvore fake nomeada; a parte
de banco cobre dry-run, delta de role_map e idempotência. A hierarquia usada é a
real do SIORG-RJ (SETD -> GABSEC -> ...), inclusive no caso das 14 áreas.
"""

import json
from dataclasses import asdict

import pytest
from sqlalchemy import inspect, text

from models import OrgaoClosure, OrgaoUnidade, Project, User, UserOrgao, db
from scripts.migrations.backfill_orgaos import (
    TABELA_PRE_COLAPSO,
    ColapsoJaAplicado,
    run_backfill_orgaos,
)
from services.authorization import PAPEL_RANK, get_user_orgao_role_map
from services.orgao_tree import rebuild_orgao_closure
from services.user_orgao_collapse import (
    SIGLAS_GENERICAS,
    ClosureNaoConstruidaError,
    aplicar_colapso,
    calcular_colapso,
    projetos_orfaos_por_poda,
    rank_do_papel,
    snapshot_role_maps,
)

GESTOR = PAPEL_RANK["gestor"]
LEITOR = PAPEL_RANK["leitor"]

# Recorte real do SIORG-RJ: SETD(2) -> GABSEC(3) -> unidades; SUBEXE(11) e
# CHEGAB(4) têm subárvore própria.
ESTRUTURA_SETD = {
    "SETD": None,
    "GABSEC": "SETD",
    "CHEGAB": "GABSEC",
    "ASSESP": "CHEGAB",
    "ASSJUR": "GABSEC",
    "ASSCOM": "GABSEC",
    "AUD": "GABSEC",
    "CORREG": "GABSEC",
    "OUVI": "GABSEC",
    "SUBEXE": "GABSEC",
    "ASPLO": "SUBEXE",
    "ASSEXE": "SUBEXE",
    "DGAF": "SUBEXE",
    "COOCOF": "DGAF",
    "COOADM": "DGAF",
}

# As 14 áreas planas que um usuário da SETD carregava no banco legado.
QUATORZE_AREAS_LEGADAS = (
    "SETD",
    "CHEGAB",
    "ASSESP",
    "ASSJUR",
    "ASSCOM",
    "AUD",
    "CORREG",
    "OUVI",
    "SUBEXE",
    "ASPLO",
    "ASSEXE",
    "DGAF",
    "COOCOF",
    "COOADM",
)


class ArvoreOrgaoFake:
    """Árvore de órgãos em memória: dá ids, ancestrais e ranks sem tocar no banco."""

    def __init__(self, pais: dict[str, str | None]) -> None:
        self._pais = dict(pais)
        self._ids = {sigla: indice for indice, sigla in enumerate(self._pais, start=1)}

    def id(self, sigla: str) -> int:
        return self._ids[sigla]

    def sigla(self, orgao_id: int) -> str:
        return next(s for s, i in self._ids.items() if i == orgao_id)

    def siglas(self, orgao_ids) -> list[str]:
        return [self.sigla(orgao_id) for orgao_id in orgao_ids]

    def ancestrais(self) -> dict[int, set[int]]:
        cadeias = {sigla: self._cadeia(sigla) for sigla in self._pais}
        return {
            self.id(sigla): {self.id(a) for a in cadeia}
            for sigla, cadeia in cadeias.items()
            if cadeia
        }

    def genericos(self) -> set[int]:
        return {s_id for s, s_id in self._ids.items() if s in SIGLAS_GENERICAS}

    def ranks(self, vinculos: dict[str, str | None]) -> dict[int, int]:
        return {self.id(s): rank_do_papel(papel) for s, papel in vinculos.items()}

    def _cadeia(self, sigla: str) -> list[str]:
        cadeia: list[str] = []
        pai = self._pais[sigla]
        while pai is not None:
            cadeia.append(pai)
            pai = self._pais[pai]
        return cadeia


def _colapsar(arvore: ArvoreOrgaoFake, vinculos: dict[str, str | None]):
    return calcular_colapso(
        arvore.ranks(vinculos), arvore.ancestrais(), arvore.genericos()
    )


@pytest.fixture
def arvore() -> ArvoreOrgaoFake:
    return ArvoreOrgaoFake(ESTRUTURA_SETD)


def test_gestor_no_ancestral_derruba_gestor_no_descendente(arvore):
    resultado = _colapsar(arvore, {"SUBEXE": "gestor", "DGAF": "gestor"})

    assert arvore.siglas(resultado.mantidos) == ["SUBEXE"]
    assert arvore.siglas(resultado.removidos) == ["DGAF"]
    (absorcao,) = resultado.absorvidos
    assert (absorcao.ancestral_id, absorcao.descendente_id) == (
        arvore.id("SUBEXE"),
        arvore.id("DGAF"),
    )
    assert (absorcao.rank_ancestral, absorcao.rank_descendente) == (GESTOR, GESTOR)


def test_leitor_no_ancestral_nao_derruba_gestor_no_descendente(arvore):
    resultado = _colapsar(arvore, {"SUBEXE": "leitor", "DGAF": "gestor"})

    assert arvore.siglas(resultado.mantidos) == ["SUBEXE", "DGAF"]
    assert resultado.absorvidos == ()
    assert resultado.removidos == ()


def test_gestor_no_ancestral_derruba_leitor_no_descendente(arvore):
    resultado = _colapsar(arvore, {"SUBEXE": "gestor", "DGAF": "leitor"})

    assert arvore.siglas(resultado.mantidos) == ["SUBEXE"]
    (absorcao,) = resultado.absorvidos
    assert (absorcao.rank_ancestral, absorcao.rank_descendente) == (GESTOR, LEITOR)


def test_ramos_irmaos_disjuntos_nao_caem(arvore):
    resultado = _colapsar(arvore, {"SUBEXE": "gestor", "CHEGAB": "editor"})

    assert sorted(arvore.siglas(resultado.mantidos)) == ["CHEGAB", "SUBEXE"]
    assert resultado.removidos == ()


def test_papel_nulo_conta_como_gestor(arvore):
    assert rank_do_papel(None) == GESTOR
    assert rank_do_papel("") == GESTOR

    resultado = _colapsar(arvore, {"SUBEXE": None, "DGAF": None})

    assert arvore.siglas(resultado.mantidos) == ["SUBEXE"]
    (absorcao,) = resultado.absorvidos
    assert absorcao.rank_ancestral == GESTOR


def test_papel_nulo_no_descendente_nao_e_absorvido_por_editor(arvore):
    resultado = _colapsar(arvore, {"SUBEXE": "editor", "DGAF": None})

    assert arvore.siglas(resultado.mantidos) == ["SUBEXE", "DGAF"]


def test_cadeia_de_tres_niveis_colapsa_direto_no_topo(arvore):
    resultado = _colapsar(
        arvore, {"SUBEXE": "gestor", "DGAF": "gestor", "COOCOF": "gestor"}
    )

    assert arvore.siglas(resultado.mantidos) == ["SUBEXE"]
    assert sorted(arvore.siglas(resultado.removidos)) == ["COOCOF", "DGAF"]
    # O par que justifica cada remoção é o ancestral de maior rank, não o pai.
    justificativas = {a.descendente_id: a.ancestral_id for a in resultado.absorvidos}
    assert justificativas[arvore.id("COOCOF")] == arvore.id("SUBEXE")


def test_poda_de_generica_acontece_antes_da_absorcao(arvore):
    resultado = _colapsar(
        arvore, {"SETD": "gestor", "CHEGAB": "gestor", "ASSJUR": "gestor"}
    )

    assert arvore.siglas(resultado.podados) == ["SETD"]
    # Absorção primeiro deixaria só SETD e a poda esvaziaria o usuário.
    assert sorted(arvore.siglas(resultado.mantidos)) == ["ASSJUR", "CHEGAB"]


def test_generica_sozinha_nao_e_podada(arvore):
    """Podar zeraria o role_map e o usuário logaria sem enxergar nada (A1)."""
    resultado = _colapsar(arvore, {"SETD": "gestor"})

    assert resultado.podados == ()
    assert arvore.siglas(resultado.mantidos) == ["SETD"]
    assert resultado.preservado_por_esvaziamento is True


def test_genericas_preservadas_ainda_absorvem_entre_si():
    arvore = ArvoreOrgaoFake({"GOVRJ": None, "SETD": "GOVRJ", "CHEGAB": "SETD"})

    resultado = _colapsar(arvore, {"GOVRJ": "gestor", "SETD": "gestor"})

    assert resultado.preservado_por_esvaziamento is True
    assert arvore.siglas(resultado.mantidos) == ["GOVRJ"]
    assert arvore.siglas(resultado.removidos) == ["SETD"]


def test_generica_com_vinculo_proprio_continua_podada(arvore):
    resultado = _colapsar(arvore, {"SETD": "gestor", "AUD": "gestor"})

    assert arvore.siglas(resultado.podados) == ["SETD"]
    assert resultado.preservado_por_esvaziamento is False


def test_quatorze_areas_da_setd_viram_os_sete_nos_mais_altos(arvore):
    vinculos = {sigla: "gestor" for sigla in QUATORZE_AREAS_LEGADAS}

    resultado = _colapsar(arvore, vinculos)

    assert len(vinculos) == 14
    assert sorted(arvore.siglas(resultado.mantidos)) == [
        "ASSCOM",
        "ASSJUR",
        "AUD",
        "CHEGAB",
        "CORREG",
        "OUVI",
        "SUBEXE",
    ]
    assert arvore.siglas(resultado.podados) == ["SETD"]
    assert len(resultado.absorvidos) == 6


def test_calcular_colapso_e_idempotente(arvore):
    vinculos = {sigla: "gestor" for sigla in QUATORZE_AREAS_LEGADAS}

    primeiro = _colapsar(arvore, vinculos)
    segundo = calcular_colapso(
        {orgao_id: GESTOR for orgao_id in primeiro.mantidos},
        arvore.ancestrais(),
        arvore.genericos(),
    )

    assert segundo.mantidos == primeiro.mantidos
    assert segundo.removidos == ()


def _criar_orgaos(estrutura: dict[str, str | None]) -> dict[str, int]:
    ids: dict[str, int] = {}
    for ordem, (sigla, pai) in enumerate(estrutura.items()):
        unidade = OrgaoUnidade(
            sigla=sigla,
            nome=f"Unidade {sigla}",
            tipo="Secretaria",
            ordem=ordem,
            pai_id=ids.get(pai) if pai else None,
        )
        db.session.add(unidade)
        db.session.flush()
        ids[sigla] = unidade.id
    rebuild_orgao_closure()
    db.session.flush()
    return ids


def _criar_usuario(username: str, orgao_ids, papel: str = "gestor") -> User:
    user = User(username=username, name=username.title(), is_admin=False)
    user.set_password("senha123")
    db.session.add(user)
    db.session.flush()
    for orgao_id in orgao_ids:
        db.session.add(UserOrgao(user_id=user.id, orgao_id=orgao_id, papel=papel))
    db.session.flush()
    return user


def _cenario_setd(siglas=QUATORZE_AREAS_LEGADAS) -> tuple[dict[str, int], int]:
    ids = _criar_orgaos(ESTRUTURA_SETD)
    user = _criar_usuario("servidor.setd", [ids[sigla] for sigla in siglas])
    db.session.commit()
    return ids, user.id


def test_aplicar_colapso_dry_run_nao_grava(app):
    with app.app_context():
        _, user_id = _cenario_setd()

        relatorio = aplicar_colapso(dry_run=True)

        assert relatorio.dry_run is True
        assert relatorio.vinculos_antes == 14
        assert relatorio.vinculos_removidos == 7
        assert relatorio.vinculos_depois == 7
        assert UserOrgao.query.filter_by(user_id=user_id).count() == 14


def test_aplicar_colapso_grava_e_enumera_o_que_o_usuario_perde(app):
    with app.app_context():
        ids, user_id = _cenario_setd()

        relatorio = aplicar_colapso(dry_run=False)

        restantes = {
            linha.orgao_id for linha in UserOrgao.query.filter_by(user_id=user_id).all()
        }
        assert restantes == {
            ids[s]
            for s in ("CHEGAB", "ASSJUR", "ASSCOM", "AUD", "CORREG", "OUVI", "SUBEXE")
        }
        (linha,) = relatorio.usuarios_com_perda_de_acesso
        assert linha.user_id == user_id
        # A poda da SETD tira exatamente SETD e o intermediário GABSEC; tudo
        # abaixo continua coberto pelos 7 nós mantidos.
        assert set(linha.role_map_perdido) == {ids["SETD"], ids["GABSEC"]}
        assert linha.role_map_rebaixado == {}
        assert linha.podados == (ids["SETD"],)


def test_aplicar_colapso_preserva_role_map_quando_nao_ha_generica(app):
    with app.app_context():
        ids = _criar_orgaos(
            {k: v for k, v in ESTRUTURA_SETD.items() if k not in ("SETD", "GABSEC")}
        )
        user = _criar_usuario(
            "servidor.subexe",
            [ids["SUBEXE"], ids["DGAF"], ids["COOCOF"], ids["COOADM"]],
        )
        db.session.commit()
        antes = get_user_orgao_role_map(user)

        relatorio = aplicar_colapso(dry_run=False)

        depois = get_user_orgao_role_map(db.session.get(User, user.id))
        assert depois == antes
        assert relatorio.role_map_depois[user.id] == relatorio.role_map_antes[user.id]
        assert UserOrgao.query.filter_by(user_id=user.id).count() == 1


def test_aplicar_colapso_e_idempotente_no_banco(app):
    with app.app_context():
        _, user_id = _cenario_setd()

        primeiro = aplicar_colapso(dry_run=False)
        segundo = aplicar_colapso(dry_run=False)

        assert primeiro.vinculos_removidos == 7
        assert segundo.vinculos_removidos == 0
        assert segundo.vinculos_antes == 7
        assert UserOrgao.query.filter_by(user_id=user_id).count() == 7


def test_colapso_nao_mistura_usuarios(app):
    with app.app_context():
        ids = _criar_orgaos(ESTRUTURA_SETD)
        um = _criar_usuario("um", [ids["SUBEXE"], ids["DGAF"]])
        outro = _criar_usuario("outro", [ids["DGAF"]])
        db.session.commit()

        aplicar_colapso(dry_run=False)

        assert [l.orgao_id for l in UserOrgao.query.filter_by(user_id=um.id)] == [
            ids["SUBEXE"]
        ]
        assert [l.orgao_id for l in UserOrgao.query.filter_by(user_id=outro.id)] == [
            ids["DGAF"]
        ]


def test_snapshot_role_maps_serializa_em_json(app):
    with app.app_context():
        ids, user_id = _cenario_setd()

        snapshot = snapshot_role_maps()

        assert set(snapshot[user_id]) >= {ids["SETD"], ids["COOCOF"]}
        assert snapshot[user_id][ids["COOCOF"]] == GESTOR
        assert json.loads(json.dumps(snapshot))[str(user_id)]


def _criar_projeto(titulo: str, orgao_id: int) -> int:
    projeto = Project(
        titulo=titulo,
        orgao_id=orgao_id,
        orgao="Orgao Colapso",
        prioridade="media",
        status="Vigente",
    )
    db.session.add(projeto)
    db.session.flush()
    return projeto.id


def test_aplicar_colapso_nao_zera_usuario_so_com_generica(app):
    """Os dois usuários reais (proderj, ramon) só tinham PRODERJ — A1."""
    with app.app_context():
        ids = _criar_orgaos(ESTRUTURA_SETD)
        so_generica = _criar_usuario("proderj", [ids["SETD"]])
        _criar_usuario("servidor.setd", [ids[s] for s in QUATORZE_AREAS_LEGADAS])
        db.session.commit()
        antes = get_user_orgao_role_map(so_generica)

        relatorio = aplicar_colapso(dry_run=False)

        restante = UserOrgao.query.filter_by(user_id=so_generica.id).all()
        assert [linha.orgao_id for linha in restante] == [ids["SETD"]]
        assert get_user_orgao_role_map(db.session.get(User, so_generica.id)) == antes
        assert [linha.username for linha in relatorio.preservados_por_esvaziamento] == [
            "proderj"
        ]


def test_preservado_por_esvaziamento_nao_conta_como_perda_de_acesso(app):
    with app.app_context():
        ids = _criar_orgaos(ESTRUTURA_SETD)
        _criar_usuario("proderj", [ids["SETD"]])
        db.session.commit()

        relatorio = aplicar_colapso(dry_run=False)

        assert relatorio.vinculos_removidos == 0
        assert relatorio.usuarios_com_perda_de_acesso == ()


def test_projetos_orfaos_por_poda_lista_quem_perdeu_todo_dono(app):
    """5 projetos com area_responsavel='SETD' caem neste caso em produção — A6."""
    with app.app_context():
        ids = _criar_orgaos(ESTRUTURA_SETD)
        _criar_usuario("servidor", [ids["SETD"], ids["AUD"]])
        orfao_id = _criar_projeto("Projeto da SETD", ids["SETD"])
        _criar_projeto("Projeto da AUD", ids["AUD"])
        db.session.commit()
        assert projetos_orfaos_por_poda() == []

        relatorio = aplicar_colapso(dry_run=False)

        assert relatorio.projetos_orfaos == ((orfao_id, "Projeto da SETD", "SETD"),)
        assert projetos_orfaos_por_poda() == [(orfao_id, "Projeto da SETD", "SETD")]


def test_projeto_alcancado_so_por_admin_conta_como_orfao(app):
    with app.app_context():
        ids = _criar_orgaos(ESTRUTURA_SETD)
        admin = _criar_usuario("chefia", [ids["AUD"]])
        admin.is_admin = True
        _criar_usuario("servidor", [ids["CHEGAB"]])
        projeto_id = _criar_projeto("Projeto da AUD", ids["AUD"])
        db.session.commit()

        relatorio = aplicar_colapso(dry_run=False)

        assert relatorio.projetos_orfaos == ((projeto_id, "Projeto da AUD", "AUD"),)


def test_aplicar_colapso_aborta_com_closure_vazia(app):
    """Sem closure a absorção não roda, mas a poda rodaria e é irreversível — M2."""
    with app.app_context():
        ids = _criar_orgaos(ESTRUTURA_SETD)
        user = _criar_usuario("servidor.setd", [ids[s] for s in QUATORZE_AREAS_LEGADAS])
        OrgaoClosure.query.filter(OrgaoClosure.depth > 0).delete()
        db.session.commit()

        with pytest.raises(ClosureNaoConstruidaError) as erro:
            aplicar_colapso(dry_run=False)

        assert "rebuild_orgao_closure" in str(erro.value)
        assert UserOrgao.query.filter_by(user_id=user.id).count() == 14


def test_arvore_sem_pai_id_dispensa_closure_profunda(app):
    with app.app_context():
        ids = _criar_orgaos({"AUD": None, "OUVI": None})
        user = _criar_usuario("servidor", [ids["AUD"], ids["OUVI"]])
        db.session.commit()

        relatorio = aplicar_colapso(dry_run=False)

        assert relatorio.vinculos_removidos == 0
        assert UserOrgao.query.filter_by(user_id=user.id).count() == 2


def _backup_existe() -> bool:
    return inspect(db.engine).has_table(TABELA_PRE_COLAPSO)


def _linhas_do_backup() -> set[tuple[int, int]]:
    linhas = db.session.execute(
        text(f"SELECT user_id, orgao_id FROM {TABELA_PRE_COLAPSO}")
    ).all()
    return {(user_id, orgao_id) for user_id, orgao_id in linhas}


def _restaurar_do_backup() -> None:
    db.session.execute(text("DELETE FROM user_orgao"))
    db.session.execute(
        text(
            "INSERT INTO user_orgao (user_id, orgao_id, papel) "
            f"SELECT user_id, orgao_id, papel FROM {TABELA_PRE_COLAPSO}"
        )
    )
    db.session.commit()


def test_colapso_grava_backup_dos_vinculos_antes_de_podar(app):
    """Sem esse espelho a poda não tem volta — E1 do ensaio MySQL."""
    with app.app_context():
        ids, user_id = _cenario_setd()
        originais = {(user_id, ids[sigla]) for sigla in QUATORZE_AREAS_LEGADAS}

        relatorio = aplicar_colapso(dry_run=False)

        assert _linhas_do_backup() == originais
        assert relatorio.backup_pre_colapso.tabela == TABELA_PRE_COLAPSO
        assert relatorio.backup_pre_colapso.linhas == 14
        assert relatorio.backup_pre_colapso.reaproveitado is False


def test_restaurar_do_backup_devolve_os_vinculos_podados(app):
    with app.app_context():
        _, user_id = _cenario_setd()
        aplicar_colapso(dry_run=False)
        assert UserOrgao.query.filter_by(user_id=user_id).count() == 7

        _restaurar_do_backup()

        assert UserOrgao.query.filter_by(user_id=user_id).count() == 14


def test_dry_run_nao_cria_o_backup(app):
    with app.app_context():
        _cenario_setd()

        relatorio = aplicar_colapso(dry_run=True)

        assert relatorio.backup_pre_colapso is None
        assert _backup_existe() is False


def test_segundo_colapso_nao_sobrescreve_o_backup_original(app):
    """O `--all --apply` repetido não pode degradar o backup para o estado pós-poda."""
    with app.app_context():
        _cenario_setd()

        aplicar_colapso(dry_run=False)
        segundo = aplicar_colapso(dry_run=False)

        assert len(_linhas_do_backup()) == 14
        assert segundo.backup_pre_colapso.linhas == 14
        assert segundo.backup_pre_colapso.reaproveitado is True


def test_backfill_aborta_apontando_para_uma_tabela_que_existe(app):
    """A mensagem do ColapsoJaAplicado manda restaurar do espelho — ele precisa existir."""
    with app.app_context():
        _cenario_setd()
        aplicar_colapso(dry_run=False)

        with pytest.raises(ColapsoJaAplicado) as erro:
            run_backfill_orgaos(dry_run=True)

        assert TABELA_PRE_COLAPSO in str(erro.value)
        assert _backup_existe() is True


def test_asdict_do_relatorio_traz_preservados_e_orfaos(app):
    """`asdict` ignora @property; o runbook (9.6) promete essas chaves no JSON — E5."""
    with app.app_context():
        ids = _criar_orgaos({**ESTRUTURA_SETD, "PRODERJ": None})
        _criar_usuario("proderj", [ids["PRODERJ"]])
        _criar_usuario("servidor", [ids["SETD"], ids["AUD"]])
        orfao_id = _criar_projeto("Projeto da SETD", ids["SETD"])
        db.session.commit()

        dados = asdict(aplicar_colapso(dry_run=False))

        assert [item["username"] for item in dados["preservados_por_esvaziamento"]] == [
            "proderj"
        ]
        assert dados["projetos_orfaos"] == ((orfao_id, "Projeto da SETD", "SETD"),)
        assert dados["vinculos_depois"] == dados["vinculos_antes"] - 1
        assert dados["backup_pre_colapso"]["linhas"] == 3
        assert json.loads(json.dumps(dados))["resumo"]


def test_resumo_mostra_preservados_orfaos_e_backup_em_texto(app):
    with app.app_context():
        ids = _criar_orgaos({**ESTRUTURA_SETD, "PRODERJ": None})
        _criar_usuario("proderj", [ids["PRODERJ"]])
        _criar_usuario("servidor", [ids["SETD"], ids["AUD"]])
        orfao_id = _criar_projeto("Projeto da SETD", ids["SETD"])
        db.session.commit()

        resumo = "\n".join(aplicar_colapso(dry_run=False).resumo)

        assert "preservados por esvaziamento: 1 (proderj)" in resumo
        assert f"projetos orfaos: 1 (#{orfao_id} Projeto da SETD [SETD])" in resumo
        assert (
            f"backup pre-colapso: {TABELA_PRE_COLAPSO} com 3 linhas (gravado)" in resumo
        )


def test_resumo_de_dry_run_diz_que_nao_gravou_backup(app):
    with app.app_context():
        _cenario_setd()

        resumo = aplicar_colapso(dry_run=True).resumo

        assert "vinculos: 14 -> 7 (7 removidos)" in resumo
        assert "backup pre-colapso: nao gravado (dry-run)" in resumo
