import type { components } from "@/lib/api/schema";

// Survey definition and the browser-side draft. Re-exported from lib/feedback.ts, which is the
// module the rest of the app imports. Section ids are keys of the generated SurveyAnswers type, so
// a section renamed or removed in the API is a compile error here rather than a 422 in front of a
// tester.

type FeedbackIn = components["schemas"]["FeedbackIn"];
export type SurveyAnswers = components["schemas"]["SurveyAnswers"];
export type SurveySectionId = keyof SurveyAnswers;

export type SectionValues = Record<string, string | number | boolean | undefined>;
export type SurveyOption = { value: string | number; label: string };
export type SurveyField = {
  key: string;
  label: string;
  kind: "choice" | "rating" | "text" | "checkbox";
  options?: ReadonlyArray<SurveyOption>;
  /** Only shown (and only sent) while this holds for the section's current answers. */
  showIf?: (values: SectionValues) => boolean;
  hint?: string;
};
export type SurveyStep = {
  id: SurveySectionId;
  title: string;
  blurb: string;
  fields: ReadonlyArray<SurveyField>;
};

export const TEXT_MAX = 2000;

const YES_NO_UNSURE: ReadonlyArray<SurveyOption> = [
  { value: "yes", label: "Yes" },
  { value: "no", label: "No" },
  { value: "not_sure", label: "Not sure" },
];
const YES_MAYBE_NO: ReadonlyArray<SurveyOption> = [
  { value: "yes", label: "Yes" },
  { value: "maybe", label: "Maybe" },
  { value: "no", label: "No" },
];

export const SURVEY_STEPS: ReadonlyArray<SurveyStep> = [
  {
    id: "session",
    title: "You and this session",
    blurb: "What you tried today.",
    fields: [
      {
        key: "task",
        label: "Which task did you try?",
        kind: "choice",
        options: [
          { value: "find_jobs", label: "Find jobs" },
          { value: "tailor_resume", label: "Tailor a resume" },
          { value: "review_package", label: "Review a package" },
          { value: "set_up_profile", label: "Set up my profile" },
          { value: "other", label: "Something else" },
        ],
      },
      { key: "task_other", label: "What was it?", kind: "text", showIf: (v) => v.task === "other" },
      {
        key: "finished",
        label: "Did you finish it?",
        kind: "choice",
        options: [
          { value: "yes", label: "Yes" },
          { value: "partly", label: "Partly" },
          { value: "no", label: "No" },
        ],
      },
      {
        key: "minutes",
        label: "Roughly how long did it take?",
        kind: "choice",
        options: [
          { value: "lt_10", label: "Under 10 min" },
          { value: "10_30", label: "10 to 30 min" },
          { value: "30_60", label: "30 to 60 min" },
          { value: "gt_60", label: "Over an hour" },
        ],
      },
    ],
  },
  {
    id: "getting_started",
    title: "Getting started",
    blurb: "Signing in and setting up.",
    fields: [
      { key: "ease", label: "How easy was it to get started? (1 hard, 5 easy)", kind: "rating" },
      { key: "stuck", label: "Where did you get stuck?", kind: "text" },
    ],
  },
  {
    id: "profile",
    title: "Your career record",
    blurb: "The Profile page.",
    fields: [
      { key: "ease", label: "How easy was it to build your record? (1 hard, 5 easy)", kind: "rating" },
      { key: "missing_or_confusing", label: "Anything missing or confusing?", kind: "text" },
    ],
  },
  {
    id: "finding_jobs",
    title: "Finding jobs",
    blurb: "The Dashboard and Jobs pages.",
    fields: [
      { key: "match_quality", label: "How good were the matches? (1 poor, 5 great)", kind: "rating" },
      { key: "bad_match_example", label: "One example of a bad match", kind: "text" },
    ],
  },
  {
    id: "review",
    title: "Tailored resume and the checks",
    blurb: "The Review page.",
    fields: [
      { key: "resume_quality", label: "How good was the tailored resume? (1 poor, 5 great)", kind: "rating" },
      { key: "flagged", label: "Did Rhapto flag or hold back a line?", kind: "choice", options: YES_NO_UNSURE },
      {
        key: "flag_verdict",
        label: "Was it right?",
        kind: "choice",
        options: [
          { value: "right", label: "Right" },
          { value: "false_alarm", label: "False alarm" },
          { value: "not_sure", label: "Not sure" },
        ],
      },
      {
        key: "would_have_noticed",
        label: "Would you have noticed it yourself?",
        kind: "choice",
        options: YES_NO_UNSURE,
        hint: "Your own recollection; it is recorded as self-reported.",
      },
      { key: "wrongly_blocked", label: "Was anything blocked that should not have been?", kind: "text" },
    ],
  },
  {
    id: "downloads",
    title: "Downloads and applying",
    blurb: "The Resumes and Dashboard pages.",
    fields: [
      {
        key: "looked_right",
        label: "Did the DOCX and PDF look right?",
        kind: "choice",
        options: [
          { value: "yes", label: "Yes" },
          { value: "no", label: "No" },
        ],
      },
      { key: "problems", label: "Anything that looked wrong?", kind: "text" },
    ],
  },
  {
    id: "overall",
    title: "Overall",
    blurb: "The big picture.",
    fields: [
      { key: "would_use", label: "Would you use it for your next real application?", kind: "choice", options: YES_MAYBE_NO },
      { key: "would_pay_19", label: "Would you pay $19 a month for it?", kind: "choice", options: YES_MAYBE_NO },
      { key: "pay_why", label: "Why, or why not?", kind: "text" },
      { key: "fix_first", label: "The one thing to fix first", kind: "text" },
      { key: "quote_ok", label: "You may quote my answers anonymously.", kind: "checkbox" },
    ],
  },
];

// Draft: unsent answers kept in this browser only (localStorage, so closing the tab does not lose
// them), keyed per user and expiring after 7 days to limit exposure on a shared browser. Every
// storage access is wrapped: private windows and blocked site data throw, and the survey must still
// work with the draft feature simply inert.

export type SurveyDraft = {
  savedAt: number;
  step: number;
  answers: Partial<Record<SurveySectionId, SectionValues>>;
};

const DRAFT_TTL_MS = 7 * 24 * 60 * 60 * 1000;

export function draftKey(userId: string): string {
  return `rhapto.feedback.draft.v1.${userId}`;
}

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

export function loadDraft(userId: string): SurveyDraft | null {
  try {
    const raw = window.localStorage.getItem(draftKey(userId));
    if (raw === null) return null;
    const draft = parseDraft(raw);
    // An expired or unreadable draft is free text nobody can restore: do not leave it behind.
    if (draft === null) window.localStorage.removeItem(draftKey(userId));
    return draft;
  } catch {
    return null;
  }
}

function parseDraft(raw: string): SurveyDraft | null {
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!isPlainObject(parsed)) return null;
    const { savedAt, step, answers } = parsed;
    if (typeof savedAt !== "number" || typeof step !== "number" || !isPlainObject(answers)) return null;
    if (Date.now() - savedAt > DRAFT_TTL_MS) return null;
    return {
      savedAt,
      step: Math.min(Math.max(Math.trunc(step), 0), SURVEY_STEPS.length - 1),
      answers: answers as SurveyDraft["answers"],
    };
  } catch {
    return null;
  }
}

export function saveDraft(userId: string, draft: SurveyDraft): void {
  try {
    window.localStorage.setItem(draftKey(userId), JSON.stringify(draft));
  } catch {
    // inert: the survey works without a draft
  }
}

export function clearDraft(userId: string): void {
  try {
    window.localStorage.removeItem(draftKey(userId));
  } catch {
    // inert
  }
}

/** The payload for POST /feedback: empty sections and fields are dropped, as is a false quote_ok. */
export function toSurveyBody(draft: SurveyDraft): FeedbackIn {
  const answers: Record<string, Record<string, string | number | boolean>> = {};
  for (const step of SURVEY_STEPS) {
    const values = draft.answers[step.id];
    if (!values) continue;
    const kept: Record<string, string | number | boolean> = {};
    for (const field of step.fields) {
      if (field.showIf && !field.showIf(values)) continue;
      const raw = values[field.key];
      if (raw === undefined || raw === null) continue;
      if (field.kind === "checkbox") {
        if (raw === true) kept[field.key] = true;
        continue;
      }
      if (field.kind === "text") {
        const text = typeof raw === "string" ? raw.trim() : "";
        if (text) kept[field.key] = text;
        continue;
      }
      kept[field.key] = raw;
    }
    if (Object.keys(kept).length > 0) answers[step.id] = kept;
  }
  return { form: "survey", answers: answers as SurveyAnswers };
}
