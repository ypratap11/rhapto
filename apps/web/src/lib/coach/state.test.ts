import { describe, expect, it } from "vitest";
import { deriveStartStep, jobIdFromTask, parseStepHint, type ServerState } from "./state";

const base: ServerState = { taskId: null, hasDocument: false, trackIds: [], confirmedTrackId: null };

describe("deriveStartStep (server state wins)", () => {
  it.each<[string, Partial<ServerState>, number, string | null]>([
    ["running task in the URL -> re-attach", { taskId: "t1", hasDocument: true, trackIds: ["a"] }, 5, "a"],
    ["document and a track -> the matches", { hasDocument: true, trackIds: ["a", "b"] }, 4, "a"],
    ["document and several tracks -> the coach's last confirmed one", { hasDocument: true, trackIds: ["a", "b"], confirmedTrackId: "b" }, 4, "b"],
    ["a confirmed track that no longer exists falls back to tracks[0]", { hasDocument: true, trackIds: ["a"], confirmedTrackId: "gone" }, 4, "a"],
    ["document, no track -> the role step", { hasDocument: true }, 2, null],
    ["no document -> upload", {}, 1, null],
    ["no document but tracks (a returning tester) -> upload", { trackIds: ["a"], confirmedTrackId: "a" }, 1, null],
  ])("%s", (_name, partial, step, trackId) => {
    expect(deriveStartStep({ ...base, ...partial })).toEqual({ step, trackId });
  });

  it("a task in the URL wins even with no document in server state", () => {
    expect(deriveStartStep({ ...base, taskId: "t1" }).step).toBe(5);
  });

  it("the URL step is only a hint, capped at the furthest step server state allows", () => {
    const withTrack = { ...base, hasDocument: true, trackIds: ["a"] };
    expect(deriveStartStep(base, 4).step).toBe(1); // asks for 4, nothing stored
    expect(deriveStartStep({ ...base, hasDocument: true }, 4).step).toBe(2);
    expect(deriveStartStep(withTrack, 5).step).toBe(4); // 5 needs a task
    expect(deriveStartStep(withTrack, 3).step).toBe(3);
    expect(deriveStartStep(withTrack, 2)).toEqual({ step: 2, trackId: "a" });
    expect(deriveStartStep(withTrack, 1).step).toBe(1);
  });
});

describe("parseStepHint", () => {
  it.each([["3", 3], ["1", 1], ["5", 5], ["0", null], ["6", null], ["x", null], ["2.5", null], [null, null]])("%s -> %s", (raw, expected) => {
    expect(parseStepHint(raw)).toBe(expected);
  });
});

describe("jobIdFromTask", () => {
  it("reads the job a tailor task was started for", () => {
    expect(jobIdFromTask({ progress: { request: { job_id: "j9" } } })).toBe("j9");
  });
  it("is null for anything else", () => {
    expect(jobIdFromTask(undefined)).toBeNull();
    expect(jobIdFromTask({ progress: {} })).toBeNull();
    expect(jobIdFromTask({ progress: { request: { job_id: 7 } } })).toBeNull();
  });
});
