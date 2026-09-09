from __future__ import annotations

from rhapto.engine.guardrails.base import GuardrailContext, iter_entries, violation
from rhapto.models.guardrail_report import Violation

RULE_NAME = "attribution"


def _missing(attribution: str, text: str) -> bool:
    return attribution.casefold() not in text.casefold()


def check_attribution(ctx: GuardrailContext) -> list[Violation]:
    """Blocks with an attribution phrase must keep it wherever they appear."""
    out: list[Violation] = []
    for i, bullet in enumerate(ctx.resume.summary):
        block = ctx.blocks.get(bullet.source_block_id)
        if block and block.attribution and _missing(block.attribution, bullet.text):
            out.append(_violation(block.attribution, f"summary[{i}]", block.id))
    for path, entry in iter_entries(ctx.resume):
        entry_block = ctx.blocks.get(entry.source_block_id)
        if entry_block and entry_block.attribution:
            text = " ".join(
                filter(None, [entry.title, entry.org, entry.role, *(b.text for b in entry.bullets)])
            )
            if _missing(entry_block.attribution, text):
                out.append(_violation(entry_block.attribution, path, entry_block.id))
        for i, bullet in enumerate(entry.bullets):
            if bullet.source_block_id == entry.source_block_id:
                continue  # covered by the entry-level check
            block = ctx.blocks.get(bullet.source_block_id)
            if block and block.attribution and _missing(block.attribution, bullet.text):
                out.append(_violation(block.attribution, f"{path}.bullets[{i}]", block.id))
    return out


def _violation(attribution: str, path: str, block_id: str) -> Violation:
    return violation(RULE_NAME, f"required attribution {attribution!r} is missing", path, block_id)
