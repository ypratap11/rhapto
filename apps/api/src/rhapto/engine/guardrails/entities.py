from __future__ import annotations

from rhapto.engine.guardrails.base import (
    GuardrailContext,
    fuzzy_entity_match,
    iter_entries,
    normalize_entity,
    violation,
)
from rhapto.models.guardrail_report import Violation

RULE_NAME = "no-invented-entities"
DEFAULT_THRESHOLD = 90


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
            source = getattr(block, field_name)
            if value is None:
                if block.type == "role" and source is not None:
                    out.append(
                        violation(
                            RULE_NAME,
                            f"{field_name} is missing on entry but block {block.id!r} has {source!r}",
                            path,
                            block.id,
                        )
                    )
                continue
            if source is None or not fuzzy_entity_match(value, source, threshold):
                out.append(
                    violation(
                        RULE_NAME,
                        # This wording is quoted on the public landing page
                        # (apps/web/src/components/landing/CaughtDemo.tsx, pinned by
                        # CaughtDemo.test.tsx); change both or neither.
                        f"{field_name} {value!r} does not match block {block.id!r} ({source!r})",
                        path,
                        block.id,
                    )
                )
        if entry.period is None and block.type == "role" and block.period is not None:
            out.append(
                violation(
                    RULE_NAME,
                    f"period is missing on entry but block {block.id!r} has {block.period!r}",
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
