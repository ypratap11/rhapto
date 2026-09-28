"""`llm_setup_status` must agree with the predicate that already gates real runs.

Architecture §2.1 and §8's cross-cutting tests. The point of this file is the equivalence matrix:
`llm_setup_status(...).llm_key` is checked against `is_llm_configured(...)`, which is what `/me`
already uses and which goes through the real `resolve_llm_config`. Checking the new predicate against
a restatement of its own premise would confirm its blind spot instead of finding it.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.api.routers.meta import is_llm_configured
from rhapto.config import Settings
from rhapto.db.repositories.llm_settings import upsert_llm_settings
from rhapto.db.repositories.users import claim_trial_run, get_or_create_user
from rhapto.engine.providers.registry import FAKE_PROVIDER_ID
from rhapto.services.secrets import encrypt
from rhapto.services.trial import llm_setup_status

ENV_KEY = "env-key-aaaaaaaaaaaaaaaaaaaa"
OWN_KEY = "own-key-bbbbbbbbbbbbbbbbbbbb"


def _settings(
    tmp_path: Path,
    *,
    env_key: str = ENV_KEY,
    auth_mode: str = "access",
    provider: str = "anthropic",
    trial_runs: int = 3,
) -> Settings:
    return Settings(
        _env_file=None,
        anthropic_api_key=env_key,
        rhapto_auth_mode=auth_mode,
        rhapto_llm_provider=provider,
        rhapto_trial_runs=trial_runs,
        rhapto_api_token="test-token",
        rhapto_user_email="test@example.com",
        rhapto_packages_dir=tmp_path / "packages",
        rhapto_soffice_binary="soffice-not-installed",
    )


async def _user(session_factory: async_sessionmaker[AsyncSession], email: str) -> uuid.UUID:
    async with session_factory() as session:
        user = await get_or_create_user(session, email)
        await session.commit()
        return user.id


async def _store_key(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    user_id: uuid.UUID,
    key: str,
) -> None:
    async with session_factory() as session:
        await upsert_llm_settings(
            session,
            user_id,
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            api_key_encrypted=encrypt(settings, key),
        )
        await session.commit()


async def _store_raw(
    session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID, ciphertext: str
) -> None:
    """A row whose ciphertext this deployment's secret cannot decrypt -- what a rotated
    RHAPTO_SECRET_KEY leaves behind."""
    async with session_factory() as session:
        await upsert_llm_settings(
            session,
            user_id,
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            api_key_encrypted=ciphertext,
        )
        await session.commit()


# --- the equivalence matrix ------------------------------------------------------------------

#: Eight states, each a real configuration this deployment can be in. `row` is what the user has
#: stored: "none", "own", "env-copy" (a hand-seeded copy of the deployment's key) or "broken".
MATRIX = [
    ("no-row-with-env", "none", {}),
    ("no-row-no-env", "none", {"env_key": ""}),
    ("own-row", "own", {}),
    ("own-row-no-env", "own", {"env_key": ""}),
    ("env-copy-row", "env-copy", {}),
    ("broken-row", "broken", {}),
    ("fake-provider", "none", {"provider": FAKE_PROVIDER_ID}),
    ("token-mode", "none", {"auth_mode": "token"}),
]


@pytest.mark.parametrize(("name", "row", "overrides"), MATRIX, ids=[m[0] for m in MATRIX])
async def test_llm_key_agrees_with_is_llm_configured(
    name: str,
    row: str,
    overrides: dict[str, object],
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    """The anti-drift device. `is_llm_configured` runs the real `resolve_llm_config`; if the new
    predicate ever starts reporting "done" for a state where a tailoring run would be refused (or
    vice versa), this fails.

    Every case here has `trial_runs_used = 0`, so the trial ceiling is not in play --
    `test_an_exhausted_trial_is_the_one_deliberate_divergence` covers the one state where the two
    predicates differ on purpose.
    """
    settings = _settings(tmp_path, **overrides)  # type: ignore[arg-type]
    user_id = await _user(session_factory, f"matrix-{name}@example.com")
    if row == "own":
        await _store_key(session_factory, settings, user_id, OWN_KEY)
    elif row == "env-copy":
        await _store_key(session_factory, settings, user_id, ENV_KEY)
    elif row == "broken":
        await _store_raw(session_factory, user_id, "not-a-fernet-token")

    async with session_factory() as session:
        status = await llm_setup_status(session, settings, user_id)
        configured = await is_llm_configured(session, settings, user_id)
    assert status.llm_key == configured, f"{name}: {status} vs is_llm_configured={configured}"


# --- the source, which is the question "whose money" ------------------------------------------


async def test_a_user_on_the_deployments_key_with_a_cap_reads_as_a_trial(
    session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    """The owner's question. Neither "you have no LLM key" (false -- they can tailor) nor a bare
    "configured" (which hides the ceiling they will hit)."""
    settings = _settings(tmp_path, trial_runs=3)
    user_id = await _user(session_factory, "trial-user@example.com")
    async with session_factory() as session:
        status = await llm_setup_status(session, settings, user_id)
    assert status.llm_key_source == "trial"
    assert status.llm_key is True
    assert status.trial_runs_left == 3


async def test_a_user_with_their_own_key_is_not_on_the_deployments(
    session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    settings = _settings(tmp_path)
    user_id = await _user(session_factory, "own-key-user@example.com")
    await _store_key(session_factory, settings, user_id, OWN_KEY)
    async with session_factory() as session:
        status = await llm_setup_status(session, settings, user_id)
    assert status.llm_key_source == "settings"
    assert status.trial_runs_left is None


async def test_a_stored_copy_of_the_deployments_key_is_still_the_deployments_key(
    session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    """The case a "has a row?" check gets wrong, and the reason `same_key` exists: an operator can
    seed a row by hand, and reading "has a row" would hand it a permanent exemption."""
    settings = _settings(tmp_path)
    user_id = await _user(session_factory, "env-copy-user@example.com")
    await _store_key(session_factory, settings, user_id, ENV_KEY)
    async with session_factory() as session:
        status = await llm_setup_status(session, settings, user_id)
    assert status.llm_key_source == "trial", "a copy of the env key must not escape the cap"
    assert status.trial_runs_left == 3


async def test_token_mode_is_the_self_hoster_and_has_no_cap(
    session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    settings = _settings(tmp_path, auth_mode="token")
    user_id = await _user(session_factory, "self-hoster@example.com")
    async with session_factory() as session:
        status = await llm_setup_status(session, settings, user_id)
    assert status.llm_key_source == "env"
    assert status.llm_key is True and status.trial_runs_left is None


async def test_a_disabled_cap_is_the_env_source_not_a_trial(
    session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    """A negative `RHAPTO_TRIAL_RUNS` is the operator turning the cap off; that is not a trial."""
    settings = _settings(tmp_path, trial_runs=-1)
    user_id = await _user(session_factory, "no-cap@example.com")
    async with session_factory() as session:
        status = await llm_setup_status(session, settings, user_id)
    assert status.llm_key_source == "env" and status.trial_runs_left is None


async def test_no_key_anywhere_is_none_and_not_done(
    session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    settings = _settings(tmp_path, env_key="")
    user_id = await _user(session_factory, "keyless@example.com")
    async with session_factory() as session:
        status = await llm_setup_status(session, settings, user_id)
    assert status.llm_key_source == "none"
    assert status.llm_key is False and status.trial_runs_left is None


async def test_a_row_that_no_longer_decrypts_is_not_done(
    session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    """A row exists and no model call can succeed. Reporting the step complete is the
    `resume_template` defect: a row describing something that is gone."""
    settings = _settings(tmp_path)
    user_id = await _user(session_factory, "broken-key@example.com")
    await _store_raw(session_factory, user_id, "not-a-fernet-token")
    async with session_factory() as session:
        status = await llm_setup_status(session, settings, user_id)
    assert status.llm_key_source == "none"
    assert status.llm_key is False


# --- the ceiling -----------------------------------------------------------------------------


async def test_an_exhausted_trial_flips_the_row_to_not_done(
    session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    """The real condition: the counter actually consumed, through `claim_trial_run` -- the same
    statement the worker uses -- not a hand-set column."""
    settings = _settings(tmp_path, trial_runs=2)
    user_id = await _user(session_factory, "exhausted@example.com")
    async with session_factory() as session:
        for _ in range(2):
            assert await claim_trial_run(session, user_id, 2) is not None
        await session.commit()

    async with session_factory() as session:
        status = await llm_setup_status(session, settings, user_id)
    assert status.llm_key_source == "trial"
    assert status.trial_runs_left == 0
    assert status.llm_key is False, "at zero the user is blocked, so the row's job is a next action"


async def test_an_exhausted_trial_is_the_one_deliberate_divergence(
    session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    """Stated rather than hidden: `is_llm_configured` asks "is a provider resolvable", which stays
    True once the allowance is gone; `llm_key` asks "would a run be admitted", which is False. The
    equivalence matrix above therefore holds only while runs remain, and this pins the exception so
    a future reader does not "fix" one of the two to match the other."""
    settings = _settings(tmp_path, trial_runs=1)
    user_id = await _user(session_factory, "divergence@example.com")
    async with session_factory() as session:
        assert await claim_trial_run(session, user_id, 1) is not None
        await session.commit()

    async with session_factory() as session:
        status = await llm_setup_status(session, settings, user_id)
        configured = await is_llm_configured(session, settings, user_id)
    assert configured is True
    assert status.llm_key is False


async def test_the_invariant_between_llm_key_and_its_source_holds_across_the_matrix(
    session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    """`llm_key == (source != "none" and (source != "trial" or trial_runs_left > 0))`.

    Driven over every state rather than asserted once, because the invariant is what stops the two
    fields being computed independently and drifting apart.
    """
    for name, row, overrides in MATRIX:
        settings = _settings(tmp_path, **overrides)  # type: ignore[arg-type]
        user_id = await _user(session_factory, f"invariant-{name}@example.com")
        if row == "own":
            await _store_key(session_factory, settings, user_id, OWN_KEY)
        elif row == "env-copy":
            await _store_key(session_factory, settings, user_id, ENV_KEY)
        elif row == "broken":
            await _store_raw(session_factory, user_id, "not-a-fernet-token")
        async with session_factory() as session:
            status = await llm_setup_status(session, settings, user_id)
        expected = status.llm_key_source != "none" and (
            status.llm_key_source != "trial" or (status.trial_runs_left or 0) > 0
        )
        assert status.llm_key is expected, f"{name}: {status}"


async def test_runs_used_can_be_supplied_without_changing_the_answer(
    session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    """The dashboard passes the count it already selected. That optimisation must not be able to
    produce a different answer from reading the counter."""
    settings = _settings(tmp_path, trial_runs=3)
    user_id = await _user(session_factory, "supplied-used@example.com")
    async with session_factory() as session:
        assert await claim_trial_run(session, user_id, 3) is not None
        await session.commit()

    async with session_factory() as session:
        read_itself = await llm_setup_status(session, settings, user_id)
        supplied = await llm_setup_status(session, settings, user_id, runs_used=1)
    assert read_itself == supplied
    assert supplied.trial_runs_left == 2
