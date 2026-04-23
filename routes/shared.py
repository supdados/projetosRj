import datetime
from zoneinfo import ZoneInfo

from flask import abort, current_app, g, request, url_for
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
    from routes.orgao_scope import sanitize_orgao_filter_for_current_user

    orgaos_disponiveis = _get_orgaos_disponiveis_for_current_user()
    selected_orgao_raw = request.args.get('orgao') or request.args.get('area')
    selected_orgao_id, invalid_orgao_filter = sanitize_orgao_filter_for_current_user(selected_orgao_raw)
    if invalid_orgao_filter:
        selected_orgao_id = None
    orgao_label_map = {str(orgao_id): orgao_sigla for orgao_id, orgao_sigla, _orgao_nome in orgaos_disponiveis}

    def build_current_orgao_url(orgao_id=None):
        query_args = request.args.to_dict(flat=False)
        query_args.pop('orgao', None)
        query_args.pop('area', None)
        query_args.pop('page', None)

        if orgao_id not in (None, '', 'None'):
            query_args['orgao'] = [str(orgao_id)]

        kwargs = dict(request.view_args or {})
        for key, values in query_args.items():
            kwargs[key] = values if len(values) > 1 else values[0]

        if request.endpoint:
            try:
                return url_for(request.endpoint, **kwargs)
            except Exception:
                pass

        query_string = '&'.join(
            f'{key}={value}'
            for key, values in query_args.items()
            for value in values
        )
        return f'{request.path}?{query_string}' if query_string else request.path

    def build_orgao_nav_url(endpoint, **kwargs):
        if selected_orgao_id not in (None, '', 'None'):
            kwargs.setdefault('orgao', selected_orgao_id)
        return url_for(endpoint, **kwargs)

    return {
        'current_year': datetime.datetime.now(datetime.UTC).year,
        'ABEP_INDICADORES_OPTIONS': ABEP_INDICADORES_OPTIONS,
        'ORGAOS_DISPONIVEIS': orgaos_disponiveis,
        'selected_orgao_global': selected_orgao_id,
        'selected_orgao_global_sigla': orgao_label_map.get(str(selected_orgao_id), '') if selected_orgao_id is not None else '',
        'build_current_orgao_url': build_current_orgao_url,
        'build_orgao_nav_url': build_orgao_nav_url,
    }


def get_or_404(model, object_id):
    instance = db.session.get(model, object_id)
    if instance is None:
        abort(404)
    return instance

