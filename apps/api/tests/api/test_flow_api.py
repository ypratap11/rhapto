from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx


async def _job(client: httpx.AsyncClient, marker: str) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/jobs",
        json={
            "jd_text": f"We need a technical program manager for {marker}. " * 4,
            "company": "ExampleCo",
            "title": "Technical Program Manager",
        },
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


async def test_hide_and_unhide_a_job(client: httpx.AsyncClient) -> None:
    job = await _job(client, "alpha")
    hidden = await client.post(f"/api/v1/jobs/{job['id']}/hide")
    assert hidden.status_code == 200 and hidden.json()["hidden_at"] is not None
    assert (await client.get("/api/v1/jobs")).json() == []
    assert [j["id"] for j in (await client.get("/api/v1/jobs?hidden=true")).json()] == [job["id"]]
    # Hiding twice is the same state, not an error: the Undo toast can fire late.
    again = await client.post(f"/api/v1/jobs/{job['id']}/hide")
    assert again.status_code == 200 and again.json()["hidden_at"] == hidden.json()["hidden_at"]
    back = await client.post(f"/api/v1/jobs/{job['id']}/unhide")
    assert back.json()["hidden_at"] is None
    assert [j["id"] for j in (await client.get("/api/v1/jobs")).json()] == [job["id"]]


async def test_hide_on_an_unknown_job_is_404(client: httpx.AsyncClient) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    assert (await client.post(f"/api/v1/jobs/{missing}/hide")).status_code == 404
    assert (await client.post(f"/api/v1/jobs/{missing}/unhide")).status_code == 404


async def test_archiving_a_package_hides_its_job_and_empties_the_queue(
    client: httpx.AsyncClient, tailored_package: dict[str, Any]
) -> None:
    package_id, job_id = tailored_package["id"], tailored_package["job_id"]
    assert [p["id"] for p in (await client.get("/api/v1/packages")).json()] == [package_id]
    archived = await client.post(f"/api/v1/packages/{package_id}/archive")
    assert archived.status_code == 200
    assert (await client.get("/api/v1/packages")).json() == []
    listed = (await client.get("/api/v1/packages?archived=true")).json()
    assert [p["id"] for p in listed] == [package_id]
    assert listed[0]["archived_at"] is not None
    assert (await client.get(f"/api/v1/jobs/{job_id}")).json()["hidden_at"] is not None


async def test_archiving_an_unknown_package_is_404(client: httpx.AsyncClient) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    assert (await client.post(f"/api/v1/packages/{missing}/archive")).status_code == 404


async def test_closing_an_application_with_a_reason(client: httpx.AsyncClient) -> None:
    job = await _job(client, "beta")
    application_id = (await client.post("/api/v1/applications", json={"job_id": job["id"]})).json()[
        "id"
    ]
    closed = await client.patch(
        f"/api/v1/applications/{application_id}",
        json={"status": "closed", "closed_reason": "no_response"},
    )
    assert closed.status_code == 200 and closed.json()["closed_reason"] == "no_response"
    bad = await client.patch(
        f"/api/v1/applications/{application_id}", json={"closed_reason": "ghosted"}
    )
    assert bad.status_code == 422
    # Reopening clears the reason rather than leaving a contradiction behind.
    reopened = await client.patch(
        f"/api/v1/applications/{application_id}", json={"status": "screen"}
    )
    assert reopened.json()["closed_reason"] is None


async def test_a_reason_without_the_closed_status_is_422(client: httpx.AsyncClient) -> None:
    job = await _job(client, "gamma")
    application_id = (await client.post("/api/v1/applications", json={"job_id": job["id"]})).json()[
        "id"
    ]
    response = await client.patch(
        f"/api/v1/applications/{application_id}",
        json={"status": "screen", "closed_reason": "filled"},
    )
    assert response.status_code == 422


async def test_a_follow_up_date_can_be_set_and_cleared(client: httpx.AsyncClient) -> None:
    job = await _job(client, "delta")
    application_id = (await client.post("/api/v1/applications", json={"job_id": job["id"]})).json()[
        "id"
    ]
    when = (datetime.now(UTC) + timedelta(days=3)).isoformat()
    set_date = await client.patch(
        f"/api/v1/applications/{application_id}", json={"follow_up_at": when}
    )
    assert set_date.json()["follow_up_at"] is not None
    # An omitted field is untouched; an explicit null clears it.
    untouched = await client.patch(
        f"/api/v1/applications/{application_id}", json={"notes": "called them"}
    )
    assert untouched.json()["follow_up_at"] is not None
    cleared = await client.patch(
        f"/api/v1/applications/{application_id}", json={"follow_up_at": None}
    )
    assert cleared.json()["follow_up_at"] is None
