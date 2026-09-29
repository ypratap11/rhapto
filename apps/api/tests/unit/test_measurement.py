from pathlib import Path
from typing import Any

import pytest
from helpers import demo_extract, good_output

from rhapto.engine.measurement import (
    final_rules,
    first_pass_rules,
    invented_project_titles,
    summarize_result,
)
from rhapto.engine.pipeline import CallBudget, TailorResult, tailor
from rhapto.engine.providers.fake import FakeEmbeddingProvider, FakeLLMProvider
from rhapto.engine.types import Profile, TailorRequest
from rhapto.profile.loader import load_profile

JD = "ExampleCo seeks a Data Platform Program Manager to lead our Snowflake migration."
MALFORMED = {"$PARAMETER_NAME": "$PARAMETER_VALUE"}
DISTINCTIVE_TITLE = "Zqxv-Wibblefrotz Award Konsortium"


@pytest.fixture
def profile(demo_profile_dir: Path) -> Profile:
    return load_profile(demo_profile_dir)


def missing_role_output() -> dict[str, Any]:
    output = good_output()
    output["sections"][0]["entries"] = []
    return output


async def _run(profile: Profile, script: list[Any], **kwargs: Any) -> TailorResult:
    llm = FakeLLMProvider(script)
    return await tailor(TailorRequest(jd_text=JD), profile, llm, FakeEmbeddingProvider(), **kwargs)


async def test_a_run_that_passed_first_time_is_clean(profile: Profile) -> None:
    result = await _run(profile, [demo_extract(), good_output()])
    assert summarize_result(result) == "passed clean"
    assert first_pass_rules(result) == [] and final_rules(result) == []


async def test_a_malformed_output_retry_is_not_read_as_a_repair(profile: Profile) -> None:
    """I-3. Three calls and a draft -- exactly the shape a repair success has -- but the third call
    was a retry after malformed output. Counting calls would report a repair that never happened."""
    result = await _run(profile, [demo_extract(), MALFORMED, good_output()])
    assert result.package.llm_calls == 3 and result.package.status == "draft"
    assert summarize_result(result) == "passed clean"


async def test_a_dropped_role_that_repair_restored_is_reported_with_its_rule(
    profile: Profile,
) -> None:
    """The C6 number: the final report is clean, yet the first pass failed `completeness`."""
    result = await _run(profile, [demo_extract(), missing_role_output(), good_output()])
    assert result.package.guardrail_report.passed
    assert first_pass_rules(result) == ["completeness"] and final_rules(result) == []
    assert summarize_result(result) == "repaired (first pass failed: completeness)"


async def test_a_dropped_role_that_repair_did_not_restore_is_blocked_after_repair(
    profile: Profile,
) -> None:
    script = [demo_extract(), missing_role_output(), missing_role_output()]
    result = await _run(profile, script)
    assert summarize_result(result) == (
        "blocked after repair (completeness); first pass failed: completeness"
    )


async def test_an_exhausted_budget_is_blocked_with_no_repair_run(profile: Profile) -> None:
    script = [demo_extract(), missing_role_output(), good_output()]
    result = await _run(profile, script, budget=CallBudget(max_calls=2))
    assert result.package.llm_calls == 2
    assert summarize_result(result) == "blocked, no repair ran (completeness)"


async def test_a_project_title_copied_from_its_block_is_not_invented(profile: Profile) -> None:
    result = await _run(profile, [demo_extract(), good_output()])
    assert invented_project_titles(result, profile.block_map()) == []


async def test_an_invented_project_title_passes_every_guardrail_and_is_still_recorded(
    profile: Profile,
) -> None:
    """U-1, the known-bad input. No rule validates an entry's title, so this run is a clean
    `draft` -- which is exactly why `invented_project_titles` has to exist. Without it the assertion
    below cannot be written, and the measurement is blind to the risk it is meant to watch.
    The helper reports block ids only (privacy), never the offending text."""
    output = good_output()
    output["sections"][1]["entries"][0]["title"] = "Award-winning evaluation platform"
    result = await _run(profile, [demo_extract(), output])
    assert result.package.status == "draft" and summarize_result(result) == "passed clean"
    assert invented_project_titles(result, profile.block_map()) == ["side-llm-tool"]


async def test_no_title_or_content_string_reaches_a_ledger_row(profile: Profile) -> None:
    """Privacy: the script may run on the owner's real profile, so a row may hold rule names, block
    ids and counts only. Known-bad: a distinctive invented title must appear nowhere in the row."""
    output = good_output()
    output["sections"][1]["entries"][0]["title"] = DISTINCTIVE_TITLE
    result = await _run(profile, [demo_extract(), output])
    blocks = profile.block_map()
    hits = invented_project_titles(result, blocks)
    assert hits == ["side-llm-tool"]
    row = [
        summarize_result(result),
        *first_pass_rules(result),
        *final_rules(result),
        *hits,
    ]
    assert "wibblefrotz" not in " ".join(row).casefold()
    assert all(h in blocks for h in hits)  # every entry is a block id, nothing free-form
