"""Guardrails for tune mode, where the source of truth is the user's own document.

The blocks-mode rules compare generated text against a block library; here there is no library,
so every check is "is this already in the document the user uploaded?". That makes the rules
simpler and stricter: a number, a name, or a year that is not in the document cannot be in the
output, because the only legitimate operation in tune mode is rephrasing what is already there.

Every tune violation is an `error`. A warning would mean "we think the model invented something
but we will write it into the user's resume anyway", which is not a trade-off this mode offers.
"""

from __future__ import annotations

import re

from rhapto.engine.document import (
    EDITABLE_ROLES,
    document_entities,
    document_numbers,
)
from rhapto.engine.guardrails.base import normalize_entity, violation
from rhapto.engine.guardrails.dates import RULE_NAME as DATES
from rhapto.engine.guardrails.entities import RULE_NAME as ENTITIES
from rhapto.engine.guardrails.metrics import (
    find_numeric_tokens,
    find_spelled_quantities,
    normalize_number,
)
from rhapto.models.guardrail_report import GuardrailReport, Violation
from rhapto.models.jd_extract import JDExtract
from rhapto.models.profile.guardrails import GuardrailRule
from rhapto.models.source_document import Edit, SourceDocument

TUNE_SCOPE = "tune-scope"
NO_NEW_NUMBERS = "no-new-numbers"
MAX_BULLET_EDITS = 6

YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
PRESENT = re.compile(r"\b(?:present|current)\b", re.IGNORECASE)
# A word that could start a capitalised entity name. Apostrophes and internal dots stay in the
# token so "B.S." and "Moody's" survive as one word.
WORD = re.compile(r"[A-Za-z][A-Za-z.'’-]*")
SENTENCE_END = ".!?\n"
# Capitalised words that are ordinary English mid-sentence and never an organisation or product
# on their own. Deliberately short: the sentence-start exemption already absorbs most prose, so
# anything else capitalised mid-sentence is a name until the document says otherwise.
COMMON_WORDS = frozenset(
    """
    i a an the and but or if when while for with at in on of to as by from that this these those
    it we our us my their his her its also however then plus per via not no so than after before
    during across into over under between within without about because both each every all most
    more less new first next last same other they he she you your there here
    january february march april may june july august september october november december
    monday tuesday wednesday thursday friday saturday sunday
    """.split()
)


def _is_sentence_start(text: str, index: int) -> bool:
    """True when nothing but whitespace, quotes or brackets separates `index` from the start of
    the text or from the end of the previous sentence."""
    for ch in reversed(text[:index]):
        if ch.isspace() or ch in "\"'([{‘“":
            continue
        return ch in SENTENCE_END
    return True


def capitalised_runs(text: str) -> list[str]:
    """Maximal runs of capitalised words that are not at the start of a sentence.

    A run is the unit checked against the document, so "Globex Corp" is reported whole rather
    than as two words that happen to be unknown. A single capitalised word counts as a run of
    one unless it is in `COMMON_WORDS`.
    """
    runs: list[str] = []
    current: list[str] = []
    end_of_previous = -1
    for match in WORD.finditer(text):
        word = match.group(0)
        capitalised = word[0].isupper()
        contiguous = bool(current) and text[end_of_previous : match.start()].strip() == ""
        if capitalised and contiguous:
            current.append(word)
        else:
            if len(current) > 1 or (current and current[0].casefold() not in COMMON_WORDS):
                runs.append(" ".join(current))
            current = []
            if capitalised and not _is_sentence_start(text, match.start()):
                current = [word]
        end_of_previous = match.end()
    if len(current) > 1 or (current and current[0].casefold() not in COMMON_WORDS):
        runs.append(" ".join(current))
    return runs


def _check_scope(doc: SourceDocument, edits: list[Edit]) -> list[Violation]:
    roles = {p.id: p.role for p in doc.paragraphs}
    out: list[Violation] = []
    bullet_edits = 0
    for i, edit in enumerate(edits):
        path = f"edits[{i}]"
        role = roles.get(edit.paragraph_id)
        if role is None:
            out.append(
                violation(
                    TUNE_SCOPE,
                    f"edit names paragraph {edit.paragraph_id!r}, which is not in the document",
                    path,
                    edit.paragraph_id,
                )
            )
            continue
        if role not in EDITABLE_ROLES:
            out.append(
                violation(
                    TUNE_SCOPE,
                    f"paragraph {edit.paragraph_id} has protected role {role!r} and must not be edited",
                    path,
                    edit.paragraph_id,
                )
            )
        if not edit.after.strip():
            out.append(
                violation(
                    TUNE_SCOPE,
                    f"edit to paragraph {edit.paragraph_id} is empty; paragraphs may be rewritten, not deleted",
                    path,
                    edit.paragraph_id,
                )
            )
        if role == "bullet":
            bullet_edits += 1
    if bullet_edits > MAX_BULLET_EDITS:
        out.append(
            violation(
                TUNE_SCOPE,
                f"{bullet_edits} bullet edits exceeds the limit of {MAX_BULLET_EDITS}",
                "edits",
                None,
            )
        )
    return out


def _new_numbers(text: str, known: set[str]) -> list[str]:
    offending = [t for t in find_numeric_tokens(text) if normalize_number(t) not in known]
    offending += [p for p in find_spelled_quantities(text) if p.casefold() not in known]
    return offending


def _check_numbers(
    doc: SourceDocument, edits: list[Edit], cover_note: str | None
) -> list[Violation]:
    known = document_numbers(doc)
    out: list[Violation] = []
    for i, edit in enumerate(edits):
        offending = _new_numbers(edit.after, known)
        if offending:
            out.append(
                violation(
                    NO_NEW_NUMBERS,
                    f"number(s) not found in the document: {', '.join(offending)}",
                    f"edits[{i}]",
                    edit.paragraph_id,
                )
            )
    if cover_note is not None:
        offending = _new_numbers(cover_note, known)
        if offending:
            out.append(
                violation(
                    NO_NEW_NUMBERS,
                    f"cover note contains number(s) not found in the document: {', '.join(offending)}",
                    "cover_note",
                    None,
                )
            )
    return out


def _check_entities(doc: SourceDocument, edits: list[Edit]) -> list[Violation]:
    source = normalize_entity(document_entities(doc))
    out: list[Violation] = []
    for i, edit in enumerate(edits):
        unknown = [
            run for run in capitalised_runs(edit.after) if normalize_entity(run) not in source
        ]
        if unknown:
            out.append(
                violation(
                    ENTITIES,
                    f"name(s) not found in the document: {', '.join(unknown)}",
                    f"edits[{i}]",
                    edit.paragraph_id,
                )
            )
    return out


def _check_dates(edits: list[Edit]) -> list[Violation]:
    out: list[Violation] = []
    for i, edit in enumerate(edits):
        before = edit.before
        added = [y for y in YEAR.findall(edit.after) if y not in before]
        added += [m.group(0) for m in PRESENT.finditer(edit.after) if not PRESENT.search(before)]
        if added:
            out.append(
                violation(
                    DATES,
                    f"date(s) added or changed by the edit: {', '.join(added)}",
                    f"edits[{i}]",
                    edit.paragraph_id,
                )
            )
    return out


def run_tune_guardrails(
    doc: SourceDocument,
    edits: list[Edit],
    extract: JDExtract,
    profile_rules: list[GuardrailRule],
    cover_note: str | None,
) -> GuardrailReport:
    """Scope and numbers always run; entities and dates run when the profile has them active.

    `extract` is unused today and accepted for signature symmetry with `run_guardrails`: a
    JD-aware rule (keyword stuffing, knockout answers) belongs here, not in a second entry point.
    Profile rules that only make sense against the block library (provenance, attribution,
    verified metrics, visibility) are silently skipped rather than rejected -- one
    `guardrails.yaml` configures both modes.
    """
    del extract
    active = {rule.rule for rule in profile_rules if rule.active}
    rules_run = [TUNE_SCOPE, NO_NEW_NUMBERS]
    violations = _check_scope(doc, edits) + _check_numbers(doc, edits, cover_note)
    if ENTITIES in active:
        rules_run.append(ENTITIES)
        violations.extend(_check_entities(doc, edits))
    if DATES in active:
        rules_run.append(DATES)
        violations.extend(_check_dates(edits))
    passed = not any(v.severity == "error" for v in violations)
    return GuardrailReport(passed=passed, rules_run=rules_run, violations=violations)
