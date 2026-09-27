from __future__ import annotations

from collections.abc import Iterable

from rhapto.engine.guardrails.attribution import RULE_NAME as ATTRIBUTION
from rhapto.engine.guardrails.attribution import check_attribution
from rhapto.engine.guardrails.base import GuardrailContext, Rule, violation
from rhapto.engine.guardrails.dates import RULE_NAME as DATES
from rhapto.engine.guardrails.dates import check_dates
from rhapto.engine.guardrails.entities import RULE_NAME as ENTITIES
from rhapto.engine.guardrails.entities import check_entities
from rhapto.engine.guardrails.metrics import RULE_NAME as METRICS
from rhapto.engine.guardrails.metrics import check_metrics, check_text_against_blocks
from rhapto.engine.guardrails.provenance import RULE_NAME as PROVENANCE
from rhapto.engine.guardrails.provenance import check_provenance
from rhapto.engine.guardrails.visibility import RULE_NAME as VISIBILITY
from rhapto.engine.guardrails.visibility import check_visibility
from rhapto.engine.types import EngineError, Profile
from rhapto.models.guardrail_report import GuardrailReport, Violation
from rhapto.models.jd_extract import JDExtract
from rhapto.models.resume_document import ResumeDocument

# Configurable rules, keyed by the name used in guardrails.yaml. Later tasks add entries.
#
# METRICS is deliberately ABSENT. CLAUDE.md states that provenance and no-unverified-metrics are both
# non-negotiable and that "neither is a user-toggleable rule" -- but metrics used to live here, which
# made it exactly that: a row in a table. Nothing seeds those rows, so every newly created account ran
# provenance alone, and its guardrail report said `passed: true` with `rules_run: ["provenance"]`,
# which reads like success. Found on this deployment the day a second person was invited: her account
# had zero guardrail rows, so a metric could have printed without being verified. It now runs
# unconditionally in run_guardrails, next to provenance, and cannot be switched off by a user, by a
# missing row, or by an `active: false` flag.
RULES: dict[str, Rule] = {
    ENTITIES: check_entities,
    DATES: check_dates,
    ATTRIBUTION: check_attribution,
    VISIBILITY: check_visibility,
}


class UnknownGuardrailError(EngineError):
    """guardrails.yaml names a rule this build does not ship."""


def run_guardrails(
    resume: ResumeDocument,
    profile: Profile,
    selection_ids: Iterable[str],
    extract: JDExtract,
    cover_note: str | None = None,
) -> GuardrailReport:
    """Run the two unconditional rules plus every active configured rule.

    Provenance and no-unverified-metrics always run, for every account, whatever is or is not in the
    `guardrails` table. They are the product's two promises; a deployment where they depend on a row
    existing is a deployment where a fresh account quietly has one of them switched off.

    A user may still carry a `no-unverified-metrics` row -- older profiles all do. Its `config` is
    honoured, and `active: false` is ignored rather than obeyed, because this rule is not one a user
    gets to turn off. It is never run twice.
    """
    ctx = GuardrailContext(
        resume=resume,
        blocks=profile.block_map(),
        selection_ids=frozenset(selection_ids),
        extract=extract,
    )
    rules_run = [PROVENANCE, METRICS]
    violations: list[Violation] = check_provenance(ctx)
    # Honour an existing row's config if the profile has one; otherwise the rule's own defaults.
    metrics_config = next((r.config for r in profile.guardrails if r.rule == METRICS), None)
    metrics_ctx = ctx if metrics_config is None else ctx.with_config(metrics_config)
    violations.extend(check_metrics(metrics_ctx))
    for rule in profile.guardrails:
        if rule.rule == METRICS:
            continue  # already run above, unconditionally
        if not rule.active:
            continue
        check = RULES.get(rule.rule)
        if check is None:
            raise UnknownGuardrailError(f"unknown guardrail rule: {rule.rule}")
        violations.extend(check(ctx.with_config(rule.config)))
        rules_run.append(rule.rule)
    if cover_note is not None:
        violations.extend(_check_cover_note(ctx, cover_note))
    passed = not any(v.severity == "error" for v in violations)
    return GuardrailReport(passed=passed, rules_run=rules_run, violations=violations)


def _check_cover_note(ctx: GuardrailContext, cover_note: str) -> list[Violation]:
    """The cover note is output the user pastes into a form, so it obeys the metric rule too."""
    selected_verified = [
        block
        for block_id, block in ctx.blocks.items()
        if block_id in ctx.selection_ids and block.verified
    ]
    offending = check_text_against_blocks(cover_note, selected_verified)
    if not offending:
        return []
    return [
        violation(
            METRICS,
            f"cover note contains metric(s) not found in a verified selected block: "
            f"{', '.join(offending)}",
            "cover_note",
            None,
        )
    ]
