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
from collections.abc import Iterator

from rhapto.engine.document import (
    EDITABLE_ROLES,
    document_entities,
    document_numbers,
    quantity_tokens,
)
from rhapto.engine.guardrails.attribution import RULE_NAME as ATTRIBUTION
from rhapto.engine.guardrails.base import normalize_entity, violation
from rhapto.engine.guardrails.dates import RULE_NAME as DATES
from rhapto.engine.guardrails.entities import RULE_NAME as ENTITIES
from rhapto.engine.guardrails.metrics import RULE_NAME as METRICS
from rhapto.engine.guardrails.provenance import RULE_NAME as PROVENANCE
from rhapto.engine.guardrails.registry import UnknownGuardrailError
from rhapto.engine.guardrails.visibility import RULE_NAME as VISIBILITY
from rhapto.models.guardrail_report import GuardrailReport, Violation
from rhapto.models.jd_extract import JDExtract
from rhapto.models.profile.guardrails import GuardrailRule
from rhapto.models.source_document import Edit, SourceDocument

TUNE_SCOPE = "tune-scope"
NO_NEW_NUMBERS = "no-new-numbers"
MAX_BULLET_EDITS = 6
# Rules that only mean something against the block library: there are no blocks in tune mode, so
# the same guardrails.yaml can list them and this entry point skips them. Anything else is a typo,
# and a typo that silently disables a validator is worse than a loud failure.
BLOCKS_ONLY = frozenset({PROVENANCE, METRICS, ATTRIBUTION, VISIBILITY})

YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
PRESENT = re.compile(r"\b(?:present|current)\b", re.IGNORECASE)
# A word that could be part of a capitalised entity name. Apostrophes and internal dots stay in
# the token so "B.S." and "Moody's" survive as one word; a trailing sentence period is stripped
# by `_runs` so "at Acme Analytics." is not read as a different org from "Acme Analytics".
WORD = re.compile(r"[A-Za-z][A-Za-z.'’-]*")
# Period/level shorthand that is capitalised but never a name: Q3, FY24, H1, P0, L5.
PERIOD_CODE = re.compile(r"^[A-Z]{1,2}\d{1,4}$")
WORD_OR_CODE = re.compile(r"[A-Za-z][A-Za-z0-9.'’-]*")
SENTENCE_END = ".!?\n"
# Ordinary English words that can legitimately sit capitalised at either end of a run ("The
# Snowflake migration"). They are trimmed off a run rather than suppressing it, so the name in
# the middle is still checked.
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
# Tokens that make a lone capitalised word read as an organisation or product rather than as
# ordinary resume prose ("Agile", "Legal", "Delivery").
NAME_SUFFIXES = frozenset(
    """
    inc corp corporation co llc llp ltd plc gmbh ag sa nv bv ab oy oyj kk pte pty
    labs lab ai io dev sdk api db sql os technologies technology systems solutions software
    group holdings partners ventures capital university institute college academy
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


def _looks_like_a_name(word: str) -> bool:
    """Whether a lone capitalised word carries an organisation or product signal.

    Resume prose capitalises plenty of ordinary nouns -- "Partnered with Finance and Legal on
    the Agile rollout" -- and flagging those burns the single repair call on a phantom
    violation, or blocks a compliant package when the repair does not "fix" it. So a word on its
    own is only checked when it looks manufactured: a digit in it, an internal capital
    (CamelCase or an acronym), or a corporate/product tail.
    """
    if any(ch.isdigit() for ch in word):
        return True
    if any(ch.isupper() for ch in word[1:]):
        return True
    return re.split(r"[-.]", word.casefold())[-1] in NAME_SUFFIXES


def _trim(words: list[str]) -> list[str]:
    start, end = 0, len(words)
    while start < end and words[start].casefold() in COMMON_WORDS:
        start += 1
    while end > start and words[end - 1].casefold() in COMMON_WORDS:
        end -= 1
    return words[start:end]


def _runs(text: str) -> Iterator[tuple[list[str], bool]]:
    """Maximal runs of adjacent capitalised words, each with whether it starts a sentence."""
    current: list[str] = []
    at_sentence_start = False
    previous_end = -1
    for match in WORD_OR_CODE.finditer(text):
        word = match.group(0).rstrip(".")
        capitalised = word[:1].isupper() and not PERIOD_CODE.match(word)
        adjacent = bool(current) and not text[previous_end : match.start()].strip()
        if capitalised and adjacent:
            current.append(word)
        else:
            if current:
                yield current, at_sentence_start
                current = []
            if capitalised:
                current = [word]
                at_sentence_start = _is_sentence_start(text, match.start())
        previous_end = match.end()
    if current:
        yield current, at_sentence_start


def capitalised_runs(text: str) -> list[str]:
    """The capitalised names in `text` worth checking against the document.

    A run is the unit checked, so "Globex Corp" is reported whole rather than as two words that
    happen to be unknown. A run is collected even when it starts a sentence -- dropping the
    first word there and restarting at the second would check "Globex Corp led the migration."
    as just "Corp", which passes on any resume containing "Corporate" -- and is discarded only
    if it turns out to be a single word, where the capital carries no information. A lone word
    mid-sentence is checked only when `_looks_like_a_name` says so.
    """
    runs: list[str] = []
    for words, at_sentence_start in _runs(text):
        trimmed = _trim(words)
        if len(trimmed) > 1:
            runs.append(" ".join(trimmed))
        elif len(trimmed) == 1 and not at_sentence_start and _looks_like_a_name(trimmed[0]):
            runs.append(trimmed[0])
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
    """Quantities in `text` whose unit-aware key is not already claimed by the document."""
    return [token for token, key in quantity_tokens(text) if key not in known]


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


def _mentions(source: str, run: str) -> bool:
    """Whether `source` contains `run` as whole words.

    Plain containment lets a short name hide inside a longer one -- "Meta" in "Metadata", "Corp"
    in "Corporate", "Lake" in "Lakehouse" -- which is exactly the inflation this rule exists to
    catch. Lookarounds rather than `\\b` so a run ending in a dot ("B.S") still matches.
    """
    return re.search(rf"(?<!\w){re.escape(run)}(?!\w)", source) is not None


def _check_entities(doc: SourceDocument, edits: list[Edit]) -> list[Violation]:
    source = normalize_entity(document_entities(doc))
    out: list[Violation] = []
    for i, edit in enumerate(edits):
        unknown = [
            run
            for run in capitalised_runs(edit.after)
            if not _mentions(source, normalize_entity(run))
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
    The `BLOCKS_ONLY` rules are skipped so one `guardrails.yaml` can configure both modes, but an
    active rule that is neither known here nor blocks-only raises `UnknownGuardrailError`, as it
    does in `run_guardrails`: a typo must not quietly switch a validator off in one mode only.
    """
    del extract
    active = {rule.rule for rule in profile_rules if rule.active}
    unknown_rules = active - BLOCKS_ONLY - {TUNE_SCOPE, NO_NEW_NUMBERS, ENTITIES, DATES}
    if unknown_rules:
        raise UnknownGuardrailError(f"unknown guardrail rule: {sorted(unknown_rules)[0]}")
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
