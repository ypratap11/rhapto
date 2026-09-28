"""Which LLM this user's work runs on: read it, set it, clear it, and probe it.

The stored key is write-only over HTTP. It goes in encrypted and comes back only as its last four
characters; every response here is built by `_current`, so there is one place that could ever leak
it.

Key precedence is body → stored key (same provider), and then, for the connectivity probe only,
the environment. The `PUT` deliberately stops at the stored key: a write that fell back to the
deployment's key copied the maintainer's key into the caller's own row (see `_key_for_write`). The
probe keeps the fallback, because it stores nothing and is what a keyless user needs in order to
check the key they are about to add.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.api.deps import (
    LlmFactory,
    current_user,
    get_llm_factory,
    get_session,
    get_settings_dep,
    get_state,
)
from rhapto.api.providers import provider_list
from rhapto.api.schemas import (
    LlmSettingsIn,
    LlmSettingsOut,
    LlmTestIn,
    LlmTestOut,
    SourceRunOut,
    SourceSettingIn,
    SourceSettingOut,
    SourceTestOut,
    UsageOut,
    UsageRecentOut,
    UsageSummaryOut,
)
from rhapto.config import Settings
from rhapto.db.models import Aggregator
from rhapto.db.repositories import profile as profile_repo
from rhapto.db.repositories import source_credentials as creds_repo
from rhapto.db.repositories.discovery import LatestRun, latest_runs_with_search
from rhapto.db.repositories.llm_settings import delete_llm_settings, upsert_llm_settings
from rhapto.engine.providers.llm import Message, SystemBlock
from rhapto.engine.providers.registry import PROVIDERS, ProviderInfo, model_for
from rhapto.services.discovery.search import SearchSpec
from rhapto.services.discovery.sources import aggregator_sources, get_aggregator
from rhapto.services.discovery.sources.status import paused_as_of_last_run, usable_source_ids
from rhapto.services.llm import env_llm_config, key_hint, redact, stored_llm_config
from rhapto.services.secrets import encrypt, fernet_for
from rhapto.services.usage import UsageSummary, usage_report

router = APIRouter()

UserDep = Annotated[uuid.UUID, Depends(current_user)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
FactoryDep = Annotated[LlmFactory, Depends(get_llm_factory)]


class Ping(BaseModel):
    """The smallest structured answer a provider can be asked for."""

    ok: bool


def known_provider(provider: str) -> ProviderInfo:
    info = PROVIDERS.get(provider)
    if info is None:
        raise HTTPException(status_code=422, detail=f"unknown provider {provider!r}")
    return info


def env_key_for(settings: Settings, info: ProviderInfo) -> str:
    """The environment's key for one provider (not necessarily the configured one)."""
    return str(getattr(settings, info.env_key.lower(), "") or "")


async def _current(session: AsyncSession, settings: Settings, user_id: uuid.UUID) -> LlmSettingsOut:
    """The stored row if there is one, else the environment's provider, else nothing configured."""
    config = await stored_llm_config(session, settings, user_id) or env_llm_config(settings)
    if config is None:
        return LlmSettingsOut(
            provider=None,
            model=None,
            key_set=False,
            key_hint=None,
            source="none",
            providers=provider_list(),
        )
    return LlmSettingsOut(
        provider=config.provider,
        model=config.model,
        key_set=True,
        # C2: the deployment's own key gets no hint. `key_hint` exists so a user can recognise
        # which of *their* keys is stored; on the env path the key is not theirs, and returning its
        # last four characters handed every keyless account the tail of the maintainer's live
        # production key. `source="env"` already tells the Settings page the deployment provides
        # the key, which is the whole of what the user needs to know.
        key_hint=key_hint(config.api_key) if config.source == "settings" else None,
        source=config.source,
        providers=provider_list(),
    )


async def _key_for_write(
    session: AsyncSession,
    settings: Settings,
    user_id: uuid.UUID,
    info: ProviderInfo,
    body_key: str | None,
    *,
    allow_env: bool,
) -> str:
    """The key to use for this write or probe: the submitted one, then this user's stored one.

    `allow_env` is the deployment's key, and it is explicit per call site rather than a default
    (C1). Now `False` at BOTH call sites, and no caller passes `True`.

    The `PUT` persists what it is handed: with the fallback in place, a keyless user who saved the
    LLM form without typing a key had the maintainer's key Fernet-encrypted into their own
    `llm_settings` row -- a stored key they never had, spending money that was never theirs, and a
    self-service exemption from any cap conditioned on having one.

    The `POST /settings/llm/test` probe used to allow it, on the reasoning that a probe costs a
    fraction of a cent. That reasoning has no count side: QA drove 25 probes past an exhausted trial
    allowance, every one returned 200, and every one was billed to the deployment. There is no rate
    limit anywhere in this API. A user testing a key they typed still tests their own; a user with a
    stored key still tests that; a user with neither has nothing of their own to test, and asking
    them for a key is the truthful answer rather than quietly spending someone else's.
    """
    submitted = (body_key or "").strip()
    if submitted:
        return submitted
    # Keeping the stored key means decrypting it, so a rotated server secret surfaces here as the
    # "re-enter your key" 409 rather than as a write that silently stores nothing usable.
    stored = await stored_llm_config(session, settings, user_id)
    if stored is not None and stored.provider == info.id:
        return stored.api_key
    if allow_env:
        from_env = env_key_for(settings, info)
        if from_env:
            return from_env
    raise HTTPException(status_code=422, detail=f"an API key is required for {info.label}")


@router.get("/settings/llm", response_model=LlmSettingsOut)
async def get_llm_settings_endpoint(
    user_id: UserDep, session: SessionDep, settings: SettingsDep
) -> LlmSettingsOut:
    return await _current(session, settings, user_id)


@router.put("/settings/llm", response_model=LlmSettingsOut)
async def put_llm_settings(
    body: LlmSettingsIn, user_id: UserDep, session: SessionDep, settings: SettingsDep
) -> LlmSettingsOut:
    info = known_provider(body.provider)
    api_key = await _key_for_write(session, settings, user_id, info, body.api_key, allow_env=False)
    await upsert_llm_settings(
        session,
        user_id,
        provider=info.id,
        model=model_for(info.id, body.model),
        api_key_encrypted=encrypt(settings, api_key),
    )
    await session.commit()
    return await _current(session, settings, user_id)


@router.delete("/settings/llm", status_code=204)
async def delete_llm_settings_endpoint(user_id: UserDep, session: SessionDep) -> Response:
    await delete_llm_settings(session, user_id)
    await session.commit()
    # 204 whether or not a row was there: the caller asked for "no stored provider", and that is
    # the state they get. The adapter cache is deliberately left alone: each entry carries the hash
    # of the key that built it, so a stale adapter can never be handed out for a different key.
    return Response(status_code=204)


#: Output budget for the connectivity probe. `Ping` needs a handful of tokens, but a reasoning
#: model spends its output budget thinking before it emits anything, so a tight cap makes the probe
#: fail with "hit the token cap" on a key and model that are both perfectly fine -- a false negative
#: at exactly the moment a new user is deciding whether this thing works. Generous enough to cover
#: a thinking pass, still a fraction of a cent.
PROBE_MAX_TOKENS = 2048


@router.post("/settings/llm/test", response_model=LlmTestOut)
async def test_llm_settings(
    body: LlmTestIn,
    user_id: UserDep,
    session: SessionDep,
    settings: SettingsDep,
    llm_factory: FactoryDep,
) -> LlmTestOut:
    """Ask the provider for one tiny structured answer. Nothing is stored either way."""
    info = known_provider(body.provider)
    api_key = await _key_for_write(session, settings, user_id, info, body.api_key, allow_env=False)
    model = model_for(info.id, body.model)
    try:
        llm = llm_factory(info.id, model, api_key)
        await llm.complete_structured(
            system=[SystemBlock(text="Reply with ok=true.")],
            messages=[Message(role="user", content="ping")],
            output_schema=Ping,
            max_tokens=PROBE_MAX_TOKENS,
        )
    except Exception as exc:
        # A failed probe is the endpoint's answer, not an error: a rejected key
        # (ProviderAuthError), an unreachable provider (EngineError) and anything an SDK raises
        # that the adapter does not map all come back as ok=false with the message, truncated so a
        # provider's wall of text cannot flood the UI.
        return LlmTestOut(ok=False, error=redact(str(exc), api_key)[:300])
    return LlmTestOut(ok=True, model=model)


def _summary_out(summary: UsageSummary) -> UsageSummaryOut:
    return UsageSummaryOut(
        calls=summary.calls,
        input_tokens=summary.input_tokens,
        output_tokens=summary.output_tokens,
        cache_read_tokens=summary.cache_read_tokens,
        cache_creation_tokens=summary.cache_creation_tokens,
        cost_usd=float(summary.cost_usd) if summary.cost_usd is not None else None,
        unpriced_calls=summary.unpriced_calls,
    )


@router.get("/settings/usage", response_model=UsageOut)
async def get_usage(user_id: UserDep, session: SessionDep) -> UsageOut:
    """All-time and last-30-day token/cost totals, plus the 20 most recent runs."""
    report = await usage_report(session, user_id)
    return UsageOut(
        totals=_summary_out(report.totals),
        last_30_days=_summary_out(report.last_30_days),
        recent=[
            UsageRecentOut(
                package_id=row.package.package_id,
                job_id=row.package.job_id,
                company=row.package.company,
                job_title=row.package.job_title,
                model=row.package.model,
                calls=row.package.calls,
                input_tokens=row.package.input_tokens,
                output_tokens=row.package.output_tokens,
                cost_usd=float(row.cost_usd) if row.cost_usd is not None else None,
                created_at=row.package.created_at,
            )
            for row in report.recent
        ],
    )


async def _source_rows(session: AsyncSession, user_id: uuid.UUID) -> dict[str, Aggregator]:
    return {row.source: row for row in await profile_repo.list_aggregators(session, user_id)}


def _one_source(rows: list[SourceSettingOut], source: str) -> SourceSettingOut:
    """The one row a write is about. `_source_settings` always includes every registered source, so
    a miss here would be a programming error, not a user error."""
    return next(r for r in rows if r.id == source)


def _run_out(entry: LatestRun) -> SourceRunOut:
    return SourceRunOut(
        started_at=entry.run.started_at,
        finished_at=entry.run.finished_at,
        found=entry.run.found,
        new=entry.run.new,
        error=entry.run.error,
        search_id=entry.run.search_id,
        search_name=entry.search_name,
        search_location=entry.search_location,
    )


async def _source_settings(session: AsyncSession, user_id: uuid.UUID) -> list[SourceSettingOut]:
    """Every configured source with its enable switch, credential state, and what it last did.

    One read each of `aggregators`, `source_credentials` and `latest_runs_with_search`; the
    per-source derivation is then pure Python over those three, so adding a source adds no query.
    """
    rows = await _source_rows(session, user_id)
    stored = await creds_repo.credentialled_sources(session, user_id)
    registry = aggregator_sources()
    runs = await latest_runs_with_search(session, user_id)
    # `configured` and the checklist's `job_sources` are the same function, so the Settings page and
    # the dashboard cannot disagree about what "set up" means.
    usable = usable_source_ids(rows, stored, registry)
    by_source: dict[str, list[LatestRun]] = {}
    for entry in runs:
        by_source.setdefault(entry.run.source, []).append(entry)
    out: list[SourceSettingOut] = []
    for info in registry:
        row = rows.get(info.name)
        # No default. A keyless source used to display as enabled when the user had no `aggregators`
        # row, while `poller.build_specs` polled only rows that exist -- so a new account saw four
        # sources on and fetched from none of them. `ensure_account` now seeds those rows, and this
        # reads the row and nothing else, so what the page shows is what the poller will use. Absent
        # row means off on both sides, which is why they can no longer disagree even if a seed is
        # missed.
        enabled = row.enabled if row is not None else False
        scopes = by_source.get(info.name, [])
        configured = info.name in usable
        paused = paused_as_of_last_run(
            [(e.run.error, e.run.started_at) for e in scopes],
            row.updated_at if row is not None else None,
        )
        out.append(
            SourceSettingOut(
                id=info.name,
                label=info.label,
                needs_key=info.needs_key,
                fields=list(info.fields),
                enabled=enabled,
                key_set=info.name in stored,
                configured=configured,
                paused=paused,
                # One `and`, no extra query: both inputs are already here. "Runnable" is a
                # present-tense claim about the next poll, so it has to account for pause --
                # architecture §12.1.
                runnable=configured and not paused,
                # `latest_runs_with_search` is sorted newest first, so the head of this source's
                # scopes is its newest run across all of them.
                last_run=_run_out(scopes[0]) if scopes else None,
            )
        )
    return out


@router.get("/settings/sources", response_model=list[SourceSettingOut])
async def list_source_settings(user_id: UserDep, session: SessionDep) -> list[SourceSettingOut]:
    return await _source_settings(session, user_id)


@router.put("/settings/sources/{source}", response_model=SourceSettingOut)
async def put_source_setting(
    source: str, body: SourceSettingIn, user_id: UserDep, session: SessionDep, settings: SettingsDep
) -> SourceSettingOut:
    info = next((i for i in aggregator_sources() if i.name == source), None)
    if info is None:
        raise HTTPException(status_code=404, detail=f"unknown source {source!r}")
    fernet = fernet_for(settings)
    if body.credentials:
        await creds_repo.put_credentials(session, fernet, user_id, source, body.credentials)
    if body.enabled and info.needs_key:
        stored = await creds_repo.get_credentials(session, fernet, user_id, source)
        missing = [f for f in info.fields if not stored.get(f)]
        if missing:
            # Enabling a source we cannot call would show up later as a failed poll run with no
            # explanation; say which field is missing while the user is looking at the form.
            raise HTTPException(status_code=422, detail=f"{info.label} needs {', '.join(missing)}")
    rows = await _source_rows(session, user_id)
    row = rows.get(source)
    if row is None:
        row = Aggregator(user_id=user_id, source=source, enabled=body.enabled, keywords=[])
        session.add(row)
    else:
        row.enabled = body.enabled
    row.updated_at = datetime.now(UTC)
    await session.commit()
    # Re-derived rather than reconstructed by hand: a second construction is a second place
    # `runnable` and `paused` could be computed differently from the GET's. It also means this
    # write's own `updated_at` bump is already reflected -- which is what lifts a pause today, as an
    # incidental side effect. `POST /settings/sources/{source}/resume` makes that deliberate.
    return _one_source(await _source_settings(session, user_id), info.name)


@router.post("/settings/sources/{source}/resume", response_model=SourceSettingOut)
async def resume_source(source: str, user_id: UserDep, session: SessionDep) -> SourceSettingOut:
    """Lift the poller's pause on one source: give it a fresh three attempts.

    It does exactly one thing -- set `aggregators.updated_at = now()` -- because that is precisely
    what lifts a pause. `poller._is_paused` counts only failures started AFTER `entry_updated_at`,
    so bumping it restarts every one of this source's streaks at once.

    That behaviour already existed, as an incidental side effect of the one `row.updated_at = ...`
    line in `PUT /settings/sources/{source}`. A named endpoint with its own test is worth five lines:
    the side effect was a single line with nothing asserting it, which a tidy-up could have removed
    without any test noticing, silently making a paused source unrecoverable from the UI.

    404 on an unknown source, and 404 when the user has no row for it -- there is no pause to lift
    on a source that has never been configured, and reporting success would be a lie about state.
    """
    info = next((i for i in aggregator_sources() if i.name == source), None)
    if info is None:
        raise HTTPException(status_code=404, detail=f"unknown source {source!r}")
    row = (await _source_rows(session, user_id)).get(source)
    if row is None:
        raise HTTPException(
            status_code=404, detail=f"{info.label} is not configured for this account"
        )
    row.updated_at = datetime.now(UTC)
    await session.commit()
    return _one_source(await _source_settings(session, user_id), info.name)


@router.post("/settings/sources/{source}/test", response_model=SourceTestOut)
async def test_source(
    source: str, user_id: UserDep, session: SessionDep, settings: SettingsDep, request: Request
) -> SourceTestOut:
    """One tiny search against the source. Never a 500: a failure is this endpoint's answer."""
    info = next((i for i in aggregator_sources() if i.name == source), None)
    if info is None:
        raise HTTPException(status_code=404, detail=f"unknown source {source!r}")
    credentials = await creds_repo.get_credentials(session, fernet_for(settings), user_id, source)
    http = get_state(request).discovery_http
    try:
        postings = await get_aggregator(source).fetch_search(
            http, SearchSpec(keywords=("program manager",)), credentials
        )
    except Exception as exc:
        return SourceTestOut(ok=False, error=redact(str(exc), *credentials.values())[:300])
    return SourceTestOut(ok=True, found=len(postings))
