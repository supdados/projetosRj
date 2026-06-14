"""Validação de destino de redirect para evitar Open Redirect (CWE-601).

Espelha `url_has_allowed_host_and_scheme` do Django: um destino só é aceito se
o valor original E a variante com '\\' normalizada para '/' apontarem para o
próprio host. Sem checar as duas formas, vetores como '//evil.com' e
'/\\evil.com' — que os navegadores normalizam para host externo — escapariam.
"""

from urllib.parse import urlparse


def safe_internal_path(raw_target: str | None, current_host: str) -> str | None:
    """Retorna um caminho relativo seguro ao próprio host, ou None.

    Exemplo:
        safe_internal_path("/projetos/5", "projetos.rj.gov.br")  # -> "/projetos/5"
        safe_internal_path("/\\evil.com", "projetos.rj.gov.br")  # -> None
    """
    if not raw_target:
        return None
    value = str(raw_target).strip()
    if not value:
        return None
    if not _targets_host(value, current_host):
        return None
    if not _targets_host(value.replace("\\", "/"), current_host):
        return None
    return _relative_target(value.replace("\\", "/"))


def _targets_host(value: str, current_host: str) -> bool:
    """True se `value` fica no próprio host (sem escapar para outro destino)."""
    parsed = urlparse(value)
    if parsed.scheme and parsed.scheme not in {"http", "https"}:
        return False
    if parsed.netloc:
        return parsed.netloc == current_host
    return value.startswith("/") and not value.startswith("//")


def _relative_target(value: str) -> str | None:
    """Extrai 'path?query' relativo de um destino já validado como seguro."""
    parsed = urlparse(value)
    path = parsed.path or "/"
    if not path.startswith("/"):
        return None
    return f"{path}?{parsed.query}" if parsed.query else path
