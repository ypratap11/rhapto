"""The Literal types in services/feedback.py and the tuples in db/models.py must not drift: the
database CHECKs are built from the tuples, the API validates against the Literals."""

from __future__ import annotations

from typing import get_args

from rhapto.db.models import FEEDBACK_FORMS, PAGE_AREAS
from rhapto.services.feedback import FeedbackForm, PageArea


def test_page_areas_match_the_literal() -> None:
    assert set(get_args(PageArea)) == set(PAGE_AREAS)
    assert len(PAGE_AREAS) == len(set(PAGE_AREAS))


def test_forms_match_the_literal() -> None:
    assert set(get_args(FeedbackForm)) == set(FEEDBACK_FORMS)
