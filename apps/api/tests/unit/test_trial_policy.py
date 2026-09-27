"""Who is capped and who is not: `services.trial`'s policy, with no database and no `get_settings()`.

`Settings(...)` is constructed directly, exactly as `test_resolve_llm.py` does, and
`stored_llm_config` is monkeypatched. Nothing here calls `get_settings()` and nothing calls
`get_settings.cache_clear()` -- that `lru_cache` has caused spurious failures in this repo and
condition C4 exists to keep it out of the trial's tests entirely.

The starred case in the architecture (§8 test 11) is
`test_a_stored_copy_of_the_deployments_key_is_still_the_deployments_key`.
"""

from __future__ import annotations

import base64
import uuid
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.config import Settings
from rhapto.services import trial as trial_service
from rhapto.services.llm import LlmConfig
from rhapto.services.secrets import KeyUnreadableError
from rhapto.services.trial import (
    TrialLimitExceededError,
    check_trial_allowance,
    configured_trial_limit,
    on_deployment_key,
    trial_limit_for,
    trial_limit_message,
)

SECRET = base64.urlsafe_b64encode(b"s" * 32).decode()
USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
ENV_KEY = "sk-env-deployment-key"
OWN_KEY = "sk-user-own-key"


def _settings(**kwargs: object) -> Settings:
    """Access mode with an env key and the default cap, unless a test says otherwise."""
    base: dict[str, object] = {
        "rhapto_secret_key": SECRET,
        "rhapto_auth_mode": "access",
        "rhapto_llm_provider": "anthropic",
        "anthropic_api_key": ENV_KEY,
    }
    base.update(kwargs)
    return Settings(_env_file=None, **base)  # type: ignore[arg-type]


def _session() -> AsyncSession:
    """`stored_llm_config` is monkeypatched in every test here, so the session is never used."""
    return cast("AsyncSession", object())


def _stored(monkeypatch: pytest.MonkeyPatch, result: object) -> None:
    """Point `services.trial`'s `stored_llm_config` at a fixed answer (or exception)."""

    async def fake(session: object, settings: object, user_id: object) -> object:
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(trial_service, "stored_llm_config", fake)


def _own_key_config() -> LlmConfig:
    return LlmConfig(
        provider="anthropic", model="claude-sonnet-5", api_key=OWN_KEY, source="settings"
    )


def _copy_of_env_key_config() -> LlmConfig:
    return LlmConfig(
        provider="anthropic", model="claude-sonnet-5", api_key=ENV_KEY, source="settings"
    )


# --- the operator's knob ---


def test_a_negative_limit_disables_the_cap() -> None:
    assert configured_trial_limit(_settings(rhapto_trial_runs=-1)) is None


def test_zero_is_a_cap_not_a_disabled_cap() -> None:
    assert configured_trial_limit(_settings(rhapto_trial_runs=0)) == 0


def test_the_default_is_three() -> None:
    assert configured_trial_limit(_settings()) == 3


# --- the message ---


def test_the_message_names_the_count_and_nothing_about_the_deployment() -> None:
    message = trial_limit_message(3)
    assert "3" in message and "Settings" in message
    for leak in ("anthropic", "Anthropic", "claude", "ANTHROPIC_API_KEY", ENV_KEY, ".env"):
        assert leak not in message, f"{leak!r} must never appear in the refusal"


def test_a_zero_limit_gets_its_own_sentence_rather_than_zero_free_runs() -> None:
    assert "does not offer free runs" in trial_limit_message(0)
    assert "Settings" in trial_limit_message(0)


def test_the_message_is_singular_for_one_run() -> None:
    assert "1 free tailoring run " in trial_limit_message(1)


# --- which accounts are spending the deployment's money ---


async def test_no_stored_row_means_the_deployment_pays(monkeypatch: pytest.MonkeyPatch) -> None:
    _stored(monkeypatch, None)
    assert await on_deployment_key(_session(), _settings(), USER_ID) is True


async def test_a_users_own_key_is_not_the_deployments(monkeypatch: pytest.MonkeyPatch) -> None:
    _stored(monkeypatch, _own_key_config())
    assert await on_deployment_key(_session(), _settings(), USER_ID) is False


async def test_nothing_in_the_environment_means_nothing_to_protect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stored(monkeypatch, None)
    assert await on_deployment_key(_session(), _settings(anthropic_api_key=""), USER_ID) is False


# --- the cap that applies ---


async def test_token_mode_is_never_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    """A self-hosted, single-account deployment: the env key is that one user's own key."""
    _stored(monkeypatch, None)
    settings = _settings(rhapto_auth_mode="token", rhapto_trial_runs=3)
    assert await trial_limit_for(_session(), settings, USER_ID) is None


async def test_the_fake_provider_is_never_capped_even_for_a_user_with_a_stored_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fake bills nothing, so the operator's no-bill promise outranks both the cap and the row --
    exactly as it already outranks the row for provider selection in `resolve_llm_config`."""
    _stored(monkeypatch, _own_key_config())
    settings = _settings(rhapto_llm_provider="fake")
    assert await trial_limit_for(_session(), settings, USER_ID) is None
    _stored(monkeypatch, None)
    assert await trial_limit_for(_session(), settings, USER_ID) is None


async def test_a_disabled_cap_applies_to_nobody(monkeypatch: pytest.MonkeyPatch) -> None:
    _stored(monkeypatch, None)
    assert await trial_limit_for(_session(), _settings(rhapto_trial_runs=-1), USER_ID) is None


async def test_a_cap_of_zero_still_applies(monkeypatch: pytest.MonkeyPatch) -> None:
    _stored(monkeypatch, None)
    assert await trial_limit_for(_session(), _settings(rhapto_trial_runs=0), USER_ID) == 0


async def test_a_keyless_user_on_a_deployment_with_a_key_is_capped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stored(monkeypatch, None)
    assert await trial_limit_for(_session(), _settings(), USER_ID) == 3


async def test_a_user_with_their_own_key_is_not_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    _stored(monkeypatch, _own_key_config())
    assert await trial_limit_for(_session(), _settings(), USER_ID) is None


async def test_nobody_is_capped_when_no_key_exists_anywhere(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`resolve_llm_config` raises `LLMNotConfiguredError` first, and it must keep doing so: the
    trial refusal is unreachable on a deployment with no key of its own to protect."""
    _stored(monkeypatch, None)
    assert await trial_limit_for(_session(), _settings(anthropic_api_key=""), USER_ID) is None


async def test_a_stored_copy_of_the_deployments_key_is_still_the_deployments_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★ The impersonated key.

    `PUT /settings/llm` used to copy the environment's key into the caller's own `llm_settings` row
    whenever they saved the form without typing one (condition C1 closes that). A gate that reads
    "does this user have a row?" would have handed anyone who did that a permanent exemption while
    they went on spending the maintainer's money -- so the gate compares the keys, and this is the
    second line of defence behind C1.
    """
    _stored(monkeypatch, _copy_of_env_key_config())
    assert await on_deployment_key(_session(), _settings(), USER_ID) is True
    assert await trial_limit_for(_session(), _settings(), USER_ID) == 3


async def test_an_undecryptable_stored_key_is_not_a_quota_problem(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A rotated `RHAPTO_SECRET_KEY` must surface as "re-enter your key", never as "you are out of
    free runs", and the gate must not raise a second exception while the first is being handled."""
    _stored(monkeypatch, KeyUnreadableError("nope"))
    assert await on_deployment_key(_session(), _settings(), USER_ID) is False
    assert await trial_limit_for(_session(), _settings(), USER_ID) is None


# --- the read-only check ---


async def test_check_allows_an_uncapped_user_without_reading_the_counter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No cap must mean no query: `trial_runs_used` would be handed the stub session and blow up."""
    _stored(monkeypatch, _own_key_config())
    await check_trial_allowance(_session(), _settings(), USER_ID)


async def test_check_refuses_at_the_limit_and_reports_the_users_own_numbers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stored(monkeypatch, None)

    async def used(session: object, user_id: object) -> int:
        return 3

    monkeypatch.setattr(trial_service, "trial_runs_used", used)
    with pytest.raises(TrialLimitExceededError) as caught:
        await check_trial_allowance(_session(), _settings(), USER_ID)
    assert caught.value.used == 3 and caught.value.limit == 3
    assert str(caught.value) == trial_limit_message(3)


async def test_check_allows_a_user_below_the_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    _stored(monkeypatch, None)

    async def used(session: object, user_id: object) -> int:
        return 2

    monkeypatch.setattr(trial_service, "trial_runs_used", used)
    await check_trial_allowance(_session(), _settings(), USER_ID)


def test_the_module_logs_nothing() -> None:
    """Deliberate, and asserted so it stays that way: a log line naming the user and the count is a
    fine thing to want and the wrong thing to add in the same change as the key that produced it."""
    source = Path(trial_service.__file__ or "")
    assert source.is_file()
    text = source.read_text(encoding="utf-8")
    for forbidden in ("getLogger", "logger.", "logging."):
        assert forbidden not in text, f"services/trial.py must not log ({forbidden})"
