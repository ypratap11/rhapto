import json
from pathlib import Path

from helpers import bullet, demo_extract, demo_resume

from rhapto.engine.compose import (
    AnswerItem,
    ComposeOutput,
    application_answers,
    assemble_resume,
    build_header,
    build_system_blocks,
    build_user_message,
    compose,
)
from rhapto.engine.providers.fake import FakeLLMProvider
from rhapto.engine.select import Selection
from rhapto.profile.loader import load_profile


def _selection() -> Selection:
    return Selection(
        block_ids=["acme-data-pm", "acme-migration", "side-llm-tool", "cred-pmp"],
        scores={},
        excluded_block_ids=[],
        requirements_text="Snowflake",
    )


def _output() -> ComposeOutput:
    resume = demo_resume()
    return ComposeOutput(
        summary=resume.summary,
        sections=resume.sections,
        cover_note="Dear team, ...",
        change_log="Emphasised Snowflake migration.",
        answers=[AnswerItem(key="why_this_company", value="Because data.")],
    )


def test_build_header_from_answers() -> None:
    header = build_header(
        {"name": "Maya Chen", "email": "m@example.com", "links": "a.example, b.example"}
    )
    assert header.name == "Maya Chen" and header.email == "m@example.com"
    assert header.links == ["a.example", "b.example"] and header.phone is None
    assert build_header({}).name == "Candidate"


def test_application_answers_excludes_header_keys() -> None:
    answers = application_answers({"name": "x", "email": "e", "notice_period": "2 weeks"})
    assert answers == {"notice_period": "2 weeks"}


def test_system_blocks_cache_rules_and_base_blocks(demo_profile_dir: Path) -> None:
    profile = load_profile(demo_profile_dir)
    blocks = build_system_blocks(profile, profile.get_track("data-pm"))
    assert blocks[0].cache is True and "source_block_id" in blocks[0].text
    assert '"id": "acme-migration"' in blocks[0].text
    assert "Data Program Management" in blocks[1].text and blocks[1].cache is False


def test_user_message_contains_job_selection_answers_feedback_previous() -> None:
    message = build_user_message(
        demo_extract(),
        _selection(),
        {"notice_period": "2 weeks"},
        feedback="lean harder on migration",
        previous=demo_resume(),
    )
    assert "Data Platform Program Manager" in message
    assert json.dumps(_selection().block_ids) in message
    assert "notice_period" in message and "lean harder on migration" in message
    assert "<previous_resume>" in message and "Acme Analytics" in message
    assert "<feedback>" not in build_user_message(demo_extract(), _selection(), {})


async def test_compose_calls_llm_with_schema_and_returns_output(demo_profile_dir: Path) -> None:
    profile = load_profile(demo_profile_dir)
    llm = FakeLLMProvider([_output()])
    output, usage = await compose(
        demo_extract(), profile, profile.get_track("data-pm"), _selection(), llm
    )
    assert output.cover_note.startswith("Dear") and usage.output_tokens == 5
    call = llm.calls[0]
    assert call.output_schema is ComposeOutput and call.system[0].cache is True
    assert call.messages[0].role == "user"


async def test_user_message_never_carries_contact_details(demo_profile_dir: Path) -> None:
    profile = load_profile(demo_profile_dir)
    assert profile.answers["email"] == "maya.chen@example.com"  # the demo profile has them
    secrets = ("maya.chen@example.com", "+1 555 0100", "Denver, CO")
    llm = FakeLLMProvider([_output(), _output()])
    track = profile.get_track("data-pm")
    await compose(demo_extract(), profile, track, _selection(), llm, "tighten it", demo_resume())
    regenerated = llm.calls[0].messages[0].content
    assert "<previous_resume>" in regenerated and "Maya Chen" in regenerated
    for secret in secrets:
        assert secret not in regenerated, secret
    await compose(demo_extract(), profile, track, _selection(), llm)
    fresh = llm.calls[1].messages[0].content
    for secret in secrets:
        assert secret not in fresh, secret


def test_assemble_resume_adds_header(demo_profile_dir: Path) -> None:
    profile = load_profile(demo_profile_dir)
    resume = assemble_resume(_output(), profile)
    assert resume.header.name == "Maya Chen" and resume.header.email == "maya.chen@example.com"
    assert resume.sections[0].entries[0].bullets[0] == bullet(
        "Led cross-functional delivery of the customer data platform across 4 teams.",
        "acme-data-pm",
    )
