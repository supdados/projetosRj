import datetime
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from flask import abort, g, redirect, request, url_for
from sqlalchemy import func, inspect

from catalogs.abep import ABEP_INDICADORES_OPTIONS, normalize_abep_indicator
from models import AreaCatalog, OrgaoUnidade, Project, ProjectHistory, UserArea, db
from models.orgao import (
    ALLOWED_TIPOS as ALLOWED_ORGAO_TIPOS,
    MAX_DEPTH as ORGAO_MAX_DEPTH,
    TIPO_RANK as ORGAO_TIPO_RANK,
)
from catalogs.objectives import (
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


def sanitize_area_filter_for_user(user, selected_area):
    normalized = normalize_area_name(selected_area)
    if not normalized or user is None or user.is_admin:
        return normalized, False

    user_areas = user.get_areas()
    if normalized in user_areas:
        return normalized, False

    return '', True


def sanitize_area_filter_for_current_user(selected_area):
    return sanitize_area_filter_for_user(getattr(g, 'user', None), selected_area)


def redirect_to_current_route_without_area():
    if request.endpoint:
        target_url = url_for(request.endpoint, **(request.view_args or {}))
    else:
        target_url = request.path

    query_args = request.args.to_dict(flat=False)
    query_args.pop('area', None)
    query_string = urlencode(query_args, doseq=True)

    if query_string:
        target_url = f'{target_url}?{query_string}'

    return redirect(target_url)


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


def is_valid_parent_tipo(parent_tipo, child_tipo):
    """Pai precisa ter rank ESTRITAMENTE menor que o filho."""
    parent_rank = ORGAO_TIPO_RANK.get(parent_tipo)
    child_rank = ORGAO_TIPO_RANK.get(child_tipo)
    if parent_rank is None or child_rank is None:
        return True
    return parent_rank < child_rank


def normalize_orgao_form(form, *, is_root=False):
    nome = (form.get('nome') or '').strip()
    sigla = (form.get('sigla') or '').strip().upper()
    tipo = (form.get('tipo') or '').strip()
    pai_id_raw = form.get('pai_id')
    ordem_raw = form.get('ordem')
    ativo_raw = form.get('ativo')

    if not nome:
        return None, 'O nome do órgão é obrigatório.'
    if len(nome) > 255:
        return None, 'O nome do órgão deve ter no máximo 255 caracteres.'
    if not sigla:
        return None, 'A sigla do órgão é obrigatória.'
    if len(sigla) > 50:
        return None, 'A sigla deve ter no máximo 50 caracteres.'
    if tipo not in ALLOWED_ORGAO_TIPOS:
        return None, 'Tipo de órgão inválido.'
    if not is_root and tipo == 'Estado':
        return None, 'O tipo "Estado" é reservado para o órgão raiz.'
    if is_root and tipo != 'Estado':
        return None, 'O órgão raiz deve ter o tipo "Estado".'

    if is_root:
        pai_id = None
    else:
        if pai_id_raw in (None, '', 'None'):
            return None, 'O órgão pai é obrigatório.'
        try:
            pai_id = int(pai_id_raw)
        except (TypeError, ValueError):
            return None, 'Órgão pai inválido.'
        pai = db.session.get(OrgaoUnidade, pai_id)
        if pai is None:
            return None, 'Órgão pai não encontrado.'
        if not is_valid_parent_tipo(pai.tipo, tipo):
            return None, f'Um órgão do tipo "{pai.tipo}" não pode ser pai de "{tipo}".'

    try:
        ordem = int(ordem_raw) if ordem_raw not in (None, '') else 0
    except (TypeError, ValueError):
        ordem = 0

    ativo = True
    if ativo_raw is not None:
        ativo_str = str(ativo_raw).strip().lower()
        ativo = ativo_str in ('1', 'true', 'on', 'yes', 'sim')

    return (
        {
            'nome': nome,
            'sigla': sigla,
            'tipo': tipo,
            'pai_id': pai_id,
            'ordem': ordem,
            'ativo': ativo,
        },
        None,
    )


def compute_orgao_depth(orgao):
    """Profundidade do nó na árvore (raiz = 1)."""
    if orgao is None:
        return 0
    depth = 1
    seen = set()
    current = orgao.pai
    while current is not None and current.id not in seen:
        seen.add(current.id)
        depth += 1
        current = current.pai
    return depth


def compute_subtree_height(orgao):
    """Altura da subárvore: 1 para folha, +1 a cada nível abaixo."""
    if orgao is None:
        return 0
    max_child = 0
    for child in orgao.filhos:
        h = compute_subtree_height(child)
        if h > max_child:
            max_child = h
    return 1 + max_child


def get_orgao_descendants(orgao_id):
    """IDs de todos os descendentes (BFS)."""
    descendants = []
    frontier = [orgao_id]
    seen = {orgao_id}
    while frontier:
        next_frontier = []
        rows = (
            db.session.query(OrgaoUnidade.id, OrgaoUnidade.pai_id)
            .filter(OrgaoUnidade.pai_id.in_(frontier))
            .all()
        )
        for row_id, _ in rows:
            if row_id in seen:
                continue
            seen.add(row_id)
            descendants.append(row_id)
            next_frontier.append(row_id)
        frontier = next_frontier
    return descendants


def would_create_cycle(orgao_id, new_pai_id):
    if new_pai_id is None:
        return False
    if new_pai_id == orgao_id:
        return True
    return new_pai_id in get_orgao_descendants(orgao_id)


def validate_orgao_move(orgao, new_pai_id):
    """Retorna mensagem de erro ou None."""
    if orgao is None:
        return 'Órgão não encontrado.'

    if new_pai_id is None:
        if orgao.tipo != 'Estado':
            return 'Apenas o órgão raiz (Estado) pode ficar sem pai.'
        return None

    if would_create_cycle(orgao.id, new_pai_id):
        return 'Não é possível mover um órgão para dentro de si mesmo.'

    new_pai = db.session.get(OrgaoUnidade, new_pai_id)
    if new_pai is None:
        return 'Órgão pai não encontrado.'

    if not is_valid_parent_tipo(new_pai.tipo, orgao.tipo):
        return f'Um órgão do tipo "{new_pai.tipo}" não pode ser pai de "{orgao.tipo}".'

    new_pai_depth = compute_orgao_depth(new_pai)
    subtree_height = compute_subtree_height(orgao)
    if new_pai_depth + subtree_height > ORGAO_MAX_DEPTH:
        return f'Profundidade máxima de {ORGAO_MAX_DEPTH} níveis excedida.'

    return None
