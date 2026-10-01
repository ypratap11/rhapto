"""Answer schemas for tester feedback (services/feedback.py).

Every test here is DB-free. The NUL case matters most: `jsonb` refuses U+0000 with a DataError that
would surface as a 500 (the one path that logs), so validation must reject it first.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from rhapto.services.feedback import (
    SECTION_AREAS,
    TEXT_MAX,
    DownloadsSection,
    FindingJobsSection,
    GettingStartedSection,
    OverallSection,
    ProfileSection,
    QuickAnswers,
    ReviewSection,
    SessionSection,
)

# (model, field) for every FreeText field: the nine the architecture counts.
TEXT_FIELDS = [
    (SessionSection, "task_other"),
    (GettingStartedSection, "stuck"),
    (ProfileSection, "missing_or_confusing"),
    (FindingJobsSection, "bad_match_example"),
    (ReviewSection, "wrongly_blocked"),
    (DownloadsSection, "problems"),
    (OverallSection, "pay_why"),
    (OverallSection, "fix_first"),
    (QuickAnswers, "text"),
]


def _build(model, field, value):  # type: ignore[no-untyped-def]
    kwargs = {field: value}
    if model is QuickAnswers:
        kwargs["kind"] = "bug"
    return model(**kwargs)


def test_there_are_nine_free_text_fields() -> None:
    assert len(TEXT_FIELDS) == 9


@pytest.mark.parametrize(("model", "field"), TEXT_FIELDS)
def test_nul_is_rejected_in_every_text_field(model, field) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValidationError):
        _build(model, field, "before\x00after")


@pytest.mark.parametrize(("model", "field"), TEXT_FIELDS)
def test_other_c0_control_is_rejected_but_newline_and_tab_are_kept(model, field) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValidationError):
        _build(model, field, "bell\x07")
    ok = _build(model, field, "line one\n\tline two")
    assert getattr(ok, field) == "line one\n\tline two"


@pytest.mark.parametrize(("model", "field"), TEXT_FIELDS)
@pytest.mark.parametrize("bad", ["a\ud800b", "\udfff", "x\udc00"])
def test_lone_surrogate_is_rejected_in_every_text_field(model, field, bad) -> None:  # type: ignore[no-untyped-def]
    """json.loads accepts a lone surrogate escape; jsonb does not, so it must stop here (422)."""
    with pytest.raises(ValidationError):
        _build(model, field, bad)


def test_a_real_astral_character_is_still_fine() -> None:
    assert QuickAnswers(kind="idea", text="nice \U0001f600").text == "nice \U0001f600"


def test_validation_message_does_not_echo_the_value() -> None:
    with pytest.raises(ValidationError) as info:
        QuickAnswers(kind="bug", text="SECRET-SENTINEL\x00")
    assert "SECRET-SENTINEL" not in str(info.value.errors(include_input=False))


def test_length_bound() -> None:
    assert QuickAnswers(kind="bug", text="x" * TEXT_MAX).text == "x" * TEXT_MAX
    with pytest.raises(ValidationError):
        QuickAnswers(kind="bug", text="x" * (TEXT_MAX + 1))
    assert TEXT_MAX == 2000


def test_blank_text_becomes_none() -> None:
    assert QuickAnswers(kind="idea", text="   ").text is None
    assert QuickAnswers(kind="idea", text="").text is None


@pytest.mark.parametrize("bad", [0, 6, -1])
def test_rating_bounds(bad: int) -> None:
    with pytest.raises(ValidationError):
        GettingStartedSection(ease=bad)
    with pytest.raises(ValidationError):
        QuickAnswers(kind="bug", rating=bad)


def test_rating_edges_accepted() -> None:
    assert GettingStartedSection(ease=1).ease == 1
    assert GettingStartedSection(ease=5).ease == 5


def test_unknown_key_is_rejected() -> None:
    with pytest.raises(ValidationError):
        QuickAnswers(kind="bug", surprise="x")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        OverallSection(would_use="yes", extra_field=1)  # type: ignore[call-arg]


def test_quick_requires_a_known_kind() -> None:
    with pytest.raises(ValidationError):
        QuickAnswers()  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        QuickAnswers(kind="rant")  # type: ignore[arg-type]


def test_quote_ok_defaults_false() -> None:
    assert OverallSection().quote_ok is False


def test_section_areas_cover_every_area_except_other() -> None:
    from typing import get_args

    from rhapto.services.feedback import PageArea

    covered = {area for areas in SECTION_AREAS.values() for area in areas}
    assert covered == set(get_args(PageArea)) - {"other"}
