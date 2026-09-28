"""A bounded trial on the deployment's own provider key.

A user with no key of their own falls back to the environment's key (`services.llm`'s documented
"zero-UI path"), which means the maintainer pays. That is correct for a self-hoster, whose env key
*is* their own, and wrong for someone invited onto a hosted instance. This module is the policy that
tells those two apart and bounds the second: which accounts are spending the deployment's money, and
how many runs each of them may.

It contains no SQL -- the two statements live in `db/repositories/users.py`, and the counter they
move is a column on `users`, never a count of `packages`. A package is an artifact the user edits
(`PATCH /packages/{id}` writes a new row carrying the parent's `llm_model` and makes no model call)
and deletes (`DELETE /jobs/{id}` cascades), so counting packages charges people for edits they made
in the review queue and hands back the whole allowance to anyone who deletes a job.

It logs nothing. Not "logs at INFO" -- nothing. A line naming the user and the count is a fine thing
to want and the wrong thing to add in the same change as the key that produced it; trial telemetry is
its own change, with user ids and counts only.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.config import Settings
from rhapto.db.repositories.users import claim_trial_run, trial_runs_used
from rhapto.engine.providers.registry import FAKE_PROVIDER_ID
from rhapto.services.llm import env_llm_config, same_key, stored_llm_config
from rhapto.services.secrets import SecretsError


def trial_limit_message(limit: int) -> str:
    """What the user is told. One integer interpolated and nothing else.

    No provider id, no model id, no env var name, no part of any key: this sentence is returned by
    the API, written onto a task row and published on the event bus, so everything about the
    deployment's configuration has to stay out of it. What it does say is the number of runs they
    had, because a refusal that will not say how many is not legible to a non-technical person.
    """
    if limit <= 0:
        return (
            "This instance does not offer free runs. Add your own provider API key in Settings "
            "to use it."
        )
    runs = "run" if limit == 1 else "runs"
    return (
        f"You have used all {limit} free tailoring {runs} on this instance. Add your own provider "
        "API key in Settings to keep going."
    )


class TrialLimitExceededError(Exception):
    """This account has spent its allowance of runs on the deployment's provider key."""

    def __init__(self, used: int, limit: int) -> None:
        self.used = used
        self.limit = limit
        super().__init__(trial_limit_message(limit))


def configured_trial_limit(settings: Settings) -> int | None:
    """The operator's cap, or None when they disabled it with a negative value.

    Zero is a cap, not "disabled": it is the setting an operator wants when nobody but themselves
    should ever run on their key.
    """
    limit = settings.rhapto_trial_runs
    return None if limit < 0 else limit


async def on_deployment_key(session: AsyncSession, settings: Settings, user_id: uuid.UUID) -> bool:
    """True when this user's next model call would be billed to the deployment's own key.

    The money-critical predicate. "No stored row ⇒ the environment pays" is exact rather than
    approximate: in `resolve_llm_config` the `or` falls through to `env_llm_config` only when
    `stored_llm_config` returns `None`, and a row that exists either yields its own config or
    raises `SecretsError`. There is no third branch.
    """
    env = env_llm_config(settings)
    if env is None:
        # Nothing of the maintainer's to protect. A user with no key anywhere keeps hearing
        # `LLMNotConfiguredError` from `resolve_llm_config`, which runs first.
        return False
    try:
        stored = await stored_llm_config(session, settings, user_id)
    except SecretsError:
        # An undecryptable stored key never reaches a provider: `resolve_llm_config` raises before
        # any call. The gate must not turn a key problem into a quota problem.
        return False
    if stored is None:
        return True
    # A stored copy of the environment's key is still the environment's key. `PUT /settings/llm`
    # no longer writes one (condition C1), but an operator can seed a row by hand, and a gate that
    # reads "has a row" would hand out a permanent exemption to whatever did.
    return same_key(stored.api_key, env.api_key)


def deployment_key_trial_limit(settings: Settings) -> int | None:
    """The cap that would apply to a user who IS on the deployment's key, or None if none can.

    The three operator-level exemptions, in one place, so that `trial_limit_for` and
    `llm_setup_status` cannot answer "does a cap apply" differently. Split out of `trial_limit_for`
    for exactly that reason: the checklist has already resolved the stored row and must not re-derive
    these, nor pay for a second read of it.
    """
    # 1. Token mode is a single-account, self-hosted deployment whose one user is the operator
    #    (`api/deps.py`'s token branch hands every request the one bootstrapped `state.user_id`).
    #    The env key is their own. Capping it would break every self-hoster and every e2e stack on
    #    the default setting -- and this exemption is what makes a default of 3 safe to ship.
    if settings.rhapto_auth_mode != "access":
        return None
    # 2. Mirrors `resolve_llm_config`'s fake-provider branch exactly, including the `is not None`
    #    guard, so the gate and the resolver can never disagree about whether the fake is really in
    #    force. The fake bills nothing; the operator's no-bill promise outranks the cap and outranks
    #    a stored key, exactly as it already outranks it for provider selection.
    if settings.rhapto_llm_provider == FAKE_PROVIDER_ID and env_llm_config(settings) is not None:
        return None
    return configured_trial_limit(settings)


async def trial_limit_for(
    session: AsyncSession, settings: Settings, user_id: uuid.UUID
) -> int | None:
    """The cap that applies to this user right now, or None when no cap applies at all."""
    limit = deployment_key_trial_limit(settings)
    if limit is None:
        return None
    # 4. The user pays for their own calls. Checked last, because it is the only branch that reads.
    if not await on_deployment_key(session, settings, user_id):
        return None
    return limit


async def check_trial_allowance(
    session: AsyncSession, settings: Settings, user_id: uuid.UUID
) -> None:
    """Raise `TrialLimitExceededError` when nothing is left. Reads only; consumes nothing.

    Deliberately racy: two simultaneous requests can both be admitted. This is a courtesy check for
    an immediate, legible answer on the way in -- the worker's `consume_trial_run` is the
    enforcement, and it has no race window.
    """
    limit = await trial_limit_for(session, settings, user_id)
    if limit is None:
        return
    used = await trial_runs_used(session, user_id)
    if used >= limit:
        raise TrialLimitExceededError(used, limit)


async def consume_trial_run(session: AsyncSession, settings: Settings, user_id: uuid.UUID) -> None:
    """Consume one run atomically, or raise `TrialLimitExceededError`.

    THE CALLER MUST COMMIT before making the model call. A worker killed between the claim and the
    call must not hand out a free run, and there is no refund path: a refund is a second place the
    counter can move and the first thing an attacker would reach for.
    """
    limit = await trial_limit_for(session, settings, user_id)
    if limit is None:
        return
    if await claim_trial_run(session, user_id, limit) is None:
        raise TrialLimitExceededError(await trial_runs_used(session, user_id), limit)


#: Whose key a user's next model call would be billed to.
#:
#: "settings" = their own stored key. "env" = this instance's key with no cap in force (a
#: self-hoster, token mode, the fake provider, or an operator who disabled the cap). "trial" = this
#: instance's key with a cap. "none" = nothing usable anywhere, which includes a stored key that no
#: longer decrypts.
LlmKeySource = Literal["settings", "env", "trial", "none"]


@dataclass(frozen=True)
class LlmSetupStatus:
    """Whether a tailoring run would be admitted right now, and on whose money.

    Two questions, not one, and the checklist needs both. "Is there a key" is the question that lies:
    a user on the deployment's key has no row and is not blocked, a row whose ciphertext no longer
    decrypts exists and blocks every run, and a hand-seeded copy of the environment's key is still
    the environment's key.
    """

    #: A tailoring run would be admitted right now. NOT "a key exists".
    llm_key: bool
    llm_key_source: LlmKeySource
    #: Runs left on this instance's key, only when a cap is in force.
    trial_runs_left: int | None = None


async def llm_setup_status(
    session: AsyncSession,
    settings: Settings,
    user_id: uuid.UUID,
    *,
    runs_used: int | None = None,
) -> LlmSetupStatus:
    """The checklist's LLM row, composed from the predicates that already govern real runs.

    Nothing here is reimplemented: it composes `stored_llm_config`, `env_llm_config`, `same_key`,
    `deployment_key_trial_limit` (which holds the three exemptions) and `trial_runs_used`. A test
    asserts `llm_setup_status(...).llm_key == await is_llm_configured(...)` across the eight-state
    matrix, so this predicate is validated against the one that already gates `/me` rather than
    against a restatement of its own premise.

    `runs_used` lets the dashboard pass the count it already selected in its checklist composite,
    instead of paying for a second statement. Left None, it reads the counter itself.

    Reads the stored row exactly once. `trial_limit_for` is deliberately NOT called, because it would
    read that row again through `on_deployment_key`; the shared part -- the exemptions -- is
    `deployment_key_trial_limit`, and the "is this user on the deployment's key" part is the one line
    below that mirrors `on_deployment_key`'s only three branches.

    No key material and no `key_hint` is exposed. `settings.py`'s C2 rule (the deployment's key gets
    no hint) is preserved by not carrying a hint at all.
    """
    env = env_llm_config(settings)
    try:
        stored = await stored_llm_config(session, settings, user_id)
    except SecretsError:
        # An undecryptable stored key never reaches a provider: `resolve_llm_config` raises before
        # any call. The user has to re-enter it, so the row is not done and there is no next action
        # other than that.
        return LlmSetupStatus(llm_key=False, llm_key_source="none")
    if stored is None and env is None:
        return LlmSetupStatus(llm_key=False, llm_key_source="none")
    # The same three branches as `on_deployment_key`: no env key means nothing of the maintainer's is
    # at stake; no stored row means the environment pays; and a stored COPY of the environment's key
    # is still the environment's key, which is why this compares digests rather than reading "has a
    # row".
    on_deployment = env is not None and (stored is None or same_key(stored.api_key, env.api_key))
    if not on_deployment:
        # Their own key. Note one nuance: with `RHAPTO_LLM_PROVIDER=fake` the deployment runs
        # everything on the fake regardless, so "settings" here means "the key you stored", not
        # "the key this call will use". Nobody's money is spent either way.
        return LlmSetupStatus(llm_key=True, llm_key_source="settings")
    limit = deployment_key_trial_limit(settings)
    if limit is None:
        return LlmSetupStatus(llm_key=True, llm_key_source="env")
    used = runs_used if runs_used is not None else await trial_runs_used(session, user_id)
    left = max(0, limit - used)
    # `llm_key` flips to False at zero because at that point the user IS blocked, and the row's job
    # is to give them the next action -- "add your own key" -- rather than read done.
    return LlmSetupStatus(llm_key=left > 0, llm_key_source="trial", trial_runs_left=left)
