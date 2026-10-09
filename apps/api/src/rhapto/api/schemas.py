from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from rhapto.db.models import APPLICATION_STATUSES, CLOSED_REASONS
from rhapto.engine.import_resume import ImportedLocation, ImportedTrack
from rhapto.engine.scoring import LocationTier
from rhapto.models.guardrail_report import GuardrailReport
from rhapto.models.jd_extract import JDExtract
from rhapto.models.profile.blocks import Block
from rhapto.models.resume_document import ResumeDocument
from rhapto.models.source_document import Edit, SourceDocument
from rhapto.services.feedback import FeedbackForm, PageArea, QuickAnswers, SurveyAnswers
from rhapto.services.trial import LlmKeySource


class HealthOut(BaseModel):
    status: str


class MeOut(BaseModel):
    email: str
    user_id: uuid.UUID
    # False when neither Settings nor the environment yields a usable provider key: the web app
    # uses it to point the user at Settings before they try to tailor anything.
    llm_configured: bool
    auth_mode: Literal["token", "access"]


class BootstrapOut(BaseModel):
    #: True the one time this call actually ran the backfill; False every other time (already
    #: seeded, or lost the atomic claim to a concurrent caller).
    seeded: bool


class ProviderInfoOut(BaseModel):
    """One supported provider, for the Settings picker."""

    id: str
    label: str
    models: list[str]
    default: str


class LlmSettingsOut(BaseModel):
    """What the user's LLM is right now. The key itself never leaves the server: only whether one
    is set, and its last four characters so the user can tell which key it is."""

    provider: str | None
    model: str | None
    key_set: bool
    key_hint: str | None
    source: Literal["settings", "env", "none"]
    providers: list[ProviderInfoOut]


# `llm_settings.model` is String(100) and `provider` is a registry id, so anything longer is a
# typo or a probe. Bounding it here makes it a 422 naming the field; without the bound an over-long
# model id reaches the INSERT and comes back as an opaque 500 (varchar truncation is a DBAPIError,
# not an IntegrityError, so nothing but the last-resort handler catches it).
ModelIdIn = Field(min_length=1, max_length=100)
ProviderIdIn = Field(max_length=20)


class LlmSettingsIn(BaseModel):
    provider: str = ProviderIdIn
    model: str = ModelIdIn
    # Omitted means "keep the key I already have" (or the environment's, for this provider).
    api_key: str | None = None


class LlmTestIn(BaseModel):
    provider: str = ProviderIdIn
    model: str = ModelIdIn
    api_key: str | None = None


class LlmTestOut(BaseModel):
    ok: bool
    model: str | None = None
    error: str | None = None


class UsageSummaryOut(BaseModel):
    """Token usage over some window, priced per model then summed (see the usage endpoint)."""

    calls: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    cost_usd: float | None
    #: Of `calls`, how many ran on a model with no price on file -- their tokens are counted
    #: above but not `cost_usd`, so the UI can say the estimate excludes them.
    unpriced_calls: int


class UsageRecentOut(BaseModel):
    package_id: uuid.UUID
    job_id: uuid.UUID
    company: str | None
    job_title: str | None
    model: str | None
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float | None
    created_at: datetime


class UsageOut(BaseModel):
    totals: UsageSummaryOut
    last_30_days: UsageSummaryOut
    recent: list[UsageRecentOut]


class ImportOut(BaseModel):
    blocks: int
    tracks: int
    bases: int
    guardrails: int


class ResumeImportOut(BaseModel):
    """A proposed profile the user has not yet accepted."""

    blocks: list[Block]
    tracks: list[ImportedTrack]
    location: ImportedLocation
    #: Blocks whose date could not be read and was deliberately left empty.
    dropped_periods: int
    #: Blocks carrying a number, which the confirmation step will walk through.
    metrics_to_confirm: int


class JobCreate(BaseModel):
    jd_text: str | None = None
    url: str | None = None
    company: str | None = None
    title: str | None = None
    location: str | None = None

    @model_validator(mode="after")
    def _one_source(self) -> JobCreate:
        if bool(self.jd_text) == bool(self.url):
            raise ValueError("provide exactly one of jd_text or url")
        if self.jd_text is not None and len(self.jd_text.strip()) < 50:
            raise ValueError("jd_text must be at least 50 characters")
        return self


class PackageSummary(BaseModel):
    id: uuid.UUID
    version: int
    status: str
    # The queue renders the mode chip from here, so "which mode produced this draft" is answerable
    # without fetching the package. Normalised on the way out, as the package endpoints do, so an
    # old row written before tune mode existed reads as "blocks".
    mode: Literal["blocks", "tune"]
    created_at: datetime


class JobScoreOut(BaseModel):
    track_id: str
    fit_score: int
    rationale: dict[str, Any]


class JobOut(BaseModel):
    id: uuid.UUID
    source: str
    company: str | None
    title: str | None
    location: str | None
    url: str | None
    jd_text: str
    extracted: JDExtract | None
    discovered_at: datetime
    latest_package: PackageSummary | None
    application_status: str | None
    best_track_id: str | None = None
    best_fit: int | None = None
    bucket: Literal["fit", "low"] | None = None
    location_tier: LocationTier | None = None
    rescued: bool = False
    repost_of: uuid.UUID | None = None
    posted_at: datetime | None = None
    scores: list[JobScoreOut] = []
    # The saved search that discovered this job, for display; None for manually-added jobs and
    # for board runs that carry no search. Left-joined in `jobs.list_jobs`.
    search_name: str | None = None
    # Not populated until Task 9 adds the column; declared now so the generated TypeScript
    # settles once.
    salary_text: str | None = None
    # "Not interested" / "no longer listed"; see Job.hidden_at and Job.unlisted_at.
    hidden_at: datetime | None = None
    unlisted_at: datetime | None = None
    # The other copies of this posting that `GET /jobs` collapsed into this row (same company and
    # title after normalisation). Computed per request, never stored; the web opens them with
    # `GET /jobs?ids=...`. Empty for `ids=` requests and for every sort that is not arranged.
    also_ids: list[uuid.UUID] = []


class TailorBody(BaseModel):
    track_id: str | None = None
    feedback: str | None = None
    parent_package_id: uuid.UUID | None = None
    # None means "pick for me": tune when the user has uploaded a resume document, blocks
    # otherwise. An explicit value always wins, so a user with a document can still run the
    # block library against a job.
    mode: Literal["blocks", "tune"] | None = None


class PackageOut(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    track_id: str
    version: int
    status: str
    resume: ResumeDocument
    cover_note: str
    change_log: str
    answers: dict[str, str]
    guardrail_report: GuardrailReport
    jd_extract: JDExtract
    llm_calls: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    llm_model: str | None
    cost_usd: float | None
    parent_package_id: uuid.UUID | None
    has_docx: bool
    has_pdf: bool
    created_at: datetime
    mode: Literal["blocks", "tune"]
    edits: list[Edit]
    source_document: SourceDocument | None
    #: What to do about each rule that fired here, keyed by rule id. Built at response time from
    #: `engine.guardrails.registry.REMEDIES` and restricted to the rules in THIS report -- never
    #: stored, because `GuardrailReport` is persisted JSONB with `extra="forbid"` and adding a field
    #: there would leave every existing row without it. A rule with no remedy is simply absent, and
    #: the panel then shows the rule id, message and path alone rather than dropping the row.
    guardrail_remedies: dict[str, str] = {}


class EditPatch(BaseModel):
    """One paragraph the human rewrote. `before` is not accepted: the stored document is the
    only authority on what the paragraph said."""

    paragraph_id: str
    after: str


class PackagePatch(BaseModel):
    """A human action on a package: `resume` in blocks mode, `edits` in tune mode, or `status`.

    Each field carries the complete new state for its mode, not a delta, so a new version is
    always a full replacement of the thing the mode owns. `status` is the odd one out: it changes
    the existing row in place and creates no version, because "I have read this and it is ready"
    is a fact about the draft that already exists, not a new draft.

    `blocked` is not settable: it is the guardrail validator's verdict, not a human's.
    """

    resume: ResumeDocument | None = None
    edits: list[EditPatch] | None = None
    status: Literal["ready", "draft"] | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> PackagePatch:
        given = [f for f in (self.resume, self.edits, self.status) if f is not None]
        if len(given) != 1:
            raise ValueError("provide exactly one of resume, edits or status")
        return self


class PackageListItem(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    company: str | None
    title: str | None
    version: int
    status: str
    mode: Literal["blocks", "tune"]
    application_status: str | None
    best_fit: int | None
    best_track_id: str | None
    created_at: datetime
    archived_at: datetime | None = None
    #: Error-severity guardrail violations on this package. The Resumes "Blocked" tab and the job
    #: card carried `status` alone, so a blocked row said "blocked" and nothing else. Read from the
    #: JSONB the list query already loads; no extra query.
    violations: int = 0


class ResumeDocumentOut(BaseModel):
    filename: str
    uploaded_at: datetime
    document: SourceDocument


class StatusChange(BaseModel):
    status: str
    at: datetime


class ApplicationCreate(BaseModel):
    job_id: uuid.UUID
    package_id: uuid.UUID | None = None


class ApplicationPatch(BaseModel):
    """A partial update. An omitted field is left alone; an explicit null clears it, which is
    why the router reads `model_dump(exclude_unset=True)` rather than testing for None."""

    model_config = ConfigDict(extra="forbid")

    status: str | None = None
    notes: str | None = None
    closed_reason: str | None = None
    follow_up_at: datetime | None = None

    @field_validator("status")
    @classmethod
    def _known_status(cls, value: str | None) -> str | None:
        if value is not None and value not in APPLICATION_STATUSES:
            raise ValueError(f"status must be one of {', '.join(APPLICATION_STATUSES)}")
        return value

    @field_validator("closed_reason")
    @classmethod
    def _known_reason(cls, value: str | None) -> str | None:
        if value is not None and value not in CLOSED_REASONS:
            raise ValueError(f"closed_reason must be one of {', '.join(CLOSED_REASONS)}")
        return value


class JobRef(BaseModel):
    id: uuid.UUID
    company: str | None
    title: str | None


class ApplicationOut(BaseModel):
    id: uuid.UUID
    job: JobRef
    package_id: uuid.UUID | None
    status: str
    applied_at: datetime | None
    notes: str
    status_history: list[StatusChange]
    created_at: datetime
    updated_at: datetime
    closed_reason: str | None = None
    follow_up_at: datetime | None = None


class BoardOut(BaseModel):
    columns: dict[str, list[ApplicationOut]]


class TaskOut(BaseModel):
    id: uuid.UUID
    type: str
    status: str
    progress: dict[str, Any]
    error: str | None
    result_ref: str | None
    created_at: datetime
    finished_at: datetime | None


class PollRunOut(BaseModel):
    id: uuid.UUID
    source: str
    board: str | None
    started_at: datetime
    finished_at: datetime | None
    found: int
    new: int
    error: str | None
    # Which saved search drove this run, for a keyless aggregator fanned out across several
    # searches (see services.discovery.poller). None for a board run.
    search_id: uuid.UUID | None = None


class SourceInfoOut(BaseModel):
    name: str
    kind: Literal["board", "aggregator"]
    label: str
    needs_board: bool


RemoteValue = Literal["include", "only", "exclude"]


class SearchIn(BaseModel):
    """What the form sends: either the one phrase the user typed, or an explicit keyword list.

    The search box has a single input, so `query` is the common case and `name` follows from it;
    the Searches tab edits the keyword list directly. Accepting both at once would leave "what
    is this search actually looking for" ambiguous, so exactly one is required.
    """

    name: str | None = Field(default=None, max_length=100)
    query: str | None = Field(default=None, max_length=200)
    keywords: list[str] | None = Field(default=None, max_length=10)
    location: str | None = Field(default=None, max_length=200)
    remote: RemoteValue = "include"
    active: bool = True

    @model_validator(mode="after")
    def _exactly_one_source(self) -> SearchIn:
        if (self.query is None) == (self.keywords is None):
            raise ValueError("provide exactly one of query or keywords")
        if self.query is not None and not self.query.strip():
            raise ValueError("query must not be blank")
        if self.keywords is not None:
            cleaned = [k.strip() for k in self.keywords if k.strip()]
            if not cleaned or any(len(k) > 60 for k in cleaned):
                raise ValueError("each keyword must be 1-60 characters")
        return self

    @property
    def resolved_keywords(self) -> list[str]:
        if self.keywords is not None:
            return [k.strip() for k in self.keywords if k.strip()]
        return [(self.query or "").strip()]

    @property
    def resolved_name(self) -> str:
        return ((self.name or "").strip() or self.resolved_keywords[0])[:100]


class SearchOut(BaseModel):
    id: uuid.UUID
    name: str
    keywords: list[str]
    location: str | None
    remote: RemoteValue
    active: bool
    derived_from_track_id: str | None
    created_at: datetime
    last_viewed_at: datetime | None = None
    #: Jobs this search found since `last_viewed_at`, excluding hidden and unlisted ones.
    new_count: int = 0
    #: Poll attempts recorded for this search. 0 means it has not run yet -- which is a different
    #: thing to say than "it found nothing", and the difference is why this is on the wire.
    runs: int = 0
    #: True when at least one of those attempts returned a posting. Read from `poll_runs`, not from
    #: `jobs.search_id`: that column is ON DELETE SET NULL and backfilled rows do not carry it, so
    #: it answers "has ever matched" wrongly. `runs > 0 and not ever_found` is the state spec §8
    #: calls "this search has never returned a job".
    ever_found: bool = False
    last_run_at: datetime | None = None


class SourceRunOut(BaseModel):
    """This source's most recent poll attempt, and what it was asked for.

    `found = 0` with `error = None` is the state the spec's §8 row 4 is about: the source answered
    and had nothing. `search_location` is the search's own string, so the row can say what was asked
    rather than only that nothing came back.

    There is deliberately no field for a suggested alternative location. Nothing in this repo can
    produce one -- no normaliser, no gazetteer, no per-source location vocabulary -- so any "Try X"
    would be a hard-coded string or an invention. `POST /searches/validate-location` (spec §9, part
    2) is what would make a real suggestion possible.
    """

    started_at: datetime
    finished_at: datetime | None
    found: int
    new: int
    error: str | None
    search_id: uuid.UUID | None
    search_name: str | None
    search_location: str | None


class SourceSettingOut(BaseModel):
    id: str
    label: str
    needs_key: bool
    fields: list[str]
    enabled: bool
    key_set: bool
    #: Is this source SET UP -- follows the poller's rule (an `aggregators` row must exist and be
    #: enabled, and a keyed source must have credentials), not this endpoint's own `enabled` default,
    #: which is why a user who has never opened Settings sees `enabled = true, configured = false`.
    #: That discrepancy is real and is recorded in docs/portal-backend-followups.md; making it
    #: visible is this branch's job, fixing it is not.
    #:
    #: Deliberately pause-free (§2.2): pause is scoped per `(source, board, search_id)`, so one
    #: boolean per source cannot carry it, and `ChecklistOut.job_sources` uses this same predicate so
    #: a transient pause does not flip a setup row to "not done".
    configured: bool = False
    #: Paused **as of the last run**: at least one of this source's scopes was refused with
    #: `PAUSED_MESSAGE` on its most recent attempt, and that attempt started after the row was last
    #: saved. There is no `paused` column -- pause is decided at poll time -- so this lags the third
    #: failure by one poll cycle, self-correcting on the next one. Covers aggregator sources only:
    #: board sources (greenhouse/lever/ashby/workday) also pause, per watchlist entry, and their
    #: surface is the watchlist, which already resets every streak on save.
    paused: bool = False
    #: Will this source run on the NEXT poll? `configured and not paused` -- a present-tense
    #: capability claim, which is why it has to account for pause: a `runnable` reading true for a
    #: source the poller will refuse would be a value asserting something about a state it does not
    #: check, which is the `resume_template` defect this whole branch exists to remove
    #: (architect's ruling, architecture §12.1).
    #:
    #: Residual proxy (§9 item 5): `paused` is "at least one scope paused", so this reads false for a
    #: source paused for some but not all of its saved searches -- it says "stopped" when it is partly
    #: working. Conservative in the direction of surfacing a real failure, which is the right bias
    #: here, and `last_run.error` names the failing scope.
    runnable: bool = False
    last_run: SourceRunOut | None = None


class SourceSettingIn(BaseModel):
    enabled: bool
    #: Omitted fields keep whatever is stored; the values never come back out.
    credentials: dict[str, str] | None = None


class SourceTestOut(BaseModel):
    ok: bool
    found: int | None = None
    error: str | None = None


class LiveSearchIn(BaseModel):
    """The search form: one free-text query plus the filter chips."""

    query: str = Field(min_length=1, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    remote: RemoteValue = "include"
    field: str | None = Field(default=None, max_length=50)
    posted_within: Literal["24h", "7d", "30d", "90d", "any"] = "90d"
    #: None means every enabled source; a list narrows the fan-out to those source ids.
    sources: list[str] | None = None


#: Every filter `GET /jobs` can be blamed for. Exactly the blamable ids in
#: `db.repositories.jobs.JOB_FILTERS` -- pinned by `tests/unit/test_job_filter_registry.py`, so a
#: new server-side filter cannot ship without the web app's widen map gaining a case for it. `ids`
#: is absent on purpose: it is a refetch mechanism, not a filter a user chose.
JobFilterId = Literal[
    "hidden",
    "search_id",
    "sources",
    "field",
    "posted_within",
    "recommended",
    "search",
    "track",
    "region",
    "bucket",
]


class JobsEmptyReasonOut(BaseModel):
    """Why `GET /jobs` returned nothing for exactly these filters.

    Computed from the same `JOB_FILTERS` registry `list_jobs` filters with, so the explanation
    cannot describe a filter the query did not apply.

    Structured, not prose: the API owns the *cause* and the web app owns the wording. The one-click
    widen needs a filter identity and a target value, which is structural rather than a sentence;
    and nothing here may be a hard-coded field name or city, which a server-rendered sentence would
    tempt. `field_name` and `user_field_names` come from the taxonomy and the user's own tracks.

    There is deliberately NO field for a suggested alternative location and none for an asserted
    cause of a zero-returning saved search. Neither is knowable: nothing in this codebase
    distinguishes an unrecognised location from an empty market, and there is no gazetteer to draw
    an alternative from. A test asserts no such field appears, so a later implementer cannot quietly
    fill one with a literal.
    """

    #: Every job this user owns, ignoring every filter. 0 means the corpus itself is empty.
    total: int
    cause: Literal["no_jobs", "field_without_tracks", "filter", "combination", "nothing_matched"]
    #: The blamed filter, only when `cause == "filter"`.
    filter_id: JobFilterId | None = None
    #: Its current value, for the sentence.
    filter_value: str | None = None
    #: Rows that appear if that one filter is widened.
    would_match: int | None = None
    #: Per blamable ACTIVE filter id, the rows that appear if that ONE filter is widened. The same
    #: leave-one-out counts the blame is chosen from, so it costs no extra query; an inactive filter
    #: is absent, and under `cause = "combination"` every value is 0 by definition.
    #:
    #: A client needs these to avoid offering a widen that would reveal nothing -- it has no other way
    #: to know. Counts only: nothing here asserts a cause or proposes a value the user did not choose,
    #: so C7 is unaffected.
    would_match_without: dict[JobFilterId, int] = {}
    #: Display name of the requested taxonomy field, from `services.taxonomy`.
    field_name: str | None = None
    #: Display names of the fields this user does have tracks in.
    user_field_names: list[str] = []
    #: Set when `search_id` is: the saved search's own name and location, how many times it has
    #: polled, and whether any of those polls ever returned a posting.
    search_name: str | None = None
    search_location: str | None = None
    search_runs: int | None = None
    search_ever_found: bool | None = None


class PerSourceOut(BaseModel):
    found: int
    new: int
    error: str | None = None


class LiveSearchOut(BaseModel):
    jobs: list[JobOut]
    #: Keyed by source id, so the UI can say which vendor was slow or needs a key.
    per_source: dict[str, PerSourceOut]


class TaxonomySuggestionOut(BaseModel):
    """One role the uploaded resume's entry titles point at, for the picker's chip row."""

    field_id: str
    field_name: str
    role_id: str
    role_name: str
    matched_title: str


class ChecklistOut(BaseModel):
    """Six profile tests plus the verified-block tally, and five setup rows so a stranger always
    has a next action.

    Every new field is COMPUTED from columns that already exist. No migration.

    Each one checks the real condition rather than a row that describes it, which is the standard
    `resume_template` had to learn the hard way (it reports the file on disk, not just the database
    row, because this deployment told its owner he was set up for three days after his upload was
    gone).
    """

    resume_template: bool
    contact_answers: bool
    tracks: bool
    blocks_verified: bool
    guardrails: bool
    location_preferences: bool
    verified_blocks: int
    total_blocks: int
    # --- setup, all computed ---
    #: A tailoring run would be admitted right now. NOT "a key exists": a user on this instance's
    #: key has no row and is not blocked, and a row whose ciphertext no longer decrypts blocks every
    #: run. See `services.trial.llm_setup_status`.
    llm_key: bool = False
    llm_key_source: LlmKeySource = "none"
    #: Runs left on this instance's key, only when a cap is in force. The row reads done while runs
    #: remain and flips to not-done at zero, because at zero the user is blocked.
    trial_runs_left: int | None = None
    #: At least one source could actually return a posting on the next poll. Follows the poller's
    #: rule, not the Settings page's display default -- so an account that has never opened Settings
    #: reads false even though Settings shows four keyless sources as enabled. That discrepancy is
    #: real; see docs/portal-backend-followups.md. Excludes pause, by design: pause is scoped per
    #: (source, board, search_id) and is answered by `SourceSettingOut.paused`.
    job_sources: bool = False
    usable_sources: int = 0
    #: At least one ACTIVE saved search. An all-inactive set polls nothing, because
    #: `poller.build_specs` filters on `active`.
    saved_searches: bool = False
    active_searches: int = 0
    #: At least one job that is neither hidden nor retired. No count is exposed: the number belongs
    #: on the Jobs page, which is the surface that can also explain it.
    jobs_found: bool = False
    #: Blocks with a missing or blank `period`. Spec §8 row 7: dateless blocks were invisible.
    dateless_blocks: int = 0


class SavedSearchCountOut(BaseModel):
    id: uuid.UUID
    name: str
    new_count: int
    #: The rail hides its badge when `new_count` is 0, which is exactly where the silence lives: a
    #: search that has never found anything looks identical to one the user has already read.
    ever_found: bool = False
    #: Poll attempts recorded for this search. Needed alongside `ever_found` because `!ever_found`
    #: alone cannot tell "polled and never matched" from "created a moment ago and not yet polled",
    #: and labelling the second one "never matched" is true and useless. Free: the dashboard already
    #: holds the `search_run_stats` row this comes from.
    runs: int = 0


class FollowUpOut(BaseModel):
    application_id: uuid.UUID
    job: JobRef
    status: str
    follow_up_at: datetime


class DashboardOut(BaseModel):
    new_fit_count: int
    needs_review_count: int
    checklist: ChecklistOut
    saved_searches: list[SavedSearchCountOut]
    due_followups: list[FollowUpOut]


class FeedbackIn(BaseModel):
    """One tester response. `user_id` and `app_version` are deliberately absent (and `extra="forbid"`
    rejects them): identity comes from `UserDep`, the version from the server."""

    model_config = ConfigDict(extra="forbid")

    form: FeedbackForm
    page_area: PageArea | None = None  # required iff quick
    answers: SurveyAnswers | QuickAnswers
    job_id: uuid.UUID | None = None  # quick only
    package_id: uuid.UUID | None = None  # quick only

    @model_validator(mode="after")
    def _shape_matches_form(self) -> FeedbackIn:
        if self.form == "quick":
            if not isinstance(self.answers, QuickAnswers):
                raise ValueError("quick feedback needs quick answers")
            if self.page_area is None:
                raise ValueError("quick feedback needs page_area")
        else:
            if not isinstance(self.answers, SurveyAnswers):
                raise ValueError("a survey needs survey answers")
            if self.page_area is not None:
                raise ValueError("a survey has no page_area")
            if self.job_id is not None or self.package_id is not None:
                raise ValueError("a survey has no page context")
            if not _survey_has_an_answer(self.answers):
                raise ValueError("a survey needs at least one answer")
        return self


def _survey_has_an_answer(answers: SurveyAnswers) -> bool:
    """True if any section carries a real answer. `quote_ok` is a consent flag, not an answer."""
    for section in answers.model_dump(exclude_none=True).values():
        if any(value is not None for key, value in section.items() if key != "quote_ok"):
            return True
    return False


class FeedbackOut(BaseModel):
    """Nothing else is echoed back: no answers, no ids of context."""

    id: uuid.UUID
    created_at: datetime


class ReadinessOut(BaseModel):
    """Spec 3.3: has the track's latest save been covered by a rescore that finished?"""

    ready: bool
