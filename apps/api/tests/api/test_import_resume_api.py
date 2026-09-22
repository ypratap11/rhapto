from __future__ import annotations

import re

import httpx
import pytest
from helpers_docx import build_fixture_docx

from rhapto.engine.import_resume import ImportedBlock, ImportedLocation, ImportedTrack, ResumeImport
from rhapto.engine.providers.fake import FakeLLMProvider
from rhapto.engine.providers.llm import LLMProvider
from rhapto.services.documents import MAX_BYTES

_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")

VALID_TAXONOMY_FIELDS = {
    "engineering",
    "data-science",
    "product",
    "program-project-management",
    "design",
    "marketing",
    "sales",
    "finance",
    "operations",
    "people",
    "customer-success",
    "other",
}


def _proposal(*, track_field: str, track_role: str) -> ResumeImport:
    """A scripted proposal shaped like what the LLM would return for the fixture resume.

    The endpoint's job under test is what it does with a proposal, not the LLM prompt itself
    (that is Task 1's job), so the LLM is stubbed rather than calling a real provider.
    """
    return ResumeImport(
        blocks=[
            ImportedBlock(
                id="acme-lead",
                type="role",
                org="Acme Analytics",
                role="Senior Data Program Manager",
                period="2019-2025",
                content="Led the Snowflake migration for 12 teams, cutting warehouse cost 30%.",
                metric="30%",
            ),
        ],
        tracks=[
            ImportedTrack(id="tpm", name="TPM", keywords=[], field=track_field, role=track_role)
        ],
        location=ImportedLocation(
            location_home="Denver, CO", location_preferred=[], remote_ok=None
        ),
    )


def _stub_llm(monkeypatch: pytest.MonkeyPatch, proposal: ResumeImport) -> None:
    """Replace the endpoint's `resolve_llm` with one returning a scripted `FakeLLMProvider`.

    The endpoint calls `resolve_llm` directly (not through the worker's injectable resolver), and
    the default test settings resolve a real Anthropic adapter with a placeholder key, so without
    this the test would attempt a real network call.
    """
    fake = FakeLLMProvider([proposal])

    async def _resolve(session: object, settings: object, user_id: object) -> LLMProvider:
        return fake

    monkeypatch.setattr("rhapto.api.routers.profile.resolve_llm", _resolve)


async def test_import_returns_a_proposal_without_persisting_anything(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec §9: the endpoint is read-only with respect to the profile."""
    _stub_llm(
        monkeypatch,
        _proposal(track_field="program-project-management", track_role="technical-program-manager"),
    )
    before = (await client.get("/api/v1/profile/blocks")).json()
    docx = build_fixture_docx()
    res = await client.post("/api/v1/profile/import-resume", files={"file": ("cv.docx", docx)})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["blocks"], "expected at least one proposed block"
    assert all(b["verified"] is False for b in body["blocks"])
    after = (await client.get("/api/v1/profile/blocks")).json()
    assert after == before, "import must not write to the profile"


async def test_a_track_with_invented_taxonomy_is_dropped(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A track whose field is not in the taxonomy would silently empty every Field filter."""
    _stub_llm(monkeypatch, _proposal(track_field="not-a-real-field", track_role="whatever"))
    docx = build_fixture_docx()
    res = await client.post("/api/v1/profile/import-resume", files={"file": ("cv.docx", docx)})
    assert res.status_code == 200, res.text
    body = res.json()
    for track in body["tracks"]:
        assert track["field"] in VALID_TAXONOMY_FIELDS
    assert body["tracks"] == [], "the invented field must be dropped, not merely flagged"


async def test_a_non_docx_upload_is_rejected(client: httpx.AsyncClient) -> None:
    res = await client.post("/api/v1/profile/import-resume", files={"file": ("cv.txt", b"hello")})
    assert res.status_code == 422
    assert "docx" in res.json()["detail"].lower()


async def test_an_oversized_upload_is_rejected(client: httpx.AsyncClient) -> None:
    """`services.documents.MAX_BYTES` (5 MB) is the cap the rest of the repo enforces on an
    uploaded resume; nothing bounded this endpoint before, so a huge file was read whole into the
    API process and then handed to the LLM."""
    oversized = b"0" * (MAX_BYTES + 1)
    res = await client.post("/api/v1/profile/import-resume", files={"file": ("cv.docx", oversized)})
    assert res.status_code == 422
    assert "5 mb" in res.json()["detail"].lower()


async def test_dropped_periods_and_metrics_to_confirm_are_reported(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The review screen's stat tiles come straight from these two counts."""
    proposal = ResumeImport(
        blocks=[
            ImportedBlock(
                id="acme-lead",
                type="role",
                org="Acme",
                role="Lead",
                period="summer of 2019",  # unparseable -> dropped
                content="Led delivery.",
                metric="30%",  # carries a metric -> needs confirming
            ),
            ImportedBlock(
                id="acme-note",
                type="achievement",
                period="2019-2023",
                content="Shipped the migration.",
                metric=None,
            ),
        ],
        tracks=[],
        location=ImportedLocation(location_home=None, location_preferred=[], remote_ok=None),
    )
    _stub_llm(monkeypatch, proposal)
    res = await client.post(
        "/api/v1/profile/import-resume", files={"file": ("cv.docx", build_fixture_docx())}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["dropped_periods"] == 1
    assert body["metrics_to_confirm"] == 1
    by_id = {b["id"]: b for b in body["blocks"]}
    assert by_id["acme-lead"]["period"] is None
    assert by_id["acme-note"]["period"] == "2019-2023"


async def test_a_malformed_block_id_does_not_500_the_import(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One bad id out of many must not destroy the whole import and the user's LLM spend."""
    proposal = ResumeImport(
        blocks=[
            ImportedBlock(id="Acme_Lead!", type="role", content="Led delivery."),
            ImportedBlock(id="good-block", type="skill", content="Python"),
        ],
        tracks=[],
        location=ImportedLocation(location_home=None, location_preferred=[], remote_ok=None),
    )
    _stub_llm(monkeypatch, proposal)
    res = await client.post(
        "/api/v1/profile/import-resume", files={"file": ("cv.docx", build_fixture_docx())}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    ids = [b["id"] for b in body["blocks"]]
    assert len(ids) == 2
    for block_id in ids:
        assert _ID_PATTERN.match(block_id), block_id


async def test_a_malformed_track_id_is_normalised(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A track id in the wrong shape must not survive to the `PUT /profile/tracks/{id}` the web
    app performs on accept -- that write 422ing after the blocks are already saved is the
    partial-import scenario in finding 3."""
    proposal = ResumeImport(
        blocks=[],
        tracks=[
            ImportedTrack(
                id="TPM Track!",
                name="TPM",
                keywords=[],
                field="program-project-management",
                role="technical-program-manager",
            )
        ],
        location=ImportedLocation(location_home=None, location_preferred=[], remote_ok=None),
    )
    _stub_llm(monkeypatch, proposal)
    res = await client.post(
        "/api/v1/profile/import-resume", files={"file": ("cv.docx", build_fixture_docx())}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["tracks"]) == 1
    assert _ID_PATTERN.match(body["tracks"][0]["id"]), body["tracks"][0]["id"]
