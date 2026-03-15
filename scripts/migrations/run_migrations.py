#!/usr/bin/env python3
"""
Script canônico de migração de banco de dados.

Objetivos:
1. Consolidar todas as migrações históricas num único fluxo idempotente.
2. Suportar SQLite (desenvolvimento/homologação) e MySQL (produção).
3. Migrar bancos mistos que ainda possuem `task_item*` para o modelo final
   task-only (`task`, `task_comment`, `task_anexo`, `legacy_task_redirect`).

Uso:
    python3 scripts/migrations/run_migrations.py
"""

from collections import defaultdict
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import MetaData, Table, inspect, select, text

from models import Project, ProjectHistory, User, UserArea, db
from catalogs.objectives import sync_goal_catalog_to_db
from routes.shared import ensure_area_catalog_seeded
from time_utils import utc_now

ALEMBIC_HEAD = 'e5f6a7b8c9d0'
VALID_TASK_STATUSES = {
    'nao_iniciada',
    'em_andamento',
    'para_validacao',
    'para_ajustes',
    'finalizada',
}
STATUS_RENAMES = {
    'programado': 'nao_iniciada',
    'validacao': 'para_validacao',
    'finalizado': 'finalizada',
}
TASK_REQUIRED_COLUMNS = {
    'descricao',
    'status',
    'responsavel',
    'ordem',
    'project_id',
    'created_by_id',
    'created_at',
    'prioridade',
    'tipo_pedido',
    'is_archived',
    'archived_at',
    'legacy_parent_task_id',
}
LEGACY_TASK_TABLES = (
    'task_item',
    'task_item_comment',
    'task_item_anexo',
)
PROJECT_COLUMNS = [
    ('special_project', 'VARCHAR(20)'),
    ('sei_process', 'VARCHAR(50)'),
    ('short_description', 'TEXT'),
    ('delivery_type', 'VARCHAR(50)'),
    ('abep_indicator', 'VARCHAR(255)'),
    ('github_link', 'VARCHAR(500)'),
    ('documentation_link', 'VARCHAR(500)'),
]
USER_AUTH_COLUMNS = [
    ('cpf_govbr', 'VARCHAR(11)'),
    ('govbr_sub', 'VARCHAR(255)'),
]
USER_AUTH_INDEXES = {
    'uq_user_cpf_govbr': {
        'ddl': 'CREATE UNIQUE INDEX uq_user_cpf_govbr ON `user` (cpf_govbr)',
        'compatible_names': {'ix_user_cpf_govbr'},
    },
    'uq_user_govbr_sub': {
        'ddl': 'CREATE UNIQUE INDEX uq_user_govbr_sub ON `user` (govbr_sub)',
        'compatible_names': {'ix_user_govbr_sub'},
    },
}
USER_NOTIFICATION_INDEXES = {
    'ix_user_notification_recipient_user_id': 'CREATE INDEX ix_user_notification_recipient_user_id ON user_notification (recipient_user_id)',
    'ix_user_notification_actor_user_id': 'CREATE INDEX ix_user_notification_actor_user_id ON user_notification (actor_user_id)',
    'ix_user_notification_event_type': 'CREATE INDEX ix_user_notification_event_type ON user_notification (event_type)',
    'ix_user_notification_is_read': 'CREATE INDEX ix_user_notification_is_read ON user_notification (is_read)',
    'ix_user_notification_recipient_read_created': (
        'CREATE INDEX ix_user_notification_recipient_read_created '
        'ON user_notification (recipient_user_id, is_read, created_at)'
    ),
}
TASK_INDEXES = {
    'ix_task_status': 'CREATE INDEX ix_task_status ON task (status)',
    'ix_task_project_id': 'CREATE INDEX ix_task_project_id ON task (project_id)',
    'ix_task_created_by_id': 'CREATE INDEX ix_task_created_by_id ON task (created_by_id)',
    'ix_task_is_archived': 'CREATE INDEX ix_task_is_archived ON task (is_archived)',
}
TASK_COMMENT_INDEX = 'CREATE INDEX ix_task_comment_task_id ON task_comment (task_id)'
TASK_ANEXO_INDEX = 'CREATE INDEX ix_task_anexo_task_id ON task_anexo (task_id)'
TASK_TEMP_TABLES = (
    'task__migration_tmp',
    'task_comment__migration_tmp',
    'task_anexo__migration_tmp',
    'legacy_task_redirect__migration_tmp',
)
CALENDAR_INCREMENTAL_COLUMNS = {
    'user_calendar_connection': [
        ('google_account_id', 'VARCHAR(255)'),
        ('google_account_email', 'VARCHAR(255)'),
        ('watch_channel_token', 'VARCHAR(255)'),
    ],
    'calendar_event': [
        ('meet_link', 'VARCHAR(512)'),
    ],
}
STAGE_INCREMENTAL_COLUMNS = {
    'etapa': [
        ('entry_type', "VARCHAR(30) NOT NULL DEFAULT 'manual'"),
    ],
}


def _emit(message, emit_output=True):
    if emit_output:
        print(message)


def _table_exists(inspector, table_name):
    return table_name in inspector.get_table_names()


def _column_names(inspector, table_name):
    if not _table_exists(inspector, table_name):
        return set()
    return {column['name'] for column in inspector.get_columns(table_name)}


def _column_default(inspector, table_name, column_name):
    if not _table_exists(inspector, table_name):
        return None
    for column in inspector.get_columns(table_name):
        if column['name'] == column_name:
            return column.get('default')
    return None


def _index_names(inspector, table_name):
    if not _table_exists(inspector, table_name):
        return set()
    try:
        return {index['name'] for index in inspector.get_indexes(table_name)}
    except Exception:
        return set()


def _fetch_rows(table_name):
    inspector = inspect(db.engine)
    if not _table_exists(inspector, table_name):
        return []
    table = Table(table_name, MetaData(), autoload_with=db.engine)
    rows = db.session.execute(select(table)).all()
    return [dict(row._mapping) for row in rows]


def _drop_table_if_exists(table_name):
    db.session.execute(text(f'DROP TABLE IF EXISTS {table_name}'))


def _disable_foreign_keys():
    if db.engine.dialect.name == 'sqlite':
        db.session.execute(text('PRAGMA foreign_keys=OFF'))
    elif db.engine.dialect.name == 'mysql':
        db.session.execute(text('SET FOREIGN_KEY_CHECKS = 0'))


def _enable_foreign_keys():
    if db.engine.dialect.name == 'sqlite':
        db.session.execute(text('PRAGMA foreign_keys=ON'))
    elif db.engine.dialect.name == 'mysql':
        db.session.execute(text('SET FOREIGN_KEY_CHECKS = 1'))


def _coerce_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_bool(value):
    if value in (None, '', 0, '0', False):
        return 0
    if value in (1, '1', True):
        return 1
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {'false', 'f', 'no', 'off'}:
            return 0
        if lowered in {'true', 't', 'yes', 'on'}:
            return 1
    return 1 if value else 0


def _normalize_status(value):
    normalized = STATUS_RENAMES.get((value or '').strip(), (value or '').strip())
    if not normalized:
        return 'nao_iniciada'
    if normalized not in VALID_TASK_STATUSES:
        return 'nao_iniciada'
    return normalized


def _next_available_id(used_ids):
    next_id = max(used_ids or {0})
    while True:
        next_id += 1
        if next_id not in used_ids:
            return next_id


def _allocate_ids(old_ids, reserved_ids):
    used_ids = set(reserved_ids)
    mapping = {}
    for old_id in sorted(old_ids):
        if old_id not in used_ids:
            mapping[old_id] = old_id
            used_ids.add(old_id)
            continue
        new_id = _next_available_id(used_ids)
        mapping[old_id] = new_id
        used_ids.add(new_id)
    return mapping


def _resolve_fallback_user_id():
    first_user_id = db.session.execute(text('SELECT id FROM user ORDER BY id ASC LIMIT 1')).scalar()
    return _coerce_int(first_user_id)


def _resolve_created_at(*values):
    for value in values:
        if value is not None:
            return value
    return utc_now()


def _resolve_created_by(fallback_user_id, *values):
    for value in values:
        coerced = _coerce_int(value)
        if coerced is not None:
            return coerced
    if fallback_user_id is None:
        raise RuntimeError("Tabela `user` sem registros: impossível definir created_by_id.")
    return fallback_user_id


def _normalize_task_payload(row, fallback_user_id, *, preserve_legacy_parent=False, legacy_parent_task_id=None):
    status = _normalize_status(row.get('status'))
    archived_at = row.get('archived_at')
    if archived_at is None:
        archived_at = row.get('finalized_at')

    payload = {
        'descricao': (row.get('descricao') or row.get('titulo') or '').strip(),
        'status': status,
        'responsavel': row.get('responsavel'),
        'ordem': _coerce_int(row.get('ordem')) or 0,
        'project_id': _coerce_int(row.get('project_id')),
        'created_by_id': _resolve_created_by(
            fallback_user_id,
            row.get('created_by_id'),
        ),
        'created_at': _resolve_created_at(row.get('created_at')),
        'prioridade': row.get('prioridade'),
        'tipo_pedido': row.get('tipo_pedido'),
        'is_archived': _normalize_bool(row.get('is_archived', row.get('is_finalized'))),
        'archived_at': archived_at,
        'legacy_parent_task_id': None,
    }

    if preserve_legacy_parent:
        payload['legacy_parent_task_id'] = _coerce_int(legacy_parent_task_id)

    return payload


def _task_schema_requires_rebuild(inspector):
    if any(_table_exists(inspector, table_name) for table_name in LEGACY_TASK_TABLES):
        return True

    if not _table_exists(inspector, 'task'):
        return False

    task_columns = _column_names(inspector, 'task')
    if {'titulo', 'is_finalized', 'finalized_at'} & task_columns:
        return True
    if not TASK_REQUIRED_COLUMNS.issubset(task_columns):
        return True

    if db.engine.dialect.name == 'sqlite':
        status_default = (_column_default(inspector, 'task', 'status') or '').lower()
        if 'programado' in status_default:
            return True

    return False


def _create_task_temp_tables():
    for table_name in TASK_TEMP_TABLES:
        _drop_table_if_exists(table_name)

    if db.engine.dialect.name == 'mysql':
        db.session.execute(
            text(
                """
                CREATE TABLE task__migration_tmp (
                    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                    descricao TEXT NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'nao_iniciada',
                    responsavel VARCHAR(100) NULL,
                    ordem INT NOT NULL DEFAULT 0,
                    project_id INT NULL,
                    created_by_id INT NOT NULL,
                    created_at DATETIME NOT NULL,
                    prioridade VARCHAR(20) NULL,
                    tipo_pedido VARCHAR(30) NULL,
                    is_archived BOOLEAN NOT NULL DEFAULT 0,
                    archived_at DATETIME NULL,
                    legacy_parent_task_id INT NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
        )
        db.session.execute(
            text(
                """
                CREATE TABLE task_comment__migration_tmp (
                    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                    content TEXT NOT NULL,
                    user_id INT NOT NULL,
                    task_id INT NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
        )
        db.session.execute(
            text(
                """
                CREATE TABLE task_anexo__migration_tmp (
                    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                    task_id INT NOT NULL,
                    filename VARCHAR(255) NOT NULL,
                    stored_filename VARCHAR(255) NOT NULL,
                    content_type VARCHAR(100) NULL,
                    uploaded_by_id INT NOT NULL,
                    created_at DATETIME NOT NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
        )
        db.session.execute(
            text(
                """
                CREATE TABLE legacy_task_redirect__migration_tmp (
                    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                    legacy_task_id INT NOT NULL,
                    project_id INT NULL,
                    sample_task_id INT NULL,
                    created_at DATETIME NOT NULL,
                    UNIQUE KEY uq_legacy_task_redirect_legacy_task_id (legacy_task_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
        )
    else:
        db.session.execute(
            text(
                """
                CREATE TABLE task__migration_tmp (
                    id INTEGER PRIMARY KEY,
                    descricao TEXT NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'nao_iniciada',
                    responsavel VARCHAR(100),
                    ordem INTEGER NOT NULL DEFAULT 0,
                    project_id INTEGER,
                    created_by_id INTEGER NOT NULL,
                    created_at DATETIME NOT NULL,
                    prioridade VARCHAR(20),
                    tipo_pedido VARCHAR(30),
                    is_archived BOOLEAN NOT NULL DEFAULT 0,
                    archived_at DATETIME,
                    legacy_parent_task_id INTEGER
                )
                """
            )
        )
        db.session.execute(
            text(
                """
                CREATE TABLE task_comment__migration_tmp (
                    id INTEGER PRIMARY KEY,
                    content TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    task_id INTEGER NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME
                )
                """
            )
        )
        db.session.execute(
            text(
                """
                CREATE TABLE task_anexo__migration_tmp (
                    id INTEGER PRIMARY KEY,
                    task_id INTEGER NOT NULL,
                    filename VARCHAR(255) NOT NULL,
                    stored_filename VARCHAR(255) NOT NULL,
                    content_type VARCHAR(100),
                    uploaded_by_id INTEGER NOT NULL,
                    created_at DATETIME NOT NULL
                )
                """
            )
        )
        db.session.execute(
            text(
                """
                CREATE TABLE legacy_task_redirect__migration_tmp (
                    id INTEGER PRIMARY KEY,
                    legacy_task_id INTEGER NOT NULL UNIQUE,
                    project_id INTEGER,
                    sample_task_id INTEGER,
                    created_at DATETIME NOT NULL
                )
                """
            )
        )


def _prepare_task_rebuild_payload():
    existing_task_rows = _fetch_rows('task')
    legacy_item_rows = _fetch_rows('task_item')
    modern_comment_rows = _fetch_rows('task_comment')
    legacy_comment_rows = _fetch_rows('task_item_comment')
    modern_anexo_rows = _fetch_rows('task_anexo')
    legacy_anexo_rows = _fetch_rows('task_item_anexo')
    existing_redirect_rows = _fetch_rows('legacy_task_redirect')

    fallback_user_id = _resolve_fallback_user_id()
    if (existing_task_rows or legacy_item_rows) and fallback_user_id is None:
        raise RuntimeError("Tabela `user` sem registros: impossível definir created_by_id.")

    task_rows_by_id = {
        _coerce_int(row['id']): row
        for row in existing_task_rows
        if _coerce_int(row.get('id')) is not None
    }
    anchor_ids = {
        _coerce_int(row.get('task_id'))
        for row in legacy_item_rows
        if _coerce_int(row.get('task_id')) is not None
    }
    anchor_ids.discard(None)

    standalone_rows = []
    for row in existing_task_rows:
        row_id = _coerce_int(row.get('id'))
        if row_id is None:
            continue
        if row_id in anchor_ids:
            continue
        standalone_rows.append(row)

    legacy_item_ids = {
        _coerce_int(row['id'])
        for row in legacy_item_rows
        if _coerce_int(row.get('id')) is not None
    }
    legacy_item_ids.discard(None)

    standalone_id_map = _allocate_ids(
        [
            _coerce_int(row['id'])
            for row in standalone_rows
            if _coerce_int(row.get('id')) is not None
        ],
        legacy_item_ids,
    )

    final_task_rows = []
    final_task_ids = set()
    standalone_project_by_old_id = {}

    for row in standalone_rows:
        old_id = _coerce_int(row.get('id'))
        if old_id is None:
            continue
        standalone_project_by_old_id[old_id] = _coerce_int(row.get('project_id'))
        payload = _normalize_task_payload(
            row,
            fallback_user_id,
            preserve_legacy_parent=True,
            legacy_parent_task_id=row.get('legacy_parent_task_id'),
        )
        payload['id'] = standalone_id_map[old_id]
        final_task_rows.append(payload)
        final_task_ids.add(payload['id'])

    anchor_items = defaultdict(list)
    for row in legacy_item_rows:
        anchor_id = _coerce_int(row.get('task_id'))
        item_id = _coerce_int(row.get('id'))
        if anchor_id is None or item_id is None:
            continue
        anchor_items[anchor_id].append(item_id)

        anchor_row = task_rows_by_id.get(anchor_id, {})
        payload = _normalize_task_payload(
            {
                'descricao': row.get('descricao'),
                'status': row.get('status'),
                'responsavel': row.get('responsavel'),
                'ordem': row.get('ordem'),
                'project_id': anchor_row.get('project_id'),
                'created_by_id': anchor_row.get('created_by_id'),
                'created_at': row.get('created_at') or anchor_row.get('created_at'),
                'prioridade': row.get('prioridade'),
                'tipo_pedido': row.get('tipo_pedido'),
                'is_archived': anchor_row.get('is_archived', anchor_row.get('is_finalized')),
                'archived_at': anchor_row.get('archived_at', anchor_row.get('finalized_at')),
            },
            fallback_user_id,
        )
        payload['id'] = item_id
        final_task_rows.append(payload)
        final_task_ids.add(item_id)

    standalone_old_to_new = {
        old_id: new_id
        for old_id, new_id in standalone_id_map.items()
        if old_id != new_id
    }
    anchor_sample_map = {
        anchor_id: min(item_ids)
        for anchor_id, item_ids in anchor_items.items()
        if item_ids
    }

    task_reference_map = {}
    task_reference_map.update({old_id: new_id for old_id, new_id in standalone_id_map.items()})
    task_reference_map.update(anchor_sample_map)

    standalone_task_id_values = [
        _coerce_int(row['id'])
        for row in modern_comment_rows
        if _coerce_int(row.get('id')) is not None
    ]
    legacy_comment_id_values = {
        _coerce_int(row['id'])
        for row in legacy_comment_rows
        if _coerce_int(row.get('id')) is not None
    }
    legacy_comment_id_values.discard(None)
    modern_comment_id_map = _allocate_ids(standalone_task_id_values, legacy_comment_id_values)

    standalone_anexo_id_values = [
        _coerce_int(row['id'])
        for row in modern_anexo_rows
        if _coerce_int(row.get('id')) is not None
    ]
    legacy_anexo_id_values = {
        _coerce_int(row['id'])
        for row in legacy_anexo_rows
        if _coerce_int(row.get('id')) is not None
    }
    legacy_anexo_id_values.discard(None)
    modern_anexo_id_map = _allocate_ids(standalone_anexo_id_values, legacy_anexo_id_values)

    final_comment_rows = []
    for row in modern_comment_rows:
        old_comment_id = _coerce_int(row.get('id'))
        old_task_id = _coerce_int(row.get('task_id'))
        if old_comment_id is None:
            continue
        new_task_id = task_reference_map.get(old_task_id)
        if new_task_id is None:
            continue
        final_comment_rows.append(
            {
                'id': modern_comment_id_map[old_comment_id],
                'content': row.get('content') or '',
                'user_id': _coerce_int(row.get('user_id')),
                'task_id': new_task_id,
                'created_at': _resolve_created_at(row.get('created_at')),
                'updated_at': row.get('updated_at'),
            }
        )

    for row in legacy_comment_rows:
        comment_id = _coerce_int(row.get('id'))
        task_id = _coerce_int(row.get('task_item_id'))
        if comment_id is None or task_id is None:
            continue
        if task_id not in final_task_ids:
            continue
        final_comment_rows.append(
            {
                'id': comment_id,
                'content': row.get('content') or '',
                'user_id': _coerce_int(row.get('user_id')),
                'task_id': task_id,
                'created_at': _resolve_created_at(row.get('created_at')),
                'updated_at': row.get('updated_at'),
            }
        )

    final_anexo_rows = []
    for row in modern_anexo_rows:
        old_anexo_id = _coerce_int(row.get('id'))
        old_task_id = _coerce_int(row.get('task_id'))
        if old_anexo_id is None:
            continue
        new_task_id = task_reference_map.get(old_task_id)
        if new_task_id is None:
            continue
        final_anexo_rows.append(
            {
                'id': modern_anexo_id_map[old_anexo_id],
                'task_id': new_task_id,
                'filename': row.get('filename') or '',
                'stored_filename': row.get('stored_filename') or '',
                'content_type': row.get('content_type'),
                'uploaded_by_id': _coerce_int(row.get('uploaded_by_id')),
                'created_at': _resolve_created_at(row.get('created_at')),
            }
        )

    for row in legacy_anexo_rows:
        anexo_id = _coerce_int(row.get('id'))
        task_id = _coerce_int(row.get('task_item_id'))
        if anexo_id is None or task_id is None:
            continue
        if task_id not in final_task_ids:
            continue
        final_anexo_rows.append(
            {
                'id': anexo_id,
                'task_id': task_id,
                'filename': row.get('filename') or '',
                'stored_filename': row.get('stored_filename') or '',
                'content_type': row.get('content_type'),
                'uploaded_by_id': _coerce_int(row.get('uploaded_by_id')),
                'created_at': _resolve_created_at(row.get('created_at')),
            }
        )

    redirects_by_legacy_id = {}
    redirect_old_ids = [
        _coerce_int(row['id'])
        for row in existing_redirect_rows
        if _coerce_int(row.get('id')) is not None
    ]
    next_redirect_id = max(redirect_old_ids or [0])

    def add_redirect(legacy_task_id, project_id, sample_task_id, created_at=None):
        nonlocal next_redirect_id
        legacy_task_id = _coerce_int(legacy_task_id)
        sample_task_id = _coerce_int(sample_task_id)
        if legacy_task_id is None or sample_task_id is None:
            return
        redirects_by_legacy_id[legacy_task_id] = {
            'legacy_task_id': legacy_task_id,
            'project_id': _coerce_int(project_id),
            'sample_task_id': sample_task_id,
            'created_at': created_at or utc_now(),
        }

    for row in existing_redirect_rows:
        sample_task_id = task_reference_map.get(
            _coerce_int(row.get('sample_task_id')),
            _coerce_int(row.get('sample_task_id')),
        )
        add_redirect(
            row.get('legacy_task_id'),
            row.get('project_id'),
            sample_task_id,
            created_at=row.get('created_at'),
        )

    for anchor_id, sample_task_id in anchor_sample_map.items():
        anchor_row = task_rows_by_id.get(anchor_id, {})
        add_redirect(
            anchor_id,
            anchor_row.get('project_id'),
            sample_task_id,
        )

    for old_id, new_id in standalone_old_to_new.items():
        add_redirect(
            old_id,
            standalone_project_by_old_id.get(old_id),
            new_id,
        )

    final_redirect_rows = []
    for legacy_task_id in sorted(redirects_by_legacy_id):
        next_redirect_id += 1
        row = redirects_by_legacy_id[legacy_task_id]
        row['id'] = next_redirect_id
        final_redirect_rows.append(row)

    return {
        'task_rows': sorted(final_task_rows, key=lambda row: row['id']),
        'comment_rows': sorted(final_comment_rows, key=lambda row: row['id']),
        'anexo_rows': sorted(final_anexo_rows, key=lambda row: row['id']),
        'redirect_rows': sorted(final_redirect_rows, key=lambda row: row['id']),
        'legacy_tables_present': any(anchor_items) or any(_fetch_rows(table_name) for table_name in LEGACY_TASK_TABLES),
        'standalone_tasks_remapped': len(standalone_old_to_new),
        'legacy_items_promoted': len(legacy_item_rows),
    }


def _insert_task_rebuild_payload(payload):
    _create_task_temp_tables()

    if payload['task_rows']:
        db.session.execute(
            text(
                """
                INSERT INTO task__migration_tmp (
                    id, descricao, status, responsavel, ordem, project_id,
                    created_by_id, created_at, prioridade, tipo_pedido,
                    is_archived, archived_at, legacy_parent_task_id
                ) VALUES (
                    :id, :descricao, :status, :responsavel, :ordem, :project_id,
                    :created_by_id, :created_at, :prioridade, :tipo_pedido,
                    :is_archived, :archived_at, :legacy_parent_task_id
                )
                """
            ),
            payload['task_rows'],
        )

    if payload['comment_rows']:
        db.session.execute(
            text(
                """
                INSERT INTO task_comment__migration_tmp (
                    id, content, user_id, task_id, created_at, updated_at
                ) VALUES (
                    :id, :content, :user_id, :task_id, :created_at, :updated_at
                )
                """
            ),
            payload['comment_rows'],
        )

    if payload['anexo_rows']:
        db.session.execute(
            text(
                """
                INSERT INTO task_anexo__migration_tmp (
                    id, task_id, filename, stored_filename, content_type,
                    uploaded_by_id, created_at
                ) VALUES (
                    :id, :task_id, :filename, :stored_filename, :content_type,
                    :uploaded_by_id, :created_at
                )
                """
            ),
            payload['anexo_rows'],
        )

    if payload['redirect_rows']:
        db.session.execute(
            text(
                """
                INSERT INTO legacy_task_redirect__migration_tmp (
                    id, legacy_task_id, project_id, sample_task_id, created_at
                ) VALUES (
                    :id, :legacy_task_id, :project_id, :sample_task_id, :created_at
                )
                """
            ),
            payload['redirect_rows'],
        )

    db.session.flush()


def _promote_task_temp_tables():
    _disable_foreign_keys()
    db.session.flush()

    for table_name in (
        'task_comment',
        'task_anexo',
        'legacy_task_redirect',
        'task_item_comment',
        'task_item_anexo',
        'task_item',
        'task',
    ):
        _drop_table_if_exists(table_name)

    db.session.execute(text('ALTER TABLE task__migration_tmp RENAME TO task'))
    db.session.execute(text('ALTER TABLE task_comment__migration_tmp RENAME TO task_comment'))
    db.session.execute(text('ALTER TABLE task_anexo__migration_tmp RENAME TO task_anexo'))
    db.session.execute(text('ALTER TABLE legacy_task_redirect__migration_tmp RENAME TO legacy_task_redirect'))
    _enable_foreign_keys()
    db.session.commit()


def _ensure_runtime_indexes():
    inspector = inspect(db.engine)

    if _table_exists(inspector, 'task'):
        for index_name, ddl in TASK_INDEXES.items():
            if index_name not in _index_names(inspector, 'task'):
                db.session.execute(text(ddl))
                db.session.commit()
                inspector = inspect(db.engine)

    if _table_exists(inspector, 'task_comment'):
        if 'ix_task_comment_task_id' not in _index_names(inspector, 'task_comment'):
            db.session.execute(text(TASK_COMMENT_INDEX))
            db.session.commit()
            inspector = inspect(db.engine)

    if _table_exists(inspector, 'task_anexo'):
        if 'ix_task_anexo_task_id' not in _index_names(inspector, 'task_anexo'):
            db.session.execute(text(TASK_ANEXO_INDEX))
            db.session.commit()
            inspector = inspect(db.engine)

    if _table_exists(inspector, 'user_notification'):
        for index_name, ddl in USER_NOTIFICATION_INDEXES.items():
            if index_name not in _index_names(inspector, 'user_notification'):
                db.session.execute(text(ddl))
                db.session.commit()
                inspector = inspect(db.engine)


def _migrate_user_areas_step(emit_output=True):
    _emit("\n-- [1/7] Iniciando migração de áreas de usuários...", emit_output)
    migrated_count = 0
    auth_columns_added = []
    auth_indexes_added = []
    try:
        db.create_all()

        inspector = inspect(db.engine)
        if not _table_exists(inspector, 'user'):
            _emit("   ✓ Tabela 'user' não encontrada; nada para migrar.", emit_output)
            return {
                'success': True,
                'migrated_count': 0,
                'auth_columns_added': auth_columns_added,
                'auth_indexes_added': auth_indexes_added,
            }

        user_columns = _column_names(inspector, 'user')
        for column_name, column_type in USER_AUTH_COLUMNS:
            if column_name in user_columns:
                continue
            db.session.execute(text(f'ALTER TABLE `user` ADD COLUMN {column_name} {column_type}'))
            auth_columns_added.append(f'user.{column_name}')
            inspector = inspect(db.engine)
            user_columns = _column_names(inspector, 'user')

        if auth_columns_added:
            db.session.commit()
            _emit(
                f"   ✓ Colunas de auth gov.br garantidas: {', '.join(auth_columns_added)}",
                emit_output,
            )

        inspector = inspect(db.engine)
        user_indexes = _index_names(inspector, 'user')
        for index_name, index_payload in USER_AUTH_INDEXES.items():
            if index_name in user_indexes:
                continue
            compatible_names = index_payload.get('compatible_names', set())
            if any(compatible_name in user_indexes for compatible_name in compatible_names):
                continue
            db.session.execute(text(index_payload['ddl']))
            auth_indexes_added.append(index_name)
            db.session.commit()
            inspector = inspect(db.engine)
            user_indexes = _index_names(inspector, 'user')

        if auth_indexes_added:
            _emit(
                f"   ✓ Índices de auth gov.br garantidos: {', '.join(auth_indexes_added)}",
                emit_output,
            )

        if 'area_responsavel' not in _column_names(inspector, 'user'):
            _emit("   ✓ Coluna legada 'user.area_responsavel' não existe; nada para migrar.", emit_output)
            return {
                'success': True,
                'migrated_count': migrated_count,
                'auth_columns_added': auth_columns_added,
                'auth_indexes_added': auth_indexes_added,
            }

        user_table = Table('user', MetaData(), autoload_with=db.engine)
        existing_links = {
            (user_id, area)
            for user_id, area in db.session.query(UserArea.user_id, UserArea.area).all()
        }

        for user_id, legacy_area in db.session.execute(
            select(user_table.c.id, user_table.c.area_responsavel)
        ).all():
            normalized_area = (legacy_area or '').strip()
            if not normalized_area:
                continue
            if (user_id, normalized_area) in existing_links:
                continue
            db.session.add(UserArea(user_id=user_id, area=normalized_area))
            existing_links.add((user_id, normalized_area))
            migrated_count += 1

        db.session.commit()
        _emit(f"   ✓ Sucesso: {migrated_count} novas áreas foram migradas.", emit_output)
        return {
            'success': True,
            'migrated_count': migrated_count,
            'auth_columns_added': auth_columns_added,
            'auth_indexes_added': auth_indexes_added,
        }
    except Exception as exc:
        db.session.rollback()
        _emit(f"   ✗ ERRO na migração de áreas: {exc}", emit_output)
        return {
            'success': False,
            'migrated_count': migrated_count,
            'auth_columns_added': auth_columns_added,
            'auth_indexes_added': auth_indexes_added,
        }


def migrate_user_areas(emit_output=True):
    return _migrate_user_areas_step(emit_output=emit_output)['success']


def ensure_project_history_table(emit_output=True):
    _emit("\n-- [2/7] Garantindo tabela de histórico de projetos...", emit_output)
    try:
        db.create_all()
        _emit("   ✓ Tabela 'project_history' pronta.", emit_output)
        return {'success': True}
    except Exception as exc:
        db.session.rollback()
        _emit(f"   ✗ ERRO ao garantir histórico de projetos: {exc}", emit_output)
        return {'success': False}


def create_history_table(emit_output=True):
    _emit("\n-- [2/7] Iniciando criação da tabela de histórico de projetos...", emit_output)
    try:
        db.create_all()

        project = Project.query.first()
        user = User.query.first()
        if project and user:
            db.session.add(
                ProjectHistory(
                    project_id=project.id,
                    user_id=user.id,
                    action_type='migration',
                    action_description='Sistema de histórico instalado com sucesso!',
                    timestamp=utc_now(),
                )
            )

        db.session.commit()
        _emit("   ✓ Sucesso: Tabela 'project_history' criada e verificada.", emit_output)
        return True
    except Exception as exc:
        db.session.rollback()
        _emit(f"   ✗ ERRO na criação da tabela de histórico: {exc}", emit_output)
        return False


def ensure_project_columns(emit_output=True):
    _emit("\n-- [3/7] Garantindo colunas de projeto e etapa...", emit_output)
    added_columns = []
    try:
        db.create_all()
        inspector = inspect(db.engine)

        if _table_exists(inspector, 'project'):
            for column_name, column_type in PROJECT_COLUMNS:
                if column_name in _column_names(inspector, 'project'):
                    continue
                db.session.execute(
                    text(f'ALTER TABLE project ADD COLUMN {column_name} {column_type}')
                )
                added_columns.append(f'project.{column_name}')
                inspector = inspect(db.engine)

        if _table_exists(inspector, 'etapa') and 'ordem' not in _column_names(inspector, 'etapa'):
            db.session.execute(text('ALTER TABLE etapa ADD COLUMN ordem INTEGER NOT NULL DEFAULT 0'))
            added_columns.append('etapa.ordem')

        db.session.commit()
        if added_columns:
            _emit(f"   ✓ Colunas garantidas: {', '.join(added_columns)}", emit_output)
        else:
            _emit("   ✓ Nenhuma coluna pendente encontrada.", emit_output)
        return {'success': True, 'added_columns': added_columns}
    except Exception as exc:
        db.session.rollback()
        _emit(f'   ✗ ERRO ao garantir colunas de projeto/etapa: {exc}', emit_output)
        return {'success': False, 'added_columns': added_columns}


def ensure_abep_indicator_column(emit_output=True):
    _emit("\n-- [4/7] Verificando coluna project.abep_indicator...", emit_output)
    try:
        result = ensure_project_columns(emit_output=False)
        if not result['success']:
            return False
        if 'project.abep_indicator' in result['added_columns']:
            _emit("   ✓ Coluna 'abep_indicator' criada com sucesso.", emit_output)
        else:
            _emit("   ✓ Coluna 'abep_indicator' ja existe.", emit_output)
        return True
    except Exception as exc:
        db.session.rollback()
        _emit(f'   ✗ ERRO ao criar coluna abep_indicator: {exc}', emit_output)
        return False


def ensure_task_schema(emit_output=True):
    _emit("\n-- [5/7] Consolidando schema de tarefas...", emit_output)
    changes = []
    try:
        db.create_all()
        inspector = inspect(db.engine)

        if not _table_exists(inspector, 'task') and not any(
            _table_exists(inspector, table_name) for table_name in LEGACY_TASK_TABLES
        ):
            _ensure_runtime_indexes()
            _emit("   ✓ Tabelas de tarefas já estavam ausentes e foram criadas quando necessário.", emit_output)
            return {'success': True, 'changes': changes}

        if _task_schema_requires_rebuild(inspector):
            payload = _prepare_task_rebuild_payload()
            _insert_task_rebuild_payload(payload)
            _promote_task_temp_tables()
            changes.append('task.rebuilt_task_only')
            if payload['legacy_items_promoted']:
                changes.append('task.migrated_legacy_items')
            if payload['standalone_tasks_remapped']:
                changes.append('task.remapped_standalone_ids')
        else:
            status_updates = []
            for old_status, new_status in STATUS_RENAMES.items():
                updated = db.session.execute(
                    text(
                        'UPDATE task SET status = :new_status WHERE status = :old_status'
                    ),
                    {'new_status': new_status, 'old_status': old_status},
                )
                if updated.rowcount:
                    status_updates.append(f'{old_status}->{new_status}')
            if status_updates:
                db.session.commit()
                changes.append('task.status_values_normalized')

        inspector = inspect(db.engine)
        if _table_exists(inspector, 'task'):
            for required_column, column_sql in (
                ('legacy_parent_task_id', 'ALTER TABLE task ADD COLUMN legacy_parent_task_id INTEGER'),
                ('prioridade', 'ALTER TABLE task ADD COLUMN prioridade VARCHAR(20)'),
                ('tipo_pedido', 'ALTER TABLE task ADD COLUMN tipo_pedido VARCHAR(30)'),
                ('is_archived', 'ALTER TABLE task ADD COLUMN is_archived BOOLEAN NOT NULL DEFAULT 0'),
                ('archived_at', 'ALTER TABLE task ADD COLUMN archived_at DATETIME'),
            ):
                if required_column in _column_names(inspector, 'task'):
                    continue
                db.session.execute(text(column_sql))
                changes.append(f'task.{required_column}')
                inspector = inspect(db.engine)
            db.session.commit()

        db.create_all()
        _ensure_runtime_indexes()

        inspector = inspect(db.engine)
        if any(_table_exists(inspector, table_name) for table_name in LEGACY_TASK_TABLES):
            _disable_foreign_keys()
            for table_name in LEGACY_TASK_TABLES:
                _drop_table_if_exists(table_name)
            _enable_foreign_keys()
            db.session.commit()
            changes.append('task.legacy_tables_dropped')

        if changes:
            _emit(f"   ✓ Ajustes aplicados: {', '.join(changes)}", emit_output)
        else:
            _emit("   ✓ Schema de tarefas já estava consolidado.", emit_output)
        return {'success': True, 'changes': changes}
    except Exception as exc:
        db.session.rollback()
        _enable_foreign_keys()
        _emit(f'   ✗ ERRO ao consolidar schema de tarefas: {exc}', emit_output)
        return {'success': False, 'changes': changes}


def sync_goal_catalog(emit_output=True):
    _emit("\n-- [6/7] Sincronizando catalogo de objetivos/resultados/indicadores...", emit_output)
    try:
        db.create_all()
        summary = sync_goal_catalog_to_db(commit=True)
        _emit(f'   ✓ Sucesso: {summary}', emit_output)
        return {'success': True, 'summary': summary}
    except Exception as exc:
        db.session.rollback()
        _emit(f'   ✗ ERRO na sincronizacao do catalogo: {exc}', emit_output)
        return {'success': False, 'summary': None}


def sync_area_catalog(emit_output=True):
    _emit("\n-- [7/7] Sincronizando catálogo de áreas...", emit_output)
    try:
        db.create_all()
        areas = ensure_area_catalog_seeded()
        _emit(f"   ✓ Sucesso: catálogo com {len(areas)} área(s).", emit_output)
        return {'success': True, 'areas': areas}
    except Exception as exc:
        db.session.rollback()
        _emit(f'   ✗ ERRO ao sincronizar catálogo de áreas: {exc}', emit_output)
        return {'success': False, 'areas': None}


def ensure_calendar_schema(emit_output=True):
    _emit("\n-- [8/8] Garantindo schema do calendário...", emit_output)
    changes = []
    try:
        db.create_all()
        inspector = inspect(db.engine)

        for table_name, required_columns in {**STAGE_INCREMENTAL_COLUMNS, **CALENDAR_INCREMENTAL_COLUMNS}.items():
            if not _table_exists(inspector, table_name):
                continue
            table_columns = _column_names(inspector, table_name)
            for column_name, column_sql_type in required_columns:
                if column_name in table_columns:
                    continue
                db.session.execute(
                    text(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql_type}')
                )
                changes.append(f'{table_name}.{column_name}')
                inspector = inspect(db.engine)
                table_columns = _column_names(inspector, table_name)

        db.session.commit()
        if changes:
            _emit(f"   ✓ Ajustes aplicados: {', '.join(changes)}", emit_output)
        else:
            _emit('   ✓ Schema do calendário já estava atualizado.', emit_output)
        return {'success': True, 'changes': changes}
    except Exception as exc:
        db.session.rollback()
        _emit(f'   ✗ ERRO ao garantir schema do calendário: {exc}', emit_output)
        return {'success': False, 'changes': changes}


def stamp_alembic_head(emit_output=True):
    if db.engine.dialect.name != 'mysql':
        return {'success': True, 'stamped': False}

    _emit("\n-- [extra] Sincronizando alembic_version com o schema final...", emit_output)
    try:
        inspector = inspect(db.engine)
        if not _table_exists(inspector, 'alembic_version'):
            db.session.execute(
                text(
                    """
                    CREATE TABLE alembic_version (
                        version_num VARCHAR(32) NOT NULL PRIMARY KEY
                    )
                    """
                )
            )
            db.session.commit()

        current_version = db.session.execute(
            text('SELECT version_num FROM alembic_version LIMIT 1')
        ).scalar()
        if current_version == ALEMBIC_HEAD:
            _emit(f'   ✓ Alembic já estava em {ALEMBIC_HEAD}.', emit_output)
            return {'success': True, 'stamped': False}

        db.session.execute(text('DELETE FROM alembic_version'))
        db.session.execute(
            text('INSERT INTO alembic_version (version_num) VALUES (:version_num)'),
            {'version_num': ALEMBIC_HEAD},
        )
        db.session.commit()
        _emit(f'   ✓ Alembic marcado em {ALEMBIC_HEAD}.', emit_output)
        return {'success': True, 'stamped': True}
    except Exception as exc:
        db.session.rollback()
        _emit(f'   ✗ ERRO ao sincronizar alembic_version: {exc}', emit_output)
        return {'success': False, 'stamped': False}


def run_all_migrations(*, emit_output=True, stamp_alembic=False):
    steps = [
        _migrate_user_areas_step(emit_output=emit_output),
        ensure_project_history_table(emit_output=emit_output),
        ensure_project_columns(emit_output=emit_output),
        ensure_task_schema(emit_output=emit_output),
        sync_goal_catalog(emit_output=emit_output),
        sync_area_catalog(emit_output=emit_output),
        ensure_calendar_schema(emit_output=emit_output),
    ]

    if not all(step.get('success') for step in steps):
        return {'success': False}

    alembic_summary = {'success': True, 'stamped': False}
    if stamp_alembic:
        alembic_summary = stamp_alembic_head(emit_output=emit_output)
        if not alembic_summary['success']:
            return {'success': False}

    project_columns_added = steps[2]['added_columns']
    task_changes = steps[3]['changes']
    calendar_changes = steps[6]['changes']

    return {
        'success': True,
        'column_added': 'project.abep_indicator' in project_columns_added,
        'task_core_cols': task_changes,
        'calendar_changes': calendar_changes,
        'area_catalog_choices': steps[5]['areas'],
        'sync_summary': steps[4]['summary'],
        'user_areas_migrated': steps[0]['migrated_count'],
        'user_auth_columns_added': steps[0].get('auth_columns_added', []),
        'user_auth_indexes_added': steps[0].get('auth_indexes_added', []),
        'project_columns_added': project_columns_added,
        'alembic_stamped': alembic_summary['stamped'],
    }


def main():
    from app import app

    with app.app_context():
        _emit('=' * 60)
        _emit('INICIANDO SCRIPT UNIFICADO DE MIGRAÇÃO DE BANCO')
        _emit('=' * 60)

        summary = run_all_migrations(
            emit_output=True,
            stamp_alembic=(db.engine.dialect.name == 'mysql'),
        )
        if not summary.get('success'):
            _emit('\n!! Migração interrompida devido a um erro.')
            return 1

        _emit('\n' + '=' * 60)
        _emit('TODAS AS MIGRAÇÕES FORAM CONCLUÍDAS COM SUCESSO!')
        _emit('=' * 60)
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
