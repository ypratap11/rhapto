from __future__ import annotations

from rhapto.engine.guardrails.base import GuardrailContext, iter_bullets, iter_entries, violation
from rhapto.models.guardrail_report import Violation

RULE_NAME = "provenance"


def check_provenance(ctx: GuardrailContext) -> list[Violation]:
    """Every entry and bullet must cite a block that exists and was selected for this run."""
    out: list[Violation] = []
    cited = [(p, e.source_block_id) for p, e in iter_entries(ctx.resume)]
    cited += [(p, b.source_block_id) for p, b in iter_bullets(ctx.resume)]
    for path, block_id in cited:
        if block_id not in ctx.blocks:
            out.append(
                violation(RULE_NAME, f"source block {block_id!r} does not exist", path, block_id)
            )
        elif block_id not in ctx.selection_ids:
            out.append(
                violation(
                    RULE_NAME, f"source block {block_id!r} was not in the selection", path, block_id
                )
            )
    return out
