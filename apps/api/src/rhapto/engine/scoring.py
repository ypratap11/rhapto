"""Deterministic track classification: embedding similarity plus keyword hits. No LLM."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from rhapto.engine.select import cosine, keyword_matches
from rhapto.models.profile.tracks import Track

SEMANTIC_WEIGHT = 0.6
KEYWORD_WEIGHT = 0.4
COSINE_FLOOR = 0.20
COSINE_CEIL = 0.80
TITLE_HIT = 2
TEXT_HIT = 1


class TrackScore(BaseModel):
    track_id: str
    fit_score: int
    semantic: int
    keywords: int
    matched: list[str]


def track_text(track: Track) -> str:
    if track.description and track.description.strip():
        return track.description.strip()
    return " ".join([track.name, *track.keywords]).strip()


def semantic_score(cos: float) -> int:
    scaled = (cos - COSINE_FLOOR) / (COSINE_CEIL - COSINE_FLOOR) * 100
    return int(round(min(100.0, max(0.0, scaled))))


def keyword_score(track: Track, title: str | None, text: str) -> tuple[int, list[str]]:
    if not track.keywords:
        return 0, []
    hits = 0
    matched: list[str] = []
    for keyword in track.keywords:
        in_title = bool(title) and keyword_matches(keyword, title or "")
        in_text = keyword_matches(keyword, text)
        if in_title:
            hits += TITLE_HIT
        elif in_text:
            hits += TEXT_HIT
        if in_title or in_text:
            matched.append(keyword)
    fraction = min(1.0, hits / len(track.keywords))
    return int(round(fraction * 100)), matched


def score_job(
    title: str | None,
    jd_text: str,
    jd_embedding: list[float],
    tracks: list[Track],
    track_embeddings: dict[str, list[float]],
) -> list[TrackScore]:
    scores: list[TrackScore] = []
    for track in tracks:
        vector = track_embeddings.get(track.id)
        semantic = semantic_score(cosine(jd_embedding, vector)) if vector else 0
        keywords, matched = keyword_score(track, title, jd_text)
        fit = int(round(SEMANTIC_WEIGHT * semantic + KEYWORD_WEIGHT * keywords))
        scores.append(
            TrackScore(
                track_id=track.id,
                fit_score=fit,
                semantic=semantic,
                keywords=keywords,
                matched=matched,
            )
        )
    return scores


def best_track(scores: list[TrackScore], tracks: list[Track]) -> TrackScore | None:
    order = {t.id: i for i, t in enumerate(tracks)}
    ranked = sorted(scores, key=lambda s: (-s.fit_score, order.get(s.track_id, len(order))))
    return ranked[0] if ranked else None


def bucket_for(
    best: TrackScore | None, tracks: list[Track], rescued: bool
) -> Literal["fit", "low"]:
    if rescued:
        return "fit"
    if best is None:
        return "low"
    track = next((t for t in tracks if t.id == best.track_id), None)
    if track is None:
        return "low"
    return "fit" if best.fit_score >= track.min_fit else "low"


def rationale(score: TrackScore) -> dict[str, Any]:
    return {
        "semantic": score.semantic,
        "keywords": score.keywords,
        "matched": score.matched,
        "weights": {"semantic": SEMANTIC_WEIGHT, "keywords": KEYWORD_WEIGHT},
    }
