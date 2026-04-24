"""Criptografia simétrica para campos sensíveis (tokens OAuth, futuramente CPF).

Usa Fernet (AES-128-CBC + HMAC-SHA256) com chave derivada do `SECRET_KEY` via
SHA-256. A intenção é proteger os dados em repouso no banco: se o dump for
vazado, os tokens seguem opacos sem acesso ao `SECRET_KEY`.

Expõe um `EncryptedText` (SQLAlchemy TypeDecorator) para uso transparente nos
modelos — a aplicação continua lendo/escrevendo strings comuns.
"""

import base64
import hashlib
import os
import threading

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.types import Text, TypeDecorator

_FERNET_PREFIX = (
    "gAAAAA"  # Token Fernet em base64 começa com esse marcador (versão 0x80).
)
_fernet_cache = {}
_fernet_cache_lock = threading.Lock()


def _derive_fernet_key(secret_key: str) -> bytes:
    digest = hashlib.sha256(secret_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _get_fernet() -> Fernet:
    """Resolve o Fernet a partir do SECRET_KEY atual.

    Prefere `current_app.config['SECRET_KEY']` quando dentro de contexto Flask;
    cai para env var `SECRET_KEY` fora do contexto (scripts de migração).
    """
    secret = None
    try:
        from flask import current_app

        secret = current_app.config.get("SECRET_KEY")
    except Exception:
        secret = None

    if not secret:
        secret = os.getenv("SECRET_KEY", "").strip()

    if not secret:
        raise RuntimeError(
            "SECRET_KEY indisponível — necessário para criptografar campos sensíveis."
        )

    with _fernet_cache_lock:
        cached = _fernet_cache.get(secret)
        if cached is not None:
            return cached
        fernet = Fernet(_derive_fernet_key(secret))
        _fernet_cache[secret] = fernet
        return fernet


def looks_like_fernet(value: str) -> bool:
    if not value or not isinstance(value, str):
        return False
    return value.startswith(_FERNET_PREFIX)


def encrypt_value(plaintext: str) -> str:
    if plaintext is None:
        return None
    if not isinstance(plaintext, str):
        plaintext = str(plaintext)
    token = _get_fernet().encrypt(plaintext.encode("utf-8"))
    return token.decode("ascii")


def decrypt_value(ciphertext: str) -> str:
    if ciphertext is None:
        return None
    if not looks_like_fernet(ciphertext):
        # Compat: valor em plaintext legado (pré-migração). Retorna como está para
        # não quebrar o fluxo; o startup migra para ciphertext posteriormente.
        return ciphertext
    try:
        return _get_fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken:
        # Se o SECRET_KEY mudou, o valor antigo é irrecuperável. Retorna None
        # para que o fluxo trate como "token ausente" e force nova conexão.
        return None


class EncryptedText(TypeDecorator):
    """Campo texto que armazena ciphertext Fernet mas se comporta como string."""

    impl = Text
    cache_ok = True

    def process_bind_param(
        self, value, dialect
    ):  # noqa: D401 — interface do SQLAlchemy
        if value is None:
            return None
        if looks_like_fernet(value):
            # Já criptografado (ex.: cópia entre registros); não re-encripta.
            return value
        return encrypt_value(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return decrypt_value(value)
