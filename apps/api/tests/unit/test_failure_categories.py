"""The failure classifier is a closed enum: sentences from shared constants, nothing else leaks."""

from __future__ import annotations

import pytest

from rhapto.engine.guardrails.registry import UnknownGuardrailError
from rhapto.engine.pipeline import LLMBudgetExceeded
from rhapto.engine.providers.errors import ProviderAuthError
from rhapto.engine.providers.llm import MalformedOutputError
from rhapto.engine.render.docx import OrphanBulletError
from rhapto.engine.render.pdf import PdfRenderError
from rhapto.engine.types import ProfileError
from rhapto.services import failure_categories as fc
from rhapto.services.documents import DocumentError
from rhapto.services.failure_categories import FAILURE_LABELS, FailureCategory, classify
from rhapto.services.llm import (
    KEY_UNREADABLE_MESSAGE,
    NOT_CONFIGURED_MESSAGE,
    LLMNotConfiguredError,
)
from rhapto.services.provider_messages import (
    PROVIDER_DISPLAY_NAMES,
    SHARED_KEY_REJECTED_MESSAGE,
    user_key_message,
)
from rhapto.services.trial import (
    BLOCKED_MESSAGE,
    FREE_RUNS_PAUSED_MESSAGE,
    AccountBlockedError,
    FreeRunsPausedError,
    TrialLimitExceededError,
    trial_limit_message,
)

SENTINEL = "SENTINEL-sk-abc"

SENTENCES: list[tuple[str, FailureCategory]] = [
    (str(AccountBlockedError()), FailureCategory.blocked),
    (str(FreeRunsPausedError()), FailureCategory.free_runs_paused),
    (str(LLMNotConfiguredError()), FailureCategory.key_not_configured),
    (KEY_UNREADABLE_MESSAGE, FailureCategory.key_unreadable),
    (SHARED_KEY_REJECTED_MESSAGE, FailureCategory.key_rejected_shared),
    *[
        (str(TrialLimitExceededError(used, limit)), FailureCategory.trial_limit)
        for used, limit in [(0, 0), (1, 1), (3, 3), (10, 10), (2, 250)]
    ],
    *[(trial_limit_message(n), FailureCategory.trial_limit) for n in (-1, 0, 1, 2, 3, 99)],
    *[
        (sentence, FailureCategory.key_rejected_own)
        for provider in PROVIDER_DISPLAY_NAMES
        for kind in ("auth", "quota")
        if (sentence := user_key_message(kind, provider)) is not None
    ],
    (
        "job 6f1c2d3e-0000-4000-8000-000000000001 not found for task "
        "6f1c2d3e-0000-4000-8000-000000000002",
        FailureCategory.job_missing,
    ),
    (
        "ValueError: job 6f1c2d3e-0000-4000-8000-000000000001 not found for task "
        "6f1c2d3e-0000-4000-8000-000000000002",
        FailureCategory.job_missing,
    ),
    (
        "ValueError: no resume document stored; upload one before tailoring in tune mode",
        FailureCategory.no_resume,
    ),
]

CLASS_PREFIXES: list[tuple[type[BaseException], FailureCategory]] = [
    (ProviderAuthError, FailureCategory.provider_error),
    (MalformedOutputError, FailureCategory.malformed_output),
    (LLMBudgetExceeded, FailureCategory.over_budget),
    (ProfileError, FailureCategory.profile_problem),
    (PdfRenderError, FailureCategory.render_failed),
    (OrphanBulletError, FailureCategory.guardrail_failed),
    (UnknownGuardrailError, FailureCategory.guardrail_failed),
    (DocumentError, FailureCategory.document_problem),
]


def test_notconfigured_constant_is_the_exception_text() -> None:
    assert str(LLMNotConfiguredError()) == NOT_CONFIGURED_MESSAGE


@pytest.mark.parametrize(("sentence", "expected"), SENTENCES)
def test_every_known_sentence_maps(sentence: str, expected: FailureCategory) -> None:
    assert classify(sentence) is expected


def test_the_sentence_list_is_not_empty_for_every_provider() -> None:
    assert len([s for s in SENTENCES if s[1] is FailureCategory.key_rejected_own]) == 2 * len(
        PROVIDER_DISPLAY_NAMES
    )


@pytest.mark.parametrize(("cls", "expected"), CLASS_PREFIXES)
def test_every_class_prefix_maps(cls: type[BaseException], expected: FailureCategory) -> None:
    assert classify(f"{cls.__name__}: {SENTINEL}") is expected


def test_every_prefix_in_the_table_is_tested() -> None:
    assert set(fc.CLASS_PREFIXES) == {cls.__name__ for cls, _ in CLASS_PREFIXES}


ADVERSARIAL = [
    f"EngineError: {SENTINEL}",
    f"ValueError: {SENTINEL}",
    f"{BLOCKED_MESSAGE} {SENTINEL}",
    f"{FREE_RUNS_PAUSED_MESSAGE}\n{SENTINEL}",
    f"{trial_limit_message(3)} {SENTINEL}",
    f"You have used all {SENTINEL} free tailoring runs on this instance. Add your own provider "
    "API key in Settings to keep going.",
    "Your Mystery key was refused. It may have expired or been revoked. "
    f"Paste a new key in Settings, then try again. {SENTINEL}",
    "Your Mystery key was refused. It may have expired or been revoked. "
    "Paste a new key in Settings, then try again.",
    f"job {SENTINEL} not found for task {SENTINEL}",
    f"ValueError: job {SENTINEL} not found for task {SENTINEL}",
    f"ValueError: parent package {SENTINEL} not found",
    "",
    ": ",
    "x" * 4000,
    f"{SENTINEL}: {SENTINEL}",
    f"EngineError: {SENTINEL}: ProfileError: {SENTINEL}",
]


@pytest.mark.parametrize("error", [*ADVERSARIAL, None])
def test_sentinel_never_survives(error: str | None) -> None:
    category = classify(error)
    assert isinstance(category, FailureCategory)
    assert SENTINEL not in FAILURE_LABELS[category]
    assert SENTINEL not in category.value


@pytest.mark.parametrize(
    "error",
    [
        f"EngineError: {SENTINEL}",
        f"ValueError: {SENTINEL}",
        f"{BLOCKED_MESSAGE} {SENTINEL}",
        f"{trial_limit_message(3)} {SENTINEL}",
        "",
        "x" * 4000,
        None,
    ],
)
def test_unmatched_inputs_are_other(error: str | None) -> None:
    assert classify(error) is FailureCategory.other


def test_unknown_provider_user_key_sentence_is_other() -> None:
    assert classify(ADVERSARIAL[7]) is FailureCategory.other


def test_labels_cover_the_enum() -> None:
    assert set(FAILURE_LABELS) == set(FailureCategory)
    assert all(label.strip() for label in FAILURE_LABELS.values())
    assert FAILURE_LABELS[FailureCategory.other] == "Other (see server logs)"


def test_enum_has_the_required_members() -> None:
    required = (
        "blocked trial_limit free_runs_paused key_not_configured key_rejected_shared "
        "key_rejected_own key_unreadable provider_error malformed_output over_budget "
        "profile_problem render_failed guardrail_failed document_problem job_missing "
        "no_resume did_not_finish other"
    ).split()
    assert set(required) <= {c.value for c in FailureCategory}


def test_constants_are_the_workers_constants() -> None:
    # The classifier must match what the worker stores, so both read the very same objects.
    from rhapto.worker import tasks

    assert tasks.SHARED_KEY_REJECTED_MESSAGE is SHARED_KEY_REJECTED_MESSAGE
    assert tasks.user_key_message is user_key_message
    assert vars(tasks)["KEY_UNREADABLE_MESSAGE"] is KEY_UNREADABLE_MESSAGE
    assert str(AccountBlockedError()) == BLOCKED_MESSAGE
    assert str(FreeRunsPausedError()) == FREE_RUNS_PAUSED_MESSAGE


def test_prefix_match_is_exact_not_startswith() -> None:
    assert classify("EngineErrorX: y") is FailureCategory.other
    assert classify("ProfileErrorX: y") is FailureCategory.other
    assert classify("xProfileError: y") is FailureCategory.other
    assert classify("profileerror: y") is FailureCategory.other
