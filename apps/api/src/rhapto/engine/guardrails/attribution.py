from __future__ import annotations

from rhapto.engine.guardrails.base import (
    GuardrailContext,
    iter_entries,
    iter_texts,
    violation,
)
from rhapto.models.guardrail_report import Violation

RULE_NAME = "attribution"


def _missing(attribution: str, text: str) -> bool:
    return attribution.casefold() not in text.casefold()


def check_attribution(ctx: GuardrailContext) -> list[Violation]:
    """Blocks with an attribution phrase must keep it wherever they appear."""
    out: list[Violation] = []
    entry_blocks: dict[str, str] = {}
    for path, entry in iter_entries(ctx.resume):
        entry_blocks[path] = entry.source_block_id
        entry_block = ctx.blocks.get(entry.source_block_id)
        if entry_block and entry_block.attribution:
            text = " ".join(
                filter(None, [entry.title, entry.org, entry.role, *(b.text for b in entry.bullets)])
            )
            if _missing(entry_block.attribution, text):
                out.append(_violation(entry_block.attribution, path, entry_block.id))
    for path, text, block_id in iter_texts(ctx.resume):
        if entry_blocks.get(path.rsplit(".", 1)[0]) == block_id:
            continue  # entry header fields and own-block bullets: covered by the entry-level check
        block = ctx.blocks.get(block_id)
        if block and block.attribution and _missing(block.attribution, text):
            out.append(_violation(block.attribution, path, block.id))
    return out


def _violation(attribution: str, path: str, block_id: str) -> Violation:
    return violation(RULE_NAME, f"required attribution {attribution!r} is missing", path, block_id)
