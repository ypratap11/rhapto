from __future__ import annotations

import pytest

from rhapto.worker.tasks import user_key_message


@pytest.mark.parametrize(
    ("provider_id", "name"),
    [
        ("openai", "OpenAI"),
        ("anthropic", "Anthropic"),
        ("gemini", "Google Gemini"),
        ("groq", "Groq"),
        ("openrouter", "OpenRouter"),
    ],
)
def test_the_two_sentences_name_the_stored_provider(provider_id: str, name: str) -> None:
    assert user_key_message("auth", provider_id) == (
        f"Your {name} key was refused. It may have expired or been revoked. "
        "Paste a new key in Settings, then try again."
    )
    assert user_key_message("quota", provider_id) == (
        f"Your {name} account is out of credit. Add credit with {name} or paste a different key in Settings."
    )


def test_an_unknown_provider_gets_no_sentence() -> None:
    assert user_key_message("auth", "fake") is None
    assert user_key_message("auth", "acme") is None
