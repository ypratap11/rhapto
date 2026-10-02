"""`FeedbackIn` shape rules, DB-free (the HTTP twins live in tests/api/test_feedback_api.py)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from pydantic import ValidationError

from rhapto.api.schemas import FeedbackIn

QUICK = {"kind": "bug", "text": "It broke."}


def ok(**kw: Any) -> FeedbackIn:
    return FeedbackIn.model_validate(kw)


def test_valid_shapes() -> None:
    assert ok(form="quick", page_area="jobs", answers=QUICK).form == "quick"
    assert ok(form="survey", answers={"overall": {"would_use": "yes"}}).page_area is None


@pytest.mark.parametrize(
    "body",
    [
        {"form": "survey", "answers": {}},
        {"form": "survey", "answers": {"overall": {}}},
        {"form": "survey", "answers": {"overall": {"quote_ok": True}}},
        {"form": "quick", "page_area": "jobs", "answers": {"overall": {"would_use": "yes"}}},
        {"form": "survey", "answers": QUICK},
        {"form": "quick", "answers": QUICK},
        {"form": "survey", "page_area": "jobs", "answers": {"overall": {"would_use": "yes"}}},
        {"form": "quick", "page_area": "nowhere", "answers": QUICK},
        {"form": "quick", "page_area": "jobs", "answers": {"kind": "rant"}},
        {"form": "quick", "page_area": "jobs", "answers": QUICK, "user_id": str(uuid.uuid4())},
        {"form": "quick", "page_area": "jobs", "answers": {"kind": "bug", "text": "a\x00b"}},
        {
            "form": "survey",
            "answers": {"overall": {"would_use": "yes"}},
            "job_id": str(uuid.uuid4()),
        },
    ],
)
def test_invalid_shapes(body: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        FeedbackIn.model_validate(body)
