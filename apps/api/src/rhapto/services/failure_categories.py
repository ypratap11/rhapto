"""A closed set of failure categories for the owner's admin dashboard.

`tasks.error` can hold a provider's own words or text a user supplied, so the dashboard never shows
it. `classify` turns it into one of a fixed list of categories and only the category's label
travels. Nothing from the input is ever copied into the result.

Matching rules, deliberately narrow:
- a fixed sentence matches only with `fullmatch`, built from the same constants and functions the
  worker uses, never retyped here;
- a `ClassName: detail` string is looked up by the exact text before the first ``": "``, and the
  detail is ignored;
- `ValueError:` is understood only for the two sentences the worker raises itself;
- anything else, including `None`, is `other`.

This module does not import `rhapto.worker`.
"""

from __future__ import annotations

import re
from enum import StrEnum

from rhapto.engine.guardrails.registry import UnknownGuardrailError
from rhapto.engine.pipeline import LLMBudgetExceeded
from rhapto.engine.providers.errors import ProviderAuthError
from rhapto.engine.providers.llm import MalformedOutputError
from rhapto.engine.render.docx import OrphanBulletError
from rhapto.engine.render.pdf import PdfRenderError
from rhapto.engine.types import ProfileError
from rhapto.services.documents import DocumentError
from rhapto.services.llm import (
    KEY_UNREADABLE_MESSAGE,
    NOT_CONFIGURED_MESSAGE,
)
from rhapto.services.provider_messages import (
    PROVIDER_DISPLAY_NAMES,
    SHARED_KEY_REJECTED_MESSAGE,
    user_key_message,
)
from rhapto.services.trial import (
    BLOCKED_MESSAGE,
    FREE_RUNS_PAUSED_MESSAGE,
    trial_limit_message,
)


class FailureCategory(StrEnum):
    blocked = "blocked"
    trial_limit = "trial_limit"
    free_runs_paused = "free_runs_paused"
    key_not_configured = "key_not_configured"
    key_rejected_shared = "key_rejected_shared"
    key_rejected_own = "key_rejected_own"
    key_unreadable = "key_unreadable"
    provider_error = "provider_error"
    malformed_output = "malformed_output"
    over_budget = "over_budget"
    profile_problem = "profile_problem"
    render_failed = "render_failed"
    guardrail_failed = "guardrail_failed"
    document_problem = "document_problem"
    job_missing = "job_missing"
    no_resume = "no_resume"
    did_not_finish = "did_not_finish"
    other = "other"


FAILURE_LABELS: dict[FailureCategory, str] = {
    FailureCategory.blocked: "Account blocked",
    FailureCategory.trial_limit: "Used all free runs",
    FailureCategory.free_runs_paused: "Free runs paused for the month",
    FailureCategory.key_not_configured: "No API key set up",
    FailureCategory.key_rejected_shared: "Shared API key refused",
    FailureCategory.key_rejected_own: "Their own API key refused",
    FailureCategory.key_unreadable: "Stored API key could not be read",
    FailureCategory.provider_error: "AI provider error",
    FailureCategory.malformed_output: "AI returned unusable output",
    FailureCategory.over_budget: "Run needed more AI calls than allowed",
    FailureCategory.profile_problem: "Problem with their profile",
    FailureCategory.render_failed: "Resume file could not be built",
    FailureCategory.guardrail_failed: "Guardrail check failed",
    FailureCategory.document_problem: "Problem with their uploaded document",
    FailureCategory.job_missing: "Job no longer found",
    FailureCategory.no_resume: "No resume uploaded for tune mode",
    FailureCategory.did_not_finish: "Did not finish",
    FailureCategory.other: "Other (see server logs)",
}

# Exact class-name lookup. `ProviderAuthError` is normally stored as one of the sentences above;
# a bare class prefix means the run did not get that far, so it is only a provider problem.
CLASS_PREFIXES: dict[str, FailureCategory] = {
    ProviderAuthError.__name__: FailureCategory.provider_error,
    MalformedOutputError.__name__: FailureCategory.malformed_output,
    LLMBudgetExceeded.__name__: FailureCategory.over_budget,
    ProfileError.__name__: FailureCategory.profile_problem,
    PdfRenderError.__name__: FailureCategory.render_failed,
    OrphanBulletError.__name__: FailureCategory.guardrail_failed,
    UnknownGuardrailError.__name__: FailureCategory.guardrail_failed,
    DocumentError.__name__: FailureCategory.document_problem,
}

_ID = r"[0-9a-fA-F-]{36}"
# These two are raised as plain `ValueError` in worker/tasks.py; the text is fixed apart from ids.
_JOB_MISSING = re.compile(rf"job {_ID} not found for task {_ID}")
_NO_RESUME = re.compile(
    re.escape("no resume document stored; upload one before tailoring in tune mode")
)

# The trial-limit sentence has one integer in it. Build the pattern from the same function with a
# probe number, then let that number be any integer.
_PROBE = 987654321
_TRIAL_LIMIT = re.compile(re.escape(trial_limit_message(_PROBE)).replace(str(_PROBE), r"\d{1,9}"))

_FIXED: dict[str, FailureCategory] = {
    BLOCKED_MESSAGE: FailureCategory.blocked,
    FREE_RUNS_PAUSED_MESSAGE: FailureCategory.free_runs_paused,
    NOT_CONFIGURED_MESSAGE: FailureCategory.key_not_configured,
    KEY_UNREADABLE_MESSAGE: FailureCategory.key_unreadable,
    SHARED_KEY_REJECTED_MESSAGE: FailureCategory.key_rejected_shared,
    trial_limit_message(0): FailureCategory.trial_limit,
    trial_limit_message(1): FailureCategory.trial_limit,
}
for _provider in PROVIDER_DISPLAY_NAMES:
    for _kind in ("auth", "quota"):
        _sentence = user_key_message(_kind, _provider)
        if _sentence is not None:
            _FIXED[_sentence] = FailureCategory.key_rejected_own


def classify(error: str | None) -> FailureCategory:
    """The category for one stored task error. Never raises, never returns any part of `error`."""
    if not error:
        return FailureCategory.other
    fixed = _FIXED.get(error)
    if fixed is not None:
        return fixed
    if _TRIAL_LIMIT.fullmatch(error):
        return FailureCategory.trial_limit
    if _JOB_MISSING.fullmatch(error):
        return FailureCategory.job_missing
    head, sep, rest = error.partition(": ")
    if not sep:
        return FailureCategory.other
    if head == "ValueError":
        if _JOB_MISSING.fullmatch(rest):
            return FailureCategory.job_missing
        if _NO_RESUME.fullmatch(rest):
            return FailureCategory.no_resume
        return FailureCategory.other
    return CLASS_PREFIXES.get(head, FailureCategory.other)
