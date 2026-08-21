"""Auditoria do colapso de vínculos: o veredito é reexecutar e comparar.

O orquestrador (``scripts/migrations/migrar_producao_v5.py``) entrega os role
maps e os vínculos de antes e de depois; aqui se lê a árvore, se recalcula o
colapso a partir da linha de base e se dá o veredito.

O veredito é uma IGUALDADE, não um julgamento: ``calcular_colapso`` roda de
novo sobre ``vinculos_pre`` e o KEEP esperado tem que bater par a par
``(user_id, orgao_id, papel)`` com o conteúdo real de ``user_orgao``. O critério
antigo ("perda explicada pela subárvore do genérico podado") tinha ponto cego —
para quem teve genérico podado, QUALQUER perda dentro daquela subárvore passava,
inclusive um vínculo apagado à mão. A perda de alcance por usuário continua
sendo calculada e impressa, mas como INFORMAÇÃO.

Uso::

    conferencia = conferir_keep(esperado, pares_de_vinculo(vinculos_pos))
    auditoria = auditar(estado, conferencia)
    auditoria.aprovada  # False se o KEEP divergiu ou se alguém ficou zerado
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable, Iterable, Mapping, Protocol, Sequence

from sqlalchemy import text

from models import db

RoleMaps = Mapping[int, Mapping[int, int]]
Descendentes = Mapping[int, set[int]]
Ancestrais = Mapping[int, set[int]]

# Um vínculo de `user_orgao` como chave de comparação.
ParVinculo = tuple[int, int, str]
Vinculos = Mapping[int, Sequence[tuple[int, str]]]

# Divergência é falha; listar mil pares no stdout só esconde as primeiras.
LIMITE_DE_PARES_LISTADOS = 20


class ResultadoComMantidos(Protocol):
    """O que a auditoria usa de ``ResultadoColapso``: os vínculos que ficam."""

    @property
    def mantidos(self) -> tuple[int, ...]: ...


CalcularColapso = Callable[[dict[int, int], Ancestrais, set[int]], ResultadoComMantidos]
RankDoPapel = Callable[[str], int]


@dataclass(frozen=True)
class EstadoColapso:
    """Fotografia antes/depois do colapso, já lida do banco e do relatório."""

    role_map_pre: RoleMaps
    role_map_pos: RoleMaps
    vinculos_pre: Vinculos
    vinculos_pos: Vinculos
    genericos: frozenset[int]
    descendentes: Descendentes
    ancestrais: Ancestrais
    usernames: Mapping[int, str]


@dataclass(frozen=True)
class PerdaDeUsuario:
    """Quanto alcance um usuário perdeu e quanto disso a poda explica."""

    user_id: int
    username: str
    perdidos: int
    explicados_pela_poda: int
    nao_explicados: tuple[int, ...]


@dataclass(frozen=True)
class UsuarioZerado:
    """Usuário que tinha acesso antes do colapso e ficou sem nada depois."""

    user_id: int
    username: str
    vinculos_antes: int


@dataclass(frozen=True)
class ConferenciaKeep:
    """Igualdade par a par entre o KEEP recalculado e o ``user_orgao`` real."""

    faltando: tuple[ParVinculo, ...]
    sobrando: tuple[ParVinculo, ...]

    @property
    def aprovada(self) -> bool:
        return not (self.faltando or self.sobrando)

    def linhas(self, usernames: Mapping[int, str]) -> list[str]:
        divergentes = [
            *(("FALTANDO em user_orgao", par) for par in self.faltando),
            *(("SOBRANDO em user_orgao", par) for par in self.sobrando),
        ]
        linhas = [
            _linha_de_par(rotulo, par, usernames)
            for rotulo, par in divergentes[:LIMITE_DE_PARES_LISTADOS]
        ]
        restantes = len(divergentes) - len(linhas)
        if restantes:
            linhas.append(f"[FALHA] ... e mais {restantes} par(es) divergente(s)")
        return linhas


@dataclass(frozen=True)
class AuditoriaColapso:
    """Veredito do stage ``verificar_role_map``."""

    perdas: tuple[PerdaDeUsuario, ...]
    sem_nenhum_vinculo: tuple[UsuarioZerado, ...]
    sem_nenhum_alcance: tuple[UsuarioZerado, ...]
    conferencia: ConferenciaKeep
    usernames: Mapping[int, str]

    @property
    def perdas_nao_explicadas(self) -> tuple[PerdaDeUsuario, ...]:
        """Informativo: perda fora da subárvore podada. Não reprova sozinha."""
        return tuple(perda for perda in self.perdas if perda.nao_explicados)

    @property
    def aprovada(self) -> bool:
        return self.conferencia.aprovada and not (
            self.sem_nenhum_vinculo or self.sem_nenhum_alcance
        )

    def linhas(self) -> list[str]:
        """Uma linha por usuário com perda, mais as divergências e os zerados."""
        linhas = [_linha_de_perda(perda) for perda in self.perdas]
        linhas.extend(self.conferencia.linhas(self.usernames))
        linhas.extend(
            _linha_de_zerado(item, "nenhum vínculo") for item in self.sem_nenhum_vinculo
        )
        linhas.extend(
            _linha_de_zerado(item, "nenhum órgão no role_map")
            for item in self.sem_nenhum_alcance
        )
        return linhas


def pares_de_vinculo(vinculos: Vinculos) -> set[ParVinculo]:
    """``{(user_id, orgao_id, papel)}`` — a forma comparável dos vínculos."""
    return {
        (int(user_id), int(orgao_id), papel)
        for user_id, pares in vinculos.items()
        for orgao_id, papel in pares
    }


def keep_esperado(
    vinculos_pre: Vinculos,
    genericos: frozenset[int],
    ancestrais: Ancestrais,
    calcular_colapso: CalcularColapso,
    rank_do_papel: RankDoPapel,
) -> set[ParVinculo]:
    """Reexecuta o colapso sobre a linha de base e devolve o KEEP esperado.

    Usa a MESMA ``calcular_colapso`` do serviço: o portão vira igualdade contra
    o algoritmo real, não contra uma reimplementação.

    Exemplo: ``keep_esperado(vinculos_pre, genericos, ancestrais, calc, rank)``.
    """
    esperado: set[ParVinculo] = set()
    for user_id, pares in vinculos_pre.items():
        ranks = _ranks_dos_pares(pares, rank_do_papel)
        mantidos = set(calcular_colapso(ranks, ancestrais, set(genericos)).mantidos)
        esperado |= {
            (int(user_id), int(orgao_id), papel)
            for orgao_id, papel in pares
            if orgao_id in mantidos
        }
    return esperado


def _ranks_dos_pares(
    pares: Sequence[tuple[int, str]], rank_do_papel: RankDoPapel
) -> dict[int, int]:
    """``{orgao_id: rank}``; linha duplicada resolve por ``max``, como o colapso."""
    ranks: dict[int, int] = {}
    for orgao_id, papel in pares:
        ranks[int(orgao_id)] = max(ranks.get(int(orgao_id), 0), rank_do_papel(papel))
    return ranks


def conferir_keep(esperado: set[ParVinculo], atual: set[ParVinculo]) -> ConferenciaKeep:
    """Diferença simétrica entre o KEEP recalculado e o estado real."""
    return ConferenciaKeep(
        faltando=tuple(sorted(esperado - atual)),
        sobrando=tuple(sorted(atual - esperado)),
    )


def alcance(vinculos: Iterable[int], descendentes: Descendentes) -> set[int]:
    """União das subárvores (inclusivas) dos órgãos vinculados."""
    alcancados: set[int] = set()
    for orgao_id in vinculos:
        alcancados |= descendentes.get(orgao_id, {orgao_id})
    return alcancados


def perdas_de_alcance(
    antes: Mapping[int, int], depois: Mapping[int, int]
) -> dict[int, tuple[int, int]]:
    """``{orgao_id: (rank_antes, rank_depois)}`` do que sumiu ou rebaixou."""
    return {
        orgao_id: (rank, depois.get(orgao_id, 0))
        for orgao_id, rank in antes.items()
        if depois.get(orgao_id, 0) < rank
    }


def cobertura_da_poda(
    vinculos_pre: Iterable[int],
    vinculos_pos: Iterable[int],
    genericos: frozenset[int],
    descendentes: Descendentes,
) -> set[int]:
    """Nós que a poda de genéricos tirou deste usuário — e só eles.

    Subárvore dos vínculos genéricos podados MENOS tudo que os vínculos
    mantidos ainda alcançam. Serve ao relato informativo; o veredito é
    ``ConferenciaKeep``.
    """
    podados = [orgao_id for orgao_id in vinculos_pre if orgao_id in genericos]
    return alcance(podados, descendentes) - alcance(vinculos_pos, descendentes)


def auditar(estado: EstadoColapso, conferencia: ConferenciaKeep) -> AuditoriaColapso:
    """Junta o veredito (igualdade do KEEP) com o relato de perda de alcance."""
    perdas = (
        _perda_do_usuario(user_id, estado) for user_id in sorted(estado.role_map_pre)
    )
    return AuditoriaColapso(
        perdas=tuple(perda for perda in perdas if perda is not None),
        sem_nenhum_vinculo=_sem_nenhum_vinculo(estado),
        sem_nenhum_alcance=_sem_nenhum_alcance(estado),
        conferencia=conferencia,
        usernames=estado.usernames,
    )


def _perda_do_usuario(user_id: int, estado: EstadoColapso) -> PerdaDeUsuario | None:
    perdidos = perdas_de_alcance(
        estado.role_map_pre[user_id], estado.role_map_pos.get(user_id, {})
    )
    if not perdidos:
        return None
    cobertura = cobertura_da_poda(
        _somente_ids(estado.vinculos_pre.get(user_id, ())),
        _somente_ids(estado.vinculos_pos.get(user_id, ())),
        estado.genericos,
        estado.descendentes,
    )
    nao_explicados = tuple(sorted(set(perdidos) - cobertura))
    return PerdaDeUsuario(
        user_id=user_id,
        username=estado.usernames.get(user_id, ""),
        perdidos=len(perdidos),
        explicados_pela_poda=len(perdidos) - len(nao_explicados),
        nao_explicados=nao_explicados,
    )


def _somente_ids(pares: Sequence[tuple[int, str]]) -> list[int]:
    return [int(orgao_id) for orgao_id, _ in pares]


def _sem_nenhum_vinculo(estado: EstadoColapso) -> tuple[UsuarioZerado, ...]:
    return tuple(
        _zerado(user_id, estado)
        for user_id, antes in sorted(estado.vinculos_pre.items())
        if antes and not estado.vinculos_pos.get(user_id)
    )


def _sem_nenhum_alcance(estado: EstadoColapso) -> tuple[UsuarioZerado, ...]:
    return tuple(
        _zerado(user_id, estado)
        for user_id, antes in sorted(estado.role_map_pre.items())
        if antes and not estado.role_map_pos.get(user_id)
    )


def _zerado(user_id: int, estado: EstadoColapso) -> UsuarioZerado:
    return UsuarioZerado(
        user_id=user_id,
        username=estado.usernames.get(user_id, ""),
        vinculos_antes=len(estado.vinculos_pre.get(user_id, ())),
    )


def _linha_de_perda(perda: PerdaDeUsuario) -> str:
    return (
        f"[info] {perda.username or perda.user_id}: {perda.perdidos} órgãos a menos, "
        f"{perda.explicados_pela_poda} explicados pela poda de genéricos, "
        f"fora da poda: {list(perda.nao_explicados) or '-'}"
    )


def _linha_de_par(rotulo: str, par: ParVinculo, usernames: Mapping[int, str]) -> str:
    user_id, orgao_id, papel = par
    return (
        f"[FALHA] {rotulo}: {usernames.get(user_id) or user_id} (id {user_id}) "
        f"-> orgao_id {orgao_id}, papel {papel or '-'}"
    )


def _linha_de_zerado(usuario: UsuarioZerado, o_que: str) -> str:
    return (
        f"[FALHA] ZERADO — {usuario.username or usuario.user_id} (id {usuario.user_id}) "
        f"tinha {usuario.vinculos_antes} vínculo(s) e ficou com {o_que}"
    )


def montar_estado(
    role_map_pre: RoleMaps,
    role_map_pos: RoleMaps,
    vinculos_pre: Vinculos,
    vinculos_pos: Vinculos,
    siglas_genericas: frozenset[str],
) -> EstadoColapso:
    """Completa a fotografia com a árvore e os usernames lidos do banco."""
    descendentes = _descendentes_por_orgao()
    return EstadoColapso(
        role_map_pre=role_map_pre,
        role_map_pos=role_map_pos,
        vinculos_pre=vinculos_pre,
        vinculos_pos=vinculos_pos,
        genericos=_ids_genericos(siglas_genericas),
        descendentes=descendentes,
        ancestrais=ancestrais_de(descendentes),
        usernames=_usernames(),
    )


def _ids_genericos(siglas: frozenset[str]) -> frozenset[int]:
    linhas = db.session.execute(text("SELECT id, sigla FROM orgao_unidade")).all()
    # Colação utf8mb4_0900_ai_ci é case/accent-insensitive: normalizar em Python.
    return frozenset(
        int(oid) for oid, sigla in linhas if (sigla or "").strip().upper() in siglas
    )


def _descendentes_por_orgao() -> dict[int, set[int]]:
    """`{orgao_id: subárvore inclusiva}` — a closure já traz a linha de depth 0."""
    linhas = db.session.execute(
        text("SELECT ancestor_id, descendant_id FROM orgao_closure")
    ).all()
    descendentes: dict[int, set[int]] = {}
    for ancestor_id, descendant_id in linhas:
        descendentes.setdefault(int(ancestor_id), set()).add(int(descendant_id))
    return descendentes


def ancestrais_de(descendentes: Descendentes) -> dict[int, set[int]]:
    """Inverte a closure em ``{orgao_id: ancestrais próprios}`` (sem o depth 0)."""
    ancestrais: dict[int, set[int]] = {}
    for ancestor_id, subarvore in descendentes.items():
        for descendant_id in subarvore - {ancestor_id}:
            ancestrais.setdefault(descendant_id, set()).add(ancestor_id)
    return ancestrais


def _usernames() -> dict[int, str]:
    linhas = db.session.execute(text("SELECT id, username FROM user")).all()
    return {int(uid): str(username) for uid, username in linhas}


def resumo(auditoria: AuditoriaColapso) -> dict[str, object]:
    """Contagens do stage: primeiro o veredito, depois o relato informativo."""
    conferencia = auditoria.conferencia
    return {
        "keep_confere": conferencia.aprovada,
        "pares_faltando": len(conferencia.faltando),
        "pares_sobrando": len(conferencia.sobrando),
        "divergencias": [
            list(par)
            for par in (conferencia.faltando + conferencia.sobrando)[
                :LIMITE_DE_PARES_LISTADOS
            ]
        ],
        "usuarios_com_perda": len(auditoria.perdas),
        "perdas_fora_da_poda_informativas": len(auditoria.perdas_nao_explicadas),
        "usuarios_sem_nenhum_vinculo": [
            asdict(item) for item in auditoria.sem_nenhum_vinculo
        ],
        "usuarios_sem_nenhum_alcance": [
            asdict(item) for item in auditoria.sem_nenhum_alcance
        ],
    }


def motivo_da_reprovacao(auditoria: AuditoriaColapso) -> str:
    """Mensagem do abort, uma cláusula por tipo de falha encontrada."""
    partes = _clausulas_de_reprovacao(auditoria)
    return "; ".join(partes) + ". Restaure o backup e revise o colapso."


def _clausulas_de_reprovacao(auditoria: AuditoriaColapso) -> list[str]:
    partes: list[str] = []
    conferencia = auditoria.conferencia
    if not conferencia.aprovada:
        partes.append(
            f"`user_orgao` diverge do colapso recalculado: "
            f"{len(conferencia.faltando)} par(es) faltando e "
            f"{len(conferencia.sobrando)} sobrando "
            f"(primeiros: {_amostra(conferencia)})"
        )
    if auditoria.sem_nenhum_vinculo:
        ids = [item.user_id for item in auditoria.sem_nenhum_vinculo]
        partes.append(f"ficaram SEM NENHUM vínculo em user_orgao: {ids}")
    if auditoria.sem_nenhum_alcance:
        ids = [item.user_id for item in auditoria.sem_nenhum_alcance]
        partes.append(f"ficaram SEM NENHUM órgão no role_map: {ids}")
    return partes


def _amostra(conferencia: ConferenciaKeep) -> list[ParVinculo]:
    return list((conferencia.faltando + conferencia.sobrando)[:5])


def serializar_mapas(mapas: RoleMaps) -> dict[str, dict[str, int]]:
    """Role maps em chaves string, do jeito que o JSON do relatório guarda."""
    return {
        str(user_id): {str(orgao_id): int(rank) for orgao_id, rank in mapa.items()}
        for user_id, mapa in mapas.items()
    }


def desserializar_mapas(bruto: dict) -> dict[int, dict[int, int]]:
    return {
        int(user_id): {int(orgao_id): int(rank) for orgao_id, rank in mapa.items()}
        for user_id, mapa in bruto.items()
    }


def vinculos_atuais() -> dict[int, list[tuple[int, str]]]:
    """``{user_id: [(orgao_id, papel)]}`` lido de ``user_orgao`` no estado atual."""
    linhas = db.session.execute(
        text("SELECT user_id, orgao_id, papel FROM user_orgao")
    ).all()
    vinculos: dict[int, list[tuple[int, str]]] = {}
    for user_id, orgao_id, papel in linhas:
        vinculos.setdefault(int(user_id), []).append((int(orgao_id), _papel(papel)))
    return vinculos


def _papel(valor: object) -> str:
    """Papel normalizado; ``None`` legado vira ``""``, que já conta como gestor."""
    return str(valor or "").strip()


def serializar_vinculos(vinculos: Vinculos) -> dict[str, list[tuple[int, str]]]:
    """Vínculos com papel, do jeito que o JSON do relatório guarda."""
    return {
        str(user_id): [(int(orgao_id), _papel(papel)) for orgao_id, papel in pares]
        for user_id, pares in vinculos.items()
    }


def desserializar_vinculos(
    bruto: Mapping[str, object],
) -> dict[int, list[tuple[int, str]]]:
    """Inverso de ``serializar_vinculos``; recusa a forma antiga sem papel."""
    return {
        int(user_id): [_par_do_json(item) for item in _lista(user_id, itens)]
        for user_id, itens in bruto.items()
    }


def _lista(user_id: object, itens: object) -> Sequence[object]:
    if isinstance(itens, (list, tuple)):
        return itens
    raise ValueError(
        f"vínculos do user_id {user_id!r} vieram como {itens!r}; "
        "esperado uma lista de pares [orgao_id, papel]"
    )


def _par_do_json(item: object) -> tuple[int, str]:
    if isinstance(item, (list, tuple)) and len(item) == 2:
        return int(item[0]), _papel(item[1])
    raise ValueError(
        f"vínculo {item!r} fora do formato esperado [orgao_id, papel] — um "
        "relatório gravado antes do portão por reexecução não serve de base"
    )
