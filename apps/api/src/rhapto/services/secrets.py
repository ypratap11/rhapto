"""Symmetric encryption for provider API keys stored in Postgres.

A stored key has to come back out in plaintext to call the provider, so this is encryption at
rest, not hashing: Fernet (AES-128-CBC + HMAC) from `cryptography`.

`RHAPTO_SECRET_KEY` is a generated Fernet key and is used verbatim. When it is empty the key is
derived from `RHAPTO_API_TOKEN`, which every deployment already sets, so adding a provider key in
Settings needs no new setup step. The trade-off is explicit: rotating the API token then makes
stored keys unreadable, which `decrypt` reports as such rather than as corrupt data. Setting
`RHAPTO_SECRET_KEY` decouples the two.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from rhapto.config import Settings

GENERATE_HINT = (
    'generate one with: python -c "from cryptography.fernet import Fernet; '
    'print(Fernet.generate_key().decode())"'
)


class SecretsError(Exception):
    """The encryption secret is missing or unusable, or a stored token cannot be read with it."""


class KeyUnreadableError(SecretsError):
    """A stored token does not decrypt with this deployment's secret (the secret changed).

    Separate from the rest because the remedy differs: the user re-enters their key, whereas a
    malformed `RHAPTO_SECRET_KEY` is the operator's to fix and must keep its own message.
    """


def derive_key(secret: str) -> bytes:
    """A Fernet key (32 urlsafe-base64 bytes) derived from an arbitrary secret string."""
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())


def fernet_for(settings: Settings) -> Fernet:
    """The Fernet for this deployment: the configured secret, else one derived from the API token."""
    if settings.rhapto_secret_key:
        try:
            return Fernet(settings.rhapto_secret_key.encode())
        except (ValueError, TypeError) as exc:
            raise SecretsError(
                f"RHAPTO_SECRET_KEY is not a valid Fernet key; {GENERATE_HINT}"
            ) from exc
    if settings.rhapto_api_token:
        return Fernet(derive_key(settings.rhapto_api_token))
    raise SecretsError("set RHAPTO_SECRET_KEY in .env")


def encrypt(settings: Settings, text: str) -> str:
    return fernet_for(settings).encrypt(text.encode()).decode()


def decrypt(settings: Settings, token: str) -> str:
    try:
        return fernet_for(settings).decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise KeyUnreadableError(
            "stored key cannot be decrypted; RHAPTO_SECRET_KEY changed"
        ) from exc
