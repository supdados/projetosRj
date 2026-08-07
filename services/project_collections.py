"""Regras de domínio das coleções de projetos (Fase 1 do MVP).

Domínio de ``ProjectCollection``/``ProjectCollectionItem``: criação atômica,
edição/remoção (com bloqueio de Favoritos), itens idempotentes com limite e os
rollups agregados em NÚMERO FIXO de queries. Nada de ``request``/``g`` aqui — o
HTTP (gates, envelope, anti-enumeração) fica em ``routes/api/collections.py``.

O service NÃO commita: valida, muta a sessão (com ``flush`` quando precisa de
id) e deixa o commit/rollback para a rota — padrão ``services/project_invites``.

Visibilidade: todo project_id que entra numa coleção é validado contra
``project_visibility_criterion`` do ATOR (admin enxerga tudo); id invisível é
indistinguível de inexistente (``ProjetoForaDoEscopo`` → 404 anti-enumeração).
"""

from __future__ import annotations

import datetime
from typing import Any, Iterable

from sqlalchemy import and_, case, func
from sqlalchemy.exc import IntegrityError

from catalogs.collection_identity import (
    COLLECTION_COLORS,
    COLLECTION_ICONS,
    FAVORITOS_COLOR,
    FAVORITOS_ICON,
)
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
    db,
)
from services.authorization import project_visibility_criterion
from time_utils import utc_now

MAX_COLECOES_CUSTOM = 30
MAX_ITENS_POR_COLECAO = 200
NOME_MAX_COLECAO = 100
DESCRICAO_MAX_COLECAO = 200
FAVORITOS_NOME = "Favoritos"

_NAO_INFORMADO: Any = object()


class ColecaoInvalida(ValueError):
    """Payload de coleção recusado (nome, ícone/cor, limite, Favoritos)."""


class ProjetoForaDoEscopo(ColecaoInvalida):
    """Projeto inexistente OU invisível ao ator — a rota mapeia para 404."""


def colecao_do_usuario(user_id: int, collection_id: int) -> ProjectCollection | None:
    """Coleção pelo id, SOMENTE se pertence ao usuário (``None`` → 404 na rota)."""
    return ProjectCollection.query.filter_by(
        id=collection_id, owner_user_id=user_id
    ).first()


def listar_colecoes(user_id: int) -> list[ProjectCollection]:
    """Coleções do usuário com Favoritos garantida (get-or-create) e primeira."""
    favoritos = get_or_create_favoritos(user_id)
    custom = (
        ProjectCollection.query.filter_by(
            owner_user_id=user_id, tipo=TIPO_COLECAO_CUSTOM
        )
        .order_by(ProjectCollection.updated_at.desc(), ProjectCollection.id.desc())
        .all()
    )
    return [favoritos, *custom]


def favoritos_existente(user_id: int) -> ProjectCollection | None:
    """Favoritos já persistida do usuário, sem criar (para leituras puras)."""
    return ProjectCollection.query.filter_by(
        owner_user_id=user_id, tipo=TIPO_COLECAO_FAVORITOS
    ).first()


def get_or_create_favoritos(user_id: int) -> ProjectCollection:
    """Coleção de sistema "Favoritos" do usuário, criada sob demanda.

    Unicidade (1 por usuário) garantida aqui — índice único parcial não é
    portável. Exemplo: ``get_or_create_favoritos(g.user.id)``.
    """
    existente = favoritos_existente(user_id)
    if existente is not None:
        return existente
    favoritos = ProjectCollection(
        owner_user_id=user_id,
        nome=FAVORITOS_NOME,
        tipo=TIPO_COLECAO_FAVORITOS,
        icone=FAVORITOS_ICON,
        cor=FAVORITOS_COLOR,
    )
    db.session.add(favoritos)
    try:
        db.session.flush()
    except IntegrityError:
        # Corrida com request concorrente: quem perdeu o INSERT relê o vencedor.
        db.session.rollback()
        existente = favoritos_existente(user_id)
        if existente is None:
            raise
        return existente
    return favoritos


def criar_colecao(
    owner: User,
    nome: str,
    descricao: str | None,
    icone: str,
    cor: str,
    project_ids: list[int] | None,
) -> ProjectCollection:
    """Cria coleção custom + itens numa única transação (fluxo do modal).

    Exemplo: ``criar_colecao(g.user, "Saúde digital", None, "pessoas",
    "success", [3, 7])`` — o chamador commita.
    """
    nome_limpo = _validar_nome(owner.id, nome)
    _validar_icone(icone)
    _validar_cor(cor)
    _validar_limite_colecoes(owner.id)
    ids_visiveis = _validar_projetos_visiveis(owner, project_ids or [])
    colecao = ProjectCollection(
        owner_user_id=owner.id,
        nome=nome_limpo,
        descricao=_validar_descricao(descricao),
        icone=icone,
        cor=cor,
    )
    db.session.add(colecao)
    db.session.flush()
    for ordem, project_id in enumerate(ids_visiveis):
        db.session.add(
            ProjectCollectionItem(
                collection_id=colecao.id, project_id=project_id, ordem=ordem
            )
        )
    return colecao


def editar_colecao(
    colecao: ProjectCollection,
    *,
    nome: Any = _NAO_INFORMADO,
    descricao: Any = _NAO_INFORMADO,
    icone: Any = _NAO_INFORMADO,
    cor: Any = _NAO_INFORMADO,
) -> ProjectCollection:
    """Edita campos informados; Favoritos é imutável (422 na rota).

    Campos ausentes no payload ficam intactos (sentinela ``_NAO_INFORMADO``).
    """
    _bloquear_favoritos(colecao, "editar")
    if nome is not _NAO_INFORMADO:
        colecao.nome = _validar_nome(colecao.owner_user_id, nome, colecao_id=colecao.id)
    if descricao is not _NAO_INFORMADO:
        colecao.descricao = _validar_descricao(descricao)
    if icone is not _NAO_INFORMADO:
        _validar_icone(icone)
        colecao.icone = icone
    if cor is not _NAO_INFORMADO:
        _validar_cor(cor)
        colecao.cor = cor
    # onupdate não dispara em PUT com valores idênticos; bump explícito mantém
    # a ordenação "atualizadas" honesta.
    _bump_updated_at(colecao)
    return colecao


def apagar_colecao(colecao: ProjectCollection) -> None:
    """Hard-delete da coleção e dos itens; projetos ficam intactos."""
    _bloquear_favoritos(colecao, "apagar")
    # DELETE explícito dos itens: o ondelete CASCADE do banco não é confiável
    # em SQLite sem PRAGMA foreign_keys.
    ProjectCollectionItem.query.filter_by(collection_id=colecao.id).delete()
    db.session.delete(colecao)


def adicionar_projeto(
    colecao: ProjectCollection, project_id: int, *, ator: User
) -> bool:
    """Adiciona projeto à coleção; idempotente (``False`` se já estava).

    Exige que o ATOR veja o projeto (anti-escalação) e bumpa ``updated_at``
    manualmente (mutação de item não toca a linha da coleção).
    """
    if not projeto_visivel_para(ator, project_id):
        raise ProjetoForaDoEscopo(
            f"projeto inexistente ou fora do escopo: id={project_id}"
        )
    ja_existe = ProjectCollectionItem.query.filter_by(
        collection_id=colecao.id, project_id=project_id
    ).first()
    if ja_existe is not None:
        return False
    _validar_limite_itens(colecao.id)
    db.session.add(
        ProjectCollectionItem(
            collection_id=colecao.id,
            project_id=project_id,
            ordem=_proxima_ordem(colecao.id),
        )
    )
    _bump_updated_at(colecao)
    return True


def remover_projeto(colecao: ProjectCollection, project_id: int) -> bool:
    """Remove o par coleção×projeto; ``False`` se não estava na coleção."""
    removidos = ProjectCollectionItem.query.filter_by(
        collection_id=colecao.id, project_id=project_id
    ).delete()
    if not removidos:
        return False
    _bump_updated_at(colecao)
    return True


def toggle_favorito(user: User, project_id: int) -> bool:
    """Alterna o projeto na coleção Favoritos; ``True`` = agora é favorito.

    Exemplo: ``favorito = toggle_favorito(g.user, project_id)``.
    """
    if not projeto_visivel_para(user, project_id):
        raise ProjetoForaDoEscopo(
            f"projeto inexistente ou fora do escopo: id={project_id}"
        )
    favoritos = get_or_create_favoritos(user.id)
    if remover_projeto(favoritos, project_id):
        return False
    return adicionar_projeto(favoritos, project_id, ator=user)


def projeto_visivel_para(ator: User, project_id: int) -> bool:
    """True se o projeto existe E está no escopo do ator (admin vê tudo)."""
    query = Project.query.filter(Project.id == project_id)
    if not ator.is_admin:
        query = query.filter(project_visibility_criterion(ator))
    return db.session.query(query.exists()).scalar()


def collection_rollups(
    collection_ids: Iterable[int], viewer: User
) -> dict[int, dict[str, int]]:
    """Agregados por coleção em 1 query (independe de N coleções).

    Retorna ``{collection_id: {projetos, etapas_total, etapas_concluidas,
    progresso_pct}}`` contando SÓ projetos visíveis ao viewer; coleção sem
    projeto visível sai zerada. Etapa concluída = ``iniciada AND done`` nas
    etapas de workflow (regra de ``Project.etapas_concluidas``).
    """
    ids = [int(collection_id) for collection_id in collection_ids]
    rollups = {collection_id: _rollup_zerado() for collection_id in ids}
    if not ids:
        return rollups
    for collection_id, projetos, total, concluidas in _rollup_rows(ids, viewer):
        rollups[collection_id] = {
            "projetos": int(projetos),
            "etapas_total": int(total),
            "etapas_concluidas": int(concluidas),
            "progresso_pct": _progresso_pct(int(concluidas), int(total)),
        }
    return rollups


def colecao_project_rows(
    colecao: ProjectCollection, viewer: User
) -> list[dict[str, Any]]:
    """Linhas da página interna da coleção em 2 queries fixas.

    Cada linha traz os campos do projeto + agregados prontos para
    ``serialize_project_collection_row``: etapas x/y, tarefas x/y, datas
    derivadas das etapas e ``atrasado`` (Vigente com etapa de workflow não
    concluída vencida — regra da lista de projetos, ortogonal ao status).
    """
    rows = [_project_row_dict(row) for row in _project_rows(colecao.id, viewer)]
    tarefas = _task_counts_by_project([row["id"] for row in rows])
    for row in rows:
        total, concluidas = tarefas.get(row["id"], (0, 0))
        row["tarefas_total"] = total
        row["tarefas_concluidas"] = concluidas
    return rows


def _rollup_rows(ids: list[int], viewer: User) -> list[Any]:
    etapa_workflow = and_(
        Etapa.project_id == Project.id, Etapa.entry_type != "google_meeting"
    )
    query = (
        db.session.query(
            ProjectCollectionItem.collection_id,
            func.count(func.distinct(Project.id)),
            func.count(Etapa.id),
            _sum_case(and_(Etapa.iniciada.is_(True), Etapa.done.is_(True))),
        )
        .select_from(ProjectCollectionItem)
        .join(Project, Project.id == ProjectCollectionItem.project_id)
        .outerjoin(Etapa, etapa_workflow)
        .filter(ProjectCollectionItem.collection_id.in_(ids))
        .group_by(ProjectCollectionItem.collection_id)
    )
    return _com_visibilidade(query, viewer).all()


def _project_rows(collection_id: int, viewer: User) -> list[Any]:
    workflow = Etapa.entry_type != "google_meeting"
    hoje = datetime.date.today()
    query = (
        db.session.query(
            Project.id,
            Project.titulo,
            Project.status,
            OrgaoUnidade.sigla,
            _sum_case(workflow).label("etapas_total"),
            _sum_case(and_(workflow, Etapa.iniciada.is_(True), Etapa.done.is_(True))),
            _sum_case(and_(workflow, Etapa.done.is_(False), Etapa.data_fim < hoje)),
            # Reunião Google fora do min/max: caso sem else vira NULL, ignorado.
            func.min(case((workflow, Etapa.data_inicio))),
            func.max(case((workflow, Etapa.data_fim))),
        )
        .select_from(ProjectCollectionItem)
        .join(Project, Project.id == ProjectCollectionItem.project_id)
        .outerjoin(OrgaoUnidade, OrgaoUnidade.id == Project.orgao_id)
        .outerjoin(Etapa, Etapa.project_id == Project.id)
        .filter(ProjectCollectionItem.collection_id == collection_id)
        .group_by(
            Project.id,
            Project.titulo,
            Project.status,
            OrgaoUnidade.sigla,
            ProjectCollectionItem.ordem,
        )
        .order_by(ProjectCollectionItem.ordem, Project.id)
    )
    return _com_visibilidade(query, viewer).all()


def _project_row_dict(row: Any) -> dict[str, Any]:
    pid, titulo, status, sigla, total, concluidas, vencidas, inicio, fim = row
    return {
        "id": pid,
        "nome": titulo,
        "orgao_sigla": sigla,
        "status": status,
        "etapas_total": int(total),
        "etapas_concluidas": int(concluidas),
        "atrasado": status == "Vigente" and int(vencidas) > 0,
        "data_inicio": inicio,
        "data_fim": fim,
    }


def _task_counts_by_project(project_ids: list[int]) -> dict[int, tuple[int, int]]:
    """``{project_id: (total, finalizadas)}`` no MESMO critério do Detalhe de
    Projeto (``routes/api/project_detail.py``): não arquivadas, com etapa e sem
    linhas-filha legadas."""
    if not project_ids:
        return {}
    rows = (
        db.session.query(
            Task.project_id,
            func.count(Task.id),
            _sum_case(Task.status == "finalizada"),
        )
        .filter(
            Task.project_id.in_(project_ids),
            Task.is_archived.is_(False),
            Task.etapa_id.isnot(None),
            Task.legacy_parent_task_id.is_(None),
        )
        .group_by(Task.project_id)
        .all()
    )
    return {pid: (int(total), int(done)) for pid, total, done in rows}


def _sum_case(condicao: Any) -> Any:
    return func.coalesce(func.sum(case((condicao, 1), else_=0)), 0)


def _com_visibilidade(query: Any, viewer: User) -> Any:
    if viewer.is_admin:
        return query
    return query.filter(project_visibility_criterion(viewer))


def _rollup_zerado() -> dict[str, int]:
    return {
        "projetos": 0,
        "etapas_total": 0,
        "etapas_concluidas": 0,
        "progresso_pct": 0,
    }


def _progresso_pct(concluidas: int, total: int) -> int:
    if total <= 0:
        return 0
    return round(100 * concluidas / total)


def _bump_updated_at(colecao: ProjectCollection) -> None:
    colecao.updated_at = utc_now()


def _bloquear_favoritos(colecao: ProjectCollection, acao: str) -> None:
    if colecao.tipo != TIPO_COLECAO_FAVORITOS:
        return
    raise ColecaoInvalida(
        f"não é possível {acao} a coleção Favoritos (coleção de sistema)"
    )


def _validar_nome(owner_id: int, nome: Any, *, colecao_id: int | None = None) -> str:
    if not isinstance(nome, str) or not nome.strip():
        raise ColecaoInvalida(f"nome inválido: {nome!r}; esperado texto não vazio")
    nome_limpo = nome.strip()
    if len(nome_limpo) > NOME_MAX_COLECAO:
        raise ColecaoInvalida(
            f"nome com {len(nome_limpo)} caracteres; máximo {NOME_MAX_COLECAO}"
        )
    # Reservado: um custom "Favoritos" quebraria o get-or-create da coleção
    # de sistema (uq_project_collection_owner_nome não distingue tipo).
    if nome_limpo.casefold() == FAVORITOS_NOME.casefold():
        raise ColecaoInvalida(f"nome reservado: {nome_limpo!r}")
    _validar_nome_unico(owner_id, nome_limpo, colecao_id)
    return nome_limpo


def _validar_descricao(descricao: Any) -> str | None:
    if descricao is None:
        return None
    if not isinstance(descricao, str):
        raise ColecaoInvalida(f"descrição inválida: {descricao!r}; esperado texto")
    limpa = descricao.strip()
    if len(limpa) > DESCRICAO_MAX_COLECAO:
        raise ColecaoInvalida(
            f"descrição com {len(limpa)} caracteres; máximo {DESCRICAO_MAX_COLECAO}"
        )
    return limpa or None


def _validar_nome_unico(owner_id: int, nome: str, colecao_id: int | None) -> None:
    query = ProjectCollection.query.filter_by(owner_user_id=owner_id, nome=nome)
    if colecao_id is not None:
        query = query.filter(ProjectCollection.id != colecao_id)
    if db.session.query(query.exists()).scalar():
        raise ColecaoInvalida(f"já existe uma coleção com o nome {nome!r}")


def _validar_icone(icone: Any) -> None:
    if icone in COLLECTION_ICONS:
        return
    esperados = "|".join(sorted(COLLECTION_ICONS))
    raise ColecaoInvalida(f"ícone inválido: {icone!r}; esperado um de {esperados}")


def _validar_cor(cor: Any) -> None:
    if cor in COLLECTION_COLORS:
        return
    esperados = "|".join(sorted(COLLECTION_COLORS))
    raise ColecaoInvalida(
        f"cor inválida: {cor!r}; esperado família da régua ({esperados})"
    )


def _validar_limite_colecoes(owner_id: int) -> None:
    total = ProjectCollection.query.filter_by(
        owner_user_id=owner_id, tipo=TIPO_COLECAO_CUSTOM
    ).count()
    if total >= MAX_COLECOES_CUSTOM:
        raise ColecaoInvalida(
            f"limite de {MAX_COLECOES_CUSTOM} coleções atingido ({total} existentes)"
        )


def _validar_limite_itens(collection_id: int) -> None:
    total = ProjectCollectionItem.query.filter_by(collection_id=collection_id).count()
    if total >= MAX_ITENS_POR_COLECAO:
        raise ColecaoInvalida(
            f"limite de {MAX_ITENS_POR_COLECAO} projetos por coleção atingido"
        )


def _validar_projetos_visiveis(owner: User, project_ids: list[int]) -> list[int]:
    ids_unicos = list(dict.fromkeys(int(pid) for pid in project_ids))
    if len(ids_unicos) > MAX_ITENS_POR_COLECAO:
        raise ColecaoInvalida(
            f"{len(ids_unicos)} projetos informados; máximo {MAX_ITENS_POR_COLECAO}"
        )
    if not ids_unicos:
        return []
    visiveis = _ids_visiveis(owner, ids_unicos)
    invisiveis = [pid for pid in ids_unicos if pid not in visiveis]
    if invisiveis:
        raise ProjetoForaDoEscopo(
            f"projetos inexistentes ou fora do escopo: ids={invisiveis}"
        )
    return ids_unicos


def _ids_visiveis(ator: User, project_ids: list[int]) -> set[int]:
    query = db.session.query(Project.id).filter(Project.id.in_(project_ids))
    if not ator.is_admin:
        query = query.filter(project_visibility_criterion(ator))
    return {pid for (pid,) in query.all()}


def _proxima_ordem(collection_id: int) -> int:
    maior = (
        db.session.query(func.max(ProjectCollectionItem.ordem))
        .filter(ProjectCollectionItem.collection_id == collection_id)
        .scalar()
    )
    return 0 if maior is None else maior + 1
