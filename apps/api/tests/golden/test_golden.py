"""Golden cases: fictional JDs + scripted LLM responses + expected pipeline outcome. Demo profile only."""

import json
from pathlib import Path
from typing import Any

import pytest

from rhapto.engine.pipeline import tailor
from rhapto.engine.providers.fake import FakeEmbeddingProvider, FakeLLMProvider
from rhapto.engine.types import TailorRequest
from rhapto.profile.loader import load_profile

CASES_DIR = Path(__file__).parent / "cases"
CASES = sorted(p for p in CASES_DIR.iterdir() if p.is_dir())


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
async def test_golden_case(case: Path, demo_profile_dir: Path) -> None:
    responses = [_load(case / "extract.json"), _load(case / "compose.json")]
    if (case / "repair.json").exists():
        responses.append(_load(case / "repair.json"))
    expected = _load(case / "expected.json")
    llm = FakeLLMProvider(responses)

    result = await tailor(
        TailorRequest(jd_text=(case / "jd.txt").read_text(encoding="utf-8")),
        load_profile(demo_profile_dir),
        llm,
        FakeEmbeddingProvider(),
    )
    package = result.package
    assert package.status == expected["status"]
    assert package.guardrail_report.passed is expected["passed"]
    assert package.llm_calls == expected["llm_calls"]
    assert (
        sorted({v.rule for v in package.guardrail_report.violations}) == expected["violation_rules"]
    )
    for block_id in expected["selected_block_ids_include"]:
        assert block_id in result.selection.block_ids, block_id
    assert len(llm.calls) == expected["llm_calls"]


def test_every_case_has_required_files() -> None:
    for case in CASES:
        for name in ("jd.txt", "extract.json", "compose.json", "expected.json"):
            assert (case / name).exists(), f"{case.name} is missing {name}"
