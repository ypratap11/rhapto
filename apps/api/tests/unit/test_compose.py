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
from rhapto.engine.prompts.compose import COMPOSE_RULES
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


def test_application_answers_excludes_header_and_scoring_keys() -> None:
    answers = application_answers(
        {
            "name": "x",
            "email": "e",
            "location_home": "Denver, CO",
            "location_preferred": "Denver, Boulder",
            "remote_ok": "yes",
            "notice_period": "2 weeks",
        }
    )
    assert answers == {"notice_period": "2 weeks"}


def test_system_blocks_cache_the_rules_and_carry_only_the_selected_blocks(
    demo_profile_dir: Path,
) -> None:
    """The composer must not see a block it is forbidden to cite.

    The prompt used to carry every block in the track's base while provenance permitted only the
    selected ones, so the model could -- and did -- cite blocks outside the selection and the
    package was rejected. Widening the selection cannot close that gap; removing the unselected
    blocks from the prompt does. The rules stay in their own cached block, stable across runs.
    """
    profile = load_profile(demo_profile_dir)
    track = profile.get_track("data-pm")
    selection = Selection(
        block_ids=["acme-migration"],
        scores={},
        excluded_block_ids=[],
        requirements_text="Snowflake",
    )
    blocks = build_system_blocks(profile, track, selection)

    assert blocks[0].cache is True and "source_block_id" in blocks[0].text
    # The rules block is stable, so it must not carry any profile content.
    assert "acme-migration" not in blocks[0].text

    assert blocks[1].cache is False
    assert '"id": "acme-migration"' in blocks[1].text
    assert "Data Program Management" in blocks[1].text
    # A base block that selection did not pick must not be visible at all.
    assert "acme-data-pm" not in blocks[1].text


def test_compose_rules_forbid_counting_words_in_the_cover_note() -> None:
    """The cover note must not spend a number on ordinary prose.

    `no-unverified-metrics` checks the cover note with the same detector it uses on bullets, and
    `CARDINAL_RE` matches a bare spelled cardinal -- so "the two things I do together" reads as an
    unsourced metric and blocks the whole package. The rule is right to be strict; the writer is
    the layer that should avoid the construction. The `one` carve-out already in `metrics.py`
    exists for exactly this class of false positive, and the prompt closes the rest of it: three
    consecutive regenerations of a real application were lost to this before the guidance existed.
    """
    assert "spelled-out numbers" in COMPOSE_RULES
    assert "cover_note" in COMPOSE_RULES


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
