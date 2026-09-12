import { describe, expect, it } from "vitest";
import { initialProgress, pipelineSteps, reduceTaskEvent } from "./task-progress";

describe("reduceTaskEvent", () => {
  it("tracks steps then done", () => {
    let s = reduceTaskEvent(initialProgress, { event: "state", data: { status: "running", progress: { step: "extract" } } });
    expect(s).toMatchObject({ status: "running", step: "extract" });
    s = reduceTaskEvent(s, { event: "progress", data: { event: "progress", step: "compose" } });
    expect(s.step).toBe("compose");
    s = reduceTaskEvent(s, { event: "done", data: { event: "done", package_id: "p1", status: "draft" } });
    expect(s).toMatchObject({ status: "succeeded", packageId: "p1", packageStatus: "draft" });
  });

  it("follows a tune run's step sequence even though it skips select and compose", () => {
    let s = reduceTaskEvent(initialProgress, { event: "state", data: { status: "running", progress: { step: "extract" } } });
    for (const step of ["tune", "validate", "render"]) {
      s = reduceTaskEvent(s, { event: "progress", data: { event: "progress", step } });
      expect(s).toMatchObject({ status: "running", step });
    }
    s = reduceTaskEvent(s, { event: "done", data: { event: "done", package_id: "p2", status: "draft" } });
    expect(s).toMatchObject({ status: "succeeded", packageId: "p2" });
  });

  it("maps a finished state event directly", () => {
    const s = reduceTaskEvent(initialProgress, { event: "state", data: { status: "succeeded", result_ref: "p9", progress: { step: "render" } } });
    expect(s).toMatchObject({ status: "succeeded", packageId: "p9", step: "render" });
    const f = reduceTaskEvent(initialProgress, { event: "state", data: { status: "failed", error: "boom" } });
    expect(f).toMatchObject({ status: "failed", error: "boom" });
  });

  it("reads the new-job count from a finished poll's state-replay result_ref", () => {
    const s = reduceTaskEvent(initialProgress, { event: "state", data: { status: "succeeded", result_ref: "new:3", progress: {} } });
    expect(s).toMatchObject({ status: "succeeded", packageId: null, newJobs: 3 });
  });

  it("reads the run's mode off the state event and keeps it across later events", () => {
    let s = reduceTaskEvent(initialProgress, { event: "state", data: { status: "running", progress: { step: "extract", request: { mode: "tune" } } } });
    expect(s.mode).toBe("tune");
    s = reduceTaskEvent(s, { event: "progress", data: { event: "progress", step: "tune" } });
    expect(s.mode).toBe("tune");
    s = reduceTaskEvent(s, { event: "done", data: { event: "done", package_id: "p1", status: "draft" } });
    expect(s.mode).toBe("tune");
    // A task row with no stored mode leaves it unknown rather than guessing.
    expect(reduceTaskEvent(initialProgress, { event: "state", data: { status: "running", progress: { step: "extract" } } }).mode).toBeNull();
  });

  it("shows each mode only the steps it runs, and the blocks pipeline when the mode is unknown", () => {
    expect(pipelineSteps("blocks")).toEqual(["extract", "select", "compose", "validate", "repair", "render"]);
    expect(pipelineSteps("tune")).toEqual(["extract", "tune", "validate", "repair", "render"]);
    expect(pipelineSteps(null)).toEqual(pipelineSteps("blocks"));
  });

  it("maps error events", () => {
    const s = reduceTaskEvent(initialProgress, { event: "error", data: { event: "error", message: "no blocks" } });
    expect(s).toMatchObject({ status: "failed", error: "no blocks" });
  });
});
