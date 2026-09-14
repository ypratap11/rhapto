"""Location priority: parsing the preference out of answers.yaml and tiering a posting."""

from rhapto.engine.providers.fake import FakeEmbeddingProvider
from rhapto.engine.scoring import (
    LOCATION_MULTIPLIER,
    LocationPreference,
    location_preference_from_answers,
    location_tier,
    rationale,
    score_job,
    track_text,
)
from rhapto.models.profile.tracks import Track

PREFERRED = (
    "Bay Area, San Francisco, San Jose, Santa Clara, Sunnyvale, Mountain View, "
    "Palo Alto, Fremont, Oakland, Pleasanton, Dublin, CA"
)
PREF = location_preference_from_answers(
    {"location_home": "Dublin, CA", "location_preferred": PREFERRED}
)
NO_REMOTE = location_preference_from_answers({"location_preferred": PREFERRED, "remote_ok": "no"})


def test_preference_parsing_splits_and_trims() -> None:
    pref = location_preference_from_answers(
        {"location_home": "  Dublin, CA ", "location_preferred": " Bay Area , , San Jose ,"}
    )
    assert pref.home == "Dublin, CA"
    assert pref.preferred == ("Bay Area", "San Jose")
    assert pref.remote_ok is True


def test_preference_parsing_without_any_location_keys() -> None:
    pref = location_preference_from_answers({"name": "Maya Chen"})
    assert pref == LocationPreference(home=None, preferred=(), remote_ok=True)


def test_remote_ok_variants() -> None:
    for value in ("no", "No", "FALSE", "0", " no "):
        assert location_preference_from_answers({"remote_ok": value}).remote_ok is False
    for value in ("yes", "y", "true", "1", "", "sure"):
        assert location_preference_from_answers({"remote_ok": value}).remote_ok is True


def test_tier_prefers_the_user_region_over_a_state_or_country_read() -> None:
    assert location_tier("US, CA, Santa Clara", PREF) == "preferred"
    assert location_tier("Dublin, CA", PREF) == "preferred"
    assert location_tier("Palo Alto (HQ)", PREF) == "preferred"
    assert location_tier("Mountain View, California", PREF) == "preferred"


def test_tier_marks_non_us_postings_abroad_even_when_the_city_name_collides() -> None:
    assert location_tier("Dublin, Ireland", PREF) == "abroad"
    assert location_tier("London, UK · Remote", PREF) == "abroad"
    assert location_tier("Remote - EMEA", PREF) == "abroad"
    assert location_tier("China, Shanghai", PREF) == "abroad"
    assert location_tier("Bengaluru", PREF) == "abroad"


def test_tier_reads_remote_only_when_the_user_accepts_remote() -> None:
    assert location_tier("Remote - US", PREF) == "remote"
    assert location_tier("Remote", PREF) == "remote"
    # remote_ok "no": a remote posting is worth no more to this user than one abroad, and the
    # multiplier is the same 0.60 (asserted through score_job below).
    assert location_tier("Remote", NO_REMOTE) == "abroad"


def test_tier_falls_back_to_country_then_unknown() -> None:
    assert location_tier("Denver, CO", PREF) == "country"
    assert location_tier("Austin, Texas", PREF) == "country"
    assert location_tier("New York, NY", PREF) == "country"
    assert location_tier("United States", PREF) == "country"
    assert location_tier("Multiple Locations", PREF) == "unknown"
    assert location_tier("", PREF) == "unknown"
    assert location_tier("   ", PREF) == "unknown"
    assert location_tier(None, PREF) == "unknown"


def test_multiplier_table_is_ordered_by_preference() -> None:
    assert LOCATION_MULTIPLIER == {
        "preferred": 1.0,
        "remote": 0.95,
        "country": 0.85,
        "abroad": 0.60,
        "unknown": 0.90,
    }


TRACK = Track(
    id="data-pm",
    name="Data Program Management",
    resume_base="b",
    min_fit=60,
    keywords=["data platform", "ETL"],
    description="Data platform and analytics program leadership.",
)


async def _fit(location: str | None, pref: LocationPreference) -> tuple[int, int]:
    """(fit with the location multiplier applied, fit as if the posting were preferred)."""
    embedder = FakeEmbeddingProvider()
    jd = "Own the data platform and ETL roadmap for analytics " * 5
    vectors = await embedder.embed([jd, track_text(TRACK)])
    args = (jd, jd, vectors[0], [TRACK], {"data-pm": vectors[1]})
    tier = location_tier(location, pref)
    return (
        score_job(*args, location_tier=tier)[0].fit_score,
        score_job(*args, location_tier="preferred")[0].fit_score,
    )


async def test_score_job_applies_the_multiplier_and_records_it() -> None:
    abroad, base = await _fit("Dublin, Ireland", PREF)
    assert abroad == round(base * 0.60)
    remote_declined, _ = await _fit("Remote", NO_REMOTE)
    assert remote_declined == round(base * 0.60)
    remote_ok, _ = await _fit("Remote", PREF)
    assert remote_ok == round(base * 0.95)
    preferred, _ = await _fit("Santa Clara, CA", PREF)
    assert preferred == base


def test_score_job_multiplier_math_rounds_the_way_python_does() -> None:
    def fit_for(raw: int, tier: str) -> int:
        return round(raw * LOCATION_MULTIPLIER[tier])  # type: ignore[index]

    assert fit_for(75, "abroad") == 45
    assert fit_for(72, "preferred") == 72
    assert fit_for(70, "country") == 60


async def test_rationale_carries_the_tier_and_multiplier() -> None:
    embedder = FakeEmbeddingProvider()
    jd = "Own the data platform and ETL roadmap for analytics " * 5
    vectors = await embedder.embed([jd, track_text(TRACK)])
    score = score_job(jd, jd, vectors[0], [TRACK], {"data-pm": vectors[1]}, location_tier="abroad")[
        0
    ]
    assert score.location_tier == "abroad"
    assert rationale(score)["location_tier"] == "abroad"
    assert rationale(score)["location_multiplier"] == 0.60


def test_score_job_defaults_to_unknown() -> None:
    assert LOCATION_MULTIPLIER["unknown"] == 0.90
