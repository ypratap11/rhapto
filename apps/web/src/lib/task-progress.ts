import { apiClient, unwrap } from "./api/client";
import type { TaskEvent } from "./api/sse";

// The engine's step order. Tune mode skips `select` and `compose` (it rewrites the uploaded
// document instead of composing from blocks) and blocks mode skips `tune`, so a run reports a
// subset of these: steps are matched by name, never by position.
export const PIPELINE_STEPS = ["extract", "select", "compose", "tune", "validate", "repair", "render"] as const;
const BLOCKS_STEPS = PIPELINE_STEPS.filter((step) => step !== "tune");
const TUNE_STEPS = PIPELINE_STEPS.filter((step) => step !== "select" && step !== "compose");
export const POLL_STEPS = ["fetch", "dedupe", "score", "done"] as const;

/**
 * The steps a run of this mode can actually report. The pills mark everything before the active
 * step as done, so listing a step the mode never runs claims work that never happened -- a tune
 * run showing green `select`/`compose`, or a blocks run showing a green `tune`. An unknown mode
 * (no `state` event seen yet, or an older task row) falls back to the blocks pipeline.
 */
export function pipelineSteps(mode: string | null): readonly string[] {
  return mode === "tune" ? TUNE_STEPS : BLOCKS_STEPS;
}

export type ProgressState = {
  status: "idle" | "running" | "succeeded" | "failed";
  step: string | null;
  packageId: string | null;
  packageStatus: string | null;
  error: string | null;
  newJobs: number | null;
  /** The tailoring mode of the run, from the task row's stored request. Null until a `state` event. */
  mode: string | null;
};

export const initialProgress: ProgressState = { status: "idle", step: null, packageId: null, packageStatus: null, error: null, newJobs: null, mode: null };

function str(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function num(value: unknown): number | null {
  return typeof value === "number" ? value : null;
}

const NEW_JOBS_RESULT_REF = /^new:(\d+)$/;

export function reduceTaskEvent(state: ProgressState, event: TaskEvent): ProgressState {
  const d = event.data;
  switch (event.event) {
    case "state": {
      const progress = (d.progress ?? {}) as Record<string, unknown>;
      const status = str(d.status);
      const step = str(progress.step) ?? state.step;
      // The worker stores the tailoring request on the task row, so the mode the run was started
      // with rides along on every `state` event; the other event kinds carry the step only.
      const request = (progress.request ?? {}) as Record<string, unknown>;
      const mode = str(request.mode) ?? state.mode;
      if (status === "succeeded") {
        const resultRef = str(d.result_ref);
        // A finished poll task's `result_ref` is the worker-set string `new:<n>`
        // (not a package id) — a replayed "state" event, sent when the SSE request
        // lands after the task already finished, is the only source for that count,
        // since there's no separate "done" event to carry it in that case.
        const newMatch = resultRef ? NEW_JOBS_RESULT_REF.exec(resultRef) : null;
        if (newMatch) return { status: "succeeded", step, packageId: null, packageStatus: state.packageStatus, error: null, newJobs: Number(newMatch[1]), mode };
        return { status: "succeeded", step, packageId: resultRef, packageStatus: state.packageStatus, error: null, newJobs: state.newJobs, mode };
      }
      if (status === "failed") return { status: "failed", step, packageId: null, packageStatus: null, error: str(d.error) ?? "task failed", newJobs: null, mode };
      return { ...state, status: "running", step, mode };
    }
    case "progress":
      return { ...state, status: "running", step: str(d.step) ?? state.step };
    case "done":
      // The poll task's "done" event has no package_id (str() returns null for the
      // missing field), so this same branch naturally covers both the tailor and
      // poll pipelines: the former resolves a package, the latter a new-jobs count.
      return { ...state, status: "succeeded", step: "render", packageId: str(d.package_id), packageStatus: str(d.status), error: null, newJobs: num(d.new_jobs) };
    case "error":
      return { ...state, status: "failed", step: state.step, packageId: null, packageStatus: null, error: str(d.message) ?? "task failed", newJobs: null };
    default:
      return state;
  }
}

/**
 * The "state" SSE event (sent when a task is already finished by the time the
 * request lands) carries a `TaskOut`, which has no package status — only
 * `packageStatus: state.packageStatus` from before, i.e. `null`. Resolve the
 * real status by fetching the package directly so a blocked package is never
 * reported as ready. Returns `null` (not "unknown") when the fetch itself
 * fails, so the caller can fall back to neutral copy.
 */
export async function resolvePackageStatus(packageId: string): Promise<string | null> {
  try {
    const pkg = await unwrap(apiClient().GET("/api/v1/packages/{package_id}", { params: { path: { package_id: packageId } } }));
    return pkg.status;
  } catch {
    return null;
  }
}
