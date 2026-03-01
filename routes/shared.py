import datetime
from zoneinfo import ZoneInfo

from flask import abort, g
from sqlalchemy import func, inspect

from abep_catalog import ABEP_INDICADORES_OPTIONS, normalize_abep_indicator
from models import AreaCatalog, Project, ProjectHistory, UserArea, db
from objective_catalog import (
    OBJETIVO_IDS,
    get_indicadores_por_resultado,
    get_objetivos_choices,
    get_resultados_por_objetivo,
)
from services.notifications import notify_project_history_action

TIMEZONE_BR = ZoneInfo('America/Sao_Paulo')
DEFAULT_AREAS_RESPONSAVEIS_CHOICES = [
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
# Compatibilidade para módulos legados que ainda importam a constante.
AREAS_RESPONSAVEIS_CHOICES = list(DEFAULT_AREAS_RESPONSAVEIS_CHOICES)


def normalize_area_name(raw_name):
    if raw_name is None:
        return ''
    normalized = ' '.join(str(raw_name).strip().split())
    return normalized


def _area_catalog_table_exists():
    inspector = inspect(db.engine)
    return 'area_catalog' in inspector.get_table_names()


def _collect_referenced_area_names():
    inspector = inspect(db.engine)
    table_names = set(inspector.get_table_names())
    candidates = []

    if 'project' in table_names:
        candidates.extend(
            area
            for (area,) in (
                db.session.query(Project.area_responsavel)
                .filter(Project.area_responsavel.isnot(None))
                .distinct()
                .all()
            )
        )
    if 'user_areas' in table_names:
        candidates.extend(
            area
            for (area,) in (
                db.session.query(UserArea.area)
                .filter(UserArea.area.isnot(None))
                .distinct()
                .all()
            )
        )
    unique_names = []
    seen = set()
    for candidate in candidates:
        normalized = normalize_area_name(candidate)
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique_names.append(normalized)
    return unique_names


def get_area_catalog_choices():
    if not _area_catalog_table_exists():
        return list(DEFAULT_AREAS_RESPONSAVEIS_CHOICES)
    return [
        area.name
        for area in AreaCatalog.query.order_by(func.lower(AreaCatalog.name), AreaCatalog.name).all()
    ]


def ensure_area_catalog_seeded():
    if not _area_catalog_table_exists():
        return list(DEFAULT_AREAS_RESPONSAVEIS_CHOICES)

    current_names = get_area_catalog_choices()
    current_keys = {name.casefold() for name in current_names}
    referenced_names = _collect_referenced_area_names()

    if current_names:
        seed_candidates = referenced_names
    else:
        seed_candidates = list(DEFAULT_AREAS_RESPONSAVEIS_CHOICES) + referenced_names

    additions = []
    for candidate in seed_candidates:
        normalized = normalize_area_name(candidate)
        if not normalized:
            continue
        key = normalized.casefold()
        if key in current_keys:
            continue
        current_keys.add(key)
        additions.append(AreaCatalog(name=normalized))

    if additions:
        db.session.add_all(additions)
        db.session.commit()

    return get_area_catalog_choices()


def validate_area_name(raw_name, current_area_id=None):
    normalized = normalize_area_name(raw_name)
    if not normalized:
        return None, 'O nome da área é obrigatório.'
    if len(normalized) > 100:
        return None, 'O nome da área deve ter no máximo 100 caracteres.'

    if _area_catalog_table_exists():
        duplicate_query = AreaCatalog.query.filter(
            func.lower(AreaCatalog.name) == normalized.casefold()
        )
        if current_area_id is not None:
            duplicate_query = duplicate_query.filter(AreaCatalog.id != current_area_id)
        if duplicate_query.first() is not None:
            return None, 'Já existe uma área com esse nome.'

    return normalized, None


def resolve_catalog_area_name(area_name):
    normalized = normalize_area_name(area_name)
    if not normalized:
        return None

    for catalog_name in get_area_catalog_choices():
        if normalized.casefold() == catalog_name.casefold():
            return catalog_name
    return None


def is_area_in_catalog(area_name):
    return resolve_catalog_area_name(area_name) is not None


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
        if not getattr(g, 'user', None):
            return

        history_entry = ProjectHistory(
            project_id=project_id,
            user_id=g.user.id,
            action_type=action_type,
            action_description=description,
            old_value=old_value,
            new_value=new_value,
        )
        db.session.add(history_entry)

        try:
            notify_project_history_action(
                project_id=project_id,
                actor_user_id=g.user.id,
                action_type=action_type,
                action_description=description,
                old_value=old_value,
                new_value=new_value,
            )
        except Exception as notification_error:
            print(f'Erro ao registrar notificacao de projeto: {notification_error}')
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
        'current_year': datetime.datetime.now(datetime.UTC).year,
        'AREAS_RESPONSAVEIS_CHOICES': get_area_catalog_choices(),
        'ABEP_INDICADORES_OPTIONS': ABEP_INDICADORES_OPTIONS,
    }


def get_or_404(model, object_id):
    instance = db.session.get(model, object_id)
    if instance is None:
        abort(404)
    return instance
