import { apiClient, unwrap } from "./api/client";
import type { TaskEvent } from "./api/sse";

export const PIPELINE_STEPS = ["extract", "select", "compose", "validate", "repair", "render"] as const;

export type ProgressState = {
  status: "idle" | "running" | "succeeded" | "failed";
  step: string | null;
  packageId: string | null;
  packageStatus: string | null;
  error: string | null;
};

export const initialProgress: ProgressState = { status: "idle", step: null, packageId: null, packageStatus: null, error: null };

function str(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

export function reduceTaskEvent(state: ProgressState, event: TaskEvent): ProgressState {
  const d = event.data;
  switch (event.event) {
    case "state": {
      const progress = (d.progress ?? {}) as Record<string, unknown>;
      const status = str(d.status);
      const step = str(progress.step) ?? state.step;
      if (status === "succeeded") return { status: "succeeded", step, packageId: str(d.result_ref), packageStatus: state.packageStatus, error: null };
      if (status === "failed") return { status: "failed", step, packageId: null, packageStatus: null, error: str(d.error) ?? "task failed" };
      return { ...state, status: "running", step };
    }
    case "progress":
      return { ...state, status: "running", step: str(d.step) ?? state.step };
    case "done":
      return { status: "succeeded", step: "render", packageId: str(d.package_id), packageStatus: str(d.status), error: null };
    case "error":
      return { status: "failed", step: state.step, packageId: null, packageStatus: null, error: str(d.message) ?? "task failed" };
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
