from pathlib import Path

import pytest
from helpers import bullet, demo_extract, demo_resume

from rhapto.engine.guardrails.registry import RULES, UnknownGuardrailError, run_guardrails
from rhapto.models.profile.guardrails import GuardrailRule
from rhapto.profile.loader import load_profile


def test_provenance_always_runs_even_with_no_configured_rules(demo_profile_dir: Path) -> None:
    profile = load_profile(demo_profile_dir).model_copy(update={"guardrails": []})
    resume = demo_resume()
    resume.summary.append(bullet("Made up.", "ghost"))
    report = run_guardrails(resume, profile, profile.block_map(), demo_extract())
    assert report.rules_run == ["provenance"]
    assert report.passed is False and report.violations[0].rule == "provenance"


def test_inactive_rules_are_skipped(demo_profile_dir: Path) -> None:
    profile = load_profile(demo_profile_dir)
    inactive = [GuardrailRule(rule=r.rule, active=False) for r in profile.guardrails]
    profile = profile.model_copy(update={"guardrails": inactive})
    report = run_guardrails(demo_resume(), profile, profile.block_map(), demo_extract())
    assert report.rules_run == ["provenance"] and report.passed is True


def test_unknown_rule_raises(demo_profile_dir: Path) -> None:
    profile = load_profile(demo_profile_dir).model_copy(
        update={"guardrails": [GuardrailRule(rule="bogus")]}
    )
    with pytest.raises(UnknownGuardrailError, match="bogus"):
        run_guardrails(demo_resume(), profile, profile.block_map(), demo_extract())


def test_registry_has_no_provenance_entry() -> None:
    assert "provenance" not in RULES
