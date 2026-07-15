"""Cliente HTTP da API pública do SIORG-RJ (``/api/publica/v1``).

Consome o contrato v1 do SIORG (envelope ``{"ok": true, "data": ...}``) com auth por
API-key (``Authorization: Bearer <token>``). Diferente do padrão single-shot de
``services/google_calendar.py``, este client tem retry com backoff para erros de
rede/5xx — o SIORG é outro serviço nosso e pode estar reiniciando durante um sync.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SIORG_MANIFESTO_PATH = "/api/publica/v1/sync/manifesto"
SIORG_ARVORE_PATH_TEMPLATE = "/api/publica/v1/unidades/{codigo}/arvore"

_MAX_TENTATIVAS = 3
_BACKOFFS_SECONDS = (0.5, 1.0)


class SiorgApiError(RuntimeError):
    """Erro de integração com a API pública do SIORG-RJ."""

    def __init__(
        self,
        mensagem: str,
        *,
        status_code: int | None = None,
        response_body: str | None = None,
    ) -> None:
        super().__init__(mensagem)
        self.status_code = status_code
        self.response_body = response_body


def _decode_body(raw_body: bytes | str | None) -> str:
    if raw_body is None:
        return ""
    if isinstance(raw_body, bytes):
        return raw_body.decode("utf-8", errors="replace")
    return str(raw_body)


def _erro_retriavel(erro: SiorgApiError) -> bool:
    return erro.status_code is None or erro.status_code >= 500


def _extrair_data_do_envelope(body: str, url: str) -> Any:
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise SiorgApiError(
            f"Resposta do SIORG em {url} não é JSON válido: {body[:200]!r} "
            '(esperado envelope {"ok": true, "data": ...}).',
            response_body=body,
        ) from exc
    if (
        not isinstance(parsed, dict)
        or parsed.get("ok") is not True
        or "data" not in parsed
    ):
        raise SiorgApiError(
            f"Envelope inesperado do SIORG em {url}: {body[:200]!r} "
            '(esperado {"ok": true, "data": ...}).',
            response_body=body,
        )
    return parsed["data"]


class SiorgClient:
    """Cliente da API pública do SIORG. ``urlopen_fn``/``sleep_fn`` injetáveis p/ teste."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout_seconds: int = 10,
        *,
        urlopen_fn: Callable[..., Any] = urlopen,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._base_url = str(base_url).strip().rstrip("/")
        self._api_key = str(api_key).strip()
        self._timeout_seconds = timeout_seconds
        self._urlopen_fn = urlopen_fn
        self._sleep_fn = sleep_fn

    def obter_manifesto(self) -> dict[str, Any]:
        data = self._get_data(SIORG_MANIFESTO_PATH)
        if not isinstance(data, dict):
            raise SiorgApiError(
                f"Manifesto do SIORG veio como {type(data).__name__} "
                "(esperado objeto com versao_global/gerado_em/total_unidades/hash)."
            )
        return data

    def obter_arvore(self, codigo_raiz: int) -> list[dict[str, Any]]:
        codigo = self._validar_codigo_raiz(codigo_raiz)
        data = self._get_data(SIORG_ARVORE_PATH_TEMPLATE.format(codigo=codigo))
        if not isinstance(data, list):
            raise SiorgApiError(
                f"Árvore do SIORG veio como {type(data).__name__} "
                "(esperada lista de nós aninhados com 'filhos')."
            )
        return data

    @staticmethod
    def _validar_codigo_raiz(codigo_raiz: int) -> int:
        try:
            return int(codigo_raiz)
        except (TypeError, ValueError) as exc:
            raise SiorgApiError(
                f"codigo_raiz inválido: {codigo_raiz!r} (esperado inteiro, ex.: 2)."
            ) from exc

    def _get_data(self, path: str) -> Any:
        url = f"{self._base_url}{path}"
        body = self._request_with_retry(url)
        return _extrair_data_do_envelope(body, url)

    def _request_with_retry(self, url: str) -> str:
        ultimo_erro: SiorgApiError | None = None
        for tentativa in range(_MAX_TENTATIVAS):
            try:
                return self._request_once(url)
            except SiorgApiError as exc:
                if not _erro_retriavel(exc):
                    raise
                ultimo_erro = exc
                if tentativa < _MAX_TENTATIVAS - 1:
                    self._sleep_fn(_BACKOFFS_SECONDS[tentativa])
        assert ultimo_erro is not None
        raise ultimo_erro

    def _request_once(self, url: str) -> str:
        request = Request(url, headers=self._headers(), method="GET")
        try:
            with self._urlopen_fn(request, timeout=self._timeout_seconds) as response:
                return _decode_body(response.read())
        except HTTPError as exc:
            body = _decode_body(exc.read())
            raise SiorgApiError(
                f"SIORG respondeu HTTP {exc.code} em {url}: {body[:300]}",
                status_code=exc.code,
                response_body=body,
            ) from exc
        except (URLError, TimeoutError) as exc:
            raise SiorgApiError(
                f"Falha de rede ao acessar o SIORG em {url}: {exc}"
            ) from exc

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        }


def siorg_client_from_config(config: Mapping[str, Any]) -> SiorgClient:
    """Constrói o client a partir das chaves ``SIORG_*`` do config do Flask."""
    api_key = str(config.get("SIORG_API_KEY", "") or "").strip()
    if not api_key:
        raise SiorgApiError(
            "SIORG_API_KEY ausente/vazia (esperado token do ApiConsumer do SIORG no .env)."
        )
    return SiorgClient(
        base_url=str(config.get("SIORG_BASE_URL", "http://localhost:5000")),
        api_key=api_key,
        timeout_seconds=int(config.get("SIORG_TIMEOUT_SECONDS", 10)),
    )
