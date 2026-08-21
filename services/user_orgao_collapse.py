"""Colapso dos vínculos redundantes de ``user_orgao`` (migração pré-produção).

O banco legado guarda os vínculos como lista plana de áreas: um usuário da SETD
carrega as 14 áreas da secretaria. Com a hierarquia SIORG e a herança
descendente de ``services.authorization`` (o rank de um vínculo se propaga para
a subárvore), quase toda linha virou ruído.

O colapso tem DUAS etapas, nesta ordem:

1. PODA — cai todo vínculo em área guarda-chuva (``SIGLAS_GENERICAS``), que na
   hierarquia nova daria o estado inteiro. A poda TIRA acesso de propósito: o
   relatório enumera nó a nó. Exceção: o usuário cujo ÚNICO vínculo é genérico
   (podar zeraria o ``role_map`` dele) fica como está e entra em
   ``preservados_por_esvaziamento``.
2. ABSORÇÃO — do que sobrou, cai o vínculo que tem ancestral vinculado de rank
   maior ou igual. Rank-aware: ``gestor`` no filho não é absorvido por
   ``leitor`` no pai, senão o colapso rebaixaria o usuário.

Fora da poda, o ``role_map`` sai bit a bit igual — é isso que
``snapshot_role_maps`` permite conferir antes de aplicar em produção.

Com ``dry_run=False`` o colapso congela ``user_orgao`` em
``legacy_user_orgao_pre_colapso`` ANTES do primeiro DELETE: é o único caminho de
volta (a poda é irreversível) e é a marca que faz o backfill abortar em vez de
recriar os vínculos podados.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from flask import g, has_request_context
from sqlalchemy import inspect, text

from models import OrgaoClosure, OrgaoUnidade, Project, User, UserOrgao, db
from services.authorization import (
    PAPEL_GESTOR,
    PAPEL_RANK,
    ROLE_MAP_CACHE_ATTR,
    get_user_orgao_role_map,
)

# Áreas guarda-chuva: vínculo nelas não sobrevive ao colapso. Decisão do
# usuário (ago/2026) — "são áreas genéricas que muita gente tinha, mas dentro
# da hierarquia agora não faz sentido".
SIGLAS_GENERICAS: frozenset[str] = frozenset({"GOVRJ", "SETD", "PRODERJ"})


class ClosureNaoConstruidaError(RuntimeError):
    """``orgao_closure`` vazia/stale numa árvore com filhos — colapso abortado."""


@dataclass(frozen=True)
class BackupPreColapso:
    """Espelho de ``user_orgao`` congelado antes da poda.

    ``reaproveitado``: a tabela já existia e NÃO foi sobrescrita.
    """

    tabela: str
    linhas: int
    reaproveitado: bool


@dataclass(frozen=True)
class Absorcao:
    """Par ancestral -> descendente que justificou remover um vínculo."""

    descendente_id: int
    ancestral_id: int
    rank_descendente: int
    rank_ancestral: int


@dataclass(frozen=True)
class ResultadoColapso:
    """Destino de cada vínculo de UM usuário, já separado por motivo."""

    mantidos: tuple[int, ...]
    podados: tuple[int, ...]
    absorvidos: tuple[Absorcao, ...]
    preservado_por_esvaziamento: bool = False

    @property
    def removidos(self) -> tuple[int, ...]:
        """IDs de órgão que perdem a linha em ``user_orgao`` (poda + absorção)."""
        absorvidos = (item.descendente_id for item in self.absorvidos)
        return tuple(sorted({*self.podados, *absorvidos}))


@dataclass(frozen=True)
class ColapsoUsuario:
    """Linha do relatório: o que um usuário perde e o que sobra para ele."""

    user_id: int
    username: str
    mantidos: tuple[int, ...]
    podados: tuple[int, ...]
    absorvidos: tuple[Absorcao, ...]
    role_map_perdido: dict[int, int]
    role_map_rebaixado: dict[int, tuple[int, int]]
    preservado_por_esvaziamento: bool

    @property
    def mudou(self) -> bool:
        return bool(self.podados or self.absorvidos)


@dataclass(frozen=True)
class RelatorioColapso:
    """Resultado global de ``aplicar_colapso``, para revisão antes de produção."""

    dry_run: bool
    vinculos_antes: int
    vinculos_removidos: int
    vinculos_depois: int
    usuarios: tuple[ColapsoUsuario, ...]
    role_map_antes: dict[int, dict[int, int]]
    role_map_depois: dict[int, dict[int, int]]
    projetos_orfaos: tuple[tuple[int, str, str], ...]
    # Campo, não property: o orquestrador serializa o relatório com
    # ``dataclasses.asdict``, que ignora property — e o runbook (9.6) promete
    # esta chave no JSON.
    preservados_por_esvaziamento: tuple[ColapsoUsuario, ...]
    backup_pre_colapso: BackupPreColapso | None
    resumo: tuple[str, ...]

    @property
    def usuarios_afetados(self) -> tuple[ColapsoUsuario, ...]:
        return tuple(item for item in self.usuarios if item.mudou)

    @property
    def usuarios_com_perda_de_acesso(self) -> tuple[ColapsoUsuario, ...]:
        return tuple(
            item
            for item in self.usuarios
            if item.role_map_perdido or item.role_map_rebaixado
        )


def calcular_colapso(
    ranks: dict[int, int],
    ancestrais: dict[int, set[int]],
    genericos: set[int],
) -> ResultadoColapso:
    """Decide o destino dos vínculos de um usuário. Função pura, sem banco.

    ``ranks`` é ``{orgao_id: rank}`` dos vínculos diretos, ``ancestrais`` é
    ``{orgao_id: ancestrais próprios}`` (pode cobrir órgãos de outros usuários)
    e ``genericos`` são os ids das áreas guarda-chuva.

    Se a poda esvaziaria o usuário (só tinha área genérica), ela não acontece:
    zerar ``user_orgao`` zera o ``role_map`` e o usuário loga sem ver nada.

    Exemplo::

        calcular_colapso({1: 30, 2: 30}, {2: {1}}, set()).mantidos  # (1,)
    """
    nao_genericos = {oid: rank for oid, rank in ranks.items() if oid not in genericos}
    preservado = bool(ranks) and not nao_genericos
    sobreviventes = dict(ranks) if preservado else nao_genericos
    podados = () if preservado else tuple(sorted(set(ranks) - set(sobreviventes)))
    absorvidos = _absorcoes(sobreviventes, ancestrais)
    removidos = {item.descendente_id for item in absorvidos}
    mantidos = tuple(oid for oid in sorted(sobreviventes) if oid not in removidos)
    return ResultadoColapso(
        mantidos=mantidos,
        podados=podados,
        absorvidos=absorvidos,
        preservado_por_esvaziamento=preservado,
    )


def _absorcoes(
    sobreviventes: dict[int, int], ancestrais: dict[int, set[int]]
) -> tuple[Absorcao, ...]:
    candidatas = (
        _absorcao_de(oid, sobreviventes, ancestrais) for oid in sorted(sobreviventes)
    )
    return tuple(item for item in candidatas if item is not None)


def _absorcao_de(
    descendente_id: int,
    sobreviventes: dict[int, int],
    ancestrais: dict[int, set[int]],
) -> Absorcao | None:
    """Ancestral vinculado de rank >= que torna o vínculo do descendente redundante."""
    rank = sobreviventes[descendente_id]
    elegiveis = [
        oid
        for oid in ancestrais.get(descendente_id, ())
        if sobreviventes.get(oid, -1) >= rank
    ]
    if not elegiveis:
        return None
    # Maior rank vence; empate pelo menor id, só para o relatório ser estável.
    melhor = max(elegiveis, key=lambda oid: (sobreviventes[oid], -oid))
    return Absorcao(descendente_id, melhor, rank, sobreviventes[melhor])


def rank_do_papel(papel: str | None) -> int:
    """Rank de um papel de vínculo; ausente ou desconhecido vale ``gestor``.

    Espelha ``services/authorization.py::_vinculo_rank`` — o papel nulo das
    linhas legadas sempre valeu gestor. Ex.: ``rank_do_papel(None)  # 30``.
    """
    return PAPEL_RANK.get(papel or PAPEL_GESTOR, PAPEL_RANK[PAPEL_GESTOR])


def snapshot_role_maps() -> dict[int, dict[int, int]]:
    """``{user_id: {orgao_id: rank}}`` de todos os usuários, serializável em JSON.

    Reusa ``get_user_orgao_role_map``: é exatamente o mapa que o colapso precisa
    preservar, então comparar contra uma reimplementação não provaria nada.

    Exemplo: ``json.dumps(snapshot_role_maps())``.
    """
    usuarios = User.query.order_by(User.id).all()
    return {user.id: dict(get_user_orgao_role_map(user)) for user in usuarios}


def aplicar_colapso(*, dry_run: bool = True) -> RelatorioColapso:
    """Poda + absorve os vínculos de todos os usuários e relata o delta.

    Com ``dry_run=True`` (default) o cálculo roda dentro da transação e ela é
    revertida no fim — o que também descarta qualquer alteração pendente na
    sessão do chamador.

    Levanta ``ClosureNaoConstruidaError`` se a closure não estiver construída —
    sem ela a absorção não roda mas a poda rodaria, e poda é irreversível.

    Exemplo: ``aplicar_colapso(dry_run=True).usuarios_com_perda_de_acesso``.
    """
    _exigir_closure_construida()
    vinculos = _vinculos_por_usuario()
    resultados = _calcular_por_usuario(vinculos)
    antes = snapshot_role_maps()
    backup = _gravar_backup_pre_colapso(dry_run=dry_run)
    for user_id, resultado in resultados.items():
        _remover_vinculos(vinculos[user_id], resultado)
    db.session.flush()
    _descartar_caches_de_role_map()
    depois = snapshot_role_maps()
    orfaos = projetos_orfaos_por_poda()
    _encerrar(dry_run=dry_run)
    return _montar_relatorio(
        vinculos, resultados, antes, depois, orfaos, backup, dry_run=dry_run
    )


def _gravar_backup_pre_colapso(*, dry_run: bool) -> BackupPreColapso | None:
    """Congela ``user_orgao`` antes do primeiro DELETE; em dry-run não grava.

    Backup existente NÃO é sobrescrito — o mais antigo é o que guarda o estado
    pré-poda, e o ``--all --apply`` repetido não pode degradá-lo.
    Ex.: ``_gravar_backup_pre_colapso(dry_run=False).linhas  # 208``.
    """
    if dry_run:
        return None
    # Import local: o helper mora no script de backfill (que lê a mesma tabela
    # como marca de "colapso já rodou"); no topo, o boot da app puxaria o script.
    from scripts.migrations.backfill_orgaos import (
        TABELA_PRE_COLAPSO,
        snapshot_user_orgao_pre_colapso,
    )

    ja_existia = _linhas_do_backup(TABELA_PRE_COLAPSO) > 0
    snapshot_user_orgao_pre_colapso()
    return BackupPreColapso(
        tabela=TABELA_PRE_COLAPSO,
        linhas=_linhas_do_backup(TABELA_PRE_COLAPSO),
        reaproveitado=ja_existia,
    )


def _linhas_do_backup(tabela: str) -> int:
    """Linhas do espelho pré-colapso; 0 quando a tabela ainda não existe."""
    if not inspect(db.engine).has_table(tabela):
        return 0
    total = db.session.execute(text(f"SELECT COUNT(*) FROM {tabela}")).scalar()
    return int(total or 0)


def _exigir_closure_construida() -> None:
    """Aborta antes da poda quando ``orgao_closure`` não reflete a hierarquia."""
    filhos = (
        db.session.query(OrgaoUnidade.id)
        .filter(OrgaoUnidade.pai_id.isnot(None))
        .count()
    )
    if not filhos or _tem_closure_profunda():
        return
    raise ClosureNaoConstruidaError(
        f"orgao_closure tem 0 linhas com depth > 0, mas orgao_unidade tem {filhos} "
        "unidades com pai_id preenchido: a absorção não aconteceria e a poda, que "
        "é irreversível, sim. Rode services.orgao_tree.rebuild_orgao_closure() "
        "antes de aplicar_colapso()."
    )


def _tem_closure_profunda() -> bool:
    linha = (
        db.session.query(OrgaoClosure.descendant_id)
        .filter(OrgaoClosure.depth > 0)
        .first()
    )
    return linha is not None


def projetos_orfaos_por_poda() -> list[tuple[int, str, str]]:
    """``[(project_id, titulo, sigla)]`` que nenhum usuário não-admin alcança.

    Lê o estado atual de ``user_orgao``; chamada dentro de ``aplicar_colapso``
    depois do flush, já reflete a poda. Só DETECTA — remanejar o projeto ou
    criar vínculo nominal é decisão do operador.

    Exemplo: ``projetos_orfaos_por_poda()  # [(12, 'Portal', 'SETD')]``.
    """
    alcancados = _orgaos_alcancados_por_nao_admins()
    linhas = (
        db.session.query(
            Project.id, Project.titulo, OrgaoUnidade.sigla, Project.orgao_id
        )
        .join(OrgaoUnidade, OrgaoUnidade.id == Project.orgao_id)
        .order_by(Project.id)
        .all()
    )
    return [
        (project_id, titulo or "", sigla or "")
        for project_id, titulo, sigla, orgao_id in linhas
        if orgao_id not in alcancados
    ]


def _orgaos_alcancados_por_nao_admins() -> set[int]:
    """União dos ``role_map`` dos não-admins ativos; admin vê tudo e não conta."""
    usuarios = User.query.filter(User.deleted_at.is_(None)).order_by(User.id).all()
    alcancados: set[int] = set()
    for user in usuarios:
        if getattr(user, "is_admin", False):
            continue
        alcancados.update(get_user_orgao_role_map(user))
    return alcancados


def _calcular_por_usuario(
    vinculos: dict[int, list[UserOrgao]],
) -> dict[int, ResultadoColapso]:
    genericos = _ids_de_siglas_genericas()
    ancestrais = _ancestrais_por_orgao(
        {linha.orgao_id for linhas in vinculos.values() for linha in linhas}
    )
    return {
        user_id: calcular_colapso(_ranks_dos_vinculos(linhas), ancestrais, genericos)
        for user_id, linhas in vinculos.items()
    }


def _vinculos_por_usuario() -> dict[int, list[UserOrgao]]:
    vinculos: dict[int, list[UserOrgao]] = {}
    linhas = UserOrgao.query.order_by(UserOrgao.user_id, UserOrgao.orgao_id).all()
    for linha in linhas:
        vinculos.setdefault(linha.user_id, []).append(linha)
    return vinculos


def _ranks_dos_vinculos(linhas: list[UserOrgao]) -> dict[int, int]:
    """``{orgao_id: rank}``; linha duplicada no mesmo órgão resolve por ``max()``."""
    ranks: dict[int, int] = {}
    for linha in linhas:
        rank = rank_do_papel(getattr(linha, "papel", None))
        ranks[linha.orgao_id] = max(ranks.get(linha.orgao_id, 0), rank)
    return ranks


def _ids_de_siglas_genericas() -> set[int]:
    """IDs das áreas guarda-chuva; normaliza em Python, nunca em SQL.

    A colação ``utf8mb4_0900_ai_ci`` do MySQL é case e accent insensitive, então
    comparar sigla no banco daria resultado diferente do SQLite de dev.
    """
    linhas = db.session.query(OrgaoUnidade.id, OrgaoUnidade.sigla).all()
    return {
        orgao_id
        for orgao_id, sigla in linhas
        if (sigla or "").strip().upper() in SIGLAS_GENERICAS
    }


def _ancestrais_por_orgao(orgao_ids: set[int]) -> dict[int, set[int]]:
    """``{orgao_id: ancestrais próprios}`` em UMA query de closure (depth > 0)."""
    if not orgao_ids:
        return {}
    linhas = (
        db.session.query(OrgaoClosure.descendant_id, OrgaoClosure.ancestor_id)
        .filter(OrgaoClosure.descendant_id.in_(orgao_ids), OrgaoClosure.depth > 0)
        .all()
    )
    ancestrais: dict[int, set[int]] = {}
    for descendant_id, ancestor_id in linhas:
        ancestrais.setdefault(descendant_id, set()).add(ancestor_id)
    return ancestrais


def _remover_vinculos(linhas: list[UserOrgao], resultado: ResultadoColapso) -> None:
    """Remove pelo ORM: ``DELETE ... IN (SELECT da mesma tabela)`` é 1093 no MySQL."""
    alvos = set(resultado.removidos)
    for linha in linhas:
        if linha.orgao_id in alvos:
            db.session.delete(linha)


def _descartar_caches_de_role_map() -> None:
    # O cache por request (TR-3) foi populado pelo snapshot "antes"; sem
    # descartar, o snapshot "depois" devolveria o mapa velho.
    db.session.expire_all()
    if has_request_context() and hasattr(g, ROLE_MAP_CACHE_ATTR):
        delattr(g, ROLE_MAP_CACHE_ATTR)


def _encerrar(*, dry_run: bool) -> None:
    if dry_run:
        db.session.rollback()
        return
    db.session.commit()


def _montar_relatorio(
    vinculos: dict[int, list[UserOrgao]],
    resultados: dict[int, ResultadoColapso],
    antes: dict[int, dict[int, int]],
    depois: dict[int, dict[int, int]],
    projetos_orfaos: list[tuple[int, str, str]],
    backup: BackupPreColapso | None,
    *,
    dry_run: bool,
) -> RelatorioColapso:
    usernames = _usernames()
    usuarios = tuple(
        _linha_do_relatorio(user_id, resultado, usernames, antes, depois)
        for user_id, resultado in sorted(resultados.items())
    )
    total_antes = sum(len(linhas) for linhas in vinculos.values())
    removidos = sum(len(item.removidos) for item in resultados.values())
    preservados = tuple(item for item in usuarios if item.preservado_por_esvaziamento)
    relatorio = RelatorioColapso(
        dry_run=dry_run,
        vinculos_antes=total_antes,
        vinculos_removidos=removidos,
        vinculos_depois=total_antes - removidos,
        usuarios=usuarios,
        role_map_antes=antes,
        role_map_depois=depois,
        projetos_orfaos=tuple(projetos_orfaos),
        preservados_por_esvaziamento=preservados,
        backup_pre_colapso=backup,
        resumo=(),
    )
    return replace(relatorio, resumo=_resumo(relatorio))


def _resumo(relatorio: RelatorioColapso) -> tuple[str, ...]:
    """Linhas prontas para leitura humana: o que o operador precisa conferir.

    O relatório inteiro passa de 40 KB — sem este bloco os preservados e os
    projetos órfãos só aparecem filtrando o JSON à mão.
    """
    perda = [item.username for item in relatorio.usuarios_com_perda_de_acesso]
    preservados = [item.username for item in relatorio.preservados_por_esvaziamento]
    orfaos = [f"#{i} {t} [{s}]" for i, t, s in relatorio.projetos_orfaos]
    return (
        f"vinculos: {relatorio.vinculos_antes} -> {relatorio.vinculos_depois} "
        f"({relatorio.vinculos_removidos} removidos)",
        f"usuarios afetados: {len(relatorio.usuarios_afetados)}",
        f"perda de alcance: {_lista(perda)}",
        f"preservados por esvaziamento: {_lista(preservados)}",
        f"projetos orfaos: {_lista(orfaos)}",
        f"backup pre-colapso: {_backup(relatorio.backup_pre_colapso)}",
    )


def _lista(itens: list[str]) -> str:
    """``2 (proderj, ramon)``, ou ``0`` quando não há nada a mostrar."""
    return f"{len(itens)} ({', '.join(itens)})" if itens else "0"


def _backup(backup: BackupPreColapso | None) -> str:
    if backup is None:
        return "nao gravado (dry-run)"
    origem = "reaproveitado de execucao anterior" if backup.reaproveitado else "gravado"
    return f"{backup.tabela} com {backup.linhas} linhas ({origem})"


def _linha_do_relatorio(
    user_id: int,
    resultado: ResultadoColapso,
    usernames: dict[int, str],
    antes: dict[int, dict[int, int]],
    depois: dict[int, dict[int, int]],
) -> ColapsoUsuario:
    perdido, rebaixado = _delta_role_map(
        antes.get(user_id, {}), depois.get(user_id, {})
    )
    return ColapsoUsuario(
        user_id=user_id,
        username=usernames.get(user_id, ""),
        mantidos=resultado.mantidos,
        podados=resultado.podados,
        absorvidos=resultado.absorvidos,
        role_map_perdido=perdido,
        role_map_rebaixado=rebaixado,
        preservado_por_esvaziamento=resultado.preservado_por_esvaziamento,
    )


def _delta_role_map(
    antes: dict[int, int], depois: dict[int, int]
) -> tuple[dict[int, int], dict[int, tuple[int, int]]]:
    """Nós que sumiram do alcance e nós que continuaram com rank menor."""
    perdido = {oid: rank for oid, rank in antes.items() if oid not in depois}
    rebaixado = {
        oid: (rank, depois[oid])
        for oid, rank in antes.items()
        if oid in depois and depois[oid] < rank
    }
    return perdido, rebaixado


def _usernames() -> dict[int, str]:
    linhas = db.session.query(User.id, User.username).all()
    return {user_id: username or "" for user_id, username in linhas}
