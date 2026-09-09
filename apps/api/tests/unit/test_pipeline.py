from pathlib import Path
from typing import Any

import pytest
from helpers import bullet, demo_extract, demo_resume

from rhapto.engine.compose import ComposeOutput
from rhapto.engine.pipeline import CallBudget, LLMBudgetExceeded, TailorResult, tailor
from rhapto.engine.providers.fake import FakeEmbeddingProvider, FakeLLMProvider
from rhapto.engine.providers.llm import TokenUsage
from rhapto.engine.types import Profile, ProfileError, TailorRequest
from rhapto.profile.loader import load_profile

JD = "ExampleCo seeks a Data Platform Program Manager to lead our Snowflake migration."


@pytest.fixture
def profile(demo_profile_dir: Path) -> Profile:
    return load_profile(demo_profile_dir)


def good_output() -> dict[str, Any]:
    resume = demo_resume()
    return ComposeOutput(
        summary=resume.summary,
        sections=resume.sections,
        cover_note="Dear ExampleCo team, " + "word " * 120,
        change_log="Emphasised migration.",
        answers={"why_this_company": "Data."},
    ).model_dump(mode="json")


def bad_output() -> dict[str, Any]:
    output = good_output()
    output["sections"][0]["entries"][0]["bullets"][1] = bullet(
        "Cut warehouse cost 25%.", "acme-migration"
    ).model_dump()
    return output


def test_call_budget() -> None:
    budget = CallBudget(max_calls=2)
    budget.before_call()
    budget.after_call(TokenUsage(input_tokens=3))
    budget.before_call()
    budget.after_call(TokenUsage(input_tokens=4))
    assert budget.calls == 2 and budget.usage.input_tokens == 7
    with pytest.raises(LLMBudgetExceeded):
        budget.before_call()


async def test_happy_path_uses_two_calls(profile: Profile) -> None:
    llm = FakeLLMProvider([demo_extract(), good_output()])
    steps: list[str] = []

    async def on_step(name: str) -> None:
        steps.append(name)

    result = await tailor(
        TailorRequest(jd_text=JD), profile, llm, FakeEmbeddingProvider(), on_step=on_step
    )
    assert isinstance(result, TailorResult)
    package = result.package
    assert package.status == "draft" and package.guardrail_report.passed and package.llm_calls == 2
    assert package.version == 1 and package.track_id == "data-pm"
    assert package.job.company == "ExampleCo" and package.job.jd_text == JD
    assert package.resume.header.name == "Maya Chen"
    assert "acme-migration" in result.selection.block_ids
    assert result.docx[:2] == b"PK"
    assert steps == ["extract", "select", "compose", "validate", "render"]


async def test_repair_path_uses_three_calls_and_passes(profile: Profile) -> None:
    llm = FakeLLMProvider([demo_extract(), bad_output(), good_output()])
    result = await tailor(TailorRequest(jd_text=JD), profile, llm, FakeEmbeddingProvider())
    assert result.package.status == "draft" and result.package.llm_calls == 3
    repair_call = llm.calls[2]
    assert "25%" in repair_call.messages[0].content and repair_call.output_schema is ComposeOutput
    assert repair_call.system == llm.calls[1].system  # same cached system blocks as compose


async def test_unrepairable_output_is_blocked(profile: Profile) -> None:
    llm = FakeLLMProvider([demo_extract(), bad_output(), bad_output()])
    result = await tailor(TailorRequest(jd_text=JD), profile, llm, FakeEmbeddingProvider())
    assert result.package.status == "blocked" and result.package.llm_calls == 3
    assert {v.rule for v in result.package.guardrail_report.violations} == {"no-unverified-metrics"}
    assert (
        result.docx[:2] == b"PK"
    )  # still rendered for review; the orphan check is the only hard stop


async def test_budget_exceeded_raises_before_fourth_call(profile: Profile) -> None:
    llm = FakeLLMProvider([demo_extract(), bad_output(), bad_output()])
    with pytest.raises(LLMBudgetExceeded):
        await tailor(
            TailorRequest(jd_text=JD),
            profile,
            llm,
            FakeEmbeddingProvider(),
            budget=CallBudget(max_calls=2),
        )
    assert len(llm.calls) == 2


async def test_orphan_bullet_blocks_without_docx(profile: Profile) -> None:
    output = good_output()
    output["summary"] = [bullet("Made up.", "ghost").model_dump()]
    llm = FakeLLMProvider([demo_extract(), output, output])
    result = await tailor(TailorRequest(jd_text=JD), profile, llm, FakeEmbeddingProvider())
    assert result.package.status == "blocked" and result.docx == b""
    assert any(v.rule == "provenance" for v in result.package.guardrail_report.violations)


async def test_regeneration_increments_version_and_passes_feedback(profile: Profile) -> None:
    first = await tailor(
        TailorRequest(jd_text=JD),
        profile,
        FakeLLMProvider([demo_extract(), good_output()]),
        FakeEmbeddingProvider(),
    )
    llm = FakeLLMProvider([demo_extract(), good_output()])
    second = await tailor(
        TailorRequest(
            jd_text=JD, feedback="lean harder on migration", previous_package=first.package
        ),
        profile,
        llm,
        FakeEmbeddingProvider(),
    )
    assert second.package.version == 2
    assert "lean harder on migration" in llm.calls[1].messages[0].content
    assert "<previous_resume>" in llm.calls[1].messages[0].content


async def test_unknown_track_raises(profile: Profile) -> None:
    with pytest.raises(ProfileError):
        await tailor(
            TailorRequest(jd_text=JD, track_id="nope"),
            profile,
            FakeLLMProvider([]),
            FakeEmbeddingProvider(),
        )
