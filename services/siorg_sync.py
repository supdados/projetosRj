"""Sincronização full da estrutura organizacional a partir do SIORG-RJ.

Identidade de integração = ``codigo`` do SIORG gravado em
``OrgaoUnidade.codigo_externo`` (string). Nunca casa por sigla. Unidades locais
sem ``codigo_externo`` (legado, ex.: ECENTRAL) são intocadas; unidades com
``codigo_externo`` ausentes do payload viram ``ativo=False`` (nunca deletadas).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from models import OrgaoUnidade, SiorgSyncLog, db
from services.authorization_reports import (
    serializar_escopo_zerado,
    usuarios_com_escopo_zerado,
)
from services.siorg_client import SiorgClient
from time_utils import utc_now

LOCK_TIMEOUT = timedelta(minutes=10)


class SiorgSyncEmAndamento(RuntimeError):
    """Já existe uma sincronização em andamento (lock via SiorgSyncLog)."""


def executar_sync_siorg(
    client: SiorgClient,
    disparado_por_id: int | None,
    *,
    codigo_raiz: int = 2,
) -> SiorgSyncLog:
    """Executa o full-sync SIORG→ProjetosRJ e devolve o ``SiorgSyncLog`` final.

    Levanta ``SiorgSyncEmAndamento`` se outro sync está em voo e propaga
    ``SiorgApiError`` do client (o log é fechado como ``erro`` antes).
    """
    _resolver_lock()
    log = SiorgSyncLog(disparado_por_id=disparado_por_id, codigo_raiz=codigo_raiz)
    db.session.add(log)
    db.session.commit()
    _ceder_para_sync_mais_antigo(log)
    try:
        return _executar_com_lock(client, log, codigo_raiz)
    except Exception as exc:
        db.session.rollback()
        _finalizar(log, "erro", erro=str(exc))
        raise


def _executar_com_lock(
    client: SiorgClient, log: SiorgSyncLog, codigo_raiz: int
) -> SiorgSyncLog:
    manifesto = client.obter_manifesto()
    log.versao_global = _versao_global_str(manifesto)
    log.hash_manifesto = manifesto.get("hash")
    if _manifesto_ja_sincronizado(manifesto, codigo_raiz):
        return _finalizar(log, "sucesso")

    nos = _achatar_arvore(client.obter_arvore(codigo_raiz))
    criadas, atualizadas, desativados_ids = _aplicar_nos(nos)
    _rebuild_closure()
    return _finalizar(
        log,
        "sucesso",
        criadas=criadas,
        atualizadas=atualizadas,
        desativadas=len(desativados_ids),
        # TR-2: só há o que relatar quando o sync desativou alguma unidade.
        usuarios_escopo_zerado=serializar_escopo_zerado(
            usuarios_com_escopo_zerado(desativados_ids)
        ),
    )


def _resolver_lock() -> None:
    limite = utc_now() - LOCK_TIMEOUT
    pendentes = SiorgSyncLog.query.filter_by(status="em_andamento").all()
    for pendente in pendentes:
        if pendente.iniciado_em >= limite:
            raise SiorgSyncEmAndamento(
                f"Sincronização #{pendente.id} em andamento desde "
                f"{pendente.iniciado_em.isoformat()}."
            )
        _finalizar(pendente, "erro", erro="Sincronização abandonada (lock expirado).")


def _ceder_para_sync_mais_antigo(log: SiorgSyncLog) -> None:
    """Re-checagem pós-commit do lock: fecha a corrida TOCTOU entre dois POSTs.

    Dois requests podem passar por ``_resolver_lock`` antes de qualquer commit;
    o log mais antigo (menor ``id``) vence e o mais novo é fechado como erro.
    """
    concorrente = (
        SiorgSyncLog.query.filter(
            SiorgSyncLog.status == "em_andamento", SiorgSyncLog.id < log.id
        )
        .order_by(SiorgSyncLog.id)
        .first()
    )
    if concorrente is None:
        return
    _finalizar(
        log,
        "erro",
        erro=(
            f"Abortada: sincronização concorrente #{concorrente.id} "
            "já estava em andamento (corrida de lock detectada)."
        ),
    )
    raise SiorgSyncEmAndamento(
        f"Sincronização #{concorrente.id} em andamento desde "
        f"{concorrente.iniciado_em.isoformat()}."
    )


def _manifesto_ja_sincronizado(manifesto: dict[str, Any], codigo_raiz: int) -> bool:
    ultimo = (
        SiorgSyncLog.query.filter_by(status="sucesso")
        .order_by(SiorgSyncLog.iniciado_em.desc(), SiorgSyncLog.id.desc())
        .first()
    )
    if ultimo is None:
        return False
    # Manifesto é global; raiz diferente exige re-sync mesmo com hash igual.
    if ultimo.codigo_raiz != codigo_raiz:
        return False
    hash_novo = manifesto.get("hash")
    # Hash presente dos dois lados decide sozinho; versao_global é só fallback.
    if hash_novo and ultimo.hash_manifesto:
        return ultimo.hash_manifesto == hash_novo
    versao_nova = _versao_global_str(manifesto)
    return versao_nova is not None and ultimo.versao_global == versao_nova


def _versao_global_str(manifesto: dict[str, Any]) -> str | None:
    versao = manifesto.get("versao_global")
    return None if versao is None else str(versao)


def _achatar_arvore(nos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Achata a árvore aninhada em lista (pais antes dos filhos)."""
    achatados: list[dict[str, Any]] = []
    fila = list(nos)
    while fila:
        no = fila.pop(0)
        achatados.append(no)
        fila.extend(no.get("filhos") or [])
    return achatados


def _aplicar_nos(nos: list[dict[str, Any]]) -> tuple[int, int, list[int]]:
    existentes = {
        orgao.codigo_externo: orgao
        for orgao in OrgaoUnidade.query.filter(
            OrgaoUnidade.codigo_externo.isnot(None)
        ).all()
    }
    por_codigo, criadas = _garantir_unidades(nos, existentes)
    atualizadas = _atualizar_unidades(nos, existentes, por_codigo)
    desativados_ids = _desativar_ausentes(existentes, por_codigo)
    return criadas, atualizadas, desativados_ids


def _garantir_unidades(
    nos: list[dict[str, Any]], existentes: dict[str, OrgaoUnidade]
) -> tuple[dict[str, OrgaoUnidade], int]:
    """Cria as unidades novas do payload; devolve (mapa codigo→orgao, criadas)."""
    por_codigo: dict[str, OrgaoUnidade] = {}
    criadas = 0
    for no in nos:
        codigo = str(no["codigo"])
        # Payload pode repetir o mesmo codigo; o primeiro nó vence.
        if codigo in por_codigo:
            continue
        orgao = existentes.get(codigo)
        if orgao is None:
            orgao = OrgaoUnidade(codigo_externo=codigo, **_campos_do_no(no))
            db.session.add(orgao)
            criadas += 1
        por_codigo[codigo] = orgao
    db.session.flush()
    return por_codigo, criadas


def _atualizar_unidades(
    nos: list[dict[str, Any]],
    existentes: dict[str, OrgaoUnidade],
    por_codigo: dict[str, OrgaoUnidade],
) -> int:
    atualizadas = 0
    for no in nos:
        codigo = str(no["codigo"])
        orgao = por_codigo[codigo]
        mudou = _aplicar_campos(orgao, no, por_codigo)
        if mudou and codigo in existentes:
            atualizadas += 1
    db.session.flush()
    return atualizadas


def _campos_do_no(no: dict[str, Any]) -> dict[str, Any]:
    return {
        "nome": no.get("nome") or str(no["codigo"]),
        "sigla": no.get("sigla") or str(no["codigo"]),
        "tipo": no.get("tipo") or "",
        "tipo_id": None,
        "ordem": no.get("ordenacao") or 0,
        "ativo": bool(no.get("ativo", True)),
    }


def _aplicar_campos(
    orgao: OrgaoUnidade, no: dict[str, Any], por_codigo: dict[str, OrgaoUnidade]
) -> bool:
    valores = _campos_do_no(no)
    valores["pai_id"] = _resolver_pai_id(orgao, no, por_codigo)
    mudou = False
    for campo, valor in valores.items():
        if getattr(orgao, campo) != valor:
            setattr(orgao, campo, valor)
            mudou = True
    return mudou


def _resolver_pai_id(
    orgao: OrgaoUnidade, no: dict[str, Any], por_codigo: dict[str, OrgaoUnidade]
) -> int | None:
    codigo_pai = no.get("codigo_pai")
    if codigo_pai is None:
        return None
    pai = por_codigo.get(str(codigo_pai))
    # Pai fora do escopo sincronizado (ex.: ente acima da raiz): preserva o atual.
    if pai is None:
        return orgao.pai_id
    return pai.id


def _desativar_ausentes(
    existentes: dict[str, OrgaoUnidade], por_codigo: dict[str, OrgaoUnidade]
) -> list[int]:
    """Desativa (nunca deleta) o que sumiu do payload; devolve os ids afetados."""
    desativados_ids: list[int] = []
    for codigo, orgao in existentes.items():
        if codigo in por_codigo or not orgao.ativo:
            continue
        orgao.ativo = False
        desativados_ids.append(orgao.id)
    return desativados_ids


def _rebuild_closure() -> None:
    # Import tardio: evita ciclo routes → api.admin_siorg → services.siorg_sync.
    from routes.orgao_tree import rebuild_orgao_closure

    rebuild_orgao_closure()


def _finalizar(log: SiorgSyncLog, status: str, **campos: Any) -> SiorgSyncLog:
    log.status = status
    log.finalizado_em = utc_now()
    for campo, valor in campos.items():
        setattr(log, campo, valor)
    db.session.commit()
    return log
