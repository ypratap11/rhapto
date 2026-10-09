"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMe, useResumeDocument, useTailor, useTask, useTracks, type JobOut, type PackageOut } from "@/lib/api/queries";
import { describeCoachError, type CoachError } from "@/lib/coach/errors";
import { fireCoachEvent } from "@/lib/coach/events";
import { deriveStartStep, jobIdFromTask, parseStepHint } from "@/lib/coach/state";
import { readConfirmedTrack, readProposal, type CachedProposal } from "@/lib/coach/storage";
import { CoachErrorNote, CoachFrame, type TranscriptItem } from "./CoachFrame";
import { MatchesStep } from "./MatchesStep";
import { PasteJob } from "./PasteJob";
import { ResultStep } from "./ResultStep";
import { RoleStep } from "./RoleStep";
import { TailorStep } from "./TailorStep";
import { UploadStep } from "./UploadStep";

type View =
  | { step: 1 }
  | { step: 2; proposal: CachedProposal | null; importError: CoachError | null }
  | { step: 4; trackId: string; roleName: string }
  | { step: 5; taskId: string }
  | { step: 6; packageId: string };

/** The scripted wizard. Where it starts comes from server state (`deriveStartStep`); after that the
 * tester's actions override it. There is no effect that copies server data into state: `view` is the
 * override if there is one, else the derivation, so a reload always lands where the data says. */
export function Coach() {
  const params = useSearchParams();
  const router = useRouter();
  const me = useMe();
  const doc = useResumeDocument();
  const tracks = useTracks();
  const tailor = useTailor();
  const taskParam = params.get("task");
  const reattached = useTask(taskParam);
  const userId = me.data?.user_id ?? null;

  const [override, setOverride] = useState<View | null>(null);
  const [pasting, setPasting] = useState(false);
  const [error, setError] = useState<CoachError | null>(null);
  const [retryBusy, setRetryBusy] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [filename, setFilename] = useState<string | null>(null);

  const started = useRef(false);
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void fireCoachEvent("started");
  }, []);

  const ready = userId !== null && doc.isFetched && tracks.isFetched;
  const initial = useMemo<View | null>(() => {
    if (!ready || userId === null) return null;
    const trackList = tracks.data ?? [];
    const start = deriveStartStep(
      { taskId: taskParam, hasDocument: doc.data != null, trackIds: trackList.map((t) => t.id), confirmedTrackId: readConfirmedTrack(userId) },
      parseStepHint(params.get("step")),
    );
    const name = (id: string | null) => trackList.find((t) => t.id === id)?.name ?? "your role";
    if (start.step === 5 && taskParam) return { step: 5, taskId: taskParam };
    if (start.step >= 3 && start.trackId) return { step: 4, trackId: start.trackId, roleName: name(start.trackId) };
    // Step 2, or step 3/4 with no track to show (a `?task=` in the URL lifts the cap, so a `?step=` hint
    // can ask for the matches when there are no tracks): the role step, which can make one.
    if (start.step >= 2 && doc.data != null) return { step: 2, proposal: readProposal(userId), importError: null };
    return { step: 1 };
  }, [ready, userId, tracks.data, doc.data, taskParam, params]);

  const view = override ?? initial;
  const currentJobId = jobId ?? jobIdFromTask(reattached.data);

  const transcript = useMemo<TranscriptItem[]>(() => {
    const items: TranscriptItem[] = [];
    const file = filename ?? doc.data?.filename ?? null;
    if (view && view.step !== 1 && file) items.push({ label: "Resume", value: file });
    if (view && (view.step === 4 || view.step === 5 || view.step === 6)) {
      const roleId = userId ? readConfirmedTrack(userId) : null;
      const list = tracks.data ?? [];
      const role = view.step === 4 ? view.roleName : (list.find((t) => t.id === roleId) ?? list[0])?.name;
      if (role) items.push({ label: "Aiming for", value: role });
    }
    return items;
  }, [view, filename, doc.data, tracks.data, userId]);

  const startTailor = useCallback(
    async (id: string) => {
      setError(null);
      setJobId(id);
      try {
        const task = await tailor.mutateAsync({ jobId: id, body: { mode: "tune" } });
        void fireCoachEvent("tailor_started");
        router.replace(`/start?task=${task.id}`);
        setPasting(false);
        setOverride({ step: 5, taskId: task.id });
      } catch (e) {
        setError(describeCoachError(e, "tailor")); // resolves: the step's double-tap guard needs it to
      }
    },
    [tailor, router],
  );

  const backToMatches = useCallback(() => {
    router.replace("/start");
    setError(null);
    const list = tracks.data ?? [];
    const id = (userId && readConfirmedTrack(userId) && list.some((t) => t.id === readConfirmedTrack(userId)) ? readConfirmedTrack(userId) : list[0]?.id) ?? null;
    if (id) setOverride({ step: 4, trackId: id, roleName: list.find((t) => t.id === id)?.name ?? "your role" });
    else setOverride({ step: 2, proposal: null, importError: null });
  }, [router, tracks.data, userId]);

  const onTaskDone = useCallback((packageId: string) => setOverride({ step: 6, packageId }), []);

  // A second guard behind TailorStep's: whatever calls this, one retry at a time claims a run.
  const retrying = useRef(false);
  const retryRun = useCallback(async () => {
    if (retrying.current) return;
    retrying.current = true;
    try {
      if (currentJobId) await startTailor(currentJobId);
      else backToMatches();
    } finally {
      retrying.current = false;
    }
  }, [currentJobId, startTailor, backToMatches]);

  const retryBlocked = useCallback(
    async (pkg: PackageOut) => {
      setRetryBusy(true);
      try {
        // Owner decision 2026-10-09: never pass the blocked package as parent; the worker would feed
        // its edits (including the one that invented the number) back to the model.
        await startTailor(pkg.job_id);
      } finally {
        setRetryBusy(false);
      }
    },
    [startTailor],
  );

  if (userId === null && me.error) {
    // TokenGate handles 401/403 before this mounts; this is a 5xx or a dropped connection.
    return (
      <CoachFrame title="Rhapto can't start right now">
        <CoachErrorNote error={describeCoachError(me.error, "jobs")} />
      </CoachFrame>
    );
  }
  if (!view || userId === null) {
    return (
      <CoachFrame title="Tailor a resume">
        <p role="status" className="text-sm text-muted-foreground">Getting things ready…</p>
      </CoachFrame>
    );
  }

  if (pasting) {
    return <PasteJob transcript={transcript} error={error} onJob={(id) => startTailor(id)} onCancel={() => setPasting(false)} />;
  }

  switch (view.step) {
    case 1:
      return (
        <UploadStep
          userId={userId}
          existingDocumentName={doc.data?.filename ?? null}
          onDone={({ filename: name, proposal, importError }) => {
            setFilename(name);
            setOverride({ step: 2, proposal, importError });
          }}
        />
      );
    case 2:
      return (
        <RoleStep
          userId={userId}
          proposal={view.proposal}
          importError={view.importError}
          transcript={transcript}
          onPaste={() => setPasting(true)}
          onConfirmed={(role) => setOverride({ step: 4, trackId: role.id, roleName: role.name })}
        />
      );
    case 4:
      return (
        <MatchesStep
          key={view.trackId}
          trackId={view.trackId}
          roleName={view.roleName}
          transcript={transcript}
          error={error}
          onPaste={() => setPasting(true)}
          onTailor={(job: JobOut) => startTailor(job.id)}
        />
      );
    case 5:
      return <TailorStep key={view.taskId} taskId={view.taskId} transcript={transcript} onDone={onTaskDone} onRetry={retryRun} onPickAnother={backToMatches} />;
    case 6:
      return <ResultStep packageId={view.packageId} transcript={transcript} retryBusy={retryBusy} onRetry={(pkg) => void retryBlocked(pkg)} onAnother={backToMatches} />;
  }
}
