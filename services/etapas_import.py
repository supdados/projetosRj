"""Importação de etapas de um modelo (``StageTemplate``) para um projeto.

Extrai a lógica de criação em sequência de etapas a partir de um modelo, antes
inline em ``routes/etapas/meetings.py`` (``import_model_to_project``). Compartilhada
pela rota Jinja legada e pelo endpoint JSON da SPA (``routes/api/etapas.py``) —
mesma regra de datas, sem duplicação. Não faz commit; a rota é dona da transação.
"""

from __future__ import annotations

import datetime

from models import Etapa, StageTemplate, StageTemplateUsage, db
from routes.shared import log_project_action
from services.etapas_dates import _add_business_days, _normalize_to_business_day


def import_template_stages(
    project,
    template: StageTemplate,
    start_date: datetime.date,
    *,
    created_by_id: int | None,
    source: str = "post_import",
) -> int:
    """Cria etapas sequenciais a partir das ``items`` de um modelo.

    Cada etapa começa no dia útil seguinte ao fim da anterior; a primeira começa
    no primeiro dia útil a partir de ``start_date``. A duração de cada etapa vem
    de ``item.duration_days`` em dias ÚTEIS (mínimo 1). Mesma semântica do
    preview do modal de importação (``addBusinessDays`` em
    ``ImportModelModal.svelte``), para que a data salva bata com a exibida.
    Registra o histórico e a ``StageTemplateUsage``. NÃO faz commit.

    Args:
        project: Instância de ``Project`` destino das etapas.
        template: ``StageTemplate`` com ``items`` carregados.
        start_date: Data de início da primeira etapa.
        created_by_id: ID do usuário que disparou a importação (ou ``None``).
        source: Origem da importação para a ``StageTemplateUsage``.

    Returns:
        Quantidade de etapas criadas.
    """
    ultima_etapa = (
        db.session.query(Etapa)
        .filter(Etapa.project_id == project.id)
        .order_by(Etapa.ordem.desc())
        .first()
    )
    ordem_inicial = (ultima_etapa.ordem + 1) if ultima_etapa else 0

    current_date = _normalize_to_business_day(start_date, forward=True)
    etapas_criadas = 0
    for index, item in enumerate(template.items):
        duration_days = item.duration_days if item.duration_days > 0 else 1
        data_inicio = current_date
        data_fim = _add_business_days(data_inicio, duration_days - 1)
        nova_etapa = Etapa(
            descricao=item.name,
            data_inicio=data_inicio,
            data_fim=data_fim,
            project_id=project.id,
            ordem=ordem_inicial + index,
            iniciada=False,
            done=False,
        )
        db.session.add(nova_etapa)
        etapas_criadas += 1
        current_date = _add_business_days(data_fim, 1)

    log_project_action(
        project_id=project.id,
        action_type="import_model",
        description=f'Importou {etapas_criadas} etapa(s) do modelo "{template.name}"',
    )
    db.session.add(
        StageTemplateUsage(
            template_id=template.id,
            project_id=project.id,
            created_by_id=created_by_id,
            source=source,
        )
    )
    return etapas_criadas
