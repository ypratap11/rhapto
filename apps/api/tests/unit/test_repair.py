from helpers import demo_resume

from rhapto.engine.compose import ComposeOutput
from rhapto.engine.providers.fake import FakeLLMProvider
from rhapto.engine.providers.llm import SystemBlock
from rhapto.engine.repair import repair
from rhapto.models.guardrail_report import GuardrailReport, Violation


async def test_repair_sends_violations_and_previous_output() -> None:
    resume = demo_resume()
    previous = ComposeOutput(
        summary=resume.summary, sections=resume.sections, cover_note="c", change_log="l", answers={}
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
