"""Posição de exibição das etapas dentro do projeto ("<projeto>.<posição>").

A tela de Detalhe numera as etapas em ordem de render (1-based, lista completa
ordenada por ``ordem``) — ver ``StageList.displayNumber`` no frontend. Telas de
listagem (Projetos Pendentes) recebem só um SUBCONJUNTO das etapas, então a
posição precisa vir do servidor para a numeração bater com a do Detalhe.
"""

from collections import defaultdict

from models import Etapa


def build_etapa_position_map(project_ids: list[int]) -> dict[int, int]:
    """Mapeia ``etapa.id`` -> posição 1-based na lista completa do projeto.

    Ordena como a tela de Detalhe (``ordem`` ascendente, nulos como 0) com
    desempate estável por ``id``. Uma única query cobre todos os projetos.

    Exemplo:
        >>> build_etapa_position_map([294])
        {8101: 1, 8102: 2, 8103: 3}
    """
    if not project_ids:
        return {}
    rows = (
        Etapa.query.filter(Etapa.project_id.in_(project_ids))
        .with_entities(Etapa.id, Etapa.project_id, Etapa.ordem)
        .all()
    )
    etapas_by_project: dict[int, list] = defaultdict(list)
    for row in rows:
        etapas_by_project[row.project_id].append(row)

    positions: dict[int, int] = {}
    for project_rows in etapas_by_project.values():
        project_rows.sort(
            key=lambda row: (row.ordem if row.ordem is not None else 0, row.id)
        )
        for index, row in enumerate(project_rows):
            positions[row.id] = index + 1
    return positions
