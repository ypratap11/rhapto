from pathlib import Path

import pytest
from helpers import bullet, demo_extract, demo_resume

from rhapto.engine.guardrails.registry import RULES, UnknownGuardrailError, run_guardrails
from rhapto.models.profile.guardrails import GuardrailRule
from rhapto.profile.loader import load_profile


def test_all_unconditional_rules_run_with_no_configured_rules(demo_profile_dir: Path) -> None:
    """An account with an empty `guardrails` table still gets BOTH product promises.

    This asserted `["provenance"]` until 2026-09-26, which was the true behaviour and the defect:
    no-unverified-metrics lived in the configurable RULES dict, nothing seeds those rows, so every
    newly created account ran provenance alone and reported `passed: true`. Found in production the
    day a second person was invited -- her account had zero rows.
    """
    profile = load_profile(demo_profile_dir).model_copy(update={"guardrails": []})
    resume = demo_resume()
    resume.summary.append(bullet("Made up.", "ghost"))
    report = run_guardrails(resume, profile, profile.block_map(), demo_extract())
    assert report.rules_run == ["provenance", "no-unverified-metrics", "completeness"]
    assert report.passed is False and report.violations[0].rule == "provenance"


def test_an_unverified_metric_is_caught_with_no_configured_rules(demo_profile_dir: Path) -> None:
    """The half of the above that actually protects the user: metrics is enforced on a bare account.

    Without this, the rules_run assertion alone would pass while check_metrics did nothing.
    """
    profile = load_profile(demo_profile_dir).model_copy(update={"guardrails": []})
    resume = demo_resume()
    # A number that appears in no verified selected block at all.
    resume.summary.append(bullet("Cut latency by 97% across 41 services.", "acme-data-pm"))
    report = run_guardrails(resume, profile, profile.block_map(), demo_extract())
    assert report.passed is False
    assert any(v.rule == "no-unverified-metrics" for v in report.violations), report.violations


def test_inactive_rules_are_skipped(demo_profile_dir: Path) -> None:
    profile = load_profile(demo_profile_dir)
    inactive = [GuardrailRule(rule=r.rule, active=False) for r in profile.guardrails]
    profile = profile.model_copy(update={"guardrails": inactive})
    report = run_guardrails(demo_resume(), profile, profile.block_map(), demo_extract())
    # The configurable rules obey `active: false`; the three unconditional ones do not appear here
    # because of a row, so they cannot be switched off by clearing one.
    assert report.rules_run == ["provenance", "no-unverified-metrics", "completeness"]
    assert report.passed is True


def test_metrics_cannot_be_switched_off_by_an_inactive_row(demo_profile_dir: Path) -> None:
    """`active: false` on no-unverified-metrics is ignored, not obeyed.

    CLAUDE.md: provenance and no-unverified-metrics are non-negotiable and neither is user-toggleable.
    A rule a user can disable is not a guarantee, and the report would still say `passed: true`.
    """
    profile = load_profile(demo_profile_dir)
    profile = profile.model_copy(
        update={"guardrails": [GuardrailRule(rule="no-unverified-metrics", active=False)]}
    )
    resume = demo_resume()
    resume.summary.append(bullet("Cut latency by 97% across 41 services.", "acme-data-pm"))
    report = run_guardrails(resume, profile, profile.block_map(), demo_extract())
    assert "no-unverified-metrics" in report.rules_run
    assert report.passed is False
    assert any(v.rule == "no-unverified-metrics" for v in report.violations), report.violations


def test_metrics_is_never_run_twice_when_a_row_exists(demo_profile_dir: Path) -> None:
    """An older profile carries a metrics row; running it unconditionally must not double-report."""
    profile = load_profile(demo_profile_dir)
    assert any(r.rule == "no-unverified-metrics" for r in profile.guardrails), "fixture drifted"
    resume = demo_resume()
    resume.summary.append(bullet("Cut latency by 97% across 41 services.", "acme-data-pm"))
    report = run_guardrails(resume, profile, profile.block_map(), demo_extract())
    assert report.rules_run.count("no-unverified-metrics") == 1
    metric_violations = [v for v in report.violations if v.rule == "no-unverified-metrics"]
    assert len(metric_violations) == len({(v.message, v.path) for v in metric_violations})


def test_unknown_rule_raises(demo_profile_dir: Path) -> None:
    profile = load_profile(demo_profile_dir).model_copy(
        update={"guardrails": [GuardrailRule(rule="bogus")]}
    )
    with pytest.raises(UnknownGuardrailError, match="bogus"):
        run_guardrails(demo_resume(), profile, profile.block_map(), demo_extract())


def test_registry_has_no_entry_for_any_unconditional_rule() -> None:
    """All three are run directly by run_guardrails, not looked up from a user's config."""
    assert "provenance" not in RULES
    assert "no-unverified-metrics" not in RULES
    assert "completeness" not in RULES
