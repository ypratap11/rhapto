from helpers import demo_resume

from rhapto.engine.compose import ComposeOutput
from rhapto.engine.providers.fake import FakeLLMProvider
from rhapto.engine.providers.llm import SystemBlock
from rhapto.engine.repair import REPAIR_INSTRUCTIONS, repair
from rhapto.models.guardrail_report import GuardrailReport, Violation


async def test_repair_sends_violations_and_previous_output() -> None:
    resume = demo_resume()
    previous = ComposeOutput(
        summary=resume.summary, sections=resume.sections, cover_note="c", change_log="l", answers=[]
    )
    fixed = previous.model_copy(update={"cover_note": "fixed"})
    report = GuardrailReport(
        passed=False,
        rules_run=["provenance", "no-unverified-metrics"],
        violations=[
            Violation(
                rule="no-unverified-metrics",
                severity="error",
                path="sections[0].entries[0].bullets[1]",
                message="metric(s) not found in verified block 'acme-migration': 25%",
                block_id="acme-migration",
            )
        ],
    )
    llm = FakeLLMProvider([fixed])
    system = [SystemBlock(text="rules", cache=True)]
    output, usage = await repair(previous, report, system, llm)
    assert output.cover_note == "fixed" and usage.input_tokens == 10
    call = llm.calls[0]
    assert call.system == system and call.output_schema is ComposeOutput
    body = call.messages[0].content
    assert (
        "sections[0].entries[0].bullets[1]" in body
        and "25%" in body
        and "<previous_output>" in body
    )


def test_repair_instructions_no_longer_tell_the_model_to_drop_bullets() -> None:
    """C1: shipping the detector while the repair prompt still says 'drop bullets' spends an LLM
    call teaching the model to commit the offence again."""
    text = " ".join(REPAIR_INSTRUCTIONS.split())  # the prompt wraps lines; compare clauses
    assert "drop bullets" not in text
    # The real restore-not-drop clauses, not incidental words in them.
    assert (
        "Never resolve ANY violation by deleting an entry, a section, or a block id" in text
    )
    assert "plus a new entry for every block id a completeness violation names" in text
    assert "shorten a low-priority entry to a single bullet -- never remove the entry" in text
    assert "remove only that bullet -- never the entry it was in" in text


def test_repair_keeps_only_entries_whose_block_id_is_in_blocks() -> None:
    """Deferred minor (T2): "keep an entry for every block id it already cites" contradicted
    provenance for an entry citing an id not in <blocks> -- that entry is un-repairable if it must
    be kept. The keep clause is scoped to <blocks>, and the other case is spelled out."""
    text = " ".join(REPAIR_INSTRUCTIONS.split())
    assert "keep an entry for every block id in <blocks> it already cites" in text
    assert (
        "An entry citing a block id that is not in <blocks> must be re-pointed to the right block"
        " or removed" in text
    )
