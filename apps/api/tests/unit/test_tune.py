"""The tune composer: prompt assembly, edit materialisation, and the LLM call shape."""

from helpers import demo_extract
from helpers_docx import build_fixture_docx

from rhapto.engine.document import parse_docx
from rhapto.engine.guardrails.tune import MAX_BULLET_EDITS as guardrail_max_bullet_edits
from rhapto.engine.prompts.tune import TUNE_RULES
from rhapto.engine.providers.fake import FakeLLMProvider
from rhapto.engine.tune import (
    MAX_BULLET_EDITS,
    ProposedEdit,
    TuneOutput,
    build_tune_system_blocks,
    build_tune_user_message,
    to_edits,
    tune,
    tune_repair,
)
from rhapto.models.guardrail_report import GuardrailReport, Violation
from rhapto.models.source_document import Edit, SourceDocument


def _doc() -> SourceDocument:
    return parse_docx(build_fixture_docx(), "resume.docx")


def _output() -> TuneOutput:
    return TuneOutput(
        edits=[
            ProposedEdit(
                paragraph_id="p9",
                text="Led the Snowflake migration for 12 teams, reducing warehouse cost 30%.",
                reason="mirrors the JD",
            )
        ],
        cover_note="I have led Snowflake migrations end to end.",
        change_log="Emphasised the migration.",
        answers=[],
    )


def test_max_bullet_edits_is_six_on_both_sides() -> None:
    """The prompt promises six and the validator enforces six; they must not drift apart."""
    assert MAX_BULLET_EDITS == 6
    assert MAX_BULLET_EDITS == guardrail_max_bullet_edits
    assert "At most 6 bullet edits" in TUNE_RULES


def test_system_blocks_are_one_cached_block_with_the_document() -> None:
    blocks = build_tune_system_blocks(_doc())
    assert len(blocks) == 1
    assert blocks[0].cache is True
    text = blocks[0].text
    assert "Rhapto's resume tuner" in text
    assert "At most 6 bullet edits" in text
    assert '<p id="p0" role="name"' in text
    assert '<p id="p9" role="bullet" section="PROFESSIONAL EXPERIENCE">' in text
    assert "<document>" in text and "</document>" in text


def test_system_blocks_skip_empty_paragraphs() -> None:
    doc = _doc()
    doc.paragraphs[10].text = ""
    text = build_tune_system_blocks(doc)[0].text
    assert '<p id="p10"' not in text
    assert '<p id="p9"' in text


def test_user_message_carries_job_answers_feedback_and_previous_edits() -> None:
    previous = [Edit(paragraph_id="p9", before="old", after="new", reason="r")]
    message = build_tune_user_message(
        demo_extract(),
        {"name": "Maya Chen", "email": "maya.chen@example.com", "salary_range": "$160k-$190k base"},
        "lean harder on migration",
        previous,
    )
    assert "<job>" in message and "ExampleCo" in message
    assert "salary_range" in message
    assert "maya.chen@example.com" not in message  # header keys never reach the LLM
    assert "lean harder on migration" in message
    assert "<previous_edits>" in message and '"after": "new"' in message


def test_user_message_omits_optional_sections() -> None:
    message = build_tune_user_message(demo_extract(), {}, None, None)
    assert "<feedback>" not in message and "<previous_edits>" not in message


def test_to_edits_fills_before_and_drops_no_ops() -> None:
    doc = _doc()
    original = next(p for p in doc.paragraphs if p.id == "p9")
    output = TuneOutput(
        edits=[
            ProposedEdit(paragraph_id="p9", text="Led the migration.", reason="tighter"),
            ProposedEdit(paragraph_id="p10", text=doc.paragraphs[10].text, reason="unchanged"),
            ProposedEdit(paragraph_id="p3", text="  " + doc.paragraphs[3].text + "  ", reason="ws"),
        ],
        cover_note="note",
        change_log="log",
    )
    edits = to_edits(doc, output)
    assert [e.paragraph_id for e in edits] == ["p9"]
    assert edits[0].before == original.text
    assert edits[0].after == "Led the migration."
    assert edits[0].reason == "tighter"


def test_to_edits_dedupes_by_paragraph_id_keeping_the_last_proposal() -> None:
    """Only the last rewrite of a paragraph reaches the document, so only it becomes an edit."""
    doc = _doc()
    output = TuneOutput(
        edits=[
            ProposedEdit(paragraph_id="p9", text="First attempt.", reason="a"),
            ProposedEdit(paragraph_id="p3", text="Summary rewrite.", reason="b"),
            ProposedEdit(paragraph_id="p9", text="Second attempt.", reason="c"),
        ],
        cover_note="note",
        change_log="log",
    )
    edits = to_edits(doc, output)
    assert [(e.paragraph_id, e.after) for e in edits] == [
        ("p3", "Summary rewrite."),
        ("p9", "Second attempt."),
    ]
    assert edits[1].reason == "c"


def test_to_edits_keeps_an_earlier_edit_when_the_later_one_is_a_no_op() -> None:
    doc = _doc()
    output = TuneOutput(
        edits=[
            ProposedEdit(paragraph_id="p9", text="A real rewrite.", reason="a"),
            ProposedEdit(paragraph_id="p9", text=doc.paragraphs[9].text, reason="b"),
        ],
        cover_note="note",
        change_log="log",
    )
    assert [e.after for e in to_edits(doc, output)] == ["A real rewrite."]


def test_to_edits_keeps_unknown_ids_so_the_scope_rule_can_flag_them() -> None:
    output = TuneOutput(
        edits=[ProposedEdit(paragraph_id="p999", text="Invented.", reason="r")],
        cover_note="note",
        change_log="log",
    )
    edits = to_edits(_doc(), output)
    assert [(e.paragraph_id, e.before) for e in edits] == [("p999", "")]


async def test_tune_returns_the_scripted_output_and_sends_the_document() -> None:
    doc = _doc()
    llm = FakeLLMProvider([_output()])
    output, usage = await tune(demo_extract(), doc, {"name": "Maya Chen"}, llm)
    assert output == _output()
    assert usage.input_tokens == 10
    call = llm.calls[0]
    assert call.output_schema is TuneOutput
    assert '<p id="p9" role="bullet"' in call.system[0].text
    assert call.system[0].cache is True
    assert "<job>" in call.messages[0].content


async def test_tune_repair_reuses_the_system_blocks_and_lists_violations() -> None:
    doc = _doc()
    system = build_tune_system_blocks(doc)
    report = GuardrailReport(
        passed=False,
        rules_run=["tune-scope", "no-new-numbers"],
        violations=[
            Violation(
                rule="no-new-numbers",
                severity="error",
                message="number(s) not in the document: 45",
                path="edits[0]",
                block_id="p9",
            )
        ],
    )
    llm = FakeLLMProvider([_output()])
    output, _usage = await tune_repair(_output(), report, system, llm)
    assert output == _output()
    call = llm.calls[0]
    assert call.system == system
    assert call.output_schema is TuneOutput
    content = call.messages[0].content
    assert "45" in content and "edits[0]" in content
    assert "<previous_output>" in content and "<violations>" in content
