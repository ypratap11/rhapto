"""Real guardrail reports for the web's review-panel tests (Release B, review I8).

The three JSON files in `apps/web/src/components/review/__fixtures__/` are NOT hand-written: they are
produced by running the real rules over the fictional `profile.example/` (and the fictional tune
fixture document), then attached to the same `checks` / `remedies` the API serves. This test fails
when they drift from what the code now produces. Regenerate with:

    cd apps/api && uv run python tests/unit/test_guardrail_report_fixture.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from helpers import bullet, demo_extract, demo_resume  # noqa: E402
from helpers_docx import build_fixture_docx  # noqa: E402

from rhapto.engine.document import parse_docx  # noqa: E402
from rhapto.engine.guardrails.registry import checks_for, remedies_for, run_guardrails  # noqa: E402
from rhapto.engine.guardrails.tune import run_tune_guardrails  # noqa: E402
from rhapto.models.guardrail_report import GuardrailReport  # noqa: E402
from rhapto.models.profile.blocks import Block  # noqa: E402
from rhapto.models.source_document import Edit  # noqa: E402
from rhapto.profile.loader import load_profile  # noqa: E402

REPO = Path(__file__).resolve().parents[4]
PROFILE_EXAMPLE = REPO / "profile.example"
FIXTURE_DIR = REPO / "apps" / "web" / "src" / "components" / "review" / "__fixtures__"
FILES = {
    "blocked-report": "blocked-report.json",
    "passed-blocks-report": "passed-blocks-report.json",
    "passed-tune-report": "passed-tune-report.json",
}

#: A credential the user selected but left empty: no org, role or content, so it cannot be printed.
#: Completeness reports it as a WARNING (completeness.py:15, raised at :226) -- never an error.
EMPTY_CREDENTIAL = Block(id="cred-draft", type="credential", content="")


def _shape(report: GuardrailReport, mode: str) -> dict[str, Any]:
    return {
        "report": report.model_dump(mode="json"),
        "checks": checks_for(report.rules_run),
        "remedies": remedies_for(v.rule for v in report.violations),
        "mode": mode,
    }


def _blocks_report(*, invent_a_number: bool) -> GuardrailReport:
    profile = load_profile(PROFILE_EXAMPLE)
    profile = profile.model_copy(update={"blocks": [*profile.blocks, EMPTY_CREDENTIAL]})
    resume = demo_resume()
    if invent_a_number:
        migration = resume.sections[0].entries[0]
        migration.bullets[1] = bullet(
            "Owned the Snowflake migration end to end, cutting warehouse cost 40%.",
            "acme-migration",
        )
    selection = [b.id for b in profile.blocks]
    return run_guardrails(resume, profile, selection, demo_extract())


def _tune_report() -> GuardrailReport:
    doc = parse_docx(build_fixture_docx(), "resume.docx")
    bullet_para = next(p for p in doc.paragraphs if p.role == "bullet")
    edit = Edit(
        paragraph_id=bullet_para.id,
        before=bullet_para.text,
        after="Led the Snowflake migration for 12 teams, reducing warehouse cost 30%.",
        reason="Lead with the outcome.",
    )
    profile = load_profile(PROFILE_EXAMPLE)
    return run_tune_guardrails(doc, [edit], demo_extract(), profile.guardrails, cover_note=None)


def build_fixtures() -> dict[str, dict[str, Any]]:
    return {
        "blocked-report": _shape(_blocks_report(invent_a_number=True), "blocks"),
        "passed-blocks-report": _shape(_blocks_report(invent_a_number=False), "blocks"),
        "passed-tune-report": _shape(_tune_report(), "tune"),
    }


def test_committed_fixtures_equal_what_the_rules_produce() -> None:
    built = build_fixtures()
    for name, filename in FILES.items():
        committed = json.loads((FIXTURE_DIR / filename).read_text(encoding="utf-8"))
        assert committed == built[name], f"{filename} is stale: re-run this file to regenerate"


def test_the_fixtures_carry_the_cases_the_web_tests_depend_on() -> None:
    built = build_fixtures()
    blocked = built["blocked-report"]["report"]
    severities = {v["severity"] for v in blocked["violations"]}
    assert blocked["passed"] is False
    assert severities == {"error", "warning"}

    passed = built["passed-blocks-report"]["report"]
    assert passed["passed"] is True
    warnings = [v for v in passed["violations"] if v["severity"] == "warning"]
    assert warnings and all(v["rule"] == "completeness" for v in warnings)
    assert not [v for v in passed["violations"] if v["severity"] == "error"]

    tune = built["passed-tune-report"]
    assert tune["mode"] == "tune"
    assert tune["report"]["passed"] is True
    assert tune["report"]["rules_run"][:2] == ["tune-scope", "no-new-numbers"]
    assert "provenance" not in tune["checks"] and "no-unverified-metrics" not in tune["checks"]
    for entry in built.values():
        assert set(entry["checks"]) == set(entry["report"]["rules_run"])


if __name__ == "__main__":
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for fixture_name, payload in build_fixtures().items():
        target = FIXTURE_DIR / FILES[fixture_name]
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {target}")
