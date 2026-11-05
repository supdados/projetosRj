"""Regras de domínio das coleções de projetos (Fases 1 e 2 do MVP).

Domínio de ``ProjectCollection``/``ProjectCollectionItem``: criação atômica,
edição/remoção (com bloqueio de Favoritos), itens idempotentes com autoria e
teto de rank, e os rollups agregados em NÚMERO FIXO de queries. O
compartilhamento com aceite (shares, convites, respostas, poda) mora em
``services/collection_shares.py``; a regra de quando um share/item concede
acesso, em ``services/collection_access.py``. Nada de ``request``/``g`` aqui —
o HTTP (gates, envelope, anti-enumeração) fica em ``routes/api/collections.py``.

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
from sqlalchemy.orm import aliased

from catalogs.collection_identity import (
    COLLECTION_COLORS,
    COLLECTION_ICONS,
    FAVORITOS_COLOR,
    FAVORITOS_ICON,
)
from models import (
    Etapa,
    OrgaoUnidade,
    PAPEL_SHARE_EDITOR,
    Project,
    ProjectCollection,
    ProjectCollectionItem,
    Task,
    TIPO_COLECAO_CUSTOM,
    TIPO_COLECAO_FAVORITOS,
    User,
    db,
)
from services.atraso import (
    etapa_em_andamento_criterion,
    etapa_vencida_criterion,
    hoje_utc,
)
from services.authorization import (
    apply_project_visibility,
    area_project_rank,
    invalidate_collection_rank_cache,
)
from services.collection_access import (
    RANK_LEITOR,
    pode_remover_item,
    rank_teto_de_inclusao,
)
from services.collection_curation import exigir_editor_apos_inclusao, reincluir_item

# Erros reexportados: rotas/serializers importam daqui (contrato antigo).
from services.collection_errors import (
    PAPEL_COLECAO_DONO,
    ColecaoInvalida,
    ColecaoSemPermissao,
    ProjetoForaDoEscopo,
    ProjetoSoPorConvite,
    bloquear_favoritos,
)
from services.collection_participation import (
    colecoes_compartilhadas_validas,
    papeis_validos_por_colecao,
)
from services.collection_shares import (
    apagar_shares_da_colecao,
    aplicar_shares_iniciais,
    auditar_item_colecao,
    auditar_item_se_compartilhada,
)
from time_utils import utc_now

MAX_COLECOES_CUSTOM = 20
NOME_MAX_COLECAO = 100
DESCRICAO_MAX_COLECAO = 200
FAVORITOS_NOME = "Favoritos"

BARRA_CONCLUIDA = "concluida"
BARRA_EXECUCAO = "execucao"
BARRA_VENCIDA = "vencida"
BARRA_PREVISTA = "prevista"

_NAO_INFORMADO: Any = object()


def colecao_do_usuario(user_id: int, collection_id: int) -> ProjectCollection | None:
    """Coleção pelo id, SOMENTE se pertence ao usuário (``None`` → 404 na rota)."""
    return ProjectCollection.query.filter_by(
        id=collection_id, owner_user_id=user_id
    ).first()


def listar_colecoes(user_id: int) -> list[tuple[ProjectCollection, str]]:
    """Pares ``(coleção, papel)``: minhas (Favoritos primeiro, custom por
    ``updated_at``) e depois as compartilhadas comigo/meu órgão exato com share
    VÁLIDO (aceito ou legado) — convite pendente fica fora do índice."""
    favoritos = get_or_create_favoritos(user_id)
    custom = (
        ProjectCollection.query.filter_by(
            owner_user_id=user_id, tipo=TIPO_COLECAO_CUSTOM
        )
        .order_by(ProjectCollection.updated_at.desc(), ProjectCollection.id.desc())
        .all()
    )
    minhas = [(colecao, PAPEL_COLECAO_DONO) for colecao in (favoritos, *custom)]
    user = db.session.get(User, user_id)
    compartilhadas = colecoes_compartilhadas_validas(user) if user else []
    return [*minhas, *compartilhadas]


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
    compartilhamentos: list[dict[str, Any]] | None = None,
) -> ProjectCollection:
    """Cria coleção custom + itens + shares iniciais numa única transação.

    ``compartilhamentos`` opcional (default nenhum = "Só eu"): lista de
    ``{"user_id"|"orgao_id": int, "papel": "viewer"|"editor"}`` — cada um nasce
    CONVITE pendente. Itens gravam autoria e teto (rank de área do dono).
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
    # Shares antes dos itens: coleção que NASCE compartilhada audita cada item.
    aplicar_shares_iniciais(colecao, owner, compartilhamentos or [])
    tetos = _tetos_de_inclusao(owner, ids_visiveis)
    for ordem, project_id in enumerate(ids_visiveis):
        db.session.add(
            _novo_item(colecao, project_id, ordem, owner, tetos.get(project_id, 0))
        )
        if compartilhamentos:
            auditar_item_colecao(
                colecao, project_id, "colecao_projeto_adicionado", owner
            )
    # Hoje nada muda para ninguém (item próprio não concede ao dono; share novo
    # é pendente), mas a regra é "toda mutação de item/share invalida": assim
    # ninguém precisa reprovar essa dedução quando a regra de acesso mudar.
    invalidate_collection_rank_cache()
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
    bloquear_favoritos(colecao, "editar")
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
    """Hard-delete da coleção, itens, shares e respostas; projetos ficam intactos."""
    bloquear_favoritos(colecao, "apagar")
    # DELETE explícito de itens, respostas E shares: o ondelete CASCADE do banco
    # não é confiável em SQLite sem PRAGMA foreign_keys, e linha órfã seria
    # herdada pela próxima coleção/share via reuso de rowid (falha aberta).
    ProjectCollectionItem.query.filter_by(collection_id=colecao.id).delete()
    apagar_shares_da_colecao(colecao.id)
    db.session.delete(colecao)
    invalidate_collection_rank_cache()


def adicionar_projeto(
    colecao: ProjectCollection, project_id: int, *, ator: User
) -> bool:
    """Adiciona projeto à coleção; idempotente (``False`` se já estava).

    Ator precisa ser dono ou editor E ver o projeto (anti-escalação). Coleção
    CUSTOM exige visibilidade PRÓPRIA (área/convite): projeto visto só via
    share de outra coleção não pode ser re-semeado — fecharia a revogação.
    O EDITOR (não dono) só inclui o que vê pela ÁREA (ou admin): projeto visto
    só por convite → ``ProjetoSoPorConvite`` (422). O item grava quem incluiu e
    o teto (rank de área do incluidor, até editor); re-incluir o próprio item
    sobe o teto. Favoritos (nunca compartilhável, nunca concede) aceita a
    derivada. Em coleção compartilhada a ação entra na trilha de auditoria.
    """
    papel = _exigir_edicao_de_itens(colecao, ator)
    derivada_ok = colecao.tipo == TIPO_COLECAO_FAVORITOS
    if not projeto_visivel_para(ator, project_id, incluir_derivada=derivada_ok):
        raise ProjetoForaDoEscopo(
            f"projeto inexistente ou fora do escopo: id={project_id}"
        )
    rank_de_area = area_project_rank(ator, db.session.get(Project, project_id))
    _exigir_area_para_editor(colecao, papel, project_id, rank_de_area)
    teto = rank_teto_de_inclusao(rank_de_area)
    ja_existe = ProjectCollectionItem.query.filter_by(
        collection_id=colecao.id, project_id=project_id
    ).first()
    if ja_existe is not None:
        reincluir_item(colecao, ja_existe, ator, teto)
        return False
    ordem = _proxima_ordem(colecao.id)
    db.session.add(_novo_item(colecao, project_id, ordem, ator, teto))
    exigir_editor_apos_inclusao(colecao, ator)
    _bump_updated_at(colecao)
    auditar_item_se_compartilhada(
        colecao, project_id, "colecao_projeto_adicionado", ator
    )
    invalidate_collection_rank_cache()
    return True


def remover_projeto(colecao: ProjectCollection, project_id: int, *, ator: User) -> bool:
    """Remove o par coleção×projeto; ``False`` se não estava na coleção.

    Dono remove qualquer item (inclusive órfão que saiu do próprio escopo).
    Editor só remove o que VÊ (404 anti-enumeração) E que ELE incluiu — item
    alheio ou legado (sem autoria = do dono) → ``ColecaoSemPermissao`` (403).
    """
    papel = _exigir_edicao_de_itens(colecao, ator)
    if papel != PAPEL_COLECAO_DONO and not projeto_visivel_para(ator, project_id):
        raise ProjetoForaDoEscopo(
            f"projeto inexistente ou fora do escopo: id={project_id}"
        )
    item = ProjectCollectionItem.query.filter_by(
        collection_id=colecao.id, project_id=project_id
    ).first()
    if item is None:
        return False
    if not pode_remover_item(papel, item.added_by_user_id, ator.id):
        raise ColecaoSemPermissao(
            f"editor id={ator.id} só remove projetos que incluiu; "
            f"projeto id={project_id} foi incluído por {item.added_by_user_id!r}"
        )
    db.session.delete(item)
    _bump_updated_at(colecao)
    auditar_item_se_compartilhada(colecao, project_id, "colecao_projeto_removido", ator)
    invalidate_collection_rank_cache()
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
    if remover_projeto(favoritos, project_id, ator=user):
        return False
    return adicionar_projeto(favoritos, project_id, ator=user)


def papel_do_usuario(colecao: ProjectCollection, user: User) -> str | None:
    """``"dono"`` | ``"editor"`` | ``"viewer"`` | ``None`` (não vê a coleção).

    Só share VÁLIDO conta (aceito ou legado; convite pendente/recusado/saiu
    não). Share direto e share por órgão de lotação exato acumulam: vence o
    papel MAIS ALTO (editor > viewer). Regra em ``collection_access``.
    """
    if user.id == colecao.owner_user_id:
        return PAPEL_COLECAO_DONO
    # Share de dono soft-deletado não concede nem o acesso à própria coleção.
    dono = db.session.get(User, colecao.owner_user_id)
    if dono is None or dono.deleted_at is not None:
        return None
    return papeis_validos_por_colecao(user, [colecao.id]).get(colecao.id)


def colecao_visivel_para(
    user: User, collection_id: int
) -> tuple[ProjectCollection, str] | None:
    """Coleção + papel quando o usuário a alcança (dono OU share válido).

    ``None`` → 404 anti-enumeração na rota (inclusive para convite pendente:
    quem só foi convidado não vê projetos nem cronograma). Exemplo:
    ``resultado = colecao_visivel_para(g.user, collection_id)``.
    """
    colecao = db.session.get(ProjectCollection, collection_id)
    if colecao is None:
        return None
    papel = papel_do_usuario(colecao, user)
    if papel is None:
        return None
    return colecao, papel


def _novo_item(
    colecao: ProjectCollection,
    project_id: int,
    ordem: int,
    ator: User,
    rank_teto: int,
) -> ProjectCollectionItem:
    return ProjectCollectionItem(
        collection_id=colecao.id,
        project_id=project_id,
        ordem=ordem,
        added_by_user_id=ator.id,
        rank_teto=rank_teto,
    )


def _tetos_de_inclusao(ator: User, project_ids: list[int]) -> dict[int, int]:
    """``{project_id: rank_teto}`` em 1 query (rank de área do ator, até editor)."""
    if not project_ids:
        return {}
    projetos = Project.query.filter(Project.id.in_(project_ids)).all()
    return {
        projeto.id: rank_teto_de_inclusao(area_project_rank(ator, projeto))
        for projeto in projetos
    }


def _exigir_area_para_editor(
    colecao: ProjectCollection, papel: str, project_id: int, rank_de_area: int
) -> None:
    """Editor só inclui o que vê pela área: convite repassado a N pessoas
    contornaria "só gestor convida". Admin passa (rank de área = 100)."""
    if papel == PAPEL_COLECAO_DONO or colecao.tipo != TIPO_COLECAO_CUSTOM:
        return
    if rank_de_area >= RANK_LEITOR:
        return
    raise ProjetoSoPorConvite(
        f"o projeto id={project_id} só é visível para você por convite; "
        "editores só incluem projetos que veem pela própria área"
    )


def _exigir_edicao_de_itens(colecao: ProjectCollection, ator: User) -> str:
    papel = papel_do_usuario(colecao, ator)
    if papel in (PAPEL_COLECAO_DONO, PAPEL_SHARE_EDITOR):
        return papel
    raise ColecaoSemPermissao(
        f"papel {papel!r} não permite alterar projetos da coleção id={colecao.id}"
    )


def projeto_visivel_para(
    ator: User, project_id: int, *, incluir_derivada: bool = True
) -> bool:
    """True se o projeto existe E está no escopo do ator (admin vê tudo).

    ``incluir_derivada=False`` ignora a visibilidade que vem de share de
    coleção — exigência das mutações de coleção CUSTOM (anti re-share).
    """
    query = apply_project_visibility(
        Project.query.filter(Project.id == project_id),
        ator,
        include_collections=incluir_derivada,
    )
    return db.session.query(query.exists()).scalar()


def collection_rollups(
    collection_ids: Iterable[int], viewer: User
) -> dict[int, dict[str, int]]:
    """Agregados por coleção em 1 query (independe de N coleções).

    Retorna ``{collection_id: {projetos, etapas_total, etapas_concluidas,
    etapas_em_andamento, etapas_atrasadas, progresso_pct}}`` contando SÓ
    projetos visíveis ao viewer; coleção sem projeto visível sai zerada. Etapa
    concluída = ``iniciada AND done`` nas etapas de workflow (regra de
    ``Project.etapas_concluidas``); atrasada e em andamento seguem
    ``services.atraso`` (excludentes entre si e com concluída). As não
    iniciadas são o resto — a barra da capa do card as deriva do total.
    """
    ids = [int(collection_id) for collection_id in collection_ids]
    rollups = {collection_id: _rollup_zerado() for collection_id in ids}
    if not ids:
        return rollups
    for row in _rollup_rows(ids, viewer):
        collection_id, projetos, total, concluidas, em_andamento, atrasadas = row
        rollups[collection_id] = {
            "projetos": int(projetos),
            "etapas_total": int(total),
            "etapas_concluidas": int(concluidas),
            "etapas_em_andamento": int(em_andamento),
            "etapas_atrasadas": int(atrasadas),
            "progresso_pct": _progresso_pct(int(concluidas), int(total)),
        }
    return rollups


def colecao_project_rows(
    colecao: ProjectCollection, viewer: User, *, papel: str | None = None
) -> list[dict[str, Any]]:
    """Linhas da página interna da coleção em 2 queries fixas.

    Cada linha traz os campos do projeto + agregados prontos para
    ``serialize_project_collection_row``: etapas x/y, tarefas x/y, datas
    derivadas das etapas, ``atrasado`` (Vigente com etapa de workflow não
    concluída vencida — regra da lista de projetos, ortogonal ao status),
    ``adicionado_por`` (``{id, name}`` ou ``None`` em item legado) e
    ``pode_remover`` (dono: tudo; editor: só o que incluiu). ``papel`` evita
    recalcular o papel do viewer quando a rota já o tem.
    """
    if papel is None:
        papel = papel_do_usuario(colecao, viewer)
    rows = [
        _project_row_dict(row, papel, viewer.id)
        for row in _project_rows(colecao.id, viewer)
    ]
    tarefas = _task_counts_by_project([row["id"] for row in rows])
    for row in rows:
        total, concluidas = tarefas.get(row["id"], (0, 0))
        row["tarefas_total"] = total
        row["tarefas_concluidas"] = concluidas
    return rows


def colecao_cronograma_rows(
    colecao: ProjectCollection, viewer: User
) -> list[dict[str, Any]]:
    """Linhas do Gantt da coleção (tela 3c) em 2 queries fixas.

    Um item por projeto VISÍVEL ao viewer, na ordem da coleção, com as etapas de
    workflow datadas e a faixa (``barra``) já classificada. Etapa sem nenhuma
    data não vira barra: entra só no contador ``sem_data`` do projeto. Exemplo:
    ``linhas = colecao_cronograma_rows(colecao, g.user)``.
    """
    projetos = [
        _cronograma_projeto_dict(row)
        for row in _cronograma_project_rows(colecao.id, viewer)
    ]
    por_id = {projeto["id"]: projeto for projeto in projetos}
    # hoje_utc(): mesmo relógio UTC do critério de atraso, não o do processo.
    hoje = hoje_utc()
    for etapa in _cronograma_etapas(list(por_id)):
        _acumular_etapa_no_cronograma(por_id[etapa.project_id], etapa, hoje)
    return projetos


def _cronograma_projeto_dict(row: Any) -> dict[str, Any]:
    project_id, titulo, sigla = row
    return {
        "id": project_id,
        "nome": titulo,
        "orgao_sigla": sigla,
        "sem_data": 0,
        "etapas": [],
    }


def _acumular_etapa_no_cronograma(
    projeto: dict[str, Any], etapa: Etapa, hoje: datetime.date
) -> None:
    if etapa.data_inicio is None and etapa.data_fim is None:
        projeto["sem_data"] += 1
        return
    projeto["etapas"].append(
        {
            "id": etapa.id,
            "nome": etapa.descricao,
            "data_inicio": etapa.data_inicio,
            "data_fim": etapa.data_fim,
            "barra": _classificar_barra(etapa, hoje),
        }
    )


def _classificar_barra(etapa: Etapa, hoje: datetime.date) -> str:
    """Faixa da barra: concluída > vencida > em execução > prevista."""
    if etapa.iniciada and etapa.done:
        return BARRA_CONCLUIDA
    if etapa.data_fim is not None and etapa.data_fim < hoje:
        return BARRA_VENCIDA
    # Fim no futuro (ou ausente) já garantido acima; basta o início ter chegado.
    if etapa.data_inicio is not None and etapa.data_inicio <= hoje:
        return BARRA_EXECUCAO
    return BARRA_PREVISTA


def _cronograma_project_rows(collection_id: int, viewer: User) -> list[Any]:
    query = (
        db.session.query(Project.id, Project.titulo, OrgaoUnidade.sigla)
        .select_from(ProjectCollectionItem)
        .join(Project, Project.id == ProjectCollectionItem.project_id)
        .outerjoin(OrgaoUnidade, OrgaoUnidade.id == Project.orgao_id)
        .filter(ProjectCollectionItem.collection_id == collection_id)
        .order_by(ProjectCollectionItem.ordem, Project.id)
    )
    return _com_visibilidade(query, viewer).all()


def _cronograma_etapas(project_ids: list[int]) -> list[Etapa]:
    if not project_ids:
        return []
    return (
        Etapa.query.filter(
            Etapa.project_id.in_(project_ids),
            Etapa.entry_type != "google_meeting",
        )
        .order_by(Etapa.project_id, Etapa.ordem, Etapa.id)
        .all()
    )


def _rollup_rows(ids: list[int], viewer: User) -> list[Any]:
    etapa_workflow = and_(
        Etapa.project_id == Project.id, Etapa.entry_type != "google_meeting"
    )
    # Um relógio só para as duas faixas: atraso e andamento não podem divergir.
    hoje = hoje_utc()
    query = (
        db.session.query(
            ProjectCollectionItem.collection_id,
            func.count(func.distinct(Project.id)),
            func.count(Etapa.id),
            _sum_case(and_(Etapa.iniciada.is_(True), Etapa.done.is_(True))),
            _sum_case(etapa_em_andamento_criterion(hoje)),
            _sum_case(etapa_vencida_criterion(hoje)),
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
    incluidor = aliased(User)
    query = (
        db.session.query(
            Project.id,
            Project.titulo,
            Project.status,
            OrgaoUnidade.sigla,
            _sum_case(workflow).label("etapas_total"),
            _sum_case(and_(workflow, Etapa.iniciada.is_(True), Etapa.done.is_(True))),
            _sum_case(etapa_vencida_criterion()),
            # Reunião Google fora do min/max: caso sem else vira NULL, ignorado.
            func.min(case((workflow, Etapa.data_inicio))),
            func.max(case((workflow, Etapa.data_fim))),
            ProjectCollectionItem.added_by_user_id,
            incluidor.name,
        )
        .select_from(ProjectCollectionItem)
        .join(Project, Project.id == ProjectCollectionItem.project_id)
        .outerjoin(OrgaoUnidade, OrgaoUnidade.id == Project.orgao_id)
        .outerjoin(Etapa, Etapa.project_id == Project.id)
        .outerjoin(incluidor, incluidor.id == ProjectCollectionItem.added_by_user_id)
        .filter(ProjectCollectionItem.collection_id == collection_id)
        .group_by(
            Project.id,
            Project.titulo,
            Project.status,
            OrgaoUnidade.sigla,
            ProjectCollectionItem.ordem,
            ProjectCollectionItem.added_by_user_id,
            incluidor.name,
        )
        .order_by(ProjectCollectionItem.ordem, Project.id)
    )
    return _com_visibilidade(query, viewer).all()


def _project_row_dict(row: Any, papel: str | None, viewer_id: int) -> dict[str, Any]:
    pid, titulo, status, sigla, total, concluidas, vencidas, inicio, fim = row[:9]
    added_by_id, added_by_nome = row[9:]
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
        "adicionado_por": (
            None if added_by_id is None else {"id": added_by_id, "name": added_by_nome}
        ),
        "pode_remover": pode_remover_item(papel, added_by_id, viewer_id),
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
    return apply_project_visibility(query, viewer)


def _rollup_zerado() -> dict[str, int]:
    return {
        "projetos": 0,
        "etapas_total": 0,
        "etapas_concluidas": 0,
        "etapas_em_andamento": 0,
        "etapas_atrasadas": 0,
        "progresso_pct": 0,
    }


def _progresso_pct(concluidas: int, total: int) -> int:
    if total <= 0:
        return 0
    return round(100 * concluidas / total)


def _bump_updated_at(colecao: ProjectCollection) -> None:
    colecao.updated_at = utc_now()


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


def _validar_projetos_visiveis(owner: User, project_ids: list[int]) -> list[int]:
    ids_unicos = list(dict.fromkeys(int(pid) for pid in project_ids))
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
    # Coleção custom nasce só com visibilidade própria (anti re-share).
    query = apply_project_visibility(
        db.session.query(Project.id).filter(Project.id.in_(project_ids)),
        ator,
        include_collections=False,
    )
    return {pid for (pid,) in query.all()}


def _proxima_ordem(collection_id: int) -> int:
    maior = (
        db.session.query(func.max(ProjectCollectionItem.ordem))
        .filter(ProjectCollectionItem.collection_id == collection_id)
        .scalar()
    )
    return 0 if maior is None else maior + 1
