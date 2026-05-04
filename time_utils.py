import datetime
import sqlite3

_SQLITE_ADAPTERS_REGISTERED = False


def utc_now():
    """Retorna UTC naive para manter compatibilidade com colunas DateTime legadas."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def _adapt_sqlite_datetime(value):
    """Serializa datetime sem depender do adaptador padrão depreciado do sqlite3."""
    if value.tzinfo is not None:
        value = value.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return value.isoformat(sep=" ")


def _adapt_sqlite_date(value):
    return value.isoformat()


def register_sqlite_adapters():
    global _SQLITE_ADAPTERS_REGISTERED

    if _SQLITE_ADAPTERS_REGISTERED:
        return

    sqlite3.register_adapter(datetime.datetime, _adapt_sqlite_datetime)
    sqlite3.register_adapter(datetime.date, _adapt_sqlite_date)
    _SQLITE_ADAPTERS_REGISTERED = True


def format_relative_time_pt(value, *, now=None):
    """Retorna descrição humana em pt-BR: "há 2 dias", "há 1 semana", etc.

    Retorna string vazia quando ``value`` é None ou no futuro.
    """
    if value is None:
        return ""
    if isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
        value = datetime.datetime(value.year, value.month, value.day)
    if not isinstance(value, datetime.datetime):
        return ""
    reference = now if now is not None else utc_now()
    if value.tzinfo is not None:
        value = value.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    if reference.tzinfo is not None:
        reference = reference.astimezone(datetime.timezone.utc).replace(tzinfo=None)

    delta = reference - value
    seconds = int(delta.total_seconds())
    if seconds < 0:
        return ""
    if seconds < 60:
        return "há instantes"
    minutes = seconds // 60
    if minutes < 60:
        return f'há {minutes} minuto{"s" if minutes != 1 else ""}'
    hours = minutes // 60
    if hours < 24:
        return f'há {hours} hora{"s" if hours != 1 else ""}'
    days = hours // 24
    if days < 7:
        return f'há {days} dia{"s" if days != 1 else ""}'
    weeks = days // 7
    if weeks < 4:
        return f'há {weeks} semana{"s" if weeks != 1 else ""}'
    months = days // 30
    if months < 12:
        return f'há {months} {"mês" if months == 1 else "meses"}'
    years = days // 365
    return f'há {years} ano{"s" if years != 1 else ""}'
