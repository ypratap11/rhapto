from __future__ import annotations

import re

from rhapto.engine.guardrails.base import GuardrailContext, iter_bullets, violation
from rhapto.models.guardrail_report import Violation
from rhapto.models.profile.blocks import Block

RULE_NAME = "no-unverified-metrics"

# A number optionally prefixed by currency and suffixed by %, percent, k/m/b, or x. Not part of a word.
NUMERIC_RE = re.compile(
    r"(?<![\w.\-])[$€£]?\d[\d,]*(?:\.\d+)?(?:\s?(?:%|percent|k|m|bn|b|x))?(?![\w\-])",
    re.IGNORECASE,
)
SPELLED_RE = re.compile(
    r"\b(?:half|a third|a quarter|a fifth|one[- ]third|doubl(?:e|ed|ing)|tripl(?:e|ed|ing)|quadrupled"
    r"|dozens?|hundreds?|thousands?|millions?|billions?|twice|thrice"
    r"|(?:two|three|four|five|six|seven|eight|nine|ten|hundred)fold)\b",
    re.IGNORECASE,
)
YEAR_RE = re.compile(r"^(?:19|20)\d{2}$")


def find_numeric_tokens(text: str) -> list[str]:
    return [m.group(0).strip() for m in NUMERIC_RE.finditer(text)]


def find_spelled_quantities(text: str) -> list[str]:
    return [m.group(0) for m in SPELLED_RE.finditer(text)]


def normalize_number(token: str) -> str:
    return re.sub(r"[^\d.]", "", token)


def _source_text(block: Block) -> str:
    return f"{block.metric or ''} {block.content}"


def _is_exempt_year(normalized: str, block: Block) -> bool:
    return (
        bool(YEAR_RE.match(normalized)) and block.period is not None and normalized in block.period
    )


def check_metrics(ctx: GuardrailContext) -> list[Violation]:
    """Every number or spelled-out quantity must appear in a verified source block."""
    out: list[Violation] = []
    for path, bullet in iter_bullets(ctx.resume):
        block = ctx.blocks.get(bullet.source_block_id)
        if block is None:
            continue
        source = _source_text(block)
        source_numbers = {normalize_number(t) for t in find_numeric_tokens(source)}
        source_lower = source.casefold()
        offending: list[str] = []
        for token in find_numeric_tokens(bullet.text):
            normalized = normalize_number(token)
            if _is_exempt_year(normalized, block):
                continue
            if not block.verified or normalized not in source_numbers:
                offending.append(token)
        for phrase in find_spelled_quantities(bullet.text):
            if not block.verified or phrase.casefold() not in source_lower:
                offending.append(phrase)
        if not offending:
            continue
        if not block.verified:
            message = (
                f"block {block.id!r} is not verified but the bullet contains "
                f"metric(s): {', '.join(offending)}"
            )
        else:
            message = f"metric(s) not found in verified block {block.id!r}: {', '.join(offending)}"
        out.append(violation(RULE_NAME, message, path, block.id))
    return out
