import datetime
from zoneinfo import ZoneInfo

from flask import abort, current_app, g
from sqlalchemy import inspect

from catalogs.abep import ABEP_INDICADORES_OPTIONS, normalize_abep_indicator
from models import ProjectHistory, db
from catalogs.objectives import (
    OBJETIVO_IDS,
    get_indicadores_por_resultado,
    get_objetivos_choices,
    get_resultados_por_objetivo,
)
from services.notifications import notify_project_history_action

TIMEZONE_BR = ZoneInfo('America/Sao_Paulo')


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
            current_app.logger.warning('Falha ao notificar histórico de projeto: %s', notification_error)
    except Exception as e:
        current_app.logger.error('Falha ao registrar histórico de projeto: %s', e)


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


def _get_orgaos_disponiveis_for_current_user():
    """Retorna lista [(id, sigla, nome)] dos orgaos no escopo do usuario atual.

    - sem user: lista vazia (evita custo de query quando nao precisa).
    - admin: todos os orgaos ativos, ordenados por sigla.
    - demais: apenas os orgaos no subtree dos vinculos do usuario.
    """
    user = getattr(g, 'user', None)
    if user is None:
        return []

    inspector = inspect(db.engine)
    if 'orgao_unidade' not in inspector.get_table_names():
        return []

    from models import OrgaoUnidade
    from routes.orgao_scope import get_user_orgao_subtree_ids

    subtree_ids = get_user_orgao_subtree_ids(user)
    if not subtree_ids:
        return []

    rows = (
        OrgaoUnidade.query
        .filter(OrgaoUnidade.id.in_(subtree_ids))
        .filter(OrgaoUnidade.ativo.is_(True))
        .order_by(OrgaoUnidade.sigla)
        .all()
    )
    return [(o.id, o.sigla, o.nome) for o in rows]


def inject_current_year():
    return {
        'current_year': datetime.datetime.now(datetime.UTC).year,
        'ABEP_INDICADORES_OPTIONS': ABEP_INDICADORES_OPTIONS,
        'ORGAOS_DISPONIVEIS': _get_orgaos_disponiveis_for_current_user(),
    }


def get_or_404(model, object_id):
    instance = db.session.get(model, object_id)
    if instance is None:
        abort(404)
    return instance


