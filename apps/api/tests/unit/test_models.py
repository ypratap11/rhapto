from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from rhapto.models.guardrail_report import GuardrailReport, Violation
from rhapto.models.jd_extract import JDExtract
from rhapto.models.package import ApplicationPackage, JobSnapshot
from rhapto.models.profile.answers import AnswersFile
from rhapto.models.profile.bases import ResumeBase
from rhapto.models.profile.blocks import Block, BlocksFile, Visibility
from rhapto.models.profile.guardrails import GuardrailRule
from rhapto.models.profile.tracks import Track
from rhapto.models.profile.watchlist import WatchlistEntry
from rhapto.models.resume_document import (
    ResumeBullet,
    ResumeDocument,
    ResumeEntry,
    ResumeHeader,
    ResumeSection,
)


def test_block_defaults() -> None:
    block = Block(id="x-1", type="achievement", content="Did a thing.")
    assert block.verified is False
    assert block.tags == []
    assert block.visibility is None
    assert block.concurrent is False


def test_block_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        Block.model_validate({"id": "x", "type": "role", "content": "c", "bogus": 1})


def test_block_rejects_bad_type() -> None:
    with pytest.raises(ValidationError):
        Block.model_validate({"id": "x", "type": "hobby", "content": "c"})


def test_blocks_file_round_trip() -> None:
    data = {
        "blocks": [
            {"id": "a", "type": "role", "content": "c", "visibility": {"exclude_when": ["t"]}}
        ]
    }
    parsed = BlocksFile.model_validate(data)
    assert parsed.blocks[0].visibility == Visibility(exclude_when=["t"])


def test_track_and_base_defaults() -> None:
    track = Track(id="t", name="T", resume_base="b")
    assert track.min_fit == 50 and track.keywords == []
    base = ResumeBase(id="b", name="B", block_ids=["a"])
    assert base.section_order[0] == "summary" and base.style == {}


def test_guardrail_rule_defaults() -> None:
    rule = GuardrailRule(rule="no-unverified-metrics")
    assert rule.active is True and rule.config == {}


def test_answers_and_watchlist() -> None:
    assert AnswersFile(answers={"name": "Maya Chen"}).answers["name"] == "Maya Chen"
    assert (
        WatchlistEntry(company="ExampleCo", source="greenhouse", board="exampleco").board
        == "exampleco"
    )


def test_jd_extract_defaults() -> None:
    extract = JDExtract(company="ExampleCo", title="PM")
    assert extract.must_have == [] and extract.context_tags == []
    assert extract.location_policy == "unspecified"


def test_resume_document_and_package() -> None:
    resume = ResumeDocument(
        header=ResumeHeader(name="Maya Chen"),
        summary=[ResumeBullet(text="Summary.", source_block_id="acme-data-pm")],
        sections=[
            ResumeSection(
                title="Experience",
                kind="experience",
                entries=[
                    ResumeEntry(
                        source_block_id="acme-data-pm",
                        org="Acme Analytics",
                        bullets=[ResumeBullet(text="Led it.", source_block_id="acme-data-pm")],
                    )
                ],
            )
        ],
    )
    package = ApplicationPackage(
        job=JobSnapshot(company="ExampleCo", title="PM", jd_text="..."),
        track_id="data-pm",
        jd_extract=JDExtract(company="ExampleCo", title="PM"),
        resume=resume,
        cover_note="Hi.",
        change_log="Emphasised data.",
        answers={},
        guardrail_report=GuardrailReport(
            passed=False,
            rules_run=["provenance"],
            violations=[
                Violation(rule="provenance", severity="error", message="m", path="summary[0]")
            ],
        ),
        version=1,
        status="blocked",
        llm_calls=2,
        created_at=datetime.now(UTC),
    )
    dumped = package.model_dump(mode="json")
    assert ApplicationPackage.model_validate(dumped).resume.sections[0].kind == "experience"
