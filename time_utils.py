import datetime
import sqlite3

_SQLITE_ADAPTERS_REGISTERED = False


def utc_now():
    """Retorna UTC naive para manter compatibilidade com colunas DateTime legadas."""
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


def _adapt_sqlite_datetime(value):
    """Serializa datetime sem depender do adaptador padrão depreciado do sqlite3."""
    if value.tzinfo is not None:
        value = value.astimezone(datetime.UTC).replace(tzinfo=None)
    return value.isoformat(sep=' ')


def _adapt_sqlite_date(value):
    return value.isoformat()


def register_sqlite_adapters():
    global _SQLITE_ADAPTERS_REGISTERED

    if _SQLITE_ADAPTERS_REGISTERED:
        return

    sqlite3.register_adapter(datetime.datetime, _adapt_sqlite_datetime)
    sqlite3.register_adapter(datetime.date, _adapt_sqlite_date)
    _SQLITE_ADAPTERS_REGISTERED = True
