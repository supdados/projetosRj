"""Testes de services/project_collections.py (coleções de projetos, Fases 1 e 2).

Cobre o que a rota NÃO pode reimplementar: get-or-create de Favoritos, validação
de identidade/limites, criação atômica com visibilidade, itens idempotentes com
bump de ``updated_at``, os rollups filtrados pelo escopo do viewer e — na Fase 2
— compartilhamento (papéis, órgão EXATO, auditoria), o acesso derivado a
projetos e o cronograma (Gantt) da coleção.

O service não commita: os testes rodam dentro de ``app.test_request_context``
(``project_visibility_criterion`` usa cache de request) e usam ``flush``/commit
explícitos.
"""

import datetime

import pytest

from models import (
    ALVO_COLECAO,
    AutorizacaoAudit,
    Etapa,
    OrgaoUnidade,
    PAPEL_SHARE_EDITOR,
    PAPEL_SHARE_VIEWER,
    Project,
    ProjectCollection,
    ProjectCollectionItem,
    ProjectCollectionShare,
    Task,
    TIPO_COLECAO_CUSTOM,
    TIPO_COLECAO_FAVORITOS,
    User,
    UserOrgao,
    db,
)
from services.authorization import (
    PAPEL_EDITOR,
    PAPEL_LEITOR,
    PAPEL_RANK,
    effective_project_rank,
)
from services.orgao_tree import rebuild_orgao_closure
from services.project_collections import (
    BARRA_CONCLUIDA,
    BARRA_EXECUCAO,
    BARRA_PREVISTA,
    BARRA_VENCIDA,
    FAVORITOS_NOME,
    MAX_COLECOES_CUSTOM,
    PAPEL_COLECAO_DONO,
    ColecaoInvalida,
    ColecaoSemPermissao,
    ProjetoForaDoEscopo,
    adicionar_projeto,
    apagar_colecao,
    colecao_cronograma_rows,
    colecao_do_usuario,
    colecao_project_rows,
    collection_rollups,
    compartilhar_colecao,
    criar_colecao,
    editar_colecao,
    get_or_create_favoritos,
    listar_colecoes,
    listar_shares,
    papel_do_usuario,
    projeto_visivel_para,
    remover_projeto,
    revogar_share,
    toggle_favorito,
)
from time_utils import utc_now

# ── Helpers de fixture ────────────────────────────────────────────────────────


def _add_orgao(sigla: str, *, pai_id: int | None = None, ativo: bool = True) -> int:
    orgao = OrgaoUnidade(
        sigla=sigla, nome=sigla, tipo="Secretaria", pai_id=pai_id, ordem=0, ativo=ativo
    )
    db.session.add(orgao)
    db.session.flush()
    return orgao.id


def _add_user(
    username: str,
    *,
    orgao_id: int | None = None,
    admin: bool = False,
    papel: str = "gestor",
):
    user = User(
        username=username, name=username.upper(), password_hash="x", is_admin=admin
    )
    db.session.add(user)
    db.session.flush()
    if orgao_id is not None:
        db.session.add(UserOrgao(user_id=user.id, orgao_id=orgao_id, papel=papel))
        db.session.flush()
    return user


def _add_project(titulo: str, orgao_id: int) -> Project:
    projeto = Project(titulo=titulo, orgao_id=orgao_id, status="Vigente")
    db.session.add(projeto)
    db.session.flush()
    return projeto


def _add_etapa(
    project_id: int,
    *,
    done: bool,
    ordem: int = 0,
    entry_type: str = "manual",
    data_inicio: datetime.date = datetime.date(2026, 1, 5),
    data_fim: datetime.date = datetime.date(2026, 1, 9),
) -> Etapa:
    etapa = Etapa(
        descricao=f"Etapa {ordem}",
        data_inicio=data_inicio,
        data_fim=data_fim,
        project_id=project_id,
        iniciada=done,
        done=done,
        ordem=ordem,
        entry_type=entry_type,
    )
    db.session.add(etapa)
    db.session.flush()
    return etapa


def _add_task(
    project_id: int,
    created_by_id: int,
    *,
    status: str = "nao_iniciada",
    ordem: int = 1,
    etapa_id: int | None = None,
    legacy_parent_task_id: int | None = None,
) -> Task:
    task = Task(
        descricao=f"Tarefa {ordem}",
        status=status,
        ordem=ordem,
        project_id=project_id,
        created_by_id=created_by_id,
        is_archived=False,
        etapa_id=etapa_id,
        legacy_parent_task_id=legacy_parent_task_id,
    )
    db.session.add(task)
    db.session.flush()
    return task


def _add_colecao(owner_id: int, nome: str) -> ProjectCollection:
    colecao = ProjectCollection(owner_user_id=owner_id, nome=nome)
    db.session.add(colecao)
    db.session.flush()
    return colecao


def _add_item(collection_id: int, project_id: int, ordem: int = 0) -> None:
    db.session.add(
        ProjectCollectionItem(
            collection_id=collection_id, project_id=project_id, ordem=ordem
        )
    )
    db.session.flush()


@pytest.fixture
def cenario(app):
    """Dono vinculado à AREA_A; projeto de AREA_B fica invisível para ele."""
    with app.app_context():
        area_a = _add_orgao("AREAA")
        area_b = _add_orgao("AREAB")
        rebuild_orgao_closure()
        dono = _add_user("dono", orgao_id=area_a)
        admin = _add_user("admin_colecoes", admin=True)
        visivel = _add_project("Projeto Visivel", area_a)
        outro_visivel = _add_project("Outro Visivel", area_a)
        invisivel = _add_project("Projeto Invisivel", area_b)
        db.session.commit()
        yield {
            "dono_id": dono.id,
            "admin_id": admin.id,
            "visivel_id": visivel.id,
            "outro_visivel_id": outro_visivel.id,
            "invisivel_id": invisivel.id,
        }


@pytest.fixture
def dono(cenario):
    return db.session.get(User, cenario["dono_id"])


@pytest.fixture
def admin(cenario):
    return db.session.get(User, cenario["admin_id"])


# ── get_or_create_favoritos ───────────────────────────────────────────────────


def test_favoritos_nasce_com_identidade_de_sistema(app, cenario):
    with app.test_request_context("/"):
        favoritos = get_or_create_favoritos(cenario["dono_id"])
        assert favoritos.tipo == TIPO_COLECAO_FAVORITOS
        assert favoritos.nome == FAVORITOS_NOME
        assert (favoritos.icone, favoritos.cor) == ("estrela", "warning")


def test_favoritos_e_idempotente(app, cenario):
    with app.test_request_context("/"):
        primeira = get_or_create_favoritos(cenario["dono_id"])
        db.session.commit()
        segunda = get_or_create_favoritos(cenario["dono_id"])
        assert segunda.id == primeira.id
        assert (
            ProjectCollection.query.filter_by(
                owner_user_id=cenario["dono_id"], tipo=TIPO_COLECAO_FAVORITOS
            ).count()
            == 1
        )


def test_listar_colecoes_devolve_favoritos_primeiro(app, cenario, dono):
    with app.test_request_context("/"):
        criar_colecao(dono, "Saude digital", None, "pessoas", "success", None)
        db.session.commit()
        pares = listar_colecoes(dono.id)
        assert [(colecao.tipo, papel) for colecao, papel in pares] == [
            (TIPO_COLECAO_FAVORITOS, PAPEL_COLECAO_DONO),
            (TIPO_COLECAO_CUSTOM, PAPEL_COLECAO_DONO),
        ]


# ── criar_colecao ─────────────────────────────────────────────────────────────


def test_criar_colecao_normaliza_nome_e_descricao(app, cenario, dono):
    with app.test_request_context("/"):
        colecao = criar_colecao(dono, "  Obras  ", "   ", "camadas", "primary", None)
        db.session.commit()
        assert colecao.nome == "Obras"
        assert colecao.descricao is None
        assert colecao.tipo == TIPO_COLECAO_CUSTOM


@pytest.mark.parametrize("nome", ["", "   ", None, 42])
def test_criar_colecao_recusa_nome_vazio(app, cenario, dono, nome):
    with app.test_request_context("/"):
        with pytest.raises(ColecaoInvalida):
            criar_colecao(dono, nome, None, "camadas", "primary", None)


def test_criar_colecao_recusa_nome_duplicado(app, cenario, dono):
    with app.test_request_context("/"):
        criar_colecao(dono, "Obras", None, "camadas", "primary", None)
        db.session.commit()
        with pytest.raises(ColecaoInvalida):
            criar_colecao(dono, "  Obras ", None, "pessoas", "success", None)


@pytest.mark.parametrize("descricao", [123, "x" * 201])
def test_criar_colecao_recusa_descricao_invalida(app, cenario, dono, descricao):
    """Regressão: int virava AttributeError 500; >200 estourava no MySQL."""
    with app.test_request_context("/"):
        with pytest.raises(ColecaoInvalida):
            criar_colecao(dono, "Obras", descricao, "camadas", "primary", None)


def test_criar_colecao_recusa_nome_reservado_favoritos(app, cenario, dono):
    with app.test_request_context("/"):
        with pytest.raises(ColecaoInvalida):
            criar_colecao(dono, "favoritos", None, "camadas", "primary", None)


def test_criar_colecao_recusa_icone_fora_da_whitelist(app, cenario, dono):
    with app.test_request_context("/"):
        with pytest.raises(ColecaoInvalida):
            criar_colecao(dono, "Obras", None, "foguete", "primary", None)


def test_criar_colecao_recusa_cor_fora_da_regua(app, cenario, dono):
    with app.test_request_context("/"):
        with pytest.raises(ColecaoInvalida):
            criar_colecao(dono, "Obras", None, "camadas", "#ff0000", None)


def test_criar_colecao_recusa_acima_do_limite(app, cenario, dono):
    with app.test_request_context("/"):
        for indice in range(MAX_COLECOES_CUSTOM):
            _add_colecao(dono.id, f"Colecao {indice}")
        db.session.commit()
        with pytest.raises(ColecaoInvalida):
            criar_colecao(dono, "Excedente", None, "camadas", "primary", None)


def test_criar_colecao_grava_itens_na_ordem_recebida(app, cenario, dono):
    with app.test_request_context("/"):
        colecao = criar_colecao(
            dono,
            "Prioritarios",
            None,
            "camadas",
            "primary",
            [cenario["outro_visivel_id"], cenario["visivel_id"]],
        )
        db.session.commit()
        itens = (
            ProjectCollectionItem.query.filter_by(collection_id=colecao.id)
            .order_by(ProjectCollectionItem.ordem)
            .all()
        )
        assert [item.project_id for item in itens] == [
            cenario["outro_visivel_id"],
            cenario["visivel_id"],
        ]


def test_criar_colecao_com_projeto_invisivel_e_atomica(app, cenario, dono):
    """Um id fora do escopo invalida a criação inteira — nada é gravado."""
    with app.test_request_context("/"):
        with pytest.raises(ProjetoForaDoEscopo):
            criar_colecao(
                dono,
                "Mista",
                None,
                "camadas",
                "primary",
                [cenario["visivel_id"], cenario["invisivel_id"]],
            )
        db.session.rollback()
        assert ProjectCollection.query.count() == 0
        assert ProjectCollectionItem.query.count() == 0


def test_colecao_do_usuario_nao_enxerga_colecao_de_outro_dono(
    app, cenario, dono, admin
):
    with app.test_request_context("/"):
        alheia = _add_colecao(admin.id, "Do admin")
        db.session.commit()
        assert colecao_do_usuario(dono.id, alheia.id) is None
        assert colecao_do_usuario(admin.id, alheia.id) is alheia


def test_criar_colecao_aceita_projeto_invisivel_ao_dono_para_admin(app, cenario, admin):
    with app.test_request_context("/"):
        colecao = criar_colecao(
            admin, "Tudo", None, "camadas", "primary", [cenario["invisivel_id"]]
        )
        db.session.commit()
        assert (
            ProjectCollectionItem.query.filter_by(collection_id=colecao.id).count() == 1
        )


# ── editar_colecao / apagar_colecao ───────────────────────────────────────────


def test_editar_colecao_altera_somente_campos_informados(app, cenario, dono):
    with app.test_request_context("/"):
        colecao = criar_colecao(dono, "Obras", "Antiga", "camadas", "primary", None)
        db.session.commit()
        editar_colecao(colecao, nome="Obras 2026", cor="success")
        db.session.commit()
        assert (colecao.nome, colecao.cor) == ("Obras 2026", "success")
        assert (colecao.descricao, colecao.icone) == ("Antiga", "camadas")


@pytest.mark.parametrize("descricao", [123, "x" * 201])
def test_editar_colecao_recusa_descricao_invalida(app, cenario, dono, descricao):
    with app.test_request_context("/"):
        colecao = criar_colecao(dono, "Obras", None, "camadas", "primary", None)
        db.session.commit()
        with pytest.raises(ColecaoInvalida):
            editar_colecao(colecao, descricao=descricao)


def test_editar_colecao_com_valores_identicos_bumpa_updated_at(app, cenario, dono):
    """Regressão: onupdate não dispara sem mudança de coluna; o bump é explícito."""
    with app.test_request_context("/"):
        colecao = criar_colecao(dono, "Obras", "Mesma", "camadas", "primary", None)
        antigo = _envelhece(colecao)
        editar_colecao(colecao, nome="Obras", descricao="Mesma", cor="primary")
        assert colecao.updated_at > antigo


def test_editar_favoritos_e_bloqueado(app, cenario):
    with app.test_request_context("/"):
        favoritos = get_or_create_favoritos(cenario["dono_id"])
        with pytest.raises(ColecaoInvalida):
            editar_colecao(favoritos, nome="Estrelinhas")


def test_apagar_favoritos_e_bloqueado(app, cenario):
    with app.test_request_context("/"):
        favoritos = get_or_create_favoritos(cenario["dono_id"])
        with pytest.raises(ColecaoInvalida):
            apagar_colecao(favoritos)


def test_apagar_colecao_remove_itens_e_preserva_projetos(app, cenario, dono):
    with app.test_request_context("/"):
        colecao = criar_colecao(
            dono, "Obras", None, "camadas", "primary", [cenario["visivel_id"]]
        )
        db.session.commit()
        apagar_colecao(colecao)
        db.session.commit()
        assert ProjectCollection.query.count() == 0
        assert ProjectCollectionItem.query.count() == 0
        assert db.session.get(Project, cenario["visivel_id"]) is not None


# ── adicionar_projeto / remover_projeto ───────────────────────────────────────


def test_adicionar_projeto_e_idempotente(app, cenario, dono):
    with app.test_request_context("/"):
        colecao = criar_colecao(dono, "Obras", None, "camadas", "primary", None)
        db.session.commit()
        assert adicionar_projeto(colecao, cenario["visivel_id"], ator=dono) is True
        db.session.commit()
        assert adicionar_projeto(colecao, cenario["visivel_id"], ator=dono) is False
        db.session.commit()
        assert (
            ProjectCollectionItem.query.filter_by(collection_id=colecao.id).count() == 1
        )


def test_adicionar_projeto_invisivel_ao_ator_e_recusado(app, cenario, dono):
    with app.test_request_context("/"):
        colecao = criar_colecao(dono, "Obras", None, "camadas", "primary", None)
        db.session.commit()
        with pytest.raises(ProjetoForaDoEscopo):
            adicionar_projeto(colecao, cenario["invisivel_id"], ator=dono)


def _envelhece(colecao: ProjectCollection) -> datetime.datetime:
    """Grava um ``updated_at`` antigo e devolve o valor JÁ persistido."""
    colecao.updated_at = utc_now() - datetime.timedelta(days=2)
    db.session.commit()
    return colecao.updated_at


def test_adicionar_projeto_bumpa_updated_at(app, cenario, dono):
    with app.test_request_context("/"):
        colecao = criar_colecao(dono, "Obras", None, "camadas", "primary", None)
        antigo = _envelhece(colecao)
        adicionar_projeto(colecao, cenario["visivel_id"], ator=dono)
        assert colecao.updated_at > antigo


def test_remover_projeto_devolve_true_e_bumpa_updated_at(app, cenario, dono):
    with app.test_request_context("/"):
        colecao = criar_colecao(
            dono, "Obras", None, "camadas", "primary", [cenario["visivel_id"]]
        )
        antigo = _envelhece(colecao)
        assert remover_projeto(colecao, cenario["visivel_id"], ator=dono) is True
        assert colecao.updated_at > antigo
        db.session.commit()
        assert ProjectCollectionItem.query.count() == 0


def test_remover_projeto_ausente_devolve_false_sem_bump(app, cenario, dono):
    with app.test_request_context("/"):
        colecao = criar_colecao(dono, "Obras", None, "camadas", "primary", None)
        antigo = _envelhece(colecao)
        assert remover_projeto(colecao, cenario["visivel_id"], ator=dono) is False
        assert colecao.updated_at == antigo


# ── toggle_favorito ───────────────────────────────────────────────────────────


def test_toggle_favorito_alterna_o_estado(app, cenario, dono):
    with app.test_request_context("/"):
        assert toggle_favorito(dono, cenario["visivel_id"]) is True
        db.session.commit()
        favoritos = get_or_create_favoritos(dono.id)
        assert (
            ProjectCollectionItem.query.filter_by(collection_id=favoritos.id).count()
            == 1
        )
        assert toggle_favorito(dono, cenario["visivel_id"]) is False
        db.session.commit()
        assert (
            ProjectCollectionItem.query.filter_by(collection_id=favoritos.id).count()
            == 0
        )


def test_toggle_favorito_recusa_projeto_fora_do_escopo(app, cenario, dono):
    with app.test_request_context("/"):
        with pytest.raises(ProjetoForaDoEscopo):
            toggle_favorito(dono, cenario["invisivel_id"])


# ── collection_rollups ────────────────────────────────────────────────────────


def test_rollups_ignoram_projeto_invisivel_ao_viewer(app, cenario, dono, admin):
    """Item gravado quando o projeto era visível não pode vazar depois."""
    with app.test_request_context("/"):
        colecao = _add_colecao(dono.id, "Mista")
        _add_item(colecao.id, cenario["visivel_id"], ordem=0)
        _add_item(colecao.id, cenario["invisivel_id"], ordem=1)
        _add_etapa(cenario["visivel_id"], done=True, ordem=0)
        _add_etapa(cenario["visivel_id"], done=False, ordem=1)
        _add_etapa(cenario["invisivel_id"], done=True, ordem=0)
        db.session.commit()

        do_dono = collection_rollups([colecao.id], dono)[colecao.id]
        assert do_dono == {
            "projetos": 1,
            "etapas_total": 2,
            "etapas_concluidas": 1,
            "progresso_pct": 50,
        }
        do_admin = collection_rollups([colecao.id], admin)[colecao.id]
        assert do_admin["projetos"] == 2
        assert do_admin["etapas_total"] == 3


def test_rollups_de_colecao_vazia_saem_zerados(app, cenario, dono):
    with app.test_request_context("/"):
        colecao = _add_colecao(dono.id, "Vazia")
        db.session.commit()
        assert collection_rollups([colecao.id], dono)[colecao.id] == {
            "projetos": 0,
            "etapas_total": 0,
            "etapas_concluidas": 0,
            "progresso_pct": 0,
        }


def test_rollups_sem_ids_devolve_dicionario_vazio(app, cenario, dono):
    with app.test_request_context("/"):
        assert collection_rollups([], dono) == {}


# ── colecao_project_rows ──────────────────────────────────────────────────────


def test_project_rows_contam_etapas_e_tarefas_do_projeto_visivel(app, cenario, dono):
    with app.test_request_context("/"):
        colecao = _add_colecao(dono.id, "Mista")
        _add_item(colecao.id, cenario["visivel_id"], ordem=0)
        _add_item(colecao.id, cenario["invisivel_id"], ordem=1)
        etapa = _add_etapa(cenario["visivel_id"], done=True, ordem=0)
        _add_etapa(cenario["visivel_id"], done=False, ordem=1)
        _add_task(
            cenario["visivel_id"],
            dono.id,
            status="finalizada",
            ordem=1,
            etapa_id=etapa.id,
        )
        _add_task(cenario["visivel_id"], dono.id, ordem=2, etapa_id=etapa.id)
        db.session.commit()

        linhas = colecao_project_rows(colecao, dono)
        assert [linha["id"] for linha in linhas] == [cenario["visivel_id"]]
        assert linhas[0]["orgao_sigla"] == "AREAA"
        # Etapa de workflow não concluída com data_fim vencida em projeto Vigente.
        assert linhas[0]["atrasado"] is True
        assert linhas[0]["etapas_total"] == 2
        assert linhas[0]["etapas_concluidas"] == 1
        assert linhas[0]["tarefas_total"] == 2
        assert linhas[0]["tarefas_concluidas"] == 1


def test_project_rows_ignoram_reuniao_google_no_min_max_de_datas(app, cenario, dono):
    """Regressão: reunião com data distante distorcia início/fim previstos."""
    with app.test_request_context("/"):
        colecao = _add_colecao(dono.id, "Datas")
        _add_item(colecao.id, cenario["visivel_id"], ordem=0)
        _add_etapa(cenario["visivel_id"], done=False, ordem=0)
        _add_etapa(
            cenario["visivel_id"],
            done=False,
            ordem=1,
            entry_type="google_meeting",
            data_inicio=datetime.date(2020, 1, 1),
            data_fim=datetime.date(2030, 12, 31),
        )
        db.session.commit()

        linha = colecao_project_rows(colecao, dono)[0]
        assert linha["data_inicio"] == datetime.date(2026, 1, 5)
        assert linha["data_fim"] == datetime.date(2026, 1, 9)


def test_project_rows_nao_contam_tarefa_legada_nem_sem_etapa(app, cenario, dono):
    """Regressão: critério de tarefas alinhado ao Detalhe de Projeto."""
    with app.test_request_context("/"):
        colecao = _add_colecao(dono.id, "Tarefas")
        _add_item(colecao.id, cenario["visivel_id"], ordem=0)
        etapa = _add_etapa(cenario["visivel_id"], done=False, ordem=0)
        raiz = _add_task(
            cenario["visivel_id"],
            dono.id,
            status="finalizada",
            ordem=1,
            etapa_id=etapa.id,
        )
        _add_task(cenario["visivel_id"], dono.id, ordem=2)  # sem etapa
        _add_task(
            cenario["visivel_id"],
            dono.id,
            ordem=3,
            etapa_id=etapa.id,
            legacy_parent_task_id=raiz.id,
        )
        db.session.commit()

        linha = colecao_project_rows(colecao, dono)[0]
        assert linha["tarefas_total"] == 1
        assert linha["tarefas_concluidas"] == 1


# ── Fase 2: compartilhamento, acesso derivado e cronograma ────────────────────


@pytest.fixture
def cenario_share(app):
    """Coleção do dono (AREAA) e destinatários de OUTRA árvore de órgãos.

    EXTERNA > FILHA > NETA existe para provar que o share por órgão alcança só o
    órgão EXATO de lotação: nem o pai nem o filho herdam.
    """
    with app.app_context():
        area_a = _add_orgao("AREAA")
        externa = _add_orgao("EXTERNA")
        filha = _add_orgao("FILHA", pai_id=externa)
        neta = _add_orgao("NETA", pai_id=filha)
        rebuild_orgao_closure()
        dono = _add_user("dono_share", orgao_id=area_a)
        convidado = _add_user("convidado", orgao_id=filha)
        chefe = _add_user("chefe", orgao_id=externa)
        subordinado = _add_user("subordinado", orgao_id=neta)
        do_dono = _add_project("Projeto do Dono", area_a)
        reservado = _add_project("Projeto Reservado", area_a)
        do_convidado = _add_project("Projeto do Convidado", filha)
        db.session.commit()
        yield {
            "dono": dono,
            "convidado": convidado,
            "chefe": chefe,
            "subordinado": subordinado,
            "externa_id": externa,
            "filha_id": filha,
            "neta_id": neta,
            "do_dono_id": do_dono.id,
            "reservado_id": reservado.id,
            "do_convidado_id": do_convidado.id,
        }


def _colecao_do_dono(share, *, com_projeto: bool = True) -> ProjectCollection:
    colecao = criar_colecao(
        share["dono"],
        "Compartilhada",
        None,
        "camadas",
        "primary",
        [share["do_dono_id"]] if com_projeto else None,
    )
    db.session.commit()
    return colecao


def _compartilhar(colecao, share, papel=PAPEL_SHARE_VIEWER, **destino):
    resultado = compartilhar_colecao(
        colecao, ator=share["dono"], papel=papel, **destino
    )
    db.session.commit()
    return resultado


def _eventos_de(colecao: ProjectCollection) -> list[str]:
    linhas = (
        AutorizacaoAudit.query.filter_by(alvo_tipo=ALVO_COLECAO, alvo_id=colecao.id)
        .order_by(AutorizacaoAudit.id)
        .all()
    )
    return [linha.evento for linha in linhas]


# ── compartilhar_colecao ──────────────────────────────────────────────────────


def test_compartilhar_com_pessoa_grava_papel_e_autor(app, cenario_share):
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_share)
        share = _compartilhar(
            colecao,
            cenario_share,
            papel=PAPEL_SHARE_EDITOR,
            user_id=cenario_share["convidado"].id,
        )
        assert (share.user_id, share.orgao_id) == (cenario_share["convidado"].id, None)
        assert share.papel == PAPEL_SHARE_EDITOR
        assert share.created_by_user_id == cenario_share["dono"].id


def test_compartilhar_com_orgao_grava_destino_de_orgao(app, cenario_share):
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_share)
        share = _compartilhar(
            colecao, cenario_share, orgao_id=cenario_share["filha_id"]
        )
        assert (share.user_id, share.orgao_id) == (None, cenario_share["filha_id"])
        assert listar_shares(colecao) == [share]


def test_compartilhar_exige_exatamente_um_destinatario(app, cenario_share):
    """XOR: nenhum destino e os dois juntos são igualmente recusados (422)."""
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_share)
        with pytest.raises(ColecaoInvalida):
            compartilhar_colecao(
                colecao, ator=cenario_share["dono"], papel=PAPEL_SHARE_VIEWER
            )
        with pytest.raises(ColecaoInvalida):
            compartilhar_colecao(
                colecao,
                ator=cenario_share["dono"],
                user_id=cenario_share["convidado"].id,
                orgao_id=cenario_share["filha_id"],
                papel=PAPEL_SHARE_VIEWER,
            )


@pytest.mark.parametrize("papel", ["dono", "admin", "", None, 1])
def test_compartilhar_recusa_papel_fora_da_whitelist(app, cenario_share, papel):
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_share)
        with pytest.raises(ColecaoInvalida):
            compartilhar_colecao(
                colecao,
                ator=cenario_share["dono"],
                user_id=cenario_share["convidado"].id,
                papel=papel,
            )


def test_compartilhar_destinatario_repetido_faz_upsert_do_papel(app, cenario_share):
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_share)
        primeiro = _compartilhar(
            colecao, cenario_share, user_id=cenario_share["convidado"].id
        )
        segundo = _compartilhar(
            colecao,
            cenario_share,
            papel=PAPEL_SHARE_EDITOR,
            user_id=cenario_share["convidado"].id,
        )
        assert segundo.id == primeiro.id
        assert segundo.papel == PAPEL_SHARE_EDITOR
        assert ProjectCollectionShare.query.count() == 1


def test_compartilhar_favoritos_e_bloqueado(app, cenario_share):
    with app.test_request_context("/"):
        favoritos = get_or_create_favoritos(cenario_share["dono"].id)
        db.session.commit()
        with pytest.raises(ColecaoInvalida):
            compartilhar_colecao(
                favoritos,
                ator=cenario_share["dono"],
                user_id=cenario_share["convidado"].id,
                papel=PAPEL_SHARE_VIEWER,
            )


def test_compartilhar_recusa_destinatario_inexistente(app, cenario_share):
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_share)
        with pytest.raises(ColecaoInvalida):
            compartilhar_colecao(
                colecao,
                ator=cenario_share["dono"],
                user_id=999999,
                papel=PAPEL_SHARE_VIEWER,
            )
        with pytest.raises(ColecaoInvalida):
            compartilhar_colecao(
                colecao,
                ator=cenario_share["dono"],
                orgao_id=999999,
                papel=PAPEL_SHARE_VIEWER,
            )


def test_compartilhar_por_quem_nao_e_dono_e_bloqueado(app, cenario_share):
    """Editor VÊ a coleção, mas gerir shares é privativo do dono (403 na rota)."""
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_share)
        _compartilhar(
            colecao,
            cenario_share,
            papel=PAPEL_SHARE_EDITOR,
            user_id=cenario_share["convidado"].id,
        )
        with pytest.raises(ColecaoSemPermissao):
            compartilhar_colecao(
                colecao,
                ator=cenario_share["convidado"],
                user_id=cenario_share["chefe"].id,
                papel=PAPEL_SHARE_VIEWER,
            )


def test_criar_colecao_aplica_compartilhamentos_iniciais(app, cenario_share):
    with app.test_request_context("/"):
        colecao = criar_colecao(
            cenario_share["dono"],
            "Nasce compartilhada",
            None,
            "camadas",
            "primary",
            None,
            [
                {"user_id": cenario_share["convidado"].id, "papel": PAPEL_SHARE_EDITOR},
                {"orgao_id": cenario_share["externa_id"], "papel": PAPEL_SHARE_VIEWER},
            ],
        )
        db.session.commit()
        assert [
            (share.user_id, share.orgao_id, share.papel)
            for share in listar_shares(colecao)
        ] == [
            (cenario_share["convidado"].id, None, PAPEL_SHARE_EDITOR),
            (None, cenario_share["externa_id"], PAPEL_SHARE_VIEWER),
        ]


# ── revogar_share ─────────────────────────────────────────────────────────────


def test_revogar_share_apaga_a_linha(app, cenario_share):
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_share)
        share = _compartilhar(
            colecao, cenario_share, user_id=cenario_share["convidado"].id
        )
        assert revogar_share(colecao, share.id, ator=cenario_share["dono"]) is True
        db.session.commit()
        assert ProjectCollectionShare.query.count() == 0


def test_revogar_share_inexistente_devolve_false(app, cenario_share):
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_share)
        assert revogar_share(colecao, 999999, ator=cenario_share["dono"]) is False


def test_revogar_share_de_outra_colecao_devolve_false(app, cenario_share):
    """Id de share válido, mas de outra coleção: 404 na rota, nada apagado."""
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_share)
        outra = criar_colecao(
            cenario_share["dono"], "Outra", None, "camadas", "primary", None
        )
        db.session.commit()
        share = _compartilhar(
            colecao, cenario_share, user_id=cenario_share["convidado"].id
        )
        assert revogar_share(outra, share.id, ator=cenario_share["dono"]) is False
        assert ProjectCollectionShare.query.count() == 1


def test_revogar_share_por_quem_nao_e_dono_e_bloqueado(app, cenario_share):
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_share)
        share = _compartilhar(
            colecao,
            cenario_share,
            papel=PAPEL_SHARE_EDITOR,
            user_id=cenario_share["convidado"].id,
        )
        with pytest.raises(ColecaoSemPermissao):
            revogar_share(colecao, share.id, ator=cenario_share["convidado"])


# ── papel_do_usuario ──────────────────────────────────────────────────────────


def test_papel_do_usuario_reconhece_dono_e_estranho(app, cenario_share):
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_share)
        assert papel_do_usuario(colecao, cenario_share["dono"]) == PAPEL_COLECAO_DONO
        assert papel_do_usuario(colecao, cenario_share["convidado"]) is None


def test_papel_do_usuario_por_share_direto(app, cenario_share):
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_share)
        _compartilhar(colecao, cenario_share, user_id=cenario_share["convidado"].id)
        assert (
            papel_do_usuario(colecao, cenario_share["convidado"]) == PAPEL_SHARE_VIEWER
        )


def test_papel_do_usuario_por_orgao_exato_de_lotacao(app, cenario_share):
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_share)
        _compartilhar(
            colecao,
            cenario_share,
            papel=PAPEL_SHARE_EDITOR,
            orgao_id=cenario_share["filha_id"],
        )
        assert (
            papel_do_usuario(colecao, cenario_share["convidado"]) == PAPEL_SHARE_EDITOR
        )
        # Pai e filho do órgão alvo não herdam o share.
        assert papel_do_usuario(colecao, cenario_share["chefe"]) is None
        assert papel_do_usuario(colecao, cenario_share["subordinado"]) is None


def test_papel_do_usuario_soma_shares_e_vence_o_mais_alto(app, cenario_share):
    """Viewer direto + editor pelo órgão: prevalece editor."""
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_share)
        _compartilhar(colecao, cenario_share, user_id=cenario_share["convidado"].id)
        _compartilhar(
            colecao,
            cenario_share,
            papel=PAPEL_SHARE_EDITOR,
            orgao_id=cenario_share["filha_id"],
        )
        assert (
            papel_do_usuario(colecao, cenario_share["convidado"]) == PAPEL_SHARE_EDITOR
        )


# ── listar_colecoes com compartilhadas ────────────────────────────────────────


def test_listar_colecoes_inclui_compartilhada_comigo_depois_das_minhas(
    app, cenario_share
):
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_share)
        _compartilhar(colecao, cenario_share, user_id=cenario_share["convidado"].id)
        pares = listar_colecoes(cenario_share["convidado"].id)
        db.session.commit()
        assert [(item.tipo, papel) for item, papel in pares] == [
            (TIPO_COLECAO_FAVORITOS, PAPEL_COLECAO_DONO),
            (TIPO_COLECAO_CUSTOM, PAPEL_SHARE_VIEWER),
        ]
        assert pares[1][0].id == colecao.id


def test_listar_colecoes_inclui_compartilhada_com_orgao_exato(app, cenario_share):
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_share)
        _compartilhar(
            colecao,
            cenario_share,
            papel=PAPEL_SHARE_EDITOR,
            orgao_id=cenario_share["filha_id"],
        )
        pares = listar_colecoes(cenario_share["convidado"].id)
        db.session.commit()
        assert (colecao.id, PAPEL_SHARE_EDITOR) in [
            (item.id, papel) for item, papel in pares
        ]


def test_listar_colecoes_ignora_share_de_orgao_diferente(app, cenario_share):
    """Share na FILHA não aparece para quem está lotado no pai nem no neto."""
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_share)
        _compartilhar(colecao, cenario_share, orgao_id=cenario_share["filha_id"])
        for user in (cenario_share["chefe"], cenario_share["subordinado"]):
            pares = listar_colecoes(user.id)
            db.session.commit()
            assert [item.tipo for item, _ in pares] == [TIPO_COLECAO_FAVORITOS]


def test_listar_colecoes_nao_duplica_colecao_com_dois_shares(app, cenario_share):
    """Share direto + share de órgão na MESMA coleção: uma linha, papel mais alto."""
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_share)
        _compartilhar(colecao, cenario_share, user_id=cenario_share["convidado"].id)
        _compartilhar(
            colecao,
            cenario_share,
            papel=PAPEL_SHARE_EDITOR,
            orgao_id=cenario_share["filha_id"],
        )
        pares = listar_colecoes(cenario_share["convidado"].id)
        db.session.commit()
        compartilhadas = [(item.id, papel) for item, papel in pares[1:]]
        assert compartilhadas == [(colecao.id, PAPEL_SHARE_EDITOR)]


# ── Acesso derivado a projetos (project_visibility_criterion) ─────────────────


def test_share_da_visibilidade_do_projeto_e_revogar_tira(app, cenario_share):
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_share)
        assert (
            projeto_visivel_para(
                cenario_share["convidado"], cenario_share["do_dono_id"]
            )
            is False
        )
        share = _compartilhar(
            colecao, cenario_share, user_id=cenario_share["convidado"].id
        )
        assert (
            projeto_visivel_para(
                cenario_share["convidado"], cenario_share["do_dono_id"]
            )
            is True
        )
        revogar_share(colecao, share.id, ator=cenario_share["dono"])
        db.session.commit()
        assert (
            projeto_visivel_para(
                cenario_share["convidado"], cenario_share["do_dono_id"]
            )
            is False
        )


def test_acesso_derivado_alcanca_so_o_orgao_exato_do_share(app, cenario_share):
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_share)
        _compartilhar(colecao, cenario_share, orgao_id=cenario_share["filha_id"])
        assert (
            projeto_visivel_para(
                cenario_share["convidado"], cenario_share["do_dono_id"]
            )
            is True
        )
        assert (
            projeto_visivel_para(cenario_share["chefe"], cenario_share["do_dono_id"])
            is False
        )
        assert (
            projeto_visivel_para(
                cenario_share["subordinado"], cenario_share["do_dono_id"]
            )
            is False
        )


def test_acesso_derivado_cobre_so_os_projetos_da_colecao(app, cenario_share):
    """Share não abre o acervo do dono: só os itens daquela coleção."""
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_share)
        _compartilhar(colecao, cenario_share, user_id=cenario_share["convidado"].id)
        assert (
            projeto_visivel_para(
                cenario_share["convidado"], cenario_share["reservado_id"]
            )
            is False
        )


# ── Papéis nas mutações de item ───────────────────────────────────────────────


def test_editor_adiciona_projeto_que_enxerga(app, cenario_share):
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_share)
        _compartilhar(
            colecao,
            cenario_share,
            papel=PAPEL_SHARE_EDITOR,
            user_id=cenario_share["convidado"].id,
        )
        assert (
            adicionar_projeto(
                colecao,
                cenario_share["do_convidado_id"],
                ator=cenario_share["convidado"],
            )
            is True
        )
        db.session.commit()
        assert (
            ProjectCollectionItem.query.filter_by(collection_id=colecao.id).count() == 2
        )


def test_editor_nao_adiciona_projeto_que_nao_enxerga(app, cenario_share):
    """Anti-escalação: o editor só empurra para a coleção o que já está no escopo DELE."""
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_share)
        _compartilhar(
            colecao,
            cenario_share,
            papel=PAPEL_SHARE_EDITOR,
            user_id=cenario_share["convidado"].id,
        )
        with pytest.raises(ProjetoForaDoEscopo):
            adicionar_projeto(
                colecao, cenario_share["reservado_id"], ator=cenario_share["convidado"]
            )


def test_editor_remove_projeto_da_colecao(app, cenario_share):
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_share)
        _compartilhar(
            colecao,
            cenario_share,
            papel=PAPEL_SHARE_EDITOR,
            user_id=cenario_share["convidado"].id,
        )
        assert (
            remover_projeto(
                colecao, cenario_share["do_dono_id"], ator=cenario_share["convidado"]
            )
            is True
        )
        db.session.commit()
        assert ProjectCollectionItem.query.count() == 0


def test_viewer_nao_muta_itens_da_colecao(app, cenario_share):
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_share)
        _compartilhar(colecao, cenario_share, user_id=cenario_share["convidado"].id)
        with pytest.raises(ColecaoSemPermissao):
            adicionar_projeto(
                colecao,
                cenario_share["do_convidado_id"],
                ator=cenario_share["convidado"],
            )
        with pytest.raises(ColecaoSemPermissao):
            remover_projeto(
                colecao, cenario_share["do_dono_id"], ator=cenario_share["convidado"]
            )


def test_estranho_nao_muta_itens_da_colecao(app, cenario_share):
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_share)
        with pytest.raises(ColecaoSemPermissao):
            adicionar_projeto(
                colecao,
                cenario_share["do_convidado_id"],
                ator=cenario_share["convidado"],
            )


# ── Auditoria (AutorizacaoAudit) ──────────────────────────────────────────────


def test_auditoria_registra_ciclo_de_vida_do_share(app, cenario_share):
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_share)
        share = _compartilhar(
            colecao, cenario_share, user_id=cenario_share["convidado"].id
        )
        _compartilhar(
            colecao,
            cenario_share,
            papel=PAPEL_SHARE_EDITOR,
            user_id=cenario_share["convidado"].id,
        )
        revogar_share(colecao, share.id, ator=cenario_share["dono"])
        db.session.commit()
        assert _eventos_de(colecao) == [
            "colecao_share_concedido",
            "colecao_share_alterado",
            "colecao_share_revogado",
        ]


def test_auditoria_do_share_guarda_ator_destino_e_papel(app, cenario_share):
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_share)
        _compartilhar(
            colecao,
            cenario_share,
            papel=PAPEL_SHARE_EDITOR,
            user_id=cenario_share["convidado"].id,
        )
        linha = AutorizacaoAudit.query.filter_by(evento="colecao_share_concedido").one()
        assert (linha.alvo_tipo, linha.alvo_id) == (ALVO_COLECAO, colecao.id)
        assert (linha.ator_id, linha.user_id) == (
            cenario_share["dono"].id,
            cenario_share["convidado"].id,
        )
        assert linha.detalhe["papel"] == PAPEL_SHARE_EDITOR
        assert linha.detalhe["destino"] == "user"


def test_auditoria_de_share_de_orgao_rotula_o_destino(app, cenario_share):
    """O user_id da linha é o ator (não há destinatário único); o rótulo
    ``destino`` evita ler o ator como beneficiário."""
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_share)
        _compartilhar(colecao, cenario_share, orgao_id=cenario_share["filha_id"])
        linha = AutorizacaoAudit.query.filter_by(evento="colecao_share_concedido").one()
        assert linha.detalhe["destino"] == "orgao"
        assert linha.user_id == cenario_share["dono"].id


def test_auditoria_registra_itens_de_colecao_compartilhada(app, cenario_share):
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_share, com_projeto=False)
        _compartilhar(
            colecao,
            cenario_share,
            papel=PAPEL_SHARE_EDITOR,
            user_id=cenario_share["convidado"].id,
        )
        adicionar_projeto(
            colecao, cenario_share["do_convidado_id"], ator=cenario_share["convidado"]
        )
        remover_projeto(
            colecao, cenario_share["do_convidado_id"], ator=cenario_share["convidado"]
        )
        db.session.commit()
        assert _eventos_de(colecao)[1:] == [
            "colecao_projeto_adicionado",
            "colecao_projeto_removido",
        ]
        linha = AutorizacaoAudit.query.filter_by(
            evento="colecao_projeto_adicionado"
        ).one()
        assert linha.detalhe["project_id"] == cenario_share["do_convidado_id"]
        assert linha.ator_id == cenario_share["convidado"].id


def test_auditoria_ignora_itens_de_colecao_pessoal(app, cenario_share):
    """Coleção sem share é gaveta pessoal: mexer nela não vira trilha."""
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_share, com_projeto=False)
        adicionar_projeto(
            colecao, cenario_share["do_dono_id"], ator=cenario_share["dono"]
        )
        remover_projeto(
            colecao, cenario_share["do_dono_id"], ator=cenario_share["dono"]
        )
        db.session.commit()
        assert _eventos_de(colecao) == []


# ── Regressões de segurança (review da Fase 2) ────────────────────────────────


def test_dono_nao_se_auto_eleva_compartilhando_com_o_proprio_orgao(app):
    """Leitor cria coleção com projeto que só LÊ e compartilha editor com o
    próprio órgão: o rank do DONO não muda; o do colega (uso legítimo) sim."""
    with app.test_request_context("/"):
        area = _add_orgao("AREALEITORA")
        dono_leitor = _add_user("dono_leitor", orgao_id=area, papel="leitor")
        colega = _add_user("colega_leitor", orgao_id=area, papel="leitor")
        projeto = _add_project("Projeto So Leitura", area)
        db.session.commit()
        colecao = criar_colecao(
            dono_leitor, "Escalada", None, "camadas", "primary", [projeto.id]
        )
        compartilhar_colecao(
            colecao, ator=dono_leitor, orgao_id=area, papel=PAPEL_SHARE_EDITOR
        )
        db.session.commit()
        assert effective_project_rank(dono_leitor, projeto) == (
            PAPEL_RANK[PAPEL_LEITOR]
        )
        assert effective_project_rank(colega, projeto) == PAPEL_RANK[PAPEL_EDITOR]


def test_apagar_colecao_remove_shares_e_nova_colecao_nao_herda(app, cenario_share):
    """Regressão: share órfão era herdado pela próxima coleção (reuso de rowid)."""
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_share)
        _compartilhar(colecao, cenario_share, user_id=cenario_share["convidado"].id)
        apagar_colecao(colecao)
        db.session.commit()
        assert ProjectCollectionShare.query.count() == 0
        nova = criar_colecao(
            cenario_share["dono"], "Nova gaveta", None, "camadas", "primary", None
        )
        db.session.commit()
        assert listar_shares(nova) == []
        assert papel_do_usuario(nova, cenario_share["convidado"]) is None


def test_viewer_nao_readiciona_projeto_derivado_em_colecao_custom_propria(
    app, cenario_share
):
    """Anti re-share transitivo: visibilidade derivada de share não semeia
    coleção custom própria — nem na criação nem em adicionar_projeto."""
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_share)
        _compartilhar(colecao, cenario_share, user_id=cenario_share["convidado"].id)
        convidado = cenario_share["convidado"]
        assert projeto_visivel_para(convidado, cenario_share["do_dono_id"]) is True
        with pytest.raises(ProjetoForaDoEscopo):
            criar_colecao(
                convidado,
                "Recompartilha",
                None,
                "camadas",
                "primary",
                [cenario_share["do_dono_id"]],
            )
        propria = criar_colecao(
            convidado, "Minha gaveta", None, "camadas", "primary", None
        )
        db.session.commit()
        with pytest.raises(ProjetoForaDoEscopo):
            adicionar_projeto(propria, cenario_share["do_dono_id"], ator=convidado)


def test_favoritos_aceita_projeto_de_visibilidade_derivada(app, cenario_share):
    """Favoritos nunca é compartilhável nem concede acesso: derivada é aceita."""
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_share)
        _compartilhar(colecao, cenario_share, user_id=cenario_share["convidado"].id)
        assert (
            toggle_favorito(cenario_share["convidado"], cenario_share["do_dono_id"])
            is True
        )


def test_compartilhar_recusa_orgao_inativo(app, cenario_share):
    with app.test_request_context("/"):
        inativo = _add_orgao("INATIVO", ativo=False)
        db.session.commit()
        colecao = _colecao_do_dono(cenario_share)
        with pytest.raises(ColecaoInvalida):
            compartilhar_colecao(
                colecao,
                ator=cenario_share["dono"],
                orgao_id=inativo,
                papel=PAPEL_SHARE_VIEWER,
            )


def test_share_de_dono_soft_deletado_nao_concede(app, cenario_share):
    with app.test_request_context("/"):
        colecao = _colecao_do_dono(cenario_share)
        _compartilhar(colecao, cenario_share, user_id=cenario_share["convidado"].id)
        cenario_share["dono"].deleted_at = utc_now()
        db.session.commit()
        convidado = cenario_share["convidado"]
        assert projeto_visivel_para(convidado, cenario_share["do_dono_id"]) is False
        pares = listar_colecoes(convidado.id)
        assert colecao.id not in [item.id for item, _ in pares]
        # Acesso direto pela URL da coleção também cai (papel None → 404).
        assert papel_do_usuario(colecao, convidado) is None


def test_itens_iniciais_de_colecao_ja_compartilhada_sao_auditados(app, cenario_share):
    """Regressão: itens do payload de criação escapavam da trilha de auditoria."""
    with app.test_request_context("/"):
        colecao = criar_colecao(
            cenario_share["dono"],
            "Nasce auditada",
            None,
            "camadas",
            "primary",
            [cenario_share["do_dono_id"]],
            [{"user_id": cenario_share["convidado"].id, "papel": PAPEL_SHARE_VIEWER}],
        )
        db.session.commit()
        assert _eventos_de(colecao) == [
            "colecao_share_concedido",
            "colecao_projeto_adicionado",
        ]
        linha = AutorizacaoAudit.query.filter_by(
            evento="colecao_projeto_adicionado", alvo_id=colecao.id
        ).one()
        assert linha.detalhe["project_id"] == cenario_share["do_dono_id"]
        assert linha.ator_id == cenario_share["dono"].id


# ── colecao_cronograma_rows (Gantt da tela 3c) ────────────────────────────────


def _dias(offset: int) -> datetime.date:
    return datetime.date.today() + datetime.timedelta(days=offset)


def test_cronograma_classifica_a_barra_de_cada_etapa(app, cenario, dono):
    with app.test_request_context("/"):
        colecao = _add_colecao(dono.id, "Cronograma")
        _add_item(colecao.id, cenario["visivel_id"], ordem=0)
        _add_etapa(
            cenario["visivel_id"],
            done=True,
            ordem=0,
            data_inicio=_dias(-20),
            data_fim=_dias(-10),
        )
        _add_etapa(
            cenario["visivel_id"],
            done=False,
            ordem=1,
            data_inicio=_dias(-9),
            data_fim=_dias(-1),
        )
        _add_etapa(
            cenario["visivel_id"],
            done=False,
            ordem=2,
            data_inicio=_dias(-1),
            data_fim=_dias(5),
        )
        _add_etapa(
            cenario["visivel_id"],
            done=False,
            ordem=3,
            data_inicio=_dias(10),
            data_fim=_dias(20),
        )
        db.session.commit()

        projeto = colecao_cronograma_rows(colecao, dono)[0]
        assert [etapa["barra"] for etapa in projeto["etapas"]] == [
            BARRA_CONCLUIDA,
            BARRA_VENCIDA,
            BARRA_EXECUCAO,
            BARRA_PREVISTA,
        ]
        assert projeto["sem_data"] == 0


def test_cronograma_conta_etapa_sem_data_fora_das_barras(app, cenario, dono):
    with app.test_request_context("/"):
        colecao = _add_colecao(dono.id, "Cronograma")
        _add_item(colecao.id, cenario["visivel_id"], ordem=0)
        _add_etapa(cenario["visivel_id"], done=False, ordem=0)
        _add_etapa(
            cenario["visivel_id"], done=False, ordem=1, data_inicio=None, data_fim=None
        )
        db.session.commit()

        projeto = colecao_cronograma_rows(colecao, dono)[0]
        assert len(projeto["etapas"]) == 1
        assert projeto["sem_data"] == 1


def test_cronograma_ignora_reuniao_google(app, cenario, dono):
    with app.test_request_context("/"):
        colecao = _add_colecao(dono.id, "Cronograma")
        _add_item(colecao.id, cenario["visivel_id"], ordem=0)
        _add_etapa(cenario["visivel_id"], done=False, ordem=0)
        _add_etapa(
            cenario["visivel_id"], done=False, ordem=1, entry_type="google_meeting"
        )
        db.session.commit()

        projeto = colecao_cronograma_rows(colecao, dono)[0]
        assert len(projeto["etapas"]) == 1
        assert projeto["sem_data"] == 0


def test_cronograma_traz_so_projeto_visivel_na_ordem_da_colecao(
    app, cenario, dono, admin
):
    with app.test_request_context("/"):
        colecao = _add_colecao(dono.id, "Cronograma")
        _add_item(colecao.id, cenario["invisivel_id"], ordem=0)
        _add_item(colecao.id, cenario["outro_visivel_id"], ordem=1)
        _add_item(colecao.id, cenario["visivel_id"], ordem=2)
        db.session.commit()

        do_dono = colecao_cronograma_rows(colecao, dono)
        assert [projeto["id"] for projeto in do_dono] == [
            cenario["outro_visivel_id"],
            cenario["visivel_id"],
        ]
        assert do_dono[0]["orgao_sigla"] == "AREAA"
        assert do_dono[0]["nome"] == "Outro Visivel"
        assert [
            projeto["id"] for projeto in colecao_cronograma_rows(colecao, admin)
        ] == [
            cenario["invisivel_id"],
            cenario["outro_visivel_id"],
            cenario["visivel_id"],
        ]
