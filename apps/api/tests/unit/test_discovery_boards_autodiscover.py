from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import User
from rhapto.db.repositories import profile as profile_repo
from rhapto.db.repositories import searches as searches_repo
from rhapto.models.profile.tracks import Track
from rhapto.services.discovery.boards import board_from_url
from rhapto.services.discovery.search import derive_searches


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://boards.greenhouse.io/exampleco/jobs/1", ("greenhouse", "exampleco")),
        ("https://JOB-BOARDS.greenhouse.io/Example-Co/jobs/9", ("greenhouse", "Example-Co")),
        ("https://jobs.lever.co/exampleco/abc-123?utm=x", ("lever", "exampleco")),
        ("https://jobs.ashbyhq.com/example.co/xyz", ("ashby", "example.co")),
        ("https://acme.myworkdayjobs.com/en-US/External/job/1", ("workday", "acme/External")),
        (
            "https://acme.myworkdayjobs.com/wday/cxs/acme/External/jobs",
            ("workday", "acme/External"),
        ),
        # Workday's own canonical posting URLs carry no language segment -- this is the exact
        # shape NVIDIA's externalUrl uses. Reading segments[1] as the site here yielded the
        # literal word "job", which added a `nvidia.wd5/job` watchlist row that 404s every poll.
        (
            "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/job/US-CA-Santa-Clara/Some-Role_JR1",
            ("workday", "nvidia.wd5/NVIDIAExternalCareerSite"),
        ),
        # The board root, with and without a language segment.
        ("https://acme.myworkdayjobs.com/External", ("workday", "acme/External")),
        ("https://acme.myworkdayjobs.com/fr-FR/External", ("workday", "acme/External")),
    ],
)
def test_board_from_url_matches_every_pattern(url: str, expected: tuple[str, str]) -> None:
    assert board_from_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://www.linkedin.com/jobs/view/1",
        "https://boards.greenhouse.io/",
        "https://evil.myworkdayjobs.com.attacker.net/en-US/External/job/1",
        "not a url",
        "https://jobs.lever.co/",
    ],
)
def test_board_from_url_rejects_non_boards(url: str) -> None:
    assert board_from_url(url) is None


async def test_derive_searches_is_idempotent(session: AsyncSession, user: User) -> None:
    await profile_repo.upsert_track(
        session,
        user.id,
        Track(
            id="tpm",
            name="TPM",
            resume_base="b",
            min_fit=60,
            keywords=[
                "program manager",
                "roadmap",
                "delivery",
                "stakeholders",
                "risk",
                "okrs",
                "ignored",
            ],
        ),
    )
    await profile_repo.set_answers(
        session,
        user.id,
        {"location_home": "Denver, CO", "location_preferred": "Boulder, CO", "remote_ok": "yes"},
    )
    await session.flush()
    created = await derive_searches(session, user.id)
    assert [c.name for c in created] == ["TPM"]
    assert created[0].keywords == [
        "program manager",
        "roadmap",
        "delivery",
        "stakeholders",
        "risk",
        "okrs",
    ]
    assert created[0].location == "Boulder, CO"
    assert created[0].remote == "include"
    assert created[0].derived_from_track_id == "tpm"
    assert await derive_searches(session, user.id) == []
    assert len(await searches_repo.list_searches(session, user.id)) == 1
