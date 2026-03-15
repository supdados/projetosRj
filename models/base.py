from flask_sqlalchemy import SQLAlchemy
from flask_sqlalchemy.query import Query

db = SQLAlchemy()


def _is_plain_entity_query(query_obj):
    descriptions = getattr(query_obj, 'column_descriptions', ())
    if len(descriptions) != 1:
        return False, None

    entity = descriptions[0].get('entity')
    if entity is None:
        return False, None

    where_criteria = getattr(query_obj, '_where_criteria', ())
    if where_criteria:
        return False, entity

    return True, entity


class _LegacyTaskScopeQuery(Query):
    legacy_parent_scope = None

    def count(self):
        is_plain_query, entity = _is_plain_entity_query(self)
        if not is_plain_query or entity is None:
            return Query.count(self)

        legacy_parent_column = getattr(entity, 'legacy_parent_task_id', None)
        if legacy_parent_column is None:
            return Query.count(self)

        if self.legacy_parent_scope == 'root':
            scoped_query = self.filter(legacy_parent_column.is_(None))
            return Query.count(scoped_query)

        if self.legacy_parent_scope == 'child':
            scoped_query = self.filter(legacy_parent_column.is_not(None))
            return Query.count(scoped_query)

        return Query.count(self)


class TaskQuery(_LegacyTaskScopeQuery):
    legacy_parent_scope = 'root'


class TaskItemQuery(_LegacyTaskScopeQuery):
    legacy_parent_scope = 'child'
