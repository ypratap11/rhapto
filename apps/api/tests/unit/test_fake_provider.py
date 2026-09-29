from __future__ import annotations

import json

import pytest

from rhapto.config import Settings
from rhapto.engine.compose import ComposeOutput
from rhapto.engine.guardrails.registry import run_guardrails
from rhapto.engine.providers.fake import FAKE_MODEL, DeterministicFakeProvider
from rhapto.engine.providers.llm import Message, SystemBlock
from rhapto.engine.providers.registry import (
    PROVIDERS,
    build_llm,
    model_for,
    provider_info,
)
from rhapto.engine.tune import TuneOutput
from rhapto.models.jd_extract import JDExtract
from rhapto.profile.loader import load_profile
from rhapto.services.llm import env_llm_config, warn_if_fake_llm

JD = (
    "Technical Program Manager, Data Platform\n"
    "You will run cross functional programs for the data platform team, manage dependencies "
    "across engineering, and report on delivery risk to leadership."
)


def _settings(provider: str = "fake", **kwargs: object) -> Settings:
    return Settings(_env_file=None, rhapto_llm_provider=provider, **kwargs)  # type: ignore[arg-type]


def test_fake_is_never_in_the_settings_picker() -> None:
    assert "fake" not in PROVIDERS
    assert provider_info("fake") is not None
    assert provider_info("nope") is None


def test_the_default_provider_is_still_anthropic() -> None:
    assert Settings(_env_file=None).rhapto_llm_provider == "anthropic"
    # Without a key, the default deployment resolves to nothing -- never to the fake.
    assert env_llm_config(Settings(_env_file=None)) is None


def test_env_resolution_picks_the_fake_up_with_no_api_key() -> None:
    config = env_llm_config(_settings())
    assert config is not None
    assert config.provider == "fake" and config.model == FAKE_MODEL
    assert build_llm(config.provider, config.model, config.api_key).__class__ is (
        DeterministicFakeProvider
    )
    assert model_for("fake", "") == FAKE_MODEL
    # A model id left over from another provider does not follow you into the fake.
    assert model_for("fake", "claude-sonnet-5") == FAKE_MODEL


def test_it_warns_loudly_only_when_active(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("WARNING"):
        assert warn_if_fake_llm(_settings()) is True
    assert "RHAPTO_LLM_PROVIDER=fake" in caplog.text
    assert "never" in caplog.text.lower()
    caplog.clear()
    with caplog.at_level("WARNING"):
        assert warn_if_fake_llm(_settings("anthropic")) is False
    assert caplog.text == ""


async def _compose(blocks_json: str, selected: list[str]) -> ComposeOutput:
    provider = DeterministicFakeProvider()
    result = await provider.complete_structured(
        system=[SystemBlock(text=f"rules\n\n<blocks>\n{blocks_json}\n</blocks>", cache=True)],
        messages=[
            Message(
                role="user",
                content=f"<selected_block_ids>\n{json.dumps(selected)}\n</selected_block_ids>",
            )
        ],
        output_schema=ComposeOutput,
    )
    return result.value


async def test_it_extracts_a_title_and_keywords_from_the_jd() -> None:
    provider = DeterministicFakeProvider()
    result = await provider.complete_structured(
        system=[SystemBlock(text="rules")],
        messages=[Message(role="user", content=JD)],
        output_schema=JDExtract,
    )
    extract = result.value
    assert extract.title == "Technical Program Manager, Data Platform"
    assert extract.company
    assert extract.keywords, "an empty extract makes the golden classification meaningless"
    # Deterministic: the same JD twice gives the same answer.
    again = await provider.complete_structured(
        system=[SystemBlock(text="rules")],
        messages=[Message(role="user", content=JD)],
        output_schema=JDExtract,
    )
    assert again.value.model_dump() == extract.model_dump()


async def test_compose_cites_only_selected_blocks_and_copies_them_verbatim(
    demo_profile_dir: object,
) -> None:
    profile = load_profile(demo_profile_dir)  # type: ignore[arg-type]
    blocks = [b.model_dump(mode="json", exclude_none=True) for b in profile.blocks]
    selected = [b["id"] for b in blocks]
    output = await _compose(json.dumps(blocks), selected)
    cited = {e.source_block_id for s in output.sections for e in s.entries}
    assert cited and cited <= set(selected)
    by_id = {b["id"]: b for b in blocks}
    for section in output.sections:
        for entry in section.entries:
            source = by_id[entry.source_block_id]
            assert entry.org == source.get("org")
            assert entry.role == source.get("role")
            assert entry.period == source.get("period")
            for bullet in entry.bullets:
                assert source["content"] in bullet.text
                assert bullet.source_block_id == entry.source_block_id
    assert output.cover_note and output.change_log


async def test_every_mandatory_block_of_the_demo_profile_gets_an_entry(
    demo_profile_dir: object,
) -> None:
    """Review C-2 (2026-09-29). The fake skips any unverified block whose content holds a digit,
    and (before this fixture change) `side-llm-tool` and `cred-pmp` both did, so the demo stack
    produced a resume with two selected blocks missing. Every role, project and credential block
    in `profile.example` must be one the fake can place."""
    profile = load_profile(demo_profile_dir)  # type: ignore[arg-type]
    blocks = [b.model_dump(mode="json", exclude_none=True) for b in profile.blocks]
    output = await _compose(json.dumps(blocks), [b["id"] for b in blocks])
    cited = {e.source_block_id for s in output.sections for e in s.entries}
    mandatory = {b.id for b in profile.blocks if b.type in ("role", "project", "credential")}
    assert mandatory == {"acme-data-pm", "side-llm-tool", "cred-pmp"}, "fixture drifted"
    assert mandatory <= cited, sorted(mandatory - cited)


async def test_a_block_outside_the_selection_is_never_cited(demo_profile_dir: object) -> None:
    profile = load_profile(demo_profile_dir)  # type: ignore[arg-type]
    blocks = [b.model_dump(mode="json", exclude_none=True) for b in profile.blocks]
    selected = [blocks[0]["id"]]
    output = await _compose(json.dumps(blocks), selected)
    cited = {e.source_block_id for s in output.sections for e in s.entries}
    assert cited == set(selected)


async def test_the_composed_resume_passes_every_guardrail(demo_profile_dir: object) -> None:
    from rhapto.engine.compose import assemble_resume

    profile = load_profile(demo_profile_dir)  # type: ignore[arg-type]
    blocks = [b.model_dump(mode="json", exclude_none=True) for b in profile.blocks]
    selected = [b["id"] for b in blocks]
    output = await _compose(json.dumps(blocks), selected)
    resume = assemble_resume(output, profile)
    extract = JDExtract(company="ExampleCo", title="Technical Program Manager")
    report = run_guardrails(resume, profile, selected, extract, cover_note=output.cover_note)
    assert report.passed, [v.model_dump() for v in report.violations]


async def test_a_period_nested_inside_another_entrys_period_is_skipped_and_recorded(
    demo_profile_dir: object,
) -> None:
    """`acme-migration` (achievement, period "2023") sits entirely inside `acme-data-pm`'s own
    period ("2019-2025"). This provider never merges an achievement's bullet into its role's
    entry the way the real compose prompt does -- every entry here cites exactly one block -- so
    giving `acme-migration` its own "experience" entry would trip the real date-consistency
    guardrail on a false-positive overlap (two "jobs" that were never actually concurrent). It
    must be dropped, and the drop must be visible rather than silent: a change to the skip logic
    that started over- or under-dropping content should break this test, not sail through with
    every existing assertion (which only check subset relations) still green.
    """
    profile = load_profile(demo_profile_dir)  # type: ignore[arg-type]
    by_id = {b.id: b for b in profile.blocks}
    blocks = [
        by_id["acme-data-pm"].model_dump(mode="json", exclude_none=True),
        by_id["acme-migration"].model_dump(mode="json", exclude_none=True),
    ]
    selected = [b["id"] for b in blocks]
    output = await _compose(json.dumps(blocks), selected)
    cited = {e.source_block_id for s in output.sections for e in s.entries}
    assert cited == {"acme-data-pm"}, "acme-migration's period nests inside acme-data-pm's"
    # Observable, not silent: the change log names the dropped block and why.
    assert "acme-migration" in output.change_log
    assert "overlap" in output.change_log.lower()


async def test_tune_mode_proposes_no_edits() -> None:
    provider = DeterministicFakeProvider()
    result = await provider.complete_structured(
        system=[SystemBlock(text="rules")],
        messages=[Message(role="user", content="<document>\np1: hello\n</document>")],
        output_schema=TuneOutput,
    )
    # Zero edits is the only rewrite of someone's own document that cannot invent anything.
    assert result.value.edits == []
    assert result.value.cover_note and result.value.change_log


async def test_an_unsupported_schema_says_so() -> None:
    from pydantic import BaseModel

    from rhapto.engine.providers.llm import MalformedOutputError

    class Surprise(BaseModel):
        whatever: int

    with pytest.raises(MalformedOutputError, match="Surprise"):
        await DeterministicFakeProvider().complete_structured(
            system=[], messages=[], output_schema=Surprise
        )
