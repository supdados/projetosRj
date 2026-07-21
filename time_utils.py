import datetime
import sqlite3

_SQLITE_ADAPTERS_REGISTERED = False


def utc_now():
    """Retorna UTC naive para manter compatibilidade com colunas DateTime legadas."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def iso_utc(value):
    """ISO 8601 com fuso EXPLÍCITO para datetimes; ``None`` passa direto.

    As colunas legadas guardam UTC naive (``utc_now``); serializar com
    ``isoformat()`` puro produz string sem offset, que o ``new Date()`` do
    browser interpreta como hora LOCAL — exibindo o dígito UTC cru (+3h no
    Brasil). Aqui o datetime naive é assumido UTC e ganha sufixo ``Z``;
    aware é convertido para UTC. ``date`` puro sai como ``YYYY-MM-DD``.

    Exemplo: ``iso_utc(utc_now())`` -> ``"2026-07-16T18:27:00.123456Z"``.
    """
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=datetime.timezone.utc)
        else:
            value = value.astimezone(datetime.timezone.utc)
        return value.isoformat().replace("+00:00", "Z")
    return value.isoformat()


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
    if days < 28:
        weeks = days // 7
        return f'há {weeks} semana{"s" if weeks != 1 else ""}'
    # max(1, ...) evita "há 0 meses" na faixa 28-29 dias (bucket sai das semanas antes de fechar 30)
    if days < 360:
        months = max(1, days // 30)
        return f'há {months} {"mês" if months == 1 else "meses"}'
    years = max(1, days // 365)
    return f'há {years} ano{"s" if years != 1 else ""}'
