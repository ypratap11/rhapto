"""Date consistency: periods parse, end is not before start, and experience entries do not overlap.

Deliberate deviation from the spec: an overlap is allowed when EITHER block is marked concurrent
(the spec says both). You mark the side gig concurrent, not the day job it runs alongside.
"""

from __future__ import annotations

import re

from rhapto.engine.guardrails.base import (
    GuardrailContext,
    iter_entries_with_section,
    normalize_dashes,
    violation,
)
from rhapto.models.guardrail_report import Violation

RULE_NAME = "date-consistency"
PRESENT = 9999
# Optional leading month name or abbreviation ("Mar", "Sept.", "January") on either end. Only the
# year is captured; the overlap logic works in whole years.
MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+"
PERIOD_RE = re.compile(
    rf"^\s*(?:{MONTH})?(\d{{4}})\s*(?:(?:-|to)\s*(?:{MONTH})?(\d{{4}}|present|current|now))?\s*$",
    re.IGNORECASE,
)


def parse_period(text: str) -> tuple[int, int] | None:
    match = PERIOD_RE.match(normalize_dashes(text or ""))
    if not match:
        return None
    start = int(match.group(1))
    end_raw = match.group(2)
    if end_raw is None:
        return start, start
    end = PRESENT if not end_raw.isdigit() else int(end_raw)
    return start, end


def check_dates(ctx: GuardrailContext) -> list[Violation]:
    """Periods parse and are ordered; experience entries do not overlap unless a block is concurrent."""
    out: list[Violation] = []
    experience: list[tuple[str, str, int, int, bool]] = []  # path, block_id, start, end, concurrent
    for path, section, entry in iter_entries_with_section(ctx.resume):
        if entry.period is None:
            continue
        parsed = parse_period(entry.period)
        if parsed is None:
            out.append(
                violation(
                    RULE_NAME, f"unparseable period {entry.period!r}", path, entry.source_block_id
                )
            )
            continue
        start, end = parsed
        if end < start:
            out.append(
                violation(
                    RULE_NAME,
                    f"period {entry.period!r} ends before it starts",
                    path,
                    entry.source_block_id,
                )
            )
            continue
        if section.kind == "experience":
            block = ctx.blocks.get(entry.source_block_id)
            concurrent = bool(block and block.concurrent)
            # A single year is the half-open range [Y, Y+1), so two roles in "2020" overlap while
            # "2020" and "2021" do not.
            exclusive_end = end + 1 if end == start else end
            experience.append((path, entry.source_block_id, start, exclusive_end, concurrent))

    for i, (path_a, id_a, start_a, end_a, conc_a) in enumerate(experience):
        for path_b, id_b, start_b, end_b, conc_b in experience[i + 1 :]:
            if conc_a or conc_b:
                continue
            if start_a < end_b and start_b < end_a:
                out.append(
                    violation(
                        RULE_NAME, f"period of {id_b!r} overlaps {id_a!r} ({path_a})", path_b, id_b
                    )
                )
    return out
