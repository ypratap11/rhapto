"""A blocked package says which rule, which bullet, and what to do about it.

Architecture §8 row 6. The condition is already fully persisted -- `packages.guardrail_report_json`
holds `rule`, `severity`, `message`, `path` and `block_id` -- so what these tests drive is whether
the two surfaces that only ever said "blocked" now carry enough to act on.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.models import Package

VIOLATION = {
    "rule": "no-unverified-metrics",
    "severity": "error",
    "message": "bullet contains a metric not found in a verified block: 40%",
    "path": "sections[0].entries[1].bullets[2]",
    "block_id": "blk-x",
}


async def _block_the_package(
    session_factory: async_sessionmaker[AsyncSession],
    package_id: uuid.UUID,
    *,
    violations: list[dict[str, Any]],
) -> None:
    """Make a real package blocked the way the validator does: a stored report that did not pass."""
    async with session_factory() as session:
        row = await session.scalar(select(Package).where(Package.id == package_id))
        assert row is not None
        report = dict(row.guardrail_report_json)
        report["passed"] = False
        report["violations"] = violations
        row.guardrail_report_json = report
        row.status = "blocked"
        await session.commit()


async def test_a_blocked_package_carries_a_remedy_for_the_rule_that_fired(
    client: httpx.AsyncClient,
    tailored_package: dict[str, Any],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _block_the_package(
        session_factory, uuid.UUID(tailored_package["id"]), violations=[VIOLATION]
    )
    body = (await client.get(f"/api/v1/packages/{tailored_package['id']}")).json()

    assert body["status"] == "blocked"
    violation = body["guardrail_report"]["violations"][0]
    # Already persisted and already on the wire -- asserted so a refactor cannot quietly drop them.
    assert violation["severity"] == "error"
    assert violation["block_id"] == "blk-x"
    assert violation["path"] == "sections[0].entries[1].bullets[2]"
    # The half that was missing: what to do.
    remedy = body["guardrail_remedies"]["no-unverified-metrics"]
    assert remedy and len(remedy) > 40


async def test_the_remedies_are_restricted_to_the_rules_in_this_report(
    client: httpx.AsyncClient,
    tailored_package: dict[str, Any],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A response carries its own report's remedies, not the whole map -- so what a user reads cannot
    describe a rule that did not fire."""
    await _block_the_package(
        session_factory, uuid.UUID(tailored_package["id"]), violations=[VIOLATION]
    )
    body = (await client.get(f"/api/v1/packages/{tailored_package['id']}")).json()
    assert set(body["guardrail_remedies"]) == {"no-unverified-metrics"}


async def test_a_second_rule_produces_a_second_remedy(
    client: httpx.AsyncClient,
    tailored_package: dict[str, Any],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The contrasting fixture: the remedies must follow the report, not a constant."""
    other = {**VIOLATION, "rule": "attribution", "message": "team work written as solo"}
    await _block_the_package(
        session_factory, uuid.UUID(tailored_package["id"]), violations=[VIOLATION, other]
    )
    body = (await client.get(f"/api/v1/packages/{tailored_package['id']}")).json()
    assert set(body["guardrail_remedies"]) == {"no-unverified-metrics", "attribution"}
    assert (
        body["guardrail_remedies"]["attribution"]
        != body["guardrail_remedies"]["no-unverified-metrics"]
    )


async def test_a_rule_with_no_remedy_is_absent_rather_than_blank(
    client: httpx.AsyncClient,
    tailored_package: dict[str, Any],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A rule added server-side first, or a historical report naming a rule this build dropped.

    The key must be absent, so the UI falls back to the rule id and message; a blank string would
    render an empty remedy line, which is worse than none.
    """
    await _block_the_package(
        session_factory,
        uuid.UUID(tailored_package["id"]),
        violations=[{**VIOLATION, "rule": "some-future-rule"}],
    )
    body = (await client.get(f"/api/v1/packages/{tailored_package['id']}")).json()
    assert body["guardrail_remedies"] == {}
    # The violation itself is still there and still readable.
    assert body["guardrail_report"]["violations"][0]["rule"] == "some-future-rule"


async def test_a_passing_package_carries_no_remedies(
    client: httpx.AsyncClient, tailored_package: dict[str, Any]
) -> None:
    body = (await client.get(f"/api/v1/packages/{tailored_package['id']}")).json()
    assert body["guardrail_report"]["passed"] is True
    assert body["guardrail_remedies"] == {}


# --- the list surface, which said "blocked" and nothing else ---------------------------------


async def test_the_list_row_counts_the_error_violations(
    client: httpx.AsyncClient,
    tailored_package: dict[str, Any],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    warning = {**VIOLATION, "severity": "warning", "rule": "visibility-context"}
    await _block_the_package(
        session_factory,
        uuid.UUID(tailored_package["id"]),
        violations=[VIOLATION, warning, {**VIOLATION, "path": "sections[1]"}],
    )
    rows = (await client.get("/api/v1/packages?status=blocked")).json()
    assert len(rows) == 1
    # Errors only: a warning does not block, so counting it would overstate what is wrong.
    assert rows[0]["violations"] == 2


async def test_a_package_that_passed_reports_no_violations_on_the_list(
    client: httpx.AsyncClient, tailored_package: dict[str, Any]
) -> None:
    rows = (await client.get("/api/v1/packages")).json()
    assert len(rows) == 1
    assert rows[0]["violations"] == 0


async def test_a_malformed_stored_report_does_not_break_the_list(
    client: httpx.AsyncClient,
    tailored_package: dict[str, Any],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """One unparseable historical report must not 500 the whole Resumes queue. The count degrades to
    zero; `GuardrailReport` validation stays on the single-package path, where it belongs."""
    async with session_factory() as session:
        row = await session.scalar(
            select(Package).where(Package.id == uuid.UUID(tailored_package["id"]))
        )
        assert row is not None
        row.guardrail_report_json = {"violations": "not-a-list"}
        await session.commit()

    response = await client.get("/api/v1/packages")
    assert response.status_code == 200
    assert response.json()[0]["violations"] == 0
