"""Testes unitários de services/siorg_client.py (HTTP falso, sem rede)."""

from __future__ import annotations

import io
import json
from typing import Any
from urllib.error import HTTPError, URLError

import pytest

from services.siorg_client import (
    SiorgApiError,
    SiorgClient,
    siorg_client_from_config,
)

MANIFESTO_DATA = {
    "versao_global": 7,
    "gerado_em": "2026-07-14T12:00:00Z",
    "total_unidades": 98,
    "hash": "abc123",
    "contrato": "v1",
}
ARVORE_DATA = [
    {"codigo": "2", "codigo_pai": None, "sigla": "SETD", "filhos": []},
]


def _envelope_ok(data: Any) -> bytes:
    return json.dumps({"ok": True, "data": data}).encode("utf-8")


class FakeHttpResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "FakeHttpResponse":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        return None


class FakeUrlopenSucesso:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.requests: list[Any] = []
        self.timeouts: list[Any] = []

    def __call__(self, request: Any, timeout: Any = None) -> FakeHttpResponse:
        self.requests.append(request)
        self.timeouts.append(timeout)
        return FakeHttpResponse(self.body)


class FakeUrlopenErrosDepoisSucesso:
    """Falha com os erros da fila e depois responde com sucesso."""

    def __init__(self, erros: list[Exception], body: bytes) -> None:
        self._erros = list(erros)
        self.body = body
        self.chamadas = 0

    def __call__(self, request: Any, timeout: Any = None) -> FakeHttpResponse:
        self.chamadas += 1
        if self._erros:
            raise self._erros.pop(0)
        return FakeHttpResponse(self.body)


class FakeUrlopenSempreErro:
    def __init__(self, fabrica_erro: Any) -> None:
        self._fabrica_erro = fabrica_erro
        self.chamadas = 0

    def __call__(self, request: Any, timeout: Any = None) -> FakeHttpResponse:
        self.chamadas += 1
        raise self._fabrica_erro()


class FakeSleep:
    def __init__(self) -> None:
        self.esperas: list[float] = []

    def __call__(self, segundos: float) -> None:
        self.esperas.append(segundos)


def _http_error(status: int, body: bytes = b'{"ok": false}') -> HTTPError:
    return HTTPError("http://siorg", status, "erro", None, io.BytesIO(body))


def _client(urlopen_fn: Any, sleep_fn: Any = None) -> SiorgClient:
    return SiorgClient(
        "http://siorg.local:5000/",
        "token-teste",
        timeout_seconds=7,
        urlopen_fn=urlopen_fn,
        sleep_fn=sleep_fn or FakeSleep(),
    )


class TestObterManifesto:
    def test_sucesso_desembrulha_envelope(self):
        fake = FakeUrlopenSucesso(_envelope_ok(MANIFESTO_DATA))
        assert _client(fake).obter_manifesto() == MANIFESTO_DATA

    def test_monta_url_header_bearer_e_timeout(self):
        fake = FakeUrlopenSucesso(_envelope_ok(MANIFESTO_DATA))
        _client(fake).obter_manifesto()
        request = fake.requests[0]
        assert (
            request.full_url == "http://siorg.local:5000/api/publica/v1/sync/manifesto"
        )
        assert request.get_header("Authorization") == "Bearer token-teste"
        assert fake.timeouts == [7]

    def test_data_nao_dict_falha(self):
        fake = FakeUrlopenSucesso(_envelope_ok([1, 2]))
        with pytest.raises(SiorgApiError, match="esperado objeto"):
            _client(fake).obter_manifesto()


class TestObterArvore:
    def test_sucesso_com_codigo_na_url(self):
        fake = FakeUrlopenSucesso(_envelope_ok(ARVORE_DATA))
        assert _client(fake).obter_arvore(2) == ARVORE_DATA
        assert fake.requests[0].full_url == (
            "http://siorg.local:5000/api/publica/v1/unidades/2/arvore"
        )

    def test_codigo_raiz_invalido_falha_sem_http(self):
        fake = FakeUrlopenSucesso(_envelope_ok(ARVORE_DATA))
        with pytest.raises(SiorgApiError, match="codigo_raiz inválido"):
            _client(fake).obter_arvore("abc")
        assert fake.requests == []

    def test_data_nao_lista_falha(self):
        fake = FakeUrlopenSucesso(_envelope_ok({"codigo": "2"}))
        with pytest.raises(SiorgApiError, match="esperada lista"):
            _client(fake).obter_arvore(2)


class TestRetry:
    def test_503_faz_retry_com_backoff_e_sucede(self):
        fake = FakeUrlopenErrosDepoisSucesso(
            [_http_error(503), _http_error(503)], _envelope_ok(MANIFESTO_DATA)
        )
        sleep = FakeSleep()
        assert _client(fake, sleep).obter_manifesto() == MANIFESTO_DATA
        assert fake.chamadas == 3
        assert sleep.esperas == [0.5, 1.0]

    def test_503_persistente_falha_apos_3_tentativas(self):
        fake = FakeUrlopenSempreErro(lambda: _http_error(503, b"indisponivel"))
        sleep = FakeSleep()
        with pytest.raises(SiorgApiError) as exc_info:
            _client(fake, sleep).obter_manifesto()
        assert fake.chamadas == 3
        assert sleep.esperas == [0.5, 1.0]
        assert exc_info.value.status_code == 503
        assert exc_info.value.response_body == "indisponivel"

    def test_401_falha_direto_sem_retry(self):
        fake = FakeUrlopenSempreErro(lambda: _http_error(401))
        sleep = FakeSleep()
        with pytest.raises(SiorgApiError) as exc_info:
            _client(fake, sleep).obter_manifesto()
        assert fake.chamadas == 1
        assert sleep.esperas == []
        assert exc_info.value.status_code == 401

    def test_timeout_de_rede_faz_retry_e_falha(self):
        fake = FakeUrlopenSempreErro(lambda: URLError(TimeoutError("timed out")))
        sleep = FakeSleep()
        with pytest.raises(SiorgApiError, match="Falha de rede") as exc_info:
            _client(fake, sleep).obter_manifesto()
        assert fake.chamadas == 3
        assert sleep.esperas == [0.5, 1.0]
        assert exc_info.value.status_code is None

    def test_timeout_error_direto_faz_retry_e_depois_sucede(self):
        fake = FakeUrlopenErrosDepoisSucesso(
            [TimeoutError("timed out")], _envelope_ok(MANIFESTO_DATA)
        )
        assert _client(fake).obter_manifesto() == MANIFESTO_DATA
        assert fake.chamadas == 2


class TestEnvelope:
    def test_corpo_nao_json_falha(self):
        fake = FakeUrlopenSucesso(b"<html>erro</html>")
        with pytest.raises(SiorgApiError, match="não é JSON válido"):
            _client(fake).obter_manifesto()

    def test_envelope_sem_ok_true_falha(self):
        fake = FakeUrlopenSucesso(json.dumps({"ok": False, "error": {}}).encode())
        with pytest.raises(SiorgApiError, match="Envelope inesperado"):
            _client(fake).obter_manifesto()


class TestFactory:
    def test_le_chaves_siorg_do_config(self):
        client = siorg_client_from_config(
            {
                "SIORG_BASE_URL": "http://siorg.rj.gov.br/",
                "SIORG_API_KEY": "chave-prod",
                "SIORG_TIMEOUT_SECONDS": 15,
            }
        )
        assert client._base_url == "http://siorg.rj.gov.br"
        assert client._api_key == "chave-prod"
        assert client._timeout_seconds == 15

    def test_sem_api_key_falha(self):
        with pytest.raises(SiorgApiError, match="SIORG_API_KEY"):
            siorg_client_from_config({"SIORG_BASE_URL": "http://x"})
