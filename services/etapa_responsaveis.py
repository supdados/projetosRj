"""Substituição transacional das áreas responsáveis de uma etapa (mudança #3)."""

import re

from sqlalchemy import func

from models import EtapaResponsavel, OrgaoUnidade, db
from services.etapas_mutation import assert_etapa_editavel

OUTRAS_LABEL = "Outras"
MOTIVO_RESPONSAVEIS_ETAPA_CONCLUIDA = (
    "Não é possível editar responsáveis de uma etapa concluída."
)

_SEPARADORES = re.compile(r"[,;/\n]+")


def split_responsavel_legado(raw: object) -> list[str]:
    """Quebra o espelho legado ``Etapa.responsavel`` nos rótulos individuais.

    ``apply_responsaveis_entries`` grava ``", ".join(labels)`` nessa coluna, então
    uma etapa com três áreas vira "SUBEXE, COODADOS, COOACES". Filtros e listas de
    opção precisam de UM item por área — não da string inteira.

    Exemplo:
        >>> split_responsavel_legado("SUBEXE, COODADOS ; COOACES")
        ['SUBEXE', 'COODADOS', 'COOACES']
    """
    if not isinstance(raw, str):
        return []
    nomes: list[str] = []
    vistos: set[str] = set()
    for parte in _SEPARADORES.split(raw):
        nome = " ".join(parte.split())
        if not nome or nome.casefold() in vistos:
            continue
        vistos.add(nome.casefold())
        nomes.append(nome)
    return nomes


def areas_from_responsavel_legado(raw: object) -> list[dict]:
    """Converte o texto espelho ``Etapa.responsavel`` em áreas ``{area_id, label}``.

    Ponte para quem só tem o texto legado (payloads antigos da API de edição):
    cada rótulo vira a unidade viva de mesma sigla e o que não casa cai em
    "Outras" (``area_id`` nulo), como no caminho canônico. A saída alimenta
    ``replace_etapa_responsaveis``, que valida de novo e reescreve o espelho.

    Exemplo:
        >>> areas_from_responsavel_legado("SUBEXE, Time externo")
        [{'area_id': 7, 'label': 'SUBEXE'}, {'area_id': None, 'label': 'Outras'}]
    """
    nomes = split_responsavel_legado(raw)
    if not nomes:
        return []
    chaves = [nome.casefold() for nome in nomes]
    ids_por_sigla: dict[str, int] = {}
    unidades = (
        OrgaoUnidade.query.filter(func.lower(OrgaoUnidade.sigla).in_(chaves))
        .order_by(OrgaoUnidade.id.asc())
        .all()
    )
    for unidade in unidades:
        ids_por_sigla.setdefault(unidade.sigla.casefold(), unidade.id)
    return [
        {"area_id": ids_por_sigla.get(chave), "label": nome}
        for nome, chave in zip(nomes, chaves)
    ]


def responsavel_display(etapa) -> str:
    """String de exibição dos responsáveis da etapa, derivada da N:N.

    Fonte canônica são as linhas ``etapa.responsaveis`` (sigla viva da área,
    fallback no ``label`` congelado se o órgão sumiu) — mesma regra do detalhe,
    então card e detalhe nunca divergem. Etapas ainda sem N:N (bancos não
    backfillados) caem no espelho legado ``Etapa.responsavel``.

    Exemplo:
        >>> responsavel_display(etapa)
        'SUBEXE, COODADOS'
    """
    labels = [
        (item.area.sigla if item.area is not None else item.label) or ""
        for item in etapa.responsaveis
    ]
    labels = [label.strip() for label in labels if label.strip()]
    if labels:
        return ", ".join(labels)
    return (etapa.responsavel or "").strip()


def parse_responsaveis_entries(raw: object) -> list[dict]:
    """Valida/normaliza a lista de {area_id, label}. Levanta ValueError com o valor recebido."""
    if not isinstance(raw, list) or not raw:
        raise ValueError(
            f"Pelo menos uma área responsável é obrigatória (recebido: {raw!r}; "
            "esperado: lista não-vazia de objetos {area_id, label})."
        )
    entries: list[dict] = []
    seen: set[object] = set()
    for item in raw:
        entry = _parse_responsavel_item(item)
        key = entry["area_id"] if entry["area_id"] is not None else OUTRAS_LABEL
        if key in seen:
            continue
        seen.add(key)
        entries.append(entry)
    return entries


def _parse_responsavel_item(item: object) -> dict:
    """Valida um item {area_id, label}; resolve a sigla viva do OrgaoUnidade."""
    if not isinstance(item, dict):
        raise ValueError(
            f"Área responsável inválida (recebido: {item!r}; esperado: objeto {{area_id, label}})."
        )
    area_id = item.get("area_id")
    if area_id is None:
        return {"area_id": None, "label": OUTRAS_LABEL}
    area = db.session.get(OrgaoUnidade, area_id)
    if area is None:
        raise ValueError(
            f"Área responsável inexistente (recebido area_id={area_id!r}; "
            "esperado: id de OrgaoUnidade cadastrado ou null para 'Outras')."
        )
    return {"area_id": area.id, "label": area.sigla}


def apply_responsaveis_entries(etapa, entries: list[dict]) -> None:
    """Aplica as linhas N:N já validadas e reescreve o mirror legado. Não faz commit.

    Reusa as linhas existentes por ``area_id`` (vira UPDATE de label/ordem) em vez
    de apagar e reinserir: o unit-of-work do SQLAlchemy emite INSERT antes de
    DELETE, então delete+insert da mesma ``(etapa_id, area_id)`` violaria o UNIQUE
    numa edição. As áreas que saíram caem no delete-orphan da reatribuição. Mesmo
    padrão de services/sei_process.py::replace_project_sei_numbers.
    """
    existentes_por_area = {item.area_id: item for item in etapa.responsaveis}
    reconstruida: list[EtapaResponsavel] = []
    vistas: set[int | None] = set()
    for entry in entries:
        area_id = entry["area_id"]
        if area_id in vistas:
            continue
        vistas.add(area_id)
        item = existentes_por_area.pop(area_id, None) or EtapaResponsavel(
            area_id=area_id
        )
        item.label = entry["label"]
        item.ordem = len(reconstruida)
        reconstruida.append(item)
    etapa.responsaveis = reconstruida
    etapa.responsavel = ", ".join(item.label for item in reconstruida)[:100]


def replace_etapa_responsaveis(etapa, raw_areas: object) -> None:
    """Substitui as linhas N:N e reescreve o mirror legado. Não faz commit."""
    assert_etapa_editavel(etapa, motivo_done=MOTIVO_RESPONSAVEIS_ETAPA_CONCLUIDA)
    apply_responsaveis_entries(etapa, parse_responsaveis_entries(raw_areas))
