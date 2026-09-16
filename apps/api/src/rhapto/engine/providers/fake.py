from __future__ import annotations

import json
import math
import re
import zlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from rhapto.engine.guardrails.dates import parse_period
from rhapto.engine.providers.llm import (
    MalformedOutputError,
    Message,
    StructuredResult,
    SystemBlock,
    T,
    TokenUsage,
)


@dataclass
class FakeCall:
    system: list[SystemBlock]
    messages: list[Message]
    output_schema: type[BaseModel]


@dataclass
class FakeLLMProvider:
    """Returns scripted responses in order and records every call."""

    responses: Sequence[BaseModel | dict[str, Any]]
    calls: list[FakeCall] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._queue = list(self.responses)

    async def complete_structured(
        self,
        *,
        system: list[SystemBlock],
        messages: list[Message],
        output_schema: type[T],
        max_tokens: int = 4096,
    ) -> StructuredResult[T]:
        if not self._queue:
            raise AssertionError("FakeLLMProvider: no scripted response left")
        raw = self._queue.pop(0)
        payload = raw if isinstance(raw, dict) else raw.model_dump(mode="json")
        # Record the call first: a malformed scripted answer is still a call the model was asked for.
        self.calls.append(
            FakeCall(system=list(system), messages=list(messages), output_schema=output_schema)
        )
        try:
            value = output_schema.model_validate(payload)
        except ValidationError as exc:
            raise MalformedOutputError(
                f"scripted {output_schema.__name__} did not match the schema: {exc.error_count()}"
            ) from exc
        return StructuredResult(value=value, usage=TokenUsage(input_tokens=10, output_tokens=5))


class FakeEmbeddingProvider:
    """Deterministic hashed bag-of-words vectors: similar texts get similar vectors."""

    def __init__(self, dimensions: int = 64) -> None:
        self.dimensions = dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.dimensions
            for word in re.findall(r"[a-z0-9]+", text.lower()):
                vec[zlib.crc32(word.encode()) % self.dimensions] += 1.0
            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            out.append([x / norm for x in vec])
        return out


FAKE_MODEL = "fake-1"

# COMPOSE_RULES itself mentions "<blocks>" in prose ("...resume blocks listed in <blocks>.") before
# the real `<blocks>...</blocks>` payload build_system_blocks appends after it, so a naive `search`
# for the first "<blocks>" would capture the rules text instead of the JSON. `(?!.*<blocks>)`
# (with DOTALL, so "." spans newlines) rejects every "<blocks>" that has another one somewhere
# ahead of it, which anchors the match on the *last* -- and therefore real -- opening tag.
_BLOCKS_RE = re.compile(r"<blocks>(?!.*<blocks>)\s*(?P<body>.*?)\s*</blocks>", re.DOTALL)
_SELECTED_RE = re.compile(
    r"<selected_block_ids>(?!.*<selected_block_ids>)\s*(?P<body>.*?)\s*</selected_block_ids>",
    re.DOTALL,
)
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z+#.-]{3,}")
_DIGIT_RE = re.compile(r"\d")

#: Block type -> the section it belongs in, and that section's title.
_SECTIONS: dict[str, tuple[str, str]] = {
    "role": ("experience", "Experience"),
    "achievement": ("experience", "Experience"),
    "project": ("projects", "Projects"),
    "skill": ("skills", "Skills"),
    "credential": ("credentials", "Credentials"),
}

_STOPWORDS = frozenset(
    {
        "will",
        "with",
        "your",
        "you",
        "this",
        "that",
        "them",
        "they",
        "have",
        "from",
        "about",
        "their",
        "while",
        "into",
        "team",
        "work",
        "role",
        "well",
        "also",
        "across",
        "using",
        "must",
        "should",
        "would",
        "which",
        "were",
        "been",
        "when",
    }
)

FAKE_COMPANY = "Example Company"


class DeterministicFakeProvider:
    """An `LLMProvider` that answers from the prompt instead of from a model.

    It exists so the Docker Compose stack and the Playwright specs can run the whole
    Find -> Tailor -> Review -> Apply flow with no vendor key, no network and no bill, and get the
    *same* package every time. It is not a mock of a good model: it is the most conservative
    answer that satisfies every guardrail.

    * **Compose** copies each selected block's `content` into one bullet, verbatim, and copies the
      block's `org`/`role`/`period` onto the entry. That is provenance, entities and dates clean by
      construction, and it cannot invent a metric because it never writes a word of its own into a
      bullet. An unverified block whose content contains a digit is skipped outright rather than
      risking the verified-metrics rule. A block whose period would overlap an already-placed
      entry (this provider never merges bullets, so it cannot fold an achievement into its role's
      own entry the way the real prompt does) is skipped for the same reason -- and named in
      `change_log`, so the drop is visible rather than silent.
    * **Tune** proposes no edits at all. Zero edits is the only rewrite of a human's own document
      that is guaranteed not to invent anything.
    * The cover note is deliberately bland: no company name, no numbers, nothing for a guardrail
      to catch.

    Selected by `RHAPTO_LLM_PROVIDER=fake`; never a default, and never offered in Settings.
    """

    def __init__(self, model: str = FAKE_MODEL) -> None:
        self.model = model
        self.calls: list[FakeCall] = []

    async def complete_structured(
        self,
        *,
        system: list[SystemBlock],
        messages: list[Message],
        output_schema: type[T],
        max_tokens: int = 4096,
    ) -> StructuredResult[T]:
        self.calls.append(
            FakeCall(system=list(system), messages=list(messages), output_schema=output_schema)
        )
        system_text = "\n\n".join(block.text for block in system)
        user_text = "\n\n".join(m.content for m in messages)
        name = output_schema.__name__
        if name == "JDExtract":
            payload: dict[str, Any] = self._extract(user_text)
        elif name == "ComposeOutput":
            payload = self._compose(system_text, user_text)
        elif name == "TuneOutput":
            payload = self._tune()
        elif name == "Ping":
            payload = {"ok": True}
        else:
            raise MalformedOutputError(
                f"DeterministicFakeProvider has no answer for {name}; "
                "teach it one in engine/providers/fake.py"
            )
        try:
            value = output_schema.model_validate(payload)
        except ValidationError as exc:
            raise MalformedOutputError(
                f"fake {name} did not match the schema: {exc.error_count()}"
            ) from exc
        return StructuredResult(value=value, usage=TokenUsage(input_tokens=0, output_tokens=0))

    def _extract(self, jd_text: str) -> dict[str, Any]:
        lines = [line.strip() for line in jd_text.splitlines() if line.strip()]
        title = lines[0][:200] if lines else "Unspecified Role"
        counts: dict[str, int] = {}
        for word in _WORD_RE.findall(jd_text.lower()):
            if word not in _STOPWORDS:
                counts[word] = counts.get(word, 0) + 1
        # Sorted by count then alphabetically, so the same JD always yields the same list.
        ranked = sorted(counts, key=lambda w: (-counts[w], w))[:8]
        return {
            "company": FAKE_COMPANY,
            "title": title,
            "location_policy": "unspecified",
            "seniority": "unspecified",
            "must_have": ranked[:4],
            "nice_to_have": [],
            "keywords": ranked,
            "likely_knockouts": [],
            "context_tags": [],
        }

    def _blocks(self, system_text: str, user_text: str) -> list[dict[str, Any]]:
        """The selected blocks, in the order the selector chose them."""
        blocks_match = _BLOCKS_RE.search(system_text)
        selected_match = _SELECTED_RE.search(user_text)
        if blocks_match is None or selected_match is None:
            return []
        try:
            blocks = json.loads(blocks_match.group("body"))
            selected = json.loads(selected_match.group("body"))
        except ValueError:
            return []
        by_id = {
            str(b["id"]): b for b in blocks if isinstance(b, dict) and isinstance(b.get("id"), str)
        }
        return [by_id[i] for i in selected if isinstance(i, str) and i in by_id]

    def _compose(self, system_text: str, user_text: str) -> dict[str, Any]:
        sections: dict[str, dict[str, Any]] = {}
        # This provider never merges bullets under one shared entry -- every entry cites exactly
        # one block, which is what keeps provenance and verbatim-copy trivially correct. But the
        # real compose prompt merges an achievement's bullet into its role's entry (same org), and
        # without that merge, a block whose own period genuinely nests inside another selected
        # block's period (an achievement inside the role that produced it, say) would become its
        # own "experience" entry and trip the date-consistency guardrail on a false-positive
        # overlap. Track the ranges already placed and skip a later block that would collide,
        # using the exact overlap rule the guardrail itself uses -- conservative, not dishonest:
        # nothing false is asserted, one potential bullet is simply left out. But it must not be
        # a *silent* omission -- record which block ids were dropped this way so the change log
        # says so, the one place this output already reports what it did and why.
        experience_ranges: list[tuple[int, int, bool]] = []
        skipped_for_dates: list[str] = []
        for block in self._blocks(system_text, user_text):
            content = str(block.get("content") or "").strip()
            if not content:
                continue
            # Verified-metrics: a number may only appear if the block carrying it is verified.
            if not block.get("verified") and _DIGIT_RE.search(content):
                continue
            kind, title = _SECTIONS.get(str(block.get("type")), ("experience", "Experience"))
            if kind == "experience":
                period_text = str(block.get("period") or "").strip()
                parsed = parse_period(period_text) if period_text else None
                if parsed is not None:
                    start, end = parsed
                    concurrent = bool(block.get("concurrent"))
                    exclusive_end = end + 1 if end == start else end
                    if any(
                        start < e and s < exclusive_end and not (concurrent or c)
                        for s, e, c in experience_ranges
                    ):
                        skipped_for_dates.append(str(block["id"]))
                        continue
                    experience_ranges.append((start, exclusive_end, concurrent))
            attribution = str(block.get("attribution") or "").strip()
            text = (
                content
                if not attribution or attribution in content
                else f"{content} ({attribution})"
            )
            section = sections.setdefault(kind, {"title": title, "kind": kind, "entries": []})
            section["entries"].append(
                {
                    "source_block_id": block["id"],
                    "org": block.get("org"),
                    "role": block.get("role"),
                    "period": block.get("period"),
                    "bullets": [{"text": text, "source_block_id": block["id"]}],
                }
            )
        ordered = [
            sections[k]
            for k in ("experience", "projects", "skills", "credentials")
            if k in sections
        ]
        change_log = (
            "Generated by the deterministic fake provider: every bullet is its source block's "
            "content, unchanged."
        )
        if skipped_for_dates:
            change_log += (
                " Skipped (period overlaps another selected block's; see date-consistency): "
                + ", ".join(skipped_for_dates)
                + "."
            )
        return {
            "summary": [],
            "sections": ordered,
            "cover_note": (
                "Thank you for considering my application. I would welcome the chance to discuss "
                "how my background fits this role."
            ),
            "change_log": change_log,
            "answers": [],
        }

    def _tune(self) -> dict[str, Any]:
        return {
            "edits": [],
            "cover_note": (
                "Thank you for considering my application. I would welcome the chance to discuss "
                "how my background fits this role."
            ),
            "change_log": "Generated by the deterministic fake provider: no edits proposed.",
            "answers": [],
        }
