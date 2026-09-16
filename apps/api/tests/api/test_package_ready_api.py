from __future__ import annotations

from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.models import APPLIED_STATUSES, Package


async def _mark_ready(client: httpx.AsyncClient, package_id: str) -> httpx.Response:
    return await client.patch(f"/api/v1/packages/{package_id}", json={"status": "ready"})


async def test_marking_ready_does_not_make_a_new_version(
    client: httpx.AsyncClient, tailored_package: dict[str, Any]
) -> None:
    package_id, job_id = tailored_package["id"], tailored_package["job_id"]
    response = await _mark_ready(client, package_id)
    # 200, not 201: nothing was written, so there is no new resource to point at.
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == package_id
    assert body["status"] == "ready"
    assert body["version"] == tailored_package["version"]
    versions = (await client.get(f"/api/v1/jobs/{job_id}/packages")).json()
    assert len(versions) == 1


async def test_ready_is_reversible(
    client: httpx.AsyncClient, tailored_package: dict[str, Any]
) -> None:
    package_id = tailored_package["id"]
    await _mark_ready(client, package_id)
    back = await client.patch(f"/api/v1/packages/{package_id}", json={"status": "draft"})
    assert back.status_code == 200 and back.json()["status"] == "draft"


async def test_marking_ready_changes_nothing_else(
    client: httpx.AsyncClient, tailored_package: dict[str, Any]
) -> None:
    before = (await client.get(f"/api/v1/packages/{tailored_package['id']}")).json()
    after = (await _mark_ready(client, tailored_package["id"])).json()
    assert {k: v for k, v in after.items() if k != "status"} == {
        k: v for k, v in before.items() if k != "status"
    }


async def test_the_status_filter_partitions_the_list(
    client: httpx.AsyncClient, tailored_package: dict[str, Any]
) -> None:
    package_id = tailored_package["id"]
    assert [p["id"] for p in (await client.get("/api/v1/packages?status=draft")).json()] == [
        package_id
    ]
    assert (await client.get("/api/v1/packages?status=ready")).json() == []
    await _mark_ready(client, package_id)
    assert (await client.get("/api/v1/packages?status=draft")).json() == []
    ready = (await client.get("/api/v1/packages?status=ready")).json()
    assert [p["id"] for p in ready] == [package_id]
    assert ready[0]["status"] == "ready"
    # Unfiltered still returns it; "Ready" is a tab, not a disappearance.
    assert [p["id"] for p in (await client.get("/api/v1/packages")).json()] == [package_id]


async def test_a_blocked_package_cannot_be_marked_ready(
    client: httpx.AsyncClient,
    tailored_package: dict[str, Any],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    package_id = tailored_package["id"]
    async with session_factory() as session:
        row = await session.get(Package, __import__("uuid").UUID(package_id))
        assert row is not None
        row.status = "blocked"
        row.guardrail_report_json = {
            "passed": False,
            "rules_run": ["verified-metrics", "provenance"],
            "violations": [
                {
                    "rule": "verified-metrics",
                    "severity": "error",
                    "path": "sections[0].entries[0].bullets[0]",
                    "message": "42% does not trace to a verified block",
                },
                {
                    "rule": "provenance",
                    "severity": "error",
                    "path": "sections[0].entries[1]",
                    "message": "source block 'nope' does not exist",
                },
            ],
        }
        await session.commit()
    response = await _mark_ready(client, package_id)
    assert response.status_code == 409
    # The message has to name the count: "Mark ready" is the last gate before a human sends this.
    assert "2" in response.json()["detail"]
    assert "guardrail" in response.json()["detail"].lower()
    assert (await client.get(f"/api/v1/packages/{package_id}")).json()["status"] == "blocked"


async def test_only_the_latest_version_may_be_marked_ready(
    client: httpx.AsyncClient, tailored_package: dict[str, Any]
) -> None:
    first = tailored_package
    resume = (await client.get(f"/api/v1/packages/{first['id']}")).json()["resume"]
    second = await client.patch(f"/api/v1/packages/{first['id']}", json={"resume": resume})
    assert second.status_code == 201, second.text
    stale = await _mark_ready(client, first["id"])
    assert stale.status_code == 409
    assert "latest" in stale.json()["detail"].lower()
    assert (await _mark_ready(client, second.json()["id"])).status_code == 200


async def test_an_editing_patch_still_creates_a_version(
    client: httpx.AsyncClient, tailored_package: dict[str, Any]
) -> None:
    resume = (await client.get(f"/api/v1/packages/{tailored_package['id']}")).json()["resume"]
    response = await client.patch(
        f"/api/v1/packages/{tailored_package['id']}", json={"resume": resume}
    )
    assert response.status_code == 201
    assert response.headers["Location"].endswith(response.json()["id"])
    assert response.json()["version"] == tailored_package["version"] + 1


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"status": "applied"},
        {"status": "blocked"},
        {"status": "ready", "resume": {}},
    ],
)
async def test_patch_body_validation(
    client: httpx.AsyncClient, tailored_package: dict[str, Any], body: dict[str, Any]
) -> None:
    response = await client.patch(f"/api/v1/packages/{tailored_package['id']}", json=body)
    assert response.status_code == 422, response.text


async def test_a_ready_package_leaves_the_needs_review_count(
    client: httpx.AsyncClient, tailored_package: dict[str, Any]
) -> None:
    assert (await client.get("/api/v1/dashboard")).json()["needs_review_count"] == 1
    await _mark_ready(client, tailored_package["id"])
    # Ready means a human already reviewed it; the hero band must not keep asking.
    assert (await client.get("/api/v1/dashboard")).json()["needs_review_count"] == 0


async def test_the_applied_tab_is_derivable_from_the_list_response(
    client: httpx.AsyncClient, tailored_package: dict[str, Any]
) -> None:
    """The Resumes page partitions one response; it never asks for ?status=applied."""
    await _mark_ready(client, tailored_package["id"])
    await client.post("/api/v1/applications", json={"job_id": tailored_package["job_id"]})
    application = (await client.get("/api/v1/applications")).json()["columns"]
    application_id = next(a["id"] for column in application.values() for a in column)
    await client.patch(f"/api/v1/applications/{application_id}", json={"status": "applied"})
    rows = (await client.get("/api/v1/packages")).json()
    assert [r["application_status"] for r in rows] == ["applied"]
    assert [r for r in rows if r["application_status"] in APPLIED_STATUSES]
