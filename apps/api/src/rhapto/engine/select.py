from __future__ import annotations

import math
import re

from pydantic import BaseModel, Field

from rhapto.engine.providers.embeddings import EmbeddingProvider
from rhapto.engine.types import Profile
from rhapto.models.jd_extract import JDExtract
from rhapto.models.profile.blocks import Block
from rhapto.models.profile.tracks import Track

TYPE_ORDER = ["role", "achievement", "project", "skill", "credential"]
#: Per-type selection caps. Sized for a library with grouped skill blocks, separate degree and
#: certification credentials, and several client engagements -- the earlier `skill: 1` /
#: `credential: 3` / `project: 3` were tuned against a library holding one skill block, so a richer
#: profile left blocks visible to the composer but outside the selection, and every package citing
#: one failed provenance.
DEFAULT_TOP_K = {"role": 6, "achievement": 6, "project": 3, "skill": 4, "credential": 5}


class SelectionConfig(BaseModel):
    top_k: dict[str, int] = Field(default_factory=lambda: dict(DEFAULT_TOP_K))
    w_embedding: float = 0.6
    w_keywords: float = 0.3
    w_tags: float = 0.1


class Selection(BaseModel):
    """Blocks chosen for composition, in TYPE_ORDER then descending score."""

    block_ids: list[str]
    scores: dict[str, float]
    excluded_block_ids: list[str]
    requirements_text: str


def block_text(block: Block) -> str:
    parts = [block.role, block.org, block.content, block.metric, " ".join(block.tags)]
    return " ".join(p for p in parts if p)


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def keyword_matches(keyword: str, text: str) -> bool:
    """Whole-word, case-insensitive match; spaces and hyphens in the keyword match either."""
    parts = [re.escape(p) for p in re.split(r"[\s\-]+", keyword.strip()) if p]
    if not parts:
        return False
    pattern = r"(?<![a-z0-9])" + r"[\s\-]+".join(parts) + r"(?![a-z0-9])"
    return re.search(pattern, text, re.IGNORECASE) is not None


async def select_blocks(
    extract: JDExtract,
    profile: Profile,
    track: Track,
    embedder: EmbeddingProvider,
    config: SelectionConfig | None = None,
) -> Selection:
    """Deterministic ranking: embeddings + keyword hits + tag overlap, top-K per block type."""
    config = config or SelectionConfig()
    block_map = profile.block_map()
    base = profile.base_for(track)
    candidates = [block_map[bid] for bid in base.block_ids if bid in block_map]

    context = set(extract.context_tags)
    excluded = [
        b.id
        for b in candidates
        if b.visibility is not None and context & set(b.visibility.exclude_when)
    ]
    candidates = [b for b in candidates if b.id not in excluded]

    requirements_text = " ".join(extract.must_have + extract.nice_to_have + extract.keywords)
    if not candidates:
        return Selection(
            block_ids=[],
            scores={},
            excluded_block_ids=excluded,
            requirements_text=requirements_text,
        )

    keywords = {k.lower() for k in extract.keywords + track.keywords if k.strip()}
    vectors = await embedder.embed([requirements_text] + [block_text(b) for b in candidates])
    requirements_vec, block_vecs = vectors[0], vectors[1:]

    scores: dict[str, float] = {}
    for block, vec in zip(candidates, block_vecs, strict=True):
        text = block_text(block).lower()
        keyword_ratio = (
            sum(1 for k in keywords if keyword_matches(k, text)) / len(keywords)
            if keywords
            else 0.0
        )
        tags = {t.lower() for t in block.tags}
        tag_overlap = len(tags & keywords) / len(tags) if tags else 0.0
        scores[block.id] = (
            config.w_embedding * cosine(requirements_vec, vec)
            + config.w_keywords * keyword_ratio
            + config.w_tags * tag_overlap
        )

    chosen: list[str] = []
    for block_type in TYPE_ORDER:
        typed = sorted(
            (b for b in candidates if b.type == block_type), key=lambda b: (-scores[b.id], b.id)
        )
        chosen.extend(b.id for b in typed[: config.top_k.get(block_type, 0)])
    return Selection(
        block_ids=chosen,
        scores=scores,
        excluded_block_ids=excluded,
        requirements_text=requirements_text,
    )
