from __future__ import annotations

import re
from collections.abc import Iterable

from rhapto.engine.guardrails.base import (
    GuardrailContext,
    iter_texts,
    normalize_entity,
    violation,
)
from rhapto.models.guardrail_report import Violation
from rhapto.models.profile.blocks import Block

RULE_NAME = "no-unverified-metrics"

# A number, optionally prefixed by currency and followed by a short unit (%, percent, k, m, bn, x,
# ms, min, TB, pp, ...). A trailing hyphen or unknown word no longer suppresses the token, so
# "40ms", "10TB" and "40-person" are all seen. The lookbehind still keeps "v2", "iso-8601" and
# "Python3" quiet: a digit glued to a word character, a dot or a dash on the left is not a metric.
NUMERIC_RE = re.compile(
    r"(?<![\w.\-])[$€£]?\d[\d,]*(?:\.\d+)?(?:\s?(?:%|percent\b|[A-Za-z]{1,4}\b))?",
    re.IGNORECASE,
)
SPELLED_RE = re.compile(
    r"\b(?:half|a third|a quarter|a fifth|one[- ]third|doubl(?:e|ed|ing)|tripl(?:e|ed|ing)|quadrupled"
    r"|dozens?|hundreds?|thousands?|millions?|billions?|twice|thrice"
    r"|(?:two|three|four|five|six|seven|eight|nine|ten|hundred)fold)\b",
    re.IGNORECASE,
)
YEAR_RE = re.compile(r"^(?:19|20)\d{2}$")

# Spelled-out cardinal numbers, e.g. "eighteen", "twenty-five", "forty thousand", "one million".
# "one" only counts as a number when it is immediately followed by a scale word (-> "one million")
# or an unambiguous quantity unit (-> "one percent"); bare "one" ("one platform") is ordinary prose.
_UNITS = (
    r"(?:two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen"
    r"|fifteen|sixteen|seventeen|eighteen|nineteen)"
)
_JOIN_UNITS = r"(?:two|three|four|five|six|seven|eight|nine)"
_TENS = r"(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)"
_SCALES = r"(?:hundred|thousand|million|billion|trillion)s?"
_ONE_UNIT = r"(?:percent|%|pct|x|times|fold|dollars?|usd|hours?|hrs?|days?|weeks?|months?|years?)"
CARDINAL_RE = re.compile(
    r"\b(?:"
    r"(?:" + _TENS + r"(?:[-\s]" + _JOIN_UNITS + r")?|" + _UNITS + r")(?:\s+" + _SCALES + r")*"
    r"|" + _SCALES + r"|one(?:\s+" + _SCALES + r")+|one(?=\s+" + _ONE_UNIT + r")"
    r")\b",
    re.IGNORECASE,
)


def find_numeric_tokens(text: str) -> list[str]:
    return [m.group(0).strip() for m in NUMERIC_RE.finditer(text)]


def find_spelled_quantities(text: str) -> list[str]:
    """SPELLED_RE idioms plus CARDINAL_RE spelled-out numbers, in text order.

    Overlapping matches (e.g. SPELLED_RE's bare "thousand" inside CARDINAL_RE's
    "forty thousand") are resolved by keeping the longer, earlier-starting span so a
    phrase is never double-reported.
    """
    candidates: list[tuple[int, int, str]] = []
    for m in SPELLED_RE.finditer(text):
        candidates.append((m.start(), m.end(), m.group(0)))
    for m in CARDINAL_RE.finditer(text):
        candidates.append((m.start(), m.end(), m.group(0)))
    candidates.sort(key=lambda c: (c[0], -(c[1] - c[0])))
    phrases: list[str] = []
    occupied_end = -1
    for start, end, phrase in candidates:
        if start < occupied_end:
            continue
        phrases.append(phrase)
        occupied_end = end
    return phrases


def normalize_number(token: str) -> str:
    return re.sub(r"[^\d.]", "", token)


def _source_text(block: Block) -> str:
    return f"{block.metric or ''} {block.content}"


def _is_exempt_year(normalized: str, block: Block) -> bool:
    return (
        bool(YEAR_RE.match(normalized)) and block.period is not None and normalized in block.period
    )


def _is_copied_period(path: str, text: str, block: Block) -> bool:
    """An entry period copied verbatim from its block is the block's own data, not a new metric."""
    return (
        path.endswith(".period")
        and block.period is not None
        and normalize_entity(text) == normalize_entity(block.period)
    )


def check_text_against_blocks(text: str, blocks: Iterable[Block]) -> list[str]:
    """Offending tokens in free text: any numeric or spelled quantity not present in some verified block's source text."""
    sources = [_source_text(block) for block in blocks if block.verified]
    source_numbers = {normalize_number(t) for s in sources for t in find_numeric_tokens(s)}
    source_lower = " ".join(sources).casefold()
    offending = [t for t in find_numeric_tokens(text) if normalize_number(t) not in source_numbers]
    offending += [p for p in find_spelled_quantities(text) if p.casefold() not in source_lower]
    return offending


def check_metrics(ctx: GuardrailContext) -> list[Violation]:
    """Every number or spelled-out quantity in a rendered text must appear in a verified source block.

    Covers summary bullets, entry header fields (title, org, role, period) and entry bullets:
    anything the renderer prints.
    """
    out: list[Violation] = []
    for path, text, block_id in iter_texts(ctx.resume):
        block = ctx.blocks.get(block_id)
        if block is None:
            continue
        if _is_copied_period(path, text, block):
            continue  # no-invented-entities owns the period field
        source = _source_text(block)
        source_numbers = {normalize_number(t) for t in find_numeric_tokens(source)}
        source_lower = source.casefold()
        offending: list[str] = []
        for token in find_numeric_tokens(text):
            normalized = normalize_number(token)
            if _is_exempt_year(normalized, block):
                continue
            if not block.verified or normalized not in source_numbers:
                offending.append(token)
        for phrase in find_spelled_quantities(text):
            if not block.verified or phrase.casefold() not in source_lower:
                offending.append(phrase)
        if not offending:
            continue
        if not block.verified:
            message = (
                # This exact wording is quoted on the public landing page
                # (apps/web/src/components/landing/ProvenanceDemo.tsx) as proof the product refuses
                # invented metrics. test_message_wording_is_exact pins it; change both or neither.
                f"block {block.id!r} is not verified but the text contains "
                f"metric(s): {', '.join(offending)}"
            )
        else:
            message = f"metric(s) not found in verified block {block.id!r}: {', '.join(offending)}"
        out.append(violation(RULE_NAME, message, path, block.id))
    return out
