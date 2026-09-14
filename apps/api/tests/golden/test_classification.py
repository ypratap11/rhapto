"""Golden classification: fictional JDs scored against the demo profile's tracks with the fake embedder."""

import json
from pathlib import Path

import pytest

from rhapto.engine.providers.fake import FakeEmbeddingProvider
from rhapto.engine.scoring import best_track, bucket_for, score_job, track_text
from rhapto.profile.loader import load_profile

CASES = json.loads(
    (Path(__file__).parent / "classification" / "cases.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
async def test_classification_case(case: dict[str, object], demo_profile_dir: Path) -> None:
    tracks = load_profile(demo_profile_dir).tracks
    embedder = FakeEmbeddingProvider()
    text = f"{case['title']}\n{case['text']}"
    vectors = await embedder.embed([text, *(track_text(t) for t in tracks)])
    scores = score_job(
        str(case["title"]),
        str(case["text"]),
        vectors[0],
        tracks,
        {t.id: v for t, v in zip(tracks, vectors[1:], strict=True)},
        # These cases are about the track, not the commute: hold the location multiplier at 1.0
        # so the expected buckets keep measuring the semantic/keyword blend alone.
        location_tier="preferred",
    )
    best = best_track(scores, tracks)
    bucket = bucket_for(best, tracks, rescued=False)
    assert bucket == case["expected_bucket"], scores
    if case["expected_track"] is not None:
        assert best is not None and best.track_id == case["expected_track"], scores


def test_twenty_cases_present() -> None:
    assert len(CASES) == 20
