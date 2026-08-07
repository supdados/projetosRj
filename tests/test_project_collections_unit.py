"""Testes de services/project_collections.py (coleções de projetos, Fase 1).

Cobre o que a rota NÃO pode reimplementar: get-or-create de Favoritos, validação
de identidade/limites, criação atômica com visibilidade, itens idempotentes com
bump de ``updated_at`` e os rollups filtrados pelo escopo do viewer.

O service não commita: os testes rodam dentro de ``app.test_request_context``
(``project_visibility_criterion`` usa cache de request) e usam ``flush``/commit
explícitos.
"""

import datetime

import pytest

from models import (
    Etapa,
    OrgaoUnidade,
    Project,
    ProjectCollection,
    ProjectCollectionItem,
    Task,
    TIPO_COLECAO_CUSTOM,
    TIPO_COLECAO_FAVORITOS,
    User,
    UserOrgao,
    db,
)
from services.orgao_tree import rebuild_orgao_closure
from services.project_collections import (
    FAVORITOS_NOME,
    MAX_COLECOES_CUSTOM,
    MAX_ITENS_POR_COLECAO,
    ColecaoInvalida,
    ProjetoForaDoEscopo,
    adicionar_projeto,
    apagar_colecao,
    colecao_do_usuario,
    colecao_project_rows,
    collection_rollups,
    criar_colecao,
    editar_colecao,
    get_or_create_favoritos,
    listar_colecoes,
    remover_projeto,
    toggle_favorito,
)
from time_utils import utc_now

# ── Helpers de fixture ────────────────────────────────────────────────────────


def _add_orgao(sigla: str) -> int:
    orgao = OrgaoUnidade(
        sigla=sigla, nome=sigla, tipo="Secretaria", pai_id=None, ordem=0, ativo=True
    )
    db.session.add(orgao)
    db.session.flush()
    return orgao.id


def _add_user(username: str, *, orgao_id: int | None = None, admin: bool = False):
    user = User(
        username=username, name=username.upper(), password_hash="x", is_admin=admin
    )
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
        colecoes = listar_colecoes(dono.id)
        assert [colecao.tipo for colecao in colecoes] == [
            TIPO_COLECAO_FAVORITOS,
            TIPO_COLECAO_CUSTOM,
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


def test_adicionar_projeto_recusa_acima_do_limite_de_itens(app, cenario, dono):
    with app.test_request_context("/"):
        colecao = criar_colecao(dono, "Obras", None, "camadas", "primary", None)
        db.session.commit()
        # Itens sintéticos: o limite conta linhas, não valida o projeto de novo.
        for indice in range(MAX_ITENS_POR_COLECAO):
            _add_item(colecao.id, 900000 + indice, ordem=indice)
        db.session.commit()
        with pytest.raises(ColecaoInvalida):
            adicionar_projeto(colecao, cenario["visivel_id"], ator=dono)


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
        assert remover_projeto(colecao, cenario["visivel_id"]) is True
        assert colecao.updated_at > antigo
        db.session.commit()
        assert ProjectCollectionItem.query.count() == 0


def test_remover_projeto_ausente_devolve_false_sem_bump(app, cenario, dono):
    with app.test_request_context("/"):
        colecao = criar_colecao(dono, "Obras", None, "camadas", "primary", None)
        antigo = _envelhece(colecao)
        assert remover_projeto(colecao, cenario["visivel_id"]) is False
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
