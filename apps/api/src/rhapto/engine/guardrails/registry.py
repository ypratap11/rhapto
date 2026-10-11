from __future__ import annotations

from collections.abc import Iterable

from rhapto.engine.guardrails.attribution import RULE_NAME as ATTRIBUTION
from rhapto.engine.guardrails.attribution import check_attribution
from rhapto.engine.guardrails.base import GuardrailContext, Rule, violation
from rhapto.engine.guardrails.completeness import RULE_NAME as COMPLETENESS
from rhapto.engine.guardrails.completeness import check_completeness
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


#: What to DO about each rule, one short sentence, written by whoever owns the rule.
#:
#: A blocked package already tells the user which rule fired, what it said and which bullet -- and
#: then stops, leaving "blocked" as the whole of the explanation on every list surface. This is the
#: missing half: the action.
#:
#: NOT part of `GuardrailReport`. That model is generated from `packages/schemas/guardrail_report.json`
#: with `extra="forbid"` and is PERSISTED as JSONB, so adding a field there would leave every existing
#: row without it. These are attached at response time instead, restricted to the rules that actually
#: appear in the report being returned.
#:
#: `test_guardrail_remedies.py` asserts this covers every `RULE_NAME` in `engine/guardrails/`, so a
#: seventh rule cannot ship with "blocked" and no next step.
# Tune mode's two rules are keyed by their literal ids: `tune.py` imports `UnknownGuardrailError` from
# this module, so importing its constants here is a certain cycle. `test_guardrail_remedies.py`
# asserts these literals equal `tune.TUNE_SCOPE` / `tune.NO_NEW_NUMBERS`.
TUNE_SCOPE_ID = "tune-scope"
NO_NEW_NUMBERS_ID = "no-new-numbers"

REMEDIES: dict[str, str] = {
    PROVENANCE: (
        "Every line has to come from an item in your experience. Regenerate, or add the claim to "
        "your experience first so the line has a source."
    ),
    METRICS: (
        "A number appeared that no confirmed item contains. Either confirm the item that holds "
        "that figure, or regenerate so the line stops stating it."
    ),
    ENTITIES: (
        "A company, job title or name appeared that does not match your own experience or resume. "
        "Regenerate, or correct it in your experience first."
    ),
    DATES: (
        "A date range is out of order, overlaps another role, or was changed. Fix the dates on "
        "that item in your experience (mark a role as overlapping if it really was), then "
        "regenerate."
    ),
    ATTRIBUTION: (
        "A note you asked to keep about shared work is missing. Regenerate, or put the wording "
        "you saved on that item back into the line."
    ),
    VISIBILITY: (
        "An item you marked to leave out for this kind of job was used anyway. Regenerate, or "
        "remove that mark on the item if it should be allowed."
    ),
    COMPLETENESS: (
        "Every selected role, project and credential must keep an entry. Shorten an entry to one "
        "line rather than deleting it, or regenerate."
    ),
    TUNE_SCOPE_ID: (
        "A change went beyond the summary, skills and bullet lines, or changed more than six "
        "bullets. Regenerate to get lighter edits."
    ),
    NO_NEW_NUMBERS_ID: (
        "A number appeared that is not in your resume. Regenerate, or add the number to your "
        "experience and confirm it first."
    ),
}

#: What each rule actually checks, in plain words, one sentence each. Mode-free: the same sentence
#: is true in blocks mode and tune mode, and `checks_for` is given only the rules that ran. Every
#: sentence was written against the rule module, and must not claim more than that code checks.
CHECK_SENTENCES: dict[str, str] = {
    PROVENANCE: "Every entry and line is linked to an item in your experience.",
    METRICS: "Every number appears in an item you confirmed.",
    COMPLETENESS: "Every role, project and credential picked for this job is still listed.",
    ENTITIES: "Company and job-title names match your own resume or profile.",
    DATES: "Dates were checked for consistency.",
    ATTRIBUTION: "Where you noted that work was shared, that note is kept.",
    VISIBILITY: "Items you marked to leave out for this kind of job were left out.",
    TUNE_SCOPE_ID: (
        "Only summary, skills and bullet lines were reworded, with at most six bullets changed."
    ),
    NO_NEW_NUMBERS_ID: "No number was added that is not already in your resume.",
}


def checks_for(rules: Iterable[str]) -> dict[str, str]:
    """The check sentences for exactly the rules named, deduplicated, skipping unknown ids."""
    return {r: CHECK_SENTENCES[r] for r in dict.fromkeys(rules) if r in CHECK_SENTENCES}


def remedies_for(rules: Iterable[str]) -> dict[str, str]:
    """The remedies for exactly the rules named, skipping any with none.

    Restricted rather than returned whole so a response carries only what its own report needs, and
    so a rule with no remedy degrades to an absent key -- which the UI renders as the rule id and
    message alone -- rather than to a missing row or a crash.
    """
    return {rule: REMEDIES[rule] for rule in dict.fromkeys(rules) if rule in REMEDIES}


class UnknownGuardrailError(EngineError):
    """guardrails.yaml names a rule this build does not ship."""


def run_guardrails(
    resume: ResumeDocument,
    profile: Profile,
    selection_ids: Iterable[str],
    extract: JDExtract,
    cover_note: str | None = None,
    *,
    include_completeness: bool = True,
) -> GuardrailReport:
    """Run the three unconditional rules plus every active configured rule.

    Provenance, no-unverified-metrics and completeness always run, for every account, whatever is or
    is not in the `guardrails` table. They are the product's promises (completeness is provenance's
    other half: a silent omission is a truthfulness failure); a deployment where they depend on a row
    existing is a deployment where a fresh account quietly has one of them switched off.

    A user may still carry a `no-unverified-metrics` row -- older profiles all do. Its `config` is
    honoured, and `active: false` is ignored rather than obeyed, because this rule is not one a user
    gets to turn off. It is never run twice.

    `include_completeness=False` is for the human hand-edit path ONLY (`api/routers/packages.py`,
    PATCH): a selected block the user deletes by hand is a deliberate choice, not a silent AI drop,
    which is what completeness guards against. Model output (tailor, repair) always runs it. This is
    a code flag and never a profile setting -- `guardrails.yaml` still cannot name the rule.
    Provenance and no-unverified-metrics run on every path, flag or not.
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
    if include_completeness:
        rules_run.append(COMPLETENESS)
        violations.extend(check_completeness(ctx))
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
