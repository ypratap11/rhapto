"""Completeness: every selected role/project/credential block gets exactly one identifiable entry.

Unconditional, like provenance and no-unverified-metrics (owner decision 1): not registered in
`registry.RULES`, so it cannot be switched off or mistyped out of `guardrails.yaml`, and it reads
no `ctx.config` (C5 -- an unconditional rule with a tunable knob is a configurable rule wearing a
disguise).

See `.superpowers/sdd/completeness-guardrail/architecture.md` sections 1-3 and 7 for the design
this implements.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from rhapto.engine.guardrails.base import (
    DEFAULT_FUZZY_THRESHOLD,
    GuardrailContext,
    fuzzy_entity_match,
    iter_entries_with_section,
    normalize_entity,
    violation,
)
from rhapto.models.guardrail_report import Violation
from rhapto.models.profile.blocks import Block
from rhapto.models.resume_document import ResumeEntry, ResumeSection

RULE_NAME = "completeness"

#: Block type -> the section kind that block's entry must live in.
MANDATORY_KINDS: Mapping[str, str] = {
    "role": "experience",
    "project": "projects",
    "credential": "credentials",
}

KIND_TITLE: Mapping[str, str] = {
    "experience": "Experience",
    "projects": "Projects",
    "credentials": "Credentials",
}

_Entry = tuple[str, ResumeSection, ResumeEntry]


def _present(value: str | None) -> bool:
    return bool((value or "").strip())


def _org_matches(a: str | None, b: str | None) -> bool:
    # Asymmetric on purpose (it is `no-invented-entities`' own comparison): the first argument's
    # tokens must all appear in the second's. It only ever feeds a message annotation here, never
    # a violation, so the asymmetry cannot create or hide an error.
    if not a or not b:
        return False
    return fuzzy_entity_match(a, b, DEFAULT_FUZZY_THRESHOLD)


def _org_appears_in_entry_text(org: str, entry: ResumeEntry) -> bool:
    """Whole-word match, so an org like "Independent" does not light up "independently"."""
    needle = re.compile(rf"\b{re.escape(normalize_entity(org))}\b")
    haystacks = [entry.org, entry.title, entry.role, *(b.text for b in entry.bullets)]
    return any(needle.search(normalize_entity(h)) for h in haystacks if h)


def _block_is_unrenderable(block: Block) -> bool:
    """A mandatory block with no org, no role and empty content renders as nothing in either
    template (`render/templates.py`); flagging its absence as an error would block every run
    forever. Architecture §7.3."""
    return not _present(block.org) and not _present(block.role) and not _present(block.content)


def _attribution_unreachable(block: Block, entry: ResumeEntry) -> bool:
    """Whether `block` needs an attribution phrase this bullet-less entry can never carry.

    Architecture §5.5: `check_attribution` reads the entry's title, org and role as well as its
    bullets (`guardrails/attribution.py`), so the phrase can already be satisfied from a header
    field. The gap therefore exists only when the entry has no bullet text AND the phrase is absent
    from that same joined text. With a bullet present, `attribution` itself reports a missing
    phrase, and a second `completeness` error for the same defect would break C7 (one violation
    per defect).
    """
    if not block.attribution or any(_present(b.text) for b in entry.bullets):
        return False
    text = " ".join(filter(None, [entry.title, entry.org, entry.role]))
    return block.attribution.casefold() not in text.casefold()


def _identity(block: Block, entry: ResumeEntry) -> tuple[bool, str]:
    """Whether `entry` gives `block` a renderable identity, per the per-type clauses in
    architecture §2, and -- when it doesn't -- a description of what's missing, for the violation
    message.
    """
    has_bullet_text = any(_present(b.text) for b in entry.bullets)
    if block.type == "role":
        has_org = _present(entry.org)
        has_title = _present(entry.role) or _present(entry.title)
        gaps = [g for g, ok in (("org", has_org), ("role/title", has_title)) if not ok]
    elif block.type == "project":
        has_title = _present(entry.title) or _present(entry.role)
        gaps = [] if has_title else ["title/role"]
    else:  # credential
        has_label = _present(entry.title) or _present(entry.role) or _present(entry.org)
        gaps = [] if (has_label or has_bullet_text) else ["a label (title/role/org) or a bullet"]
    if _attribution_unreachable(block, entry):
        gaps.append("a bullet carrying the required attribution phrase")
    return (not gaps, " and ".join(gaps))


def _describe(block: Block) -> str:
    """Identify `block` from its own fields, never the document -- the document is what's
    missing. Falls back to the start of `content` for a block with no org, role or period
    (the `cred-pmp` shape)."""
    parts = [p for p in (block.org, block.role) if p and p.strip()]
    head = " — ".join(parts)
    if _present(block.period):
        head = f"{head}, {block.period}" if head else (block.period or "")
    return head or (block.content or "").strip()[:60]


def _merge_annotation(
    ctx: GuardrailContext, block: Block, kind: str, all_entries: list[_Entry]
) -> str:
    """Architecture §3: when `block` has no entry anywhere, look for evidence its content
    survived somewhere else. Substitution is checked before fold, and fold's bullet scan
    excludes bullets citing the entry's own block -- otherwise an entry that cites a same-org
    block which is unselected, or of another type (so the substitution branch does not fire),
    would have its own bullets reported as "folded".
    """
    if not _present(block.org):
        return ""
    org = block.org or ""
    for path, section, entry in all_entries:
        if section.kind != kind or entry.source_block_id == block.id:
            continue
        sibling = ctx.blocks.get(entry.source_block_id)
        if (
            sibling is not None
            and sibling.id in ctx.selection_ids
            and sibling.type == block.type
            and _org_matches(sibling.org, org)
        ):
            return (
                f"; block {sibling.id!r} (same organisation) is present at {path} -- check "
                "whether one entry was substituted for both"
            )
        folded = [
            i
            for i, b in enumerate(entry.bullets)
            if b.source_block_id != entry.source_block_id
            and (src := ctx.blocks.get(b.source_block_id)) is not None
            and _org_matches(src.org, org)
        ]
        if folded:
            return (
                f"; its content appears folded into {path} (bullets {folded} cite blocks whose "
                f"org is {org!r})"
            )
        if _org_appears_in_entry_text(org, entry):
            return (
                f"; its content appears folded into {path} (org {org!r} appears in that "
                "entry's text)"
            )
    return ""


def check_completeness(ctx: GuardrailContext) -> list[Violation]:
    """Every selected role/project/credential block has exactly one identifiable entry citing it.

    Reads only `ctx.resume`, `ctx.blocks` and `ctx.selection_ids` -- never `ctx.config` (C5).
    Violations are sorted by `(block_id, message)` so output order never depends on `frozenset`
    iteration order.
    """
    all_entries: list[_Entry] = list(iter_entries_with_section(ctx.resume))
    out: list[Violation] = []
    for block_id in sorted(ctx.selection_ids):
        block = ctx.blocks.get(block_id)
        if block is None or block.type not in MANDATORY_KINDS:
            continue
        if _block_is_unrenderable(block):
            out.append(
                violation(
                    RULE_NAME,
                    f"{block.type} block {block.id!r} is selected but carries no org, role or "
                    "content and cannot be rendered; fix the block library",
                    f"selection.block_ids[{block.id!r}]",
                    block.id,
                    severity="warning",
                )
            )
            continue
        kind = MANDATORY_KINDS[block.type]
        citing = [(p, s, e) for p, s, e in all_entries if e.source_block_id == block_id]
        right_section = [(p, s, e) for p, s, e in citing if s.kind == kind]
        qualifying = [(p, s, e) for p, s, e in right_section if _identity(block, e)[0]]
        if len(qualifying) == 1:
            continue
        if len(qualifying) > 1:
            paths = [p for p, _, _ in qualifying]
            out.append(
                violation(
                    RULE_NAME,
                    f"{block.type} block {block.id!r} ({_describe(block)}) appears in "
                    f"{len(paths)} entries ({', '.join(paths)}); expected exactly one",
                    paths[1],
                    block.id,
                )
            )
        elif right_section:
            path, _, entry = right_section[0]
            _, gap = _identity(block, entry)
            out.append(
                violation(
                    RULE_NAME,
                    f"{block.type} block {block.id!r} ({_describe(block)}) was selected but its "
                    f"entry in {KIND_TITLE[kind]} is missing {gap} and cannot be identified",
                    path,
                    block.id,
                )
            )
        elif citing:
            wrong_kinds = sorted({s.kind for _, s, _ in citing})
            out.append(
                violation(
                    RULE_NAME,
                    f"{block.type} block {block.id!r} ({_describe(block)}) was selected but "
                    f"does not appear in {KIND_TITLE[kind]}; its entry is in "
                    f"{'/'.join(wrong_kinds)} instead",
                    citing[0][0],
                    block.id,
                )
            )
        else:
            message = (
                f"{block.type} block {block.id!r} ({_describe(block)}) was selected but does "
                f"not appear in {KIND_TITLE[kind]}"
            )
            message += _merge_annotation(ctx, block, kind, all_entries)
            out.append(
                violation(RULE_NAME, message, f"selection.block_ids[{block.id!r}]", block.id)
            )
    return sorted(out, key=lambda v: (v.block_id or "", v.message))
