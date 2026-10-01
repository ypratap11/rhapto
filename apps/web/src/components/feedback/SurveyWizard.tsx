"use client";

import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";
import { useSignedIn } from "@/components/shell/TokenGate";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api/client";
import { useMe, useSubmitFeedback } from "@/lib/api/queries";
import {
  clearDraft,
  loadDraft,
  saveDraft,
  type SectionValues,
  SURVEY_STEPS,
  type SurveyDraft,
  type SurveyField,
  TEXT_MAX,
  toSurveyBody,
} from "@/lib/feedback";
import { ChoiceGroup } from "./ChoiceGroup";
import { FeedbackNotice } from "./FeedbackNotice";

const SAVE_DELAY_MS = 300;
type Answers = SurveyDraft["answers"];

/** The draft is keyed by user id, so the wizard waits for /me (already cached by TokenGate). */
export function SurveyWizard() {
  const signedIn = useSignedIn();
  const me = useMe({ enabled: signedIn });
  if (!me.isSuccess) return null;
  return <SurveyForm userId={me.data.user_id} />;
}

function hasAnswers(answers: Answers): boolean {
  return Object.keys(toSurveyBody({ savedAt: 0, step: 0, answers }).answers as object).length > 0;
}

function SurveyForm({ userId }: { userId: string }) {
  const submit = useSubmitFeedback();
  const [initial] = useState(() => loadDraft(userId));
  const [answers, setAnswers] = useState<Answers>(initial?.answers ?? {});
  const [step, setStep] = useState(initial?.step ?? 0);
  const [restored, setRestored] = useState(initial !== null);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Debounced draft save. An answer-less form clears the draft instead of saving an empty one, so
  // "Start over" (and a never-touched form) leaves nothing behind in the browser.
  useEffect(() => {
    if (done) return;
    const timer = setTimeout(() => {
      if (hasAnswers(answers)) saveDraft(userId, { savedAt: Date.now(), step, answers });
      else clearDraft(userId);
    }, SAVE_DELAY_MS);
    return () => clearTimeout(timer);
  }, [answers, step, done, userId]);

  // Leaving within the debounce window must not lose the last keystrokes.
  const latest = useRef({ answers, step, done });
  useEffect(() => {
    latest.current = { answers, step, done };
  });
  useEffect(
    () => () => {
      const { answers: a, step: s, done: d } = latest.current;
      if (!d && hasAnswers(a)) saveDraft(userId, { savedAt: Date.now(), step: s, answers: a });
    },
    [userId],
  );

  // Focus moves to the step heading on every step change (keyboard and screen-reader users land at
  // the top of the new step), but not on first render, which would steal focus from the page.
  const headingRef = useRef<HTMLHeadingElement>(null);
  const firstRender = useRef(true);
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    headingRef.current?.focus();
  }, [step]);

  if (done) {
    return (
      <section aria-live="polite" className="space-y-4">
        <h2 className="font-serif text-2xl">Thank you</h2>
        <p>Thank you — your answers were sent.</p>
        <Link href="/dashboard" className="inline-block text-sm underline">
          Back to dashboard
        </Link>
      </section>
    );
  }

  const current = SURVEY_STEPS[step];
  if (!current) return null;
  const values: SectionValues = answers[current.id] ?? {};
  const last = step === SURVEY_STEPS.length - 1;
  const sectionId = current.id;

  function setValue(key: string, value: string | number | boolean | undefined) {
    setAnswers((prev) => ({ ...prev, [sectionId]: { ...prev[sectionId], [key]: value } }));
  }

  async function send() {
    setError(null);
    try {
      await submit.mutateAsync(toSurveyBody({ savedAt: Date.now(), step, answers }));
      clearDraft(userId);
      setDone(true);
    } catch (e) {
      // Answers and draft stay: a failed send must never cost a tester their words.
      setError(e instanceof ApiError ? e.message : "Could not send your answers. Try again in a moment.");
    }
  }

  return (
    <div className="space-y-5">
      {restored ? (
        <p className="flex flex-wrap items-center gap-x-3 text-sm text-muted-foreground">
          <span>Restored your unsent answers.</span>
          <button
            type="button"
            className="underline hover:text-foreground"
            onClick={() => {
              clearDraft(userId);
              setAnswers({});
              setStep(0);
              setRestored(false);
              setError(null);
            }}
          >
            Start over
          </button>
        </p>
      ) : null}

      <div className="space-y-2">
        <p className="text-sm text-muted-foreground">{`Step ${step + 1} of ${SURVEY_STEPS.length}`}</p>
        <div
          role="progressbar"
          aria-label="Survey progress"
          aria-valuemin={1}
          aria-valuemax={SURVEY_STEPS.length}
          aria-valuenow={step + 1}
          className="h-1.5 w-full overflow-hidden rounded-full bg-muted"
        >
          <div className="h-full bg-primary" style={{ width: `${((step + 1) / SURVEY_STEPS.length) * 100}%` }} />
        </div>
      </div>

      <section className="space-y-5">
        <div className="space-y-1">
          <h2 ref={headingRef} tabIndex={-1} className="font-serif text-xl outline-none">
            {current.title}
          </h2>
          <p className="text-sm text-muted-foreground">{current.blurb} Every question is optional.</p>
        </div>
        {step === 0 ? <FeedbackNotice /> : null}
        {current.fields
          .filter((f) => !f.showIf || f.showIf(values))
          .map((field) => (
            <FieldControl key={`${current.id}.${field.key}`} field={field} value={values[field.key]} onChange={(v) => setValue(field.key, v)} />
          ))}
      </section>

      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}

      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-between">
        <Button type="button" variant="outline" className="w-full sm:w-auto" disabled={step === 0} onClick={() => setStep(step - 1)}>
          Back
        </Button>
        <div className="flex flex-col-reverse gap-2 sm:flex-row">
          {last ? (
            <Button type="button" className="w-full sm:w-auto" disabled={!hasAnswers(answers) || submit.isPending} onClick={() => void send()}>
              Submit
            </Button>
          ) : (
            <>
              <Button type="button" variant="ghost" className="w-full sm:w-auto" onClick={() => setStep(step + 1)}>
                Skip
              </Button>
              <Button type="button" className="w-full sm:w-auto" onClick={() => setStep(step + 1)}>
                Next
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function FieldControl({
  field,
  value,
  onChange,
}: {
  field: SurveyField;
  value: string | number | boolean | undefined;
  onChange: (value: string | number | boolean | undefined) => void;
}) {
  const id = useId();
  if (field.kind === "text") {
    const text = typeof value === "string" ? value : "";
    return (
      <div className="space-y-1.5">
        <Label htmlFor={id}>{field.label}</Label>
        <Textarea id={id} rows={4} maxLength={TEXT_MAX} value={text} onChange={(e) => onChange(e.target.value)} />
        <p className="text-right text-xs text-muted-foreground">{`${text.length} / ${TEXT_MAX}`}</p>
      </div>
    );
  }
  if (field.kind === "checkbox") {
    return (
      <label className="flex min-h-9 items-start gap-2 text-sm">
        <input
          type="checkbox"
          className="mt-0.5 size-4 accent-[var(--primary)]"
          checked={value === true}
          onChange={(e) => onChange(e.target.checked)}
        />
        {field.label}
      </label>
    );
  }
  const options = field.kind === "rating" ? [1, 2, 3, 4, 5].map((n) => ({ value: n, label: String(n) })) : (field.options ?? []);
  return (
    <div className="space-y-1">
      <ChoiceGroup
        legend={field.label}
        options={options}
        value={value as string | number | undefined}
        onChange={(v) => onChange(v ?? undefined)}
      />
      {field.hint ? <p className="text-xs text-muted-foreground">{field.hint}</p> : null}
    </div>
  );
}
