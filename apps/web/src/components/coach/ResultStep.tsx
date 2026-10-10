"use client";

import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useAnswers, usePackage, type PackageOut } from "@/lib/api/queries";
import { DOWNLOAD_DOCX, DOWNLOAD_PDF, RESULT_READY, RESULT_TITLE, WHAT_CHANGED } from "@/lib/coach/copy";
import { describeCoachError, type CoachError } from "@/lib/coach/errors";
import { fireCoachEvent } from "@/lib/coach/events";
import { downloadAuthenticated, resumeFilename } from "@/lib/download";
import { CoachErrorNote, CoachFrame, type TranscriptItem } from "./CoachFrame";

const MAX_CHANGES = 6;

/** The homepage promises that a blocked draft shows "which rule fired". Each rule gets a plain-words
 * line first, then its name exactly as the engine reports it (the same name the full details page
 * and the homepage proof print). The coach only runs tune mode, so the tune-mode rules are the ones
 * worded here; any other rule still shows its name and message, never nothing. */
const RULE_WORDS: Record<string, string> = {
  "no-new-numbers": "A number that isn't in your resume",
  "tune-scope": "A change outside the lines Rhapto may rewrite",
  "no-invented-entities": "A name (an employer, school or tool) that isn't in your resume",
  "date-consistency": "Dates that don't line up with your resume",
};

/** The spec's headline says the draft "added something", which is true only of these two rules; any
 * other rule gets the neutral sentence (controller ruling 2026-10-09). */
const ADDED_SOMETHING = new Set(["no-new-numbers", "no-invented-entities"]);
const HEADLINE_ADDED = "Rhapto stopped this draft because it added something that isn't in your resume";
const HEADLINE_CHECK = "Rhapto stopped this draft because it didn't pass one of its checks";

export function ResultStep({
  packageId,
  transcript,
  retryBusy,
  error: retryError = null,
  onRetry,
  onAnother,
}: {
  packageId: string;
  transcript?: TranscriptItem[];
  retryBusy: boolean;
  /** Why the last retry was refused, in plain words. */
  error?: CoachError | null;
  onRetry: (pkg: PackageOut) => void;
  onAnother: () => void;
}) {
  const pkg = usePackage(packageId);
  const answers = useAnswers();
  const [error, setError] = useState<CoachError | null>(null);

  async function download(kind: "pdf" | "docx") {
    setError(null);
    try {
      await downloadAuthenticated(`/api/v1/packages/${packageId}/files/resume.${kind}`, resumeFilename(answers.data?.name, kind));
      void fireCoachEvent("downloaded");
    } catch (e) {
      setError(describeCoachError(e, "jobs"));
    }
  }

  const data = pkg.data;
  if (!data) {
    return (
      <CoachFrame title={RESULT_TITLE} transcript={transcript}>
        {pkg.error ? <CoachErrorNote error={describeCoachError(pkg.error, "jobs")} /> : <p role="status" className="text-sm text-muted-foreground">Opening your resume…</p>}
      </CoachFrame>
    );
  }

  const details = (
    <Link href={`/jobs/${data.job_id}/packages/${data.id}`} className="text-sm text-primary underline underline-offset-4">
      See full details
    </Link>
  );

  if (data.status === "blocked") {
    // Only errors block a package; a warning in the same report did not stop it, so it is not listed.
    const fired = (data.guardrail_report?.violations ?? []).filter((v) => v.severity === "error");
    return (
      <CoachFrame title="Rhapto stopped this draft" transcript={transcript}>
        <p>{fired.every((v) => ADDED_SOMETHING.has(v.rule)) ? HEADLINE_ADDED : HEADLINE_CHECK}</p>
        {fired.length > 0 ? (
          <section aria-labelledby="coach-fired" className="space-y-2">
            <h2 id="coach-fired" className="text-base font-medium">What stopped it</h2>
            <ul aria-labelledby="coach-fired" className="space-y-3">
              {fired.map((v, i) => (
                <li key={`${v.rule}-${v.path}-${i}`} className="text-sm">
                  <p className="font-medium">{RULE_WORDS[v.rule] ?? "A line that didn't pass Rhapto's check"}</p>
                  <p className="text-muted-foreground">
                    Rule <code className="font-mono">{v.rule}</code>: {v.message}
                  </p>
                </li>
              ))}
            </ul>
          </section>
        ) : null}
        <p className="text-sm text-muted-foreground">Nothing was saved for download. You can try again, or pick another job.</p>
        <CoachErrorNote error={retryError} />
        <div className="flex flex-wrap gap-3">
          <Button type="button" className="max-md:min-h-11" disabled={retryBusy} onClick={() => onRetry(data)}>
            Try again (uses another run)
          </Button>
          <Button type="button" variant="outline" className="max-md:min-h-11" onClick={onAnother}>
            Pick another job
          </Button>
        </div>
        <p>{details}</p>
      </CoachFrame>
    );
  }

  const changes = data.edits.slice(0, MAX_CHANGES);
  return (
    <CoachFrame title={RESULT_TITLE} transcript={transcript}>
      <p className="text-sm text-muted-foreground">{RESULT_READY}</p>
      <CoachErrorNote error={error} />
      <div className="flex flex-wrap gap-3">
        {data.has_docx ? <Button type="button" size="lg" onClick={() => void download("docx")}>{DOWNLOAD_DOCX}</Button> : null}
        {data.has_pdf ? <Button type="button" size="lg" variant="outline" onClick={() => void download("pdf")}>{DOWNLOAD_PDF}</Button> : null}
      </div>
      <section aria-labelledby="coach-changes" className="space-y-2">
        <h2 id="coach-changes" className="text-base font-medium">{WHAT_CHANGED}</h2>
        {changes.length > 0 ? (
          <ul className="space-y-3">
            {changes.map((edit) => (
              <li key={edit.paragraph_id} className="text-sm">
                <p className="font-medium">{edit.reason}</p>
                <p className="text-muted-foreground">{edit.after}</p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">Your resume already fit this job, so nothing needed to change.</p>
        )}
      </section>
      <div className="flex flex-wrap items-center gap-4">
        <Button type="button" variant="outline" onClick={onAnother}>
          Done. Try another?
        </Button>
        {details}
      </div>
    </CoachFrame>
  );
}
