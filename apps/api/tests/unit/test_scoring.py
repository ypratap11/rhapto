from rhapto.engine.providers.fake import FakeEmbeddingProvider
from rhapto.engine.scoring import (
    KEYWORD_WEIGHT,
    LOCATION_MULTIPLIER,
    SEMANTIC_WEIGHT,
    TrackScore,
    best_track,
    bucket_for,
    keyword_score,
    score_job,
    semantic_score,
    track_text,
)
from rhapto.models.profile.tracks import Track

DATA = Track(
    id="data-pm",
    name="Data Program Management",
    resume_base="b",
    min_fit=60,
    keywords=["Data Program Manager", "analytics", "data platform", "ETL"],
    description="Data platform and analytics program leadership.",
)
AI = Track(
    id="ai-pm",
    name="AI Product/Program",
    resume_base="b",
    min_fit=55,
    keywords=["AI Product Manager", "LLM", "GenAI", "ML platform"],
    description="AI product and program roles leveraging hands-on LLM work.",
)


def test_semantic_score_maps_cosine_band() -> None:
    assert semantic_score(0.20) == 0 and semantic_score(0.80) == 100
    assert semantic_score(0.50) == 50
    assert semantic_score(-1.0) == 0 and semantic_score(0.99) == 100


def test_keyword_score_title_counts_double_and_caps() -> None:
    score, matched = keyword_score(DATA, "Data Program Manager", "we run ETL and analytics")
    # title hit 2 + text hits 1 + 1 = 4 over 4 keywords -> 100
    assert score == 100 and matched == ["Data Program Manager", "analytics", "ETL"]
    score, matched = keyword_score(DATA, None, "nothing relevant here")
    assert score == 0 and matched == []
    score, _ = keyword_score(Track(id="t", name="t", resume_base="b"), "x", "y")
    assert score == 0  # no keywords -> 0, never a division by zero


def test_track_text_falls_back_to_name_and_keywords() -> None:
    assert track_text(DATA) == "Data platform and analytics program leadership."
    bare = Track(id="t", name="Ops Lead", resume_base="b", keywords=["SRE", "on-call"])
    assert track_text(bare) == "Ops Lead SRE on-call"


async def test_score_job_blends_and_orders_by_track() -> None:
    embedder = FakeEmbeddingProvider()
    jd = "Data Program Manager to lead our analytics data platform and ETL modernisation"
    vectors = await embedder.embed([jd, track_text(DATA), track_text(AI)])
    scores = score_job(
        "Data Program Manager",
        jd,
        vectors[0],
        [DATA, AI],
        {"data-pm": vectors[1], "ai-pm": vectors[2]},
        location_tier="preferred",
    )
    assert [s.track_id for s in scores] == ["data-pm", "ai-pm"]
    data = scores[0]
    assert data.fit_score == round(SEMANTIC_WEIGHT * data.semantic + KEYWORD_WEIGHT * data.keywords)
    assert data.fit_score > scores[1].fit_score
    # No location known is not the same as a location the user wants: the default tier costs 10%.
    unknown = score_job(
        "Data Program Manager", jd, vectors[0], [DATA, AI], {"data-pm": vectors[1]}
    )[0]
    assert unknown.location_tier == "unknown"
    assert unknown.fit_score == round(data.fit_score * LOCATION_MULTIPLIER["unknown"])


def test_best_track_ties_resolve_by_track_order_and_bucket_uses_min_fit() -> None:
    tie = [
        TrackScore(track_id="ai-pm", fit_score=60, semantic=60, keywords=60, matched=[]),
        TrackScore(track_id="data-pm", fit_score=60, semantic=60, keywords=60, matched=[]),
    ]
    best = best_track(tie, [DATA, AI])
    assert best is not None and best.track_id == "data-pm"
    assert bucket_for(best, [DATA, AI], rescued=False) == "fit"
    low = TrackScore(track_id="data-pm", fit_score=59, semantic=59, keywords=59, matched=[])
    assert bucket_for(low, [DATA, AI], rescued=False) == "low"
    assert bucket_for(low, [DATA, AI], rescued=True) == "fit"
    assert (
        best_track([], [DATA, AI]) is None and bucket_for(None, [DATA, AI], rescued=False) == "low"
    )
