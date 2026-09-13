"""Fernet key derivation and round trips for stored provider keys."""

from __future__ import annotations

import base64
import hashlib

import pytest

from rhapto.config import Settings
from rhapto.services.secrets import SecretsError, decrypt, encrypt, fernet_for

SECRET_A = base64.urlsafe_b64encode(b"a" * 32).decode()
SECRET_B = base64.urlsafe_b64encode(b"b" * 32).decode()


def _settings(**kwargs: str) -> Settings:
    return Settings(_env_file=None, **kwargs)  # type: ignore[arg-type]


def test_round_trip_with_explicit_secret() -> None:
    settings = _settings(rhapto_secret_key=SECRET_A)
    token = encrypt(settings, "sk-test-abcd1234")
    assert token != "sk-test-abcd1234"
    assert decrypt(settings, token) == "sk-test-abcd1234"


def test_round_trip_with_derived_secret() -> None:
    settings = _settings(rhapto_api_token="token-for-derivation")
    assert decrypt(settings, encrypt(settings, "sk-test-abcd1234")) == "sk-test-abcd1234"


def test_decrypt_with_a_different_secret_raises() -> None:
    token = encrypt(_settings(rhapto_secret_key=SECRET_A), "sk-test-abcd1234")
    with pytest.raises(SecretsError, match="RHAPTO_SECRET_KEY changed"):
        decrypt(_settings(rhapto_secret_key=SECRET_B), token)


def test_no_secret_and_no_api_token_raises() -> None:
    with pytest.raises(SecretsError, match="set RHAPTO_SECRET_KEY"):
        fernet_for(_settings(rhapto_secret_key="", rhapto_api_token=""))


def test_derivation_from_api_token_is_deterministic() -> None:
    settings = _settings(rhapto_api_token="token-for-derivation")
    expected = base64.urlsafe_b64encode(hashlib.sha256(b"token-for-derivation").digest())
    first = encrypt(settings, "sk-test-abcd1234")
    assert decrypt(_settings(rhapto_secret_key=expected.decode()), first) == "sk-test-abcd1234"
    assert (
        decrypt(settings, encrypt(_settings(rhapto_api_token="token-for-derivation"), "x")) == "x"
    )


def test_explicit_secret_wins_over_derivation() -> None:
    both = _settings(rhapto_secret_key=SECRET_A, rhapto_api_token="token-for-derivation")
    assert decrypt(_settings(rhapto_secret_key=SECRET_A), encrypt(both, "k")) == "k"


def test_a_secret_that_is_not_a_fernet_key_raises_with_the_generation_hint() -> None:
    with pytest.raises(SecretsError, match="not a valid Fernet key"):
        fernet_for(_settings(rhapto_secret_key="hunter2"))


def test_garbage_token_raises_secrets_error() -> None:
    with pytest.raises(SecretsError):
        decrypt(_settings(rhapto_secret_key=SECRET_A), "not-a-fernet-token")
