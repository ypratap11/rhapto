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
