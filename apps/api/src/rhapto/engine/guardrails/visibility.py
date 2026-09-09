from __future__ import annotations

from rhapto.engine.guardrails.base import GuardrailContext, iter_bullets, iter_entries, violation
from rhapto.models.guardrail_report import Violation

RULE_NAME = "visibility-context"


def check_visibility(ctx: GuardrailContext) -> list[Violation]:
    """No entry or bullet may derive from a block excluded by the JD's context tags."""
    context = set(ctx.extract.context_tags)
    if not context:
        return []
    out: list[Violation] = []
    cited = [(p, e.source_block_id) for p, e in iter_entries(ctx.resume)]
    cited += [(p, b.source_block_id) for p, b in iter_bullets(ctx.resume)]
    for path, block_id in cited:
        block = ctx.blocks.get(block_id)
        if block is None or block.visibility is None:
            continue
        hits = sorted(context & set(block.visibility.exclude_when))
        if hits:
            out.append(
                violation(
                    RULE_NAME,
                    f"block {block_id!r} is excluded for context {', '.join(hits)}",
                    path,
                    block_id,
                )
            )
    return out
