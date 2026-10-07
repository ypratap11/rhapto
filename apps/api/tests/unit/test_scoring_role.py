from __future__ import annotations

import pytest
from helpers import QA, QA_NO_EXCLUDE, TPM, TPM_NO_EXCLUDE

from rhapto.engine.scoring import (
    TITLE_MISS_CAP,
    LocationTier,
    RoleTitles,
    TrackScore,
    best_track,
    rationale,
    role_fit,
    score_job,
    title_match,
)
from rhapto.models.profile.tracks import Track

KEYWORDS = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta", "iota", "kappa"]
ROLE_TRACK = Track(id="role-track", name="Role", resume_base="b", min_fit=60, keywords=KEYWORDS)


def _score(
    title: str | None,
    role: RoleTitles | None,
    *,
    cosine: float = 0.5,
    hits: int = 3,
    tier: LocationTier = "preferred",
) -> TrackScore:
    """One track, controlled inputs: cosine 0.5 -> semantic 50; hits 3 of 10 keywords -> keywords 30."""
    jd_vector = [1.0, 0.0]
    track_vectors = {"role-track": [cosine, (1.0 - cosine * cosine) ** 0.5]}
    mapping = {"role-track": role} if role is not None else None
    [score] = score_job(
        title,
        " ".join(KEYWORDS[:hits]),
        jd_vector,
        [ROLE_TRACK],
        track_vectors,
        tier,
        has_location_preference=True,
        role_titles=mapping,
    )
    return score


def test_title_match_rules() -> None:
    assert title_match("senior qa ENGINEER", QA) == "QA engineer"
    assert title_match("Quality-Assurance Lead", QA) == "quality assurance"  # hyphen == space
    assert title_match("Flight Test Engineer", QA) is None  # an exclusion beats an accepted phrase
    assert title_match("QA Engineer, Flight Systems", QA) is None  # ... anywhere in the title
    assert title_match("", QA) is None and title_match(None, QA) is None
    assert title_match("   ", QA) is None


@pytest.mark.parametrize(
    ("tier", "expected"),
    [("preferred", 68), ("remote", 65), ("unknown", 62), ("country", 58), ("abroad", 41)],
)
def test_worked_numbers_for_a_title_match(tier: LocationTier, expected: int) -> None:
    """Spec B3: semantic 50, keywords 30, title 100 -> raw 68.5; Python rounds half to even."""
    score = _score("Senior QA Engineer", QA, tier=tier)
    assert (score.semantic, score.keywords) == (50, 30)
    assert score.blend == "role" and score.title_match == "QA engineer"
    assert score.fit_score == expected
    assert role_fit(100, 50, 30, score.location_multiplier) == expected


def test_the_cap_is_a_true_ceiling_applied_after_the_multiplier() -> None:
    # No title match, perfect semantic and keywords: raw 55, so the cap (not the blend) decides.
    assert TITLE_MISS_CAP == 45
    for tier, expected in [("preferred", 45), ("remote", 45), ("country", 45), ("abroad", 33)]:
        score = _score("Office Manager", QA, cosine=1.0, hits=10, tier=tier)  # type: ignore[arg-type]
        assert score.title_match is None and score.blend == "role"
        assert score.fit_score == expected  # abroad: 55 * 0.6 = 33, below the cap, so unchanged
    assert role_fit(0, 100, 100, 1.0) == 45


@pytest.mark.parametrize(
    "title", ["Flight Test Engineer", "Mechanical Test Engineer", "Supplier Quality Engineer"]
)
def test_known_bad_titles_are_capped_and_would_not_be_without_exclusions(title: str) -> None:
    # Premise: the title genuinely CONTAINS an accepted phrase. Without this the negative below
    # could pass for the wrong reason (architect finding C-1 caught exactly that).
    assert title_match(title, QA_NO_EXCLUDE) is not None
    # ... and with the exclusions removed it scores like a real match, which is the bug.
    assert _score(title, QA_NO_EXCLUDE).fit_score > TITLE_MISS_CAP
    protected = _score(title, QA)
    assert protected.title_match is None
    assert protected.fit_score <= TITLE_MISS_CAP


def test_construction_program_manager_is_capped_but_would_not_be_without_exclusions() -> None:
    title = "Program Manager, Construction"
    assert title_match(title, TPM_NO_EXCLUDE) == "program manager"
    assert _score(title, TPM_NO_EXCLUDE).fit_score > TITLE_MISS_CAP
    protected = _score(title, TPM)
    assert protected.title_match is None and protected.fit_score <= TITLE_MISS_CAP


def test_a_title_with_no_accepted_phrase_is_capped_whatever_the_description_says() -> None:
    # Topically perfect (probe finding 2: "Agentic AI Engineer" ranked 70-72 for an AI-program track).
    score = _score("Agentic AI Engineer", TPM, cosine=1.0, hits=10)
    assert score.title_match is None and score.fit_score == TITLE_MISS_CAP


def test_title_matches_clear_min_fit_at_the_preferred_tier() -> None:
    assert _score("Senior QA Engineer", QA).fit_score >= 60
    assert _score("Technical Program Manager, Platform", TPM).fit_score >= 60


def test_fallbacks_score_exactly_like_the_legacy_blend() -> None:
    legacy = _score("Senior QA Engineer", None)
    assert legacy.blend == "legacy" and legacy.title_match is None
    assert legacy.fit_score == 42  # round(0.6 * 50 + 0.4 * 30) * 1.0
    cases = {
        "role without titles": _score("Senior QA Engineer", RoleTitles(titles=())),
        "job with no title": _score(None, QA),
        "job with a blank title": _score("   ", QA),
    }
    for name, score in cases.items():
        assert score.blend == "legacy", name
        assert score.title_match is None, name
        assert score.fit_score == legacy.fit_score, name
    # A mapping that does not name this track (a stale role id resolves to no entry at all).
    [other] = score_job(
        "Senior QA Engineer",
        " ".join(KEYWORDS[:3]),
        [1.0, 0.0],
        [ROLE_TRACK],
        {"role-track": [0.5, 0.75**0.5]},
        "preferred",
        role_titles={"some-other-track": QA},
    )
    assert other.blend == "legacy" and other.fit_score == legacy.fit_score


def test_a_hand_written_track_defeats_the_cap_for_a_mixed_account() -> None:
    """KNOWN LIMIT, measured not hidden (spec B2, section 8): `best_track` takes the maximum across
    tracks, so a hand-written track (legacy blend, no title check) lifts a wrong-role job above the
    cap. No production account is mixed today; `rhapto rank-preview --synthetic-mixed` reports the
    effect on real data."""
    hand = Track(id="hand", name="Hand", resume_base="b", min_fit=60, keywords=KEYWORDS)
    vectors = {"role-track": [1.0, 0.0], "hand": [1.0, 0.0]}  # cosine 1: semantic 100 for both
    scores = score_job(
        "Flight Test Engineer",
        " ".join(KEYWORDS),
        [1.0, 0.0],
        [ROLE_TRACK, hand],
        vectors,
        "preferred",
        role_titles={"role-track": QA},
    )
    by_id = {s.track_id: s for s in scores}
    assert by_id["role-track"].blend == "role" and by_id["role-track"].fit_score == 45
    best = best_track(scores, [ROLE_TRACK, hand])
    assert best is not None and best.track_id == "hand" and best.blend == "legacy"
    assert best.fit_score > TITLE_MISS_CAP


def test_rationale_reports_the_blend_actually_used() -> None:
    hit = rationale(_score("Senior QA Engineer", QA))
    assert hit["blend"] == "role" and hit["title_match"] == "QA engineer" and hit["title"] == 100
    assert hit["weights"] == {"title": 0.45, "semantic": 0.35, "keywords": 0.2}
    miss = rationale(_score("Office Manager", QA))
    assert miss["title"] == 0 and miss["title_match"] is None
    legacy = rationale(_score("Senior QA Engineer", None))
    assert legacy["blend"] == "legacy" and legacy["title_match"] is None
    assert legacy["weights"] == {"semantic": 0.6, "keywords": 0.4}
    assert "title" not in legacy
    for payload in (hit, miss, legacy):
        assert payload["location_tier"] == "preferred" and payload["location_multiplier"] == 1.0
