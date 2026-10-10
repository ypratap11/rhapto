"use client";

import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { useImportResume, useUploadResumeDocument } from "@/lib/api/queries";
import { CHOOSE_FILE, UPLOAD_HINT, UPLOAD_TITLE } from "@/lib/coach/copy";
import { checkResumeFile, describeCoachError, type CoachError } from "@/lib/coach/errors";
import { fireCoachEvent } from "@/lib/coach/events";
import { writeProposal, type CachedProposal } from "@/lib/coach/storage";
import { CoachErrorNote, CoachFrame } from "./CoachFrame";

export type UploadDone = { filename: string; proposal: CachedProposal | null; importError: CoachError | null };

export function UploadStep({
  userId,
  existingDocumentName,
  onDone,
}: {
  userId: string;
  existingDocumentName: string | null;
  onDone: (result: UploadDone) => void;
}) {
  const upload = useUploadResumeDocument();
  const importResume = useImportResume();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<CoachError | null>(null);
  const input = useRef<HTMLInputElement>(null);
  // State lags a fast second event; a ref does not. Together with `disabled` this makes a double
  // click or a second tab-key press unable to start a second paid import.
  const inFlight = useRef(false);

  async function handleFile(file: File) {
    if (inFlight.current) return;
    const bad = checkResumeFile(file);
    if (bad) {
      setError(bad);
      return;
    }
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      // Document first: free, and the same checks as the import would make. If it fails, nothing
      // has been spent and we stop. If the import fails afterwards, the document is stored, so the
      // tester can still paste a job and tune it.
      try {
        await upload.mutateAsync(file);
      } catch (e) {
        setError(describeCoachError(e, "upload"));
        return;
      }
      void fireCoachEvent("resume_in");
      let proposal: CachedProposal | null = null;
      let importError: CoachError | null = null;
      try {
        const out = await importResume.mutateAsync(file);
        proposal = { tracks: out.tracks, location: out.location };
        writeProposal(userId, proposal); // a reload before step 2 must not import (and pay) again
      } catch (e) {
        importError = describeCoachError(e, "import");
      }
      onDone({ filename: file.name, proposal, importError });
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  return (
    <CoachFrame title={UPLOAD_TITLE} hint={UPLOAD_HINT}>
      {existingDocumentName ? (
        <p className="text-sm text-muted-foreground">
          You already have <span className="text-foreground">{existingDocumentName}</span> on file. Uploading a new one replaces it.
        </p>
      ) : null}
      <CoachErrorNote error={error} />
      <input
        ref={input}
        type="file"
        accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        aria-label="Choose your resume (.docx)"
        className="sr-only"
        disabled={busy}
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = ""; // picking the same file again must fire a change
          if (file) void handleFile(file);
        }}
      />
      <Button type="button" size="lg" disabled={busy} onClick={() => input.current?.click()}>
        {CHOOSE_FILE}
      </Button>
      {busy ? (
        <p role="status" className="text-sm text-muted-foreground">
          Reading your resume&hellip; this takes a few seconds.
        </p>
      ) : null}
    </CoachFrame>
  );
}
