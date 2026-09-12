"""Golden tune cases: fictional JDs + scripted tune responses + expected pipeline outcome.

Mirrors `test_golden.py`, but the input is the user's own DOCX (the `helpers_docx` fixture)
instead of the block library, so each case scripts `tune.json` where the blocks cases script
`compose.json`.
"""

import io
import json
from pathlib import Path
from typing import Any

import pytest
from docx import Document
from helpers_docx import build_fixture_docx

from rhapto.engine.document import parse_docx
from rhapto.engine.pipeline import tailor
from rhapto.engine.providers.fake import FakeEmbeddingProvider, FakeLLMProvider
from rhapto.engine.types import TailorRequest
from rhapto.profile.loader import load_profile

CASES_DIR = Path(__file__).parent / "tune"
CASES = sorted(p for p in CASES_DIR.iterdir() if p.is_dir())


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
async def test_golden_tune_case(case: Path, demo_profile_dir: Path) -> None:
    responses = [_load(case / "extract.json"), _load(case / "tune.json")]
    if (case / "repair.json").exists():
        responses.append(_load(case / "repair.json"))
    expected = _load(case / "expected.json")
    llm = FakeLLMProvider(responses)

    source_docx = build_fixture_docx()
    result = await tailor(
        TailorRequest(
            jd_text=(case / "jd.txt").read_text(encoding="utf-8"),
            mode="tune",
            source_document=parse_docx(source_docx, "resume.docx"),
            source_docx=source_docx,
        ),
        load_profile(demo_profile_dir),
        llm,
        FakeEmbeddingProvider(),
    )
    package = result.package
    assert package.mode == "tune"
    assert package.status == expected["status"]
    assert package.guardrail_report.passed is expected["passed"]
    assert package.llm_calls == expected["llm_calls"]
    assert (
        sorted({v.rule for v in package.guardrail_report.violations}) == expected["violation_rules"]
    )
    assert package.guardrail_report.rules_run == expected["rules_run"]
    assert [e.paragraph_id for e in package.edits] == expected["edited_paragraph_ids"]
    assert len(llm.calls) == expected["llm_calls"]

    texts = [p.text for p in Document(io.BytesIO(result.docx)).paragraphs]
    for wanted in expected["docx_contains"]:
        assert wanted in texts, wanted


def test_every_tune_case_has_required_files() -> None:
    assert len(CASES) >= 2
    for case in CASES:
        for name in ("jd.txt", "extract.json", "tune.json", "expected.json"):
            assert (case / name).exists(), f"{case.name} is missing {name}"
