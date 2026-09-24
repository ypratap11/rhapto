from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from rhapto.config import Settings, get_settings
from rhapto.services.llm import clear_llm_cache, resolve_llm

TOKEN = "test-token"


@pytest.fixture(autouse=True)
def _clear_adapter_cache() -> None:
    clear_llm_cache()


@pytest.fixture(autouse=True)
def _real_env_says_fake(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """`tailor_job` resolves its provider through the process-wide `get_settings()`, not through
    the `api_settings` fixture that only shapes this test's FastAPI app -- so actually proving the
    env -> registry -> adapter path for `RHAPTO_LLM_PROVIDER=fake` (the point of `llm_resolver`
    below) means the real environment variable has to be set and `get_settings`'s cache dropped,
    not just this test's own `Settings` object built in isolation."""
    monkeypatch.setenv("RHAPTO_LLM_PROVIDER", "fake")
    # `_no_provider_env` (autouse, tests/conftest.py) deletes RHAPTO_SECRET_KEY for every test;
    # `get_settings()` now refuses to construct at all without one, so the real call this
    # fixture forces (via `tailor_job` below) needs a value present for the test body, not just
    # at teardown.
    monkeypatch.setenv("RHAPTO_SECRET_KEY", "test-fake-provider-real-env-secret")
    get_settings.cache_clear()
    try:
        yield
    finally:
        # `get_settings` is a process-wide singleton (`@lru_cache`): leaving it cleared here
        # would make whichever test runs next -- with RHAPTO_SECRET_KEY deleted by
        # `_no_provider_env` for its own duration, same as this one -- hit
        # `MissingSecretKeyError` the first time anything calls `get_settings()` for real.
        # RHAPTO_SECRET_KEY (set above) is still in effect here, before monkeypatch unwinds it,
        # so this reseeds the cache with a working value before handing back control.
        get_settings.cache_clear()
        get_settings()


@pytest.fixture
def api_settings(tmp_path: Path) -> Settings:
    """The e2e stack's environment: the fake provider and no vendor key anywhere."""
    return Settings(
        _env_file=None,
        rhapto_llm_provider="fake",
        anthropic_api_key="",
        rhapto_api_token=TOKEN,
        rhapto_user_email="test@example.com",
        rhapto_packages_dir=tmp_path / "packages",
        rhapto_soffice_binary="soffice-not-installed",
    )


@pytest.fixture
def llm_resolver():  # type: ignore[no-untyped-def]
    """The real resolver, so the run goes through env -> registry -> adapter for real.

    The default fixture injects a scripted double, which would prove nothing about whether
    RHAPTO_LLM_PROVIDER=fake actually resolves.
    """
    return resolve_llm


async def test_me_reports_the_stack_as_configured(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/me")).json()["llm_configured"] is True


async def test_the_fake_is_not_offered_in_settings(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/v1/settings/llm")).json()
    assert "fake" not in [p["id"] for p in body["providers"]]
    # Nor can it be saved: it is an environment switch for the e2e stack, not a user choice.
    rejected = await client.put(
        "/api/v1/settings/llm", json={"provider": "fake", "model": "fake-1"}
    )
    assert rejected.status_code == 422


async def test_a_whole_tailor_run_produces_a_clean_package(
    client: httpx.AsyncClient, imported_profile: None
) -> None:
    job = (
        await client.post(
            "/api/v1/jobs",
            json={
                "jd_text": (
                    "Technical Program Manager, Data Platform\n"
                    "Run cross functional programs for the data platform team and report on "
                    "delivery risk to leadership. " * 3
                ),
                "company": "ExampleCo",
                "title": "Technical Program Manager",
            },
        )
    ).json()
    task = await client.post(f"/api/v1/jobs/{job['id']}/tailor", json={})
    assert task.status_code in (200, 202), task.text
    packages = (await client.get(f"/api/v1/jobs/{job['id']}/packages")).json()
    assert packages, "the inline enqueuer should have produced a package"
    package = packages[-1]
    assert package["status"] == "draft", package["guardrail_report"]
    assert package["guardrail_report"]["passed"] is True
    assert package["resume"]["sections"], "an empty resume is not a usable e2e fixture"
    block_ids = {
        b["source_block_id"]
        for section in package["resume"]["sections"]
        for entry in section["entries"]
        for b in entry["bullets"]
    }
    assert block_ids, "every bullet must still cite a block"
