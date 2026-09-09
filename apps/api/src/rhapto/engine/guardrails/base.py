from __future__ import annotations

import re
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from rhapto.models.guardrail_report import Violation
from rhapto.models.jd_extract import JDExtract
from rhapto.models.profile.blocks import Block
from rhapto.models.resume_document import (
    ResumeBullet,
    ResumeDocument,
    ResumeEntry,
    ResumeSection,
)

DASHES = re.compile(r"[‒–—−]")


def normalize_dashes(text: str) -> str:
    return DASHES.sub("-", text)


def normalize_entity(text: str) -> str:
    """Case-folded, dash- and whitespace-normalized form used to compare entity strings."""
    dashed = normalize_dashes(text)
    collapsed_dashes = re.sub(r"\s*-\s*", "-", dashed)
    return re.sub(r"\s+", " ", collapsed_dashes).strip().casefold()


@dataclass(frozen=True)
class GuardrailContext:
    resume: ResumeDocument
    blocks: Mapping[str, Block]
    selection_ids: frozenset[str]
    extract: JDExtract
    config: Mapping[str, Any] = field(default_factory=dict)

    def with_config(self, config: Mapping[str, Any]) -> GuardrailContext:
        return replace(self, config=config)


Rule = Callable[[GuardrailContext], list[Violation]]


def iter_entries_with_section(
    resume: ResumeDocument,
) -> Iterator[tuple[str, ResumeSection, ResumeEntry]]:
    for s, section in enumerate(resume.sections):
        for e, entry in enumerate(section.entries):
            yield f"sections[{s}].entries[{e}]", section, entry


def iter_entries(resume: ResumeDocument) -> Iterator[tuple[str, ResumeEntry]]:
    for path, _section, entry in iter_entries_with_section(resume):
        yield path, entry


def iter_bullets(resume: ResumeDocument) -> Iterator[tuple[str, ResumeBullet]]:
    for i, b in enumerate(resume.summary):
        yield f"summary[{i}]", b
    for entry_path, entry in iter_entries(resume):
        for i, b in enumerate(entry.bullets):
            yield f"{entry_path}.bullets[{i}]", b


ENTRY_TEXT_FIELDS = ("title", "org", "role", "period")


def iter_texts(resume: ResumeDocument) -> Iterator[tuple[str, str, str]]:
    """Every rendered text with its path and source block id: summary bullets, entry header fields, entry bullets."""
    for i, b in enumerate(resume.summary):
        yield f"summary[{i}]", b.text, b.source_block_id
    for entry_path, entry in iter_entries(resume):
        for field_name in ENTRY_TEXT_FIELDS:
            value: str | None = getattr(entry, field_name)
            if value is not None:
                yield f"{entry_path}.{field_name}", value, entry.source_block_id
        for i, b in enumerate(entry.bullets):
            yield f"{entry_path}.bullets[{i}]", b.text, b.source_block_id


def violation(
    rule: str,
    message: str,
    path: str,
    block_id: str | None = None,
    severity: Literal["error", "warning"] = "error",
) -> Violation:
    return Violation(rule=rule, severity=severity, message=message, path=path, block_id=block_id)
