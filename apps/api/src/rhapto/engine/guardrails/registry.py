from __future__ import annotations

from collections.abc import Iterable

from rhapto.engine.guardrails.base import GuardrailContext, Rule
from rhapto.engine.guardrails.metrics import RULE_NAME as METRICS
from rhapto.engine.guardrails.metrics import check_metrics
from rhapto.engine.guardrails.provenance import RULE_NAME as PROVENANCE
from rhapto.engine.guardrails.provenance import check_provenance
from rhapto.engine.types import EngineError, Profile
from rhapto.models.guardrail_report import GuardrailReport, Violation
from rhapto.models.jd_extract import JDExtract
from rhapto.models.resume_document import ResumeDocument

# Configurable rules, keyed by the name used in guardrails.yaml. Later tasks add entries.
RULES: dict[str, Rule] = {METRICS: check_metrics}


class UnknownGuardrailError(EngineError):
    """guardrails.yaml names a rule this build does not ship."""


def run_guardrails(
    resume: ResumeDocument,
    profile: Profile,
    selection_ids: Iterable[str],
    extract: JDExtract,
) -> GuardrailReport:
    ctx = GuardrailContext(
        resume=resume,
        blocks=profile.block_map(),
        selection_ids=frozenset(selection_ids),
        extract=extract,
    )
    rules_run = [PROVENANCE]
    violations: list[Violation] = check_provenance(ctx)
    for rule in profile.guardrails:
        if not rule.active:
            continue
        check = RULES.get(rule.rule)
        if check is None:
            raise UnknownGuardrailError(f"unknown guardrail rule: {rule.rule}")
        violations.extend(check(ctx.with_config(rule.config)))
        rules_run.append(rule.rule)
    passed = not any(v.severity == "error" for v in violations)
    return GuardrailReport(passed=passed, rules_run=rules_run, violations=violations)
