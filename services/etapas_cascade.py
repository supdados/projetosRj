"""Cascata de datas entre etapas subsequentes de um projeto."""

from models import Etapa, db
from services.project_meetings import MEETING_ENTRY_TYPE


def cascade_subsequent_dates(project_id, base_etapa_ordem, days_to_add):
    """Desloca datas de todas as etapas após ``base_etapa_ordem`` em ``days_to_add`` dias úteis.

    Não faz commit — a rota é responsável pela transação.
    """
    # Import tardio: ``routes.etapas.helpers`` é uma rota e importá-lo no topo cria
    # um ciclo (services -> routes.etapas -> crud -> services.etapas_cascade) quando
    # o serviço é carregado cedo (ex.: por routes.api.etapas). Importar na chamada
    # mantém o serviço independente de rotas no carregamento do módulo.
    from routes.etapas.helpers import _add_business_days, _normalize_to_business_day

    subsequent_etapas = (
        Etapa.query.filter(
            Etapa.project_id == project_id,
            Etapa.ordem > base_etapa_ordem,
            Etapa.entry_type != MEETING_ENTRY_TYPE,
        )
        .order_by(Etapa.ordem.asc(), Etapa.id.asc())
        .all()
    )

    for etapa in subsequent_etapas:
        if etapa.data_inicio:
            etapa.data_inicio = _add_business_days(etapa.data_inicio, days_to_add)
            etapa.data_inicio = _normalize_to_business_day(
                etapa.data_inicio, forward=True
            )
        if etapa.data_fim:
            etapa.data_fim = _add_business_days(etapa.data_fim, days_to_add)
            etapa.data_fim = _normalize_to_business_day(etapa.data_fim, forward=True)
