import datetime
from zoneinfo import ZoneInfo

from flask import g

from abep_catalog import ABEP_INDICADORES_OPTIONS, normalize_abep_indicator
from models import ProjectHistory, db
from objective_catalog import (
    OBJETIVO_IDS,
    get_indicadores_por_resultado,
    get_objetivos_choices,
    get_resultados_por_objetivo,
)

TIMEZONE_BR = ZoneInfo('America/Sao_Paulo')
AREAS_RESPONSAVEIS_CHOICES = [
    'Auditoria',
    'CHEGAB',
    'SUPDADOS',
    'SUBDGD',
    'SUPEST',
    'SUPIM',
    'SUPPAE',
    'PRODERJ',
    'ASSESP',
    'ECENTRAL',
    'SUBEDD',
    'VPD',
    'VPE',
    'VPT',
]


def format_local_time(dt, fmt='%d/%m %H:%M'):
    """Converte datetime UTC (naive) para horário do Brasil e retorna string."""
    if dt is None:
        return None
    utc = dt.replace(tzinfo=ZoneInfo('UTC')) if dt.tzinfo is None else dt
    return utc.astimezone(TIMEZONE_BR).strftime(fmt)


def log_project_action(project_id, action_type, description, old_value=None, new_value=None):
    """
    Registra uma ação no histórico do projeto.
    """
    try:
        history_entry = ProjectHistory(
            project_id=project_id,
            user_id=g.user.id,
            action_type=action_type,
            action_description=description,
            old_value=old_value,
            new_value=new_value,
        )
        db.session.add(history_entry)
    except Exception as e:
        print(f'Erro ao registrar histórico: {e}')


def get_goal_catalog_context():
    """Retorna estruturas de objetivo/resultado/indicador vindas do catalogo canonico."""
    return (
        get_objetivos_choices(),
        get_resultados_por_objetivo(),
        get_indicadores_por_resultado(),
    )


def parse_objetivo_filter(raw_value):
    if not raw_value:
        return None
    try:
        objetivo_id = int(raw_value)
    except (TypeError, ValueError):
        return None
    if objetivo_id not in OBJETIVO_IDS:
        return None
    return objetivo_id


def parse_abep_indicator_filter(raw_value):
    if not raw_value:
        return None
    try:
        normalized = normalize_abep_indicator(raw_value)
    except ValueError:
        return None
    return normalized


def inject_current_year():
    return {
        'current_year': datetime.datetime.utcnow().year,
        'AREAS_RESPONSAVEIS_CHOICES': AREAS_RESPONSAVEIS_CHOICES,
        'ABEP_INDICADORES_OPTIONS': ABEP_INDICADORES_OPTIONS,
    }
