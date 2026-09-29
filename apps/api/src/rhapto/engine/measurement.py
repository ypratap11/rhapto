"""Phase 4 measurement (completeness guardrail): pure aggregation over one `tailor()` result.

The live part of Phase 4 -- calling real providers with real API keys for a fixed JD -- lives in
`scripts/measure_completeness.py`, outside this package's mypy/ruff/pytest gate because it makes
network calls. This module holds the part worth a unit test: reading what a run actually did.

It reads `TailorResult.pre_repair_report` and `TailorResult.repaired`, never `llm_calls`. A third
call is not evidence of a repair: `_structured_call` spends one on a malformed-output retry, which
leaves a `draft` package with three calls and nothing repaired. And `package.guardrail_report` is
the POST-repair report, so on its own it cannot tell a model that dropped a role and was repaired
from one that never dropped anything -- which is the number architecture condition C6 exists to get.

Privacy: everything returned here is a rule name, a block id or a count, never resume or block
text, because the script may be run against the owner's real profile.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from rhapto.engine.pipeline import TailorResult
from rhapto.models.profile.blocks import Block

_TOKEN = re.compile(r"[a-z0-9]+")


def first_pass_rules(result: TailorResult) -> list[str]:
    """Distinct rule names the FIRST compose failed, sorted; empty when it passed."""
    if result.pre_repair_report is None:
        return []
    return sorted({v.rule for v in result.pre_repair_report.violations if v.severity == "error"})


def final_rules(result: TailorResult) -> list[str]:
    """Distinct rule names still failing in the package that was actually stored, sorted."""
    report = result.package.guardrail_report
    return sorted({v.rule for v in report.violations if v.severity == "error"})


def summarize_result(result: TailorResult) -> str:
    """One-line verdict for a Phase 4 ledger row."""
    if result.pre_repair_report is None:
        return "passed clean"
    first = ", ".join(first_pass_rules(result))
    if result.package.status == "draft":
        return f"repaired (first pass failed: {first})"
    final = ", ".join(final_rules(result))
    if result.repaired:
        return f"blocked after repair ({final}); first pass failed: {first}"
    return f"blocked, no repair ran ({final})"


def invented_project_titles(result: TailorResult, blocks: Mapping[str, Block]) -> list[str]:
    """Block ids of project entries whose `title` or `role` text does not come from the block cited.

    This is the instrument for U-1. The project clause of `completeness` needs a `title` or `role`
    on the entry, no rule validates `title` (`no-invented-entities` checks org, role and period),
    and a project block with no `role` leaves a composer nothing to copy. So an invented title
    passes every guardrail and is invisible to `first_pass_rules`/`final_rules`. "Comes from the
    block" is deliberately loose: every word of the text appears among the words of the block's
    role, org and content. That makes this an upper bound (a paraphrase is counted) and never a
    miss for a title that adds a word the block does not have.

    Returns one block id per offending entry (the count is the length) and never the text itself:
    the ledger may be produced from a real profile, so it holds ids and counts only.
    """
    found: list[str] = []
    for section in result.package.resume.sections:
        if section.kind != "projects":
            continue
        for entry in section.entries:
            block = blocks.get(entry.source_block_id)
            if block is None:
                continue
            sourced = set(
                _TOKEN.findall(
                    " ".join(filter(None, [block.role, block.org, block.content])).casefold()
                )
            )
            if any(
                text and text.strip() and not set(_TOKEN.findall(text.casefold())) <= sourced
                for text in (entry.title, entry.role)
            ):
                found.append(entry.source_block_id)
    return found
