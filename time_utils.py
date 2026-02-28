import datetime


def utc_now():
    """Retorna UTC naive para manter compatibilidade com colunas DateTime legadas."""
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
