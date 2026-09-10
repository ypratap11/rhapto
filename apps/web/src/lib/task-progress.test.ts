import { describe, expect, it } from "vitest";
import { initialProgress, reduceTaskEvent } from "./task-progress";

describe("reduceTaskEvent", () => {
  it("tracks steps then done", () => {
    let s = reduceTaskEvent(initialProgress, { event: "state", data: { status: "running", progress: { step: "extract" } } });
    expect(s).toMatchObject({ status: "running", step: "extract" });
    s = reduceTaskEvent(s, { event: "progress", data: { event: "progress", step: "compose" } });
    expect(s.step).toBe("compose");
    s = reduceTaskEvent(s, { event: "done", data: { event: "done", package_id: "p1", status: "draft" } });
    expect(s).toMatchObject({ status: "succeeded", packageId: "p1", packageStatus: "draft" });
  });

  it("maps a finished state event directly", () => {
    const s = reduceTaskEvent(initialProgress, { event: "state", data: { status: "succeeded", result_ref: "p9", progress: { step: "render" } } });
    expect(s).toMatchObject({ status: "succeeded", packageId: "p9", step: "render" });
    const f = reduceTaskEvent(initialProgress, { event: "state", data: { status: "failed", error: "boom" } });
    expect(f).toMatchObject({ status: "failed", error: "boom" });
  });

  it("maps error events", () => {
    const s = reduceTaskEvent(initialProgress, { event: "error", data: { event: "error", message: "no blocks" } });
    expect(s).toMatchObject({ status: "failed", error: "no blocks" });
  });
});
