from __future__ import annotations

import uuid

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.repositories import documents as documents_repo


async def test_get_taxonomy_returns_the_twelve_fields(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/v1/taxonomy")).json()
    assert [f["id"] for f in body["fields"]][:3] == ["engineering", "data-science", "product"]
    ppm = next(f for f in body["fields"] if f["id"] == "program-project-management")
    assert ppm["themuse_category"] == "Project Management"
    assert ppm["adzuna_category"] == "Consultancy Jobs"
    tpm = next(r for r in ppm["roles"] if r["id"] == "technical-program-manager")
    assert 6 <= len(tpm["keywords"]) <= 10


async def test_suggestions_are_empty_without_an_uploaded_resume(
    client: httpx.AsyncClient,
) -> None:
    assert (await client.get("/api/v1/taxonomy/suggestions")).json() == []


async def test_suggestions_match_the_parsed_entry_titles(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    parsed = {
        "filename": "resume.docx",
        "sections": [],
        "paragraphs": [
            {"id": "p1", "text": "Maya Chen", "role": "name"},
            {
                "id": "p2",
                "text": "Senior Technical Program Manager, Platform",
                "role": "entry_title",
            },
            {"id": "p3", "text": "Delivered three programs", "role": "bullet"},
            {"id": "p4", "text": "Data Analyst", "role": "entry_title"},
            {"id": "p5", "text": "Technical Program Manager II", "role": "entry_title"},
            {"id": "p6", "text": "Barista", "role": "entry_title"},
        ],
    }
    async with session_factory() as session:
        await documents_repo.upsert_document(
            session, user_id, filename="resume.docx", path="/tmp/resume.docx", parsed=parsed
        )
        await session.commit()
    body = (await client.get("/api/v1/taxonomy/suggestions")).json()
    # One entry per role, in document order; the second TPM title adds nothing and Barista
    # matches no role at all.
    assert [(s["role_id"], s["matched_title"]) for s in body] == [
        ("technical-program-manager", "Senior Technical Program Manager, Platform"),
        ("data-analyst", "Data Analyst"),
    ]
    assert body[0]["field_id"] == "program-project-management"
    assert body[0]["field_name"] == "Program and Project Management"
    assert body[0]["role_name"] == "Technical Program Manager"


async def test_a_track_round_trips_its_field_and_role(client: httpx.AsyncClient) -> None:
    created = await client.put(
        "/api/v1/profile/tracks/tpm",
        json={
            "id": "tpm",
            "name": "Technical Program Manager",
            "resume_base": "default",
            "min_fit": 60,
            "keywords": ["technical program manager", "TPM"],
            "field": "program-project-management",
            "role": "technical-program-manager",
        },
    )
    assert created.status_code == 201
    row = next(t for t in (await client.get("/api/v1/profile/tracks")).json() if t["id"] == "tpm")
    assert row["field"] == "program-project-management"
    assert row["role"] == "technical-program-manager"


async def test_a_track_without_a_field_still_round_trips(client: httpx.AsyncClient) -> None:
    created = await client.put(
        "/api/v1/profile/tracks/manual",
        json={"id": "manual", "name": "Manual", "resume_base": "default", "keywords": ["x"]},
    )
    assert created.status_code == 201
    assert created.json()["field"] is None and created.json()["role"] is None


async def test_a_track_with_an_unknown_field_is_rejected(client: httpx.AsyncClient) -> None:
    response = await client.put(
        "/api/v1/profile/tracks/bogus",
        json={
            "id": "bogus",
            "name": "Bogus",
            "resume_base": "default",
            "field": "not-a-real-field",
        },
    )
    assert response.status_code == 422


async def test_a_track_whose_role_belongs_to_a_different_field_is_rejected(
    client: httpx.AsyncClient,
) -> None:
    response = await client.put(
        "/api/v1/profile/tracks/mismatched",
        json={
            "id": "mismatched",
            "name": "Mismatched",
            "resume_base": "default",
            # technical-program-manager belongs to program-project-management, not engineering.
            "field": "engineering",
            "role": "technical-program-manager",
        },
    )
    assert response.status_code == 422


async def test_a_track_with_a_role_but_no_field_is_rejected(client: httpx.AsyncClient) -> None:
    response = await client.put(
        "/api/v1/profile/tracks/rootless",
        json={
            "id": "rootless",
            "name": "Rootless",
            "resume_base": "default",
            "role": "technical-program-manager",
        },
    )
    assert response.status_code == 422


async def test_a_track_with_a_field_and_no_role_is_accepted(client: httpx.AsyncClient) -> None:
    response = await client.put(
        "/api/v1/profile/tracks/fielded",
        json={
            "id": "fielded",
            "name": "Fielded",
            "resume_base": "default",
            "field": "engineering",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["field"] == "engineering" and body["role"] is None
