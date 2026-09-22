import re

import pytest

from rhapto.engine.import_resume import (
    MAX_RESUME_CHARS,
    ImportedBlock,
    ImportedTrack,
    ResumeImport,
    import_resume,
    to_blocks,
    to_tracks,
)
from rhapto.engine.providers.fake import FakeLLMProvider
from rhapto.models.source_document import DocParagraph, SourceDocument


def _doc() -> SourceDocument:
    return SourceDocument(
        filename="cv.docx",
        paragraphs=[
            DocParagraph(id="p1", text="Jane Roe", role="heading", section=None),
            DocParagraph(
                id="p2",
                text="Delivery Lead, Acme 2019-2023",
                role="entry_title",
                section="Experience",
            ),
        ],
        sections=[],
    )


def _payload() -> dict:
    return ResumeImport(
        blocks=[
            ImportedBlock(
                id="acme-lead",
                type="role",
                org="Acme",
                role="Delivery Lead",
                period="2019-2023",
                content="Led delivery for Acme.",
                metric=None,
            ),
        ],
        tracks=[],
        location={"location_home": "Dublin, CA", "location_preferred": [], "remote_ok": "yes"},
    ).model_dump(mode="json")


async def test_import_resume_makes_one_call_and_returns_the_proposal() -> None:
    llm = FakeLLMProvider([_payload()])
    result, usage = await import_resume(_doc(), llm)
    assert [b.id for b in result.blocks] == ["acme-lead"]
    assert result.location.location_home == "Dublin, CA"
    assert usage.output_tokens >= 0


async def test_an_empty_document_is_rejected_before_spending_a_call() -> None:
    empty = SourceDocument(filename="cv.docx", paragraphs=[], sections=[])
    llm = FakeLLMProvider([])
    with pytest.raises(ValueError, match="empty"):
        await import_resume(empty, llm)


async def test_a_huge_document_is_truncated_before_it_reaches_the_llm() -> None:
    """A large upload must not translate into an unbounded prompt charged to the user's key."""
    huge = SourceDocument(
        filename="cv.docx",
        paragraphs=[
            DocParagraph(id="p1", text="x" * (MAX_RESUME_CHARS * 3), role="other", section=None)
        ],
        sections=[],
    )
    llm = FakeLLMProvider([_payload()])
    await import_resume(huge, llm)
    assert len(llm.calls) == 1
    sent = llm.calls[0].messages[0].content
    assert len(sent) <= MAX_RESUME_CHARS + len("<resume>\n\n</resume>")


def test_imported_blocks_are_never_verified() -> None:
    """The whole provenance guarantee rests on this: a number the user has not confirmed
    must not be citable. An import that auto-verified would put a figure they wrote once
    onto every future resume with Rhapto's blessing."""
    blocks = to_blocks(
        [
            ImportedBlock(id="a", type="role", content="Cut costs 30%.", metric="30%"),
        ]
    )
    assert all(b.verified is False for b in blocks)


def test_an_unparseable_period_is_dropped_not_guessed() -> None:
    """Fabricating employment dates on a CV is not a recoverable error."""
    blocks = to_blocks(
        [
            ImportedBlock(id="a", type="role", period="summer of 2019", content="x"),
            ImportedBlock(id="b", type="role", period="2019-2023", content="y"),
        ]
    )
    assert blocks[0].period is None
    assert blocks[1].period == "2019-2023"


def test_duplicate_ids_are_made_unique() -> None:
    """Four colliding `acme` ids, plus an explicit `acme-2` that lands *before* them, so the
    auto-suffix loop must notice `acme-2` is already taken and skip past it rather than reusing
    it -- the scenario the review manually verified before any test covered it."""
    blocks = to_blocks(
        [
            ImportedBlock(id="acme-2", type="credential", content="explicit"),
            ImportedBlock(id="acme", type="role", content="a"),
            ImportedBlock(id="acme", type="project", content="b"),
            ImportedBlock(id="acme", type="skill", content="c"),
            ImportedBlock(id="acme", type="achievement", content="d"),
        ]
    )
    ids = [b.id for b in blocks]
    assert len(ids) == len(set(ids)) == 5
    assert ids == ["acme-2", "acme", "acme-3", "acme-4", "acme-5"]


def test_a_malformed_id_from_the_llm_is_normalised_not_rejected() -> None:
    """`Acme_Lead!`/`Acme-Lead` are ordinary LLM output; `Block.id` requires
    `^[a-z0-9][a-z0-9-]*$`. A bad id must be fixed, not left to blow up `to_blocks` with an
    unhandled `ValidationError` that would 500 the whole import over one block."""
    blocks = to_blocks(
        [
            ImportedBlock(id="Acme_Lead!", type="role", content="a"),
            ImportedBlock(id="Acme-Lead", type="role", content="b"),
            ImportedBlock(id="!!!", type="role", content="c"),
        ]
    )
    ids = [b.id for b in blocks]
    for block_id in ids:
        assert re.match(r"^[a-z0-9][a-z0-9-]*$", block_id), block_id
    assert len(ids) == len(set(ids)) == 3
    # The two ids that normalise to the same slug ("acme-lead") must still end up unique.
    assert ids[0] == "acme-lead"
    assert ids[1] == "acme-lead-2"


def test_to_tracks_normalises_and_deduplicates_ids() -> None:
    tracks = to_tracks(
        [
            ImportedTrack(
                id="TPM",
                name="TPM",
                keywords=[],
                field="program-project-management",
                role="technical-program-manager",
            ),
            ImportedTrack(
                id="tpm",
                name="TPM 2",
                keywords=[],
                field="program-project-management",
                role="technical-program-manager",
            ),
            ImportedTrack(
                id="", name="Blank", keywords=[], field="engineering", role="software-engineer"
            ),
        ]
    )
    ids = [t.id for t in tracks]
    for track_id in ids:
        assert re.match(r"^[a-z0-9][a-z0-9-]*$", track_id), track_id
    assert len(ids) == len(set(ids)) == 3
    assert ids[0] == "tpm"
    assert ids[1] == "tpm-2"
