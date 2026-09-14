"""Deterministic track classification: embedding similarity plus keyword hits. No LLM."""

from __future__ import annotations

import re
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

LocationTier = Literal["preferred", "remote", "country", "abroad", "unknown"]

# How much of a job's fit survives its location. A great role in the wrong hemisphere is not
# a great role for this user, so the penalty is a multiplier on the blended fit rather than
# another weighted term: it cannot be out-argued by a strong keyword match.
LOCATION_MULTIPLIER: dict[LocationTier, float] = {
    "preferred": 1.0,
    "remote": 0.95,
    "country": 0.85,
    "abroad": 0.60,
    "unknown": 0.90,
}

# Values that mean "no" for `remote_ok`; everything else (including a blank answer) means yes.
_FALSEY = {"no", "false", "0"}

# A country or macro-region outside the US. Matched before the user's preferred list, because
# a named country settles the question: "Dublin, Ireland" is abroad even for a user whose
# preferred list names Dublin, CA.
NON_US_COUNTRIES: tuple[str, ...] = (
    "UK",
    "United Kingdom",
    "Great Britain",
    "England",
    "Scotland",
    "Wales",
    "Ireland",
    "Germany",
    "France",
    "Netherlands",
    "Belgium",
    "Spain",
    "Portugal",
    "Italy",
    "Poland",
    "Czechia",
    "Czech Republic",
    "Austria",
    "Hungary",
    "Romania",
    "Bulgaria",
    "Greece",
    "Denmark",
    "Norway",
    "Sweden",
    "Finland",
    "Estonia",
    "Latvia",
    "Lithuania",
    "Switzerland",
    "Israel",
    "Turkey",
    "United Arab Emirates",
    "UAE",
    "Saudi Arabia",
    "Egypt",
    "Nigeria",
    "Kenya",
    "South Africa",
    "India",
    "Pakistan",
    "Bangladesh",
    "Sri Lanka",
    "China",
    "Hong Kong",
    "Taiwan",
    "Japan",
    "Korea",
    "South Korea",
    "Singapore",
    "Malaysia",
    "Indonesia",
    "Thailand",
    "Vietnam",
    "Philippines",
    "Australia",
    "New Zealand",
    "Canada",
    "Mexico",
    "Brazil",
    "Argentina",
    "Chile",
    "Colombia",
    "Peru",
    "Costa Rica",
    "EMEA",
    "APAC",
    "LATAM",
    "Europe",
    "Asia",
    "Latin America",
)

# Well-known non-US cities. Matched *after* the preferred list (so a US namesake the user
# actually lives near still wins) and only when the text carries no US signal at all, which
# keeps "Vancouver, WA" in the country tier.
NON_US_CITIES: tuple[str, ...] = (
    "London",
    "Manchester",
    "Edinburgh",
    "Dublin",
    "Berlin",
    "Munich",
    "Hamburg",
    "Paris",
    "Amsterdam",
    "Brussels",
    "Madrid",
    "Barcelona",
    "Lisbon",
    "Milan",
    "Rome",
    "Warsaw",
    "Krakow",
    "Prague",
    "Vienna",
    "Budapest",
    "Bucharest",
    "Stockholm",
    "Copenhagen",
    "Oslo",
    "Helsinki",
    "Zurich",
    "Geneva",
    "Tel Aviv",
    "Dubai",
    "Bangalore",
    "Bengaluru",
    "Hyderabad",
    "Pune",
    "Chennai",
    "Mumbai",
    "Gurgaon",
    "Noida",
    "New Delhi",
    "Shanghai",
    "Beijing",
    "Shenzhen",
    "Taipei",
    "Tokyo",
    "Osaka",
    "Seoul",
    "Sydney",
    "Melbourne",
    "Toronto",
    "Vancouver",
    "Montreal",
    "Sao Paulo",
    "São Paulo",
    "Buenos Aires",
    "Mexico City",
    "Guadalajara",
)

_US_STATE_CODES = frozenset(
    """AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV
    NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY PR""".split()
)
_US_STATE_NAMES: tuple[str, ...] = (
    "Alabama",
    "Alaska",
    "Arizona",
    "Arkansas",
    "California",
    "Colorado",
    "Connecticut",
    "Delaware",
    "Florida",
    "Georgia",
    "Hawaii",
    "Idaho",
    "Illinois",
    "Indiana",
    "Iowa",
    "Kansas",
    "Kentucky",
    "Louisiana",
    "Maine",
    "Maryland",
    "Massachusetts",
    "Michigan",
    "Minnesota",
    "Mississippi",
    "Missouri",
    "Montana",
    "Nebraska",
    "Nevada",
    "New Hampshire",
    "New Jersey",
    "New Mexico",
    "New York",
    "North Carolina",
    "North Dakota",
    "Ohio",
    "Oklahoma",
    "Oregon",
    "Pennsylvania",
    "Rhode Island",
    "South Carolina",
    "South Dakota",
    "Tennessee",
    "Texas",
    "Utah",
    "Vermont",
    "Virginia",
    "Washington",
    "West Virginia",
    "Wisconsin",
    "Wyoming",
)
# "US"/"USA"/"U.S." are matched case-sensitively: lowercase "us" is an English pronoun.
_US_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])(?:USA?|U\.S\.A?\.?)(?![A-Za-z0-9])")
_STATE_CODE_RE = re.compile(r",\s*([A-Za-z]{2})(?![A-Za-z0-9])")


class LocationPreference(BaseModel):
    """Where this user wants to work, read off `answers.yaml`. Empty means "no preference"."""

    home: str | None = None
    preferred: tuple[str, ...] = ()
    remote_ok: bool = True


def location_preference_from_answers(answers: dict[str, str]) -> LocationPreference:
    home = (answers.get("location_home") or "").strip() or None
    preferred = tuple(
        part.strip()
        for part in (answers.get("location_preferred") or "").split(",")
        if part.strip()
    )
    remote = (answers.get("remote_ok") or "").strip().lower()
    return LocationPreference(home=home, preferred=preferred, remote_ok=remote not in _FALSEY)


def _any_match(terms: tuple[str, ...], text: str) -> bool:
    return any(keyword_matches(term, text) for term in terms)


def _has_us_signal(text: str) -> bool:
    if _US_TOKEN_RE.search(text) or keyword_matches("United States", text):
        return True
    if any(code.group(1).upper() in _US_STATE_CODES for code in _STATE_CODE_RE.finditer(text)):
        return True
    return _any_match(_US_STATE_NAMES, text)


def location_tier(location: str | None, pref: LocationPreference) -> LocationTier:
    """Tier one posting from its location field alone.

    The job description body is deliberately ignored: postings name offices on three
    continents in their boilerplate, so the body would tier almost everything "preferred".
    """
    text = (location or "").strip()
    if not text:
        return "unknown"
    if _any_match(NON_US_COUNTRIES, text):
        return "abroad"
    if _any_match(pref.preferred, text):
        return "preferred"
    us_signal = _has_us_signal(text)
    if not us_signal and _any_match(NON_US_CITIES, text):
        return "abroad"
    if keyword_matches("remote", text):
        # A user who has said remote_ok: no gains nothing from a remote listing, so it is
        # worth no more to them than a posting abroad — and carries the same multiplier.
        return "remote" if pref.remote_ok else "abroad"
    if us_signal:
        return "country"
    return "unknown"


class TrackScore(BaseModel):
    track_id: str
    fit_score: int
    semantic: int
    keywords: int
    matched: list[str]
    location_tier: LocationTier = "unknown"


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
    location_tier: LocationTier = "unknown",
) -> list[TrackScore]:
    multiplier = LOCATION_MULTIPLIER[location_tier]
    scores: list[TrackScore] = []
    for track in tracks:
        vector = track_embeddings.get(track.id)
        semantic = semantic_score(cosine(jd_embedding, vector)) if vector else 0
        keywords, matched = keyword_score(track, title, jd_text)
        fit = int(round(SEMANTIC_WEIGHT * semantic + KEYWORD_WEIGHT * keywords))
        scores.append(
            TrackScore(
                track_id=track.id,
                fit_score=int(round(fit * multiplier)),
                semantic=semantic,
                keywords=keywords,
                matched=matched,
                location_tier=location_tier,
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
        "location_tier": score.location_tier,
        "location_multiplier": LOCATION_MULTIPLIER[score.location_tier],
    }
