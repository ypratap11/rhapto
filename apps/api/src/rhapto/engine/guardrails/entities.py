from __future__ import annotations

import re

from rapidfuzz import fuzz

from rhapto.engine.guardrails.base import GuardrailContext, iter_entries, violation
from rhapto.models.guardrail_report import Violation

RULE_NAME = "no-invented-entities"
DEFAULT_THRESHOLD = 90
DASHES = re.compile(r"[‒–—−]")


def normalize_entity(text: str) -> str:
    return re.sub(r"\s+", " ", DASHES.sub("-", text)).strip().casefold()


def _fuzzy_match(candidate: str, source: str, threshold: int) -> bool:
    a, b = normalize_entity(candidate), normalize_entity(source)
    return a == b or fuzz.ratio(a, b) >= threshold


def check_entities(ctx: GuardrailContext) -> list[Violation]:
    """Entry org, role, and period must match the entry's source block (fuzzy for org/role, exact for period)."""
    threshold = int(ctx.config.get("fuzzy_threshold", DEFAULT_THRESHOLD))
    out: list[Violation] = []
    for path, entry in iter_entries(ctx.resume):
        block = ctx.blocks.get(entry.source_block_id)
        if block is None:
            continue
        for field_name in ("org", "role"):
            value = getattr(entry, field_name)
            if value is None:
                continue
            source = getattr(block, field_name)
            if source is None or not _fuzzy_match(value, source, threshold):
                out.append(
                    violation(
                        RULE_NAME,
                        f"{field_name} {value!r} does not match block {block.id!r} ({source!r})",
                        path,
                        block.id,
                    )
                )
        if entry.period is not None and (
            block.period is None or normalize_entity(entry.period) != normalize_entity(block.period)
        ):
            out.append(
                violation(
                    RULE_NAME,
                    f"period {entry.period!r} does not match block {block.id!r} ({block.period!r})",
                    path,
                    block.id,
                )
            )
    return out
