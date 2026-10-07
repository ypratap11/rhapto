"""Deterministic track classification: embedding similarity plus keyword hits. No LLM."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
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

# Role-first blend (search-quality spec B3). The title says whether a job IS the user's role; the
# description only says what it is about. A job whose title is not the role is capped, after the
# location multiplier, so 45 is a true ceiling.
TITLE_WEIGHT = 0.45
ROLE_SEMANTIC_WEIGHT = 0.35
ROLE_KEYWORD_WEIGHT = 0.20
TITLE_MISS_CAP = 45

LocationTier = Literal["preferred", "remote", "country", "abroad", "unknown"]
Blend = Literal["role", "legacy"]

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

# Well-known non-US cities, each with the ISO country code a posting is likely to pair it
# with. The code matters because half of them collide with a US state code: "Berlin, DE" is
# Germany, not Delaware, and "Toronto, CA" is Canada, not California. A city that appears
# alongside its own code vetoes that code as a US signal, and tiers the posting abroad before
# the preferred list is consulted -- otherwise a bare state code in that list ("CA") would
# claim it. The bare city name is still checked later, after the preferred list, so a US
# namesake the user actually lives near ("Dublin, CA") still wins.
NON_US_CITIES: tuple[tuple[str, str], ...] = (
    ("London", "GB"),
    ("Manchester", "GB"),
    ("Edinburgh", "GB"),
    ("Dublin", "IE"),
    ("Berlin", "DE"),
    ("Munich", "DE"),
    ("Hamburg", "DE"),
    ("Paris", "FR"),
    ("Amsterdam", "NL"),
    ("Brussels", "BE"),
    ("Madrid", "ES"),
    ("Barcelona", "ES"),
    ("Lisbon", "PT"),
    ("Milan", "IT"),
    ("Rome", "IT"),
    ("Warsaw", "PL"),
    ("Krakow", "PL"),
    ("Prague", "CZ"),
    ("Vienna", "AT"),
    ("Budapest", "HU"),
    ("Bucharest", "RO"),
    ("Stockholm", "SE"),
    ("Copenhagen", "DK"),
    ("Oslo", "NO"),
    ("Helsinki", "FI"),
    ("Zurich", "CH"),
    ("Geneva", "CH"),
    ("Tel Aviv", "IL"),
    ("Dubai", "AE"),
    ("Bangalore", "IN"),
    ("Bengaluru", "IN"),
    ("Hyderabad", "IN"),
    ("Pune", "IN"),
    ("Chennai", "IN"),
    ("Mumbai", "IN"),
    ("Gurgaon", "IN"),
    ("Noida", "IN"),
    ("New Delhi", "IN"),
    ("Shanghai", "CN"),
    ("Beijing", "CN"),
    ("Shenzhen", "CN"),
    ("Taipei", "TW"),
    ("Tokyo", "JP"),
    ("Osaka", "JP"),
    ("Seoul", "KR"),
    ("Sydney", "AU"),
    ("Melbourne", "AU"),
    ("Toronto", "CA"),
    ("Vancouver", "CA"),
    ("Montreal", "CA"),
    ("Sao Paulo", "BR"),
    ("São Paulo", "BR"),
    ("Buenos Aires", "AR"),
    ("Mexico City", "MX"),
    ("Guadalajara", "MX"),
    ("Bogota", "CO"),
    ("Bogotá", "CO"),
    ("Lima", "PE"),
    ("Santiago", "CL"),
)
_NON_US_CITY_NAMES: tuple[str, ...] = tuple(city for city, _ in NON_US_CITIES)

# US states and territories, code to name. One table: the codes read a posting's
# "Denver, CO", the names read its "Austin, Texas", and a qualified preferred entry
# accepts either spelling of its state half.
US_STATES: dict[str, str] = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "DC": "District of Columbia",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "PR": "Puerto Rico",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
}
_US_STATE_CODES = frozenset(US_STATES)
_US_STATE_NAMES: tuple[str, ...] = tuple(US_STATES.values())
# "US"/"USA"/"U.S." are matched case-sensitively: lowercase "us" is an English pronoun.
_US_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])(?:USA?|U\.S\.A?\.?)(?![A-Za-z0-9])")
_STATE_CODE_RE = re.compile(r",\s*([A-Za-z]{2})(?![A-Za-z0-9])")
# A preferred entry of the form "Denver, CO" — the comma is part of the entry, not a separator.
_QUALIFIED_RE = re.compile(r"^(?P<place>.+?),\s*(?P<code>[A-Za-z]{2})$")


# The answers `location_preference_from_answers` reads. They are settings, not questions an
# employer asks, so `engine.compose` strips them from the LLM prompts and the answers endpoint
# re-scores the queue when one of them changes — all three import this one definition.
SCORING_KEYS = frozenset({"location_home", "location_preferred", "remote_ok"})


class LocationPreference(BaseModel):
    """Where this user wants to work, read off `answers.yaml`. Empty means "no preference"."""

    home: str | None = None
    preferred: tuple[str, ...] = ()
    remote_ok: bool = True

    @property
    def terms(self) -> tuple[str, ...]:
        """What a posting's location is matched against: the preferred list, falling back to
        `location_home` so a user who has only said where they live still gets a preferred tier.
        """
        if self.preferred:
            return self.preferred
        return (self.home,) if self.home else ()


def _split_preferred(value: str) -> tuple[str, ...]:
    """Split the comma-separated list, keeping each "City, ST" pair together.

    A bare town name matches its namesakes nationwide — "Aurora" is Aurora, IL as much as
    Aurora, CO — so users are told to qualify each entry with its state. That makes the comma
    ambiguous, and the two-letter state code is what disambiguates it: a part that is nothing
    but a state code belongs to the part before it.
    """
    parts = [part.strip() for part in value.split(",") if part.strip()]
    entries: list[str] = []
    for part in parts:
        if entries and len(part) == 2 and part.upper() in _US_STATE_CODES:
            entries[-1] = f"{entries[-1]}, {part.upper()}"
        else:
            entries.append(part)
    return tuple(entries)


def location_preference_from_answers(answers: dict[str, str]) -> LocationPreference:
    home = (answers.get("location_home") or "").strip() or None
    preferred = _split_preferred(answers.get("location_preferred") or "")
    remote = (answers.get("remote_ok") or "").strip().lower()
    return LocationPreference(home=home, preferred=preferred, remote_ok=remote not in _FALSEY)


def _any_match(terms: tuple[str, ...], text: str) -> bool:
    return any(keyword_matches(term, text) for term in terms)


def _preferred_matches(term: str, text: str) -> bool:
    """A "City, ST" entry needs both halves present, in either spelling of the state.

    So "Denver, CO" matches a posting saying "Denver, CO" or "Denver, Colorado", and does not
    match "Denver, PA". Any other entry ("Bay Area", "Front Range") is a plain whole-word match.
    """
    qualified = _QUALIFIED_RE.match(term)
    if qualified is None:
        return keyword_matches(term, text)
    code = qualified.group("code").upper()
    if code not in US_STATES:
        return keyword_matches(term, text)
    return keyword_matches(qualified.group("place").strip(), text) and (
        keyword_matches(code, text) or keyword_matches(US_STATES[code], text)
    )


def _foreign_city_codes(text: str) -> frozenset[str]:
    """Two-letter codes in `text` that belong to a foreign city named in the same string.

    "Berlin, DE" yields {"DE"}, so Delaware cannot claim it; "Vancouver, WA" yields nothing,
    because Vancouver's code is CA and the text says WA.
    """
    codes = {match.group(1).upper() for match in _STATE_CODE_RE.finditer(text)}
    if not codes:
        return frozenset()
    return frozenset(
        code for city, code in NON_US_CITIES if code in codes and keyword_matches(city, text)
    )


def _has_us_signal(text: str, ignore: frozenset[str] = frozenset()) -> bool:
    if _US_TOKEN_RE.search(text) or keyword_matches("United States", text):
        return True
    for match in _STATE_CODE_RE.finditer(text):
        code = match.group(1).upper()
        if code in _US_STATE_CODES and code not in ignore:
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
    foreign_codes = _foreign_city_codes(text)
    us_signal = _has_us_signal(text, ignore=foreign_codes)
    # A named country settles the question — but only when nothing in the string is in the US.
    # Boards routinely list several offices in one field ("San Francisco, CA; London, UK"), and
    # one of them being abroad must not cost the user the one down the road.
    if not us_signal and (foreign_codes or _any_match(NON_US_COUNTRIES, text)):
        return "abroad"
    if any(_preferred_matches(term, text) for term in pref.terms):
        return "preferred"
    if not us_signal and _any_match(_NON_US_CITY_NAMES, text):
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
    #: The multiplier actually applied to reach `fit_score` -- not always `LOCATION_MULTIPLIER
    #: [location_tier]`; see `_location_multiplier`. Recorded here so `rationale` reports what
    #: happened rather than recomputing it from the tier alone.
    location_multiplier: float = 1.0
    #: The `titles` phrase that matched the job's title, or None (no match, or the legacy blend).
    title_match: str | None = None
    #: Which blend produced `fit_score`: "role" (title-first) or "legacy" (semantic + keywords).
    blend: Blend = "legacy"


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


@dataclass(frozen=True)
class RoleTitles:
    """One taxonomy role's title phrases, resolved by the caller. `engine/` cannot read the
    taxonomy (it imports no service), so `services.scoring` hands these in per track."""

    titles: tuple[str, ...]
    exclude: tuple[str, ...] = ()


def title_match(title: str | None, role: RoleTitles) -> str | None:
    """The `titles` phrase `title` matches, or None.

    A title is a match when it contains a `titles` phrase AND no `exclude` phrase: "Flight Test
    Engineer" contains "test engineer" but is vetoed by "flight". Whole-word, case-insensitive
    (`keyword_matches`). A blank title never matches.
    """
    if not title or not title.strip():
        return None
    if any(keyword_matches(phrase, title) for phrase in role.exclude):
        return None
    return next((phrase for phrase in role.titles if keyword_matches(phrase, title)), None)


def role_fit(title_score: int, semantic: int, keywords: int, multiplier: float) -> int:
    """The role-first blend: one rounding, then the cap last (so it is a true ceiling)."""
    raw = (
        TITLE_WEIGHT * title_score
        + ROLE_SEMANTIC_WEIGHT * semantic
        + ROLE_KEYWORD_WEIGHT * keywords
    )
    fit = int(round(raw * multiplier))
    return min(fit, TITLE_MISS_CAP) if title_score == 0 else fit


#: Tiers a posting can only land in through the *absence* of location information (`unknown`)
#: or a US-but-not-preferred read (`country`) -- as opposed to `abroad` (the posting itself says
#: another country) and `remote` (a separate preference, `remote_ok`). Penalising either of these
#: two for a user who never said where they want to work punishes silence as if it were a
#: rejection.
_PREFERENCE_ONLY_PENALTY_TIERS = frozenset({"unknown", "country"})


def _location_multiplier(tier: LocationTier, *, has_location_preference: bool) -> float:
    """The multiplier to apply for `tier`, given whether this user expressed any preference.

    `pref.terms` empty means "no preference at all" (`LocationPreference`'s own docstring).
    Spec §8: 99 of 122 matches lost fit to a location the user never said they cared about, so a
    user with no preference pays no `unknown`/`country` penalty -- `abroad` and `remote` are
    unaffected, since those reflect the posting's own location or the separate `remote_ok`
    answer, not the (empty) preferred-locations list.
    """
    if not has_location_preference and tier in _PREFERENCE_ONLY_PENALTY_TIERS:
        return 1.0
    return LOCATION_MULTIPLIER[tier]


def score_job(
    title: str | None,
    jd_text: str,
    jd_embedding: list[float],
    tracks: list[Track],
    track_embeddings: dict[str, list[float]],
    location_tier: LocationTier = "unknown",
    *,
    has_location_preference: bool = True,
    role_titles: Mapping[str, RoleTitles] | None = None,
) -> list[TrackScore]:
    """Score one job against every track.

    A track listed in `role_titles` (keyed by track id) with a non-empty `titles` is scored with
    the role-first blend, provided the job has a title; every other track -- no entry, an empty
    role, a job with no title -- keeps today's semantic + keyword blend, unchanged.
    """
    multiplier = _location_multiplier(
        location_tier, has_location_preference=has_location_preference
    )
    has_title = bool(title and title.strip())
    scores: list[TrackScore] = []
    for track in tracks:
        vector = track_embeddings.get(track.id)
        semantic = semantic_score(cosine(jd_embedding, vector)) if vector else 0
        keywords, matched = keyword_score(track, title, jd_text)
        role = (role_titles or {}).get(track.id)
        blend: Blend = "legacy"
        phrase: str | None = None
        if role is not None and role.titles and has_title:
            phrase = title_match(title, role)
            fit_score = role_fit(100 if phrase else 0, semantic, keywords, multiplier)
            blend = "role"
        else:
            fit = int(round(SEMANTIC_WEIGHT * semantic + KEYWORD_WEIGHT * keywords))
            fit_score = int(round(fit * multiplier))
        scores.append(
            TrackScore(
                track_id=track.id,
                fit_score=fit_score,
                semantic=semantic,
                keywords=keywords,
                matched=matched,
                location_tier=location_tier,
                location_multiplier=multiplier,
                title_match=phrase,
                blend=blend,
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
    """Why this score, as stored in `job_scores.rationale_json`. Reports the blend actually used."""
    weights: dict[str, float]
    if score.blend == "role":
        weights = {
            "title": TITLE_WEIGHT,
            "semantic": ROLE_SEMANTIC_WEIGHT,
            "keywords": ROLE_KEYWORD_WEIGHT,
        }
    else:
        weights = {"semantic": SEMANTIC_WEIGHT, "keywords": KEYWORD_WEIGHT}
    payload: dict[str, Any] = {
        "semantic": score.semantic,
        "keywords": score.keywords,
        "matched": score.matched,
        "blend": score.blend,
        "title_match": score.title_match,
        "weights": weights,
        "location_tier": score.location_tier,
        "location_multiplier": score.location_multiplier,
    }
    if score.blend == "role":
        payload["title"] = 100 if score.title_match else 0
    return payload
