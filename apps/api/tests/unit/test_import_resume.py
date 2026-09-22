import pytest

from rhapto.engine.import_resume import ImportedBlock, ResumeImport, import_resume, to_blocks
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
    blocks = to_blocks(
        [
            ImportedBlock(id="acme", type="role", content="x"),
            ImportedBlock(id="acme", type="project", content="y"),
        ]
    )
    assert len({b.id for b in blocks}) == 2
