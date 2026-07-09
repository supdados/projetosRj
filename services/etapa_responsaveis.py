"""Substituição transacional das áreas responsáveis de uma etapa (mudança #3)."""

from models import EtapaResponsavel, OrgaoUnidade, db

OUTRAS_LABEL = "Outras"


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
    apply_responsaveis_entries(etapa, parse_responsaveis_entries(raw_areas))
