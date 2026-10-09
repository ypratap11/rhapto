import { afterEach, describe, expect, it, vi } from "vitest";
import { clearProposal, readConfirmedTrack, readProposal, writeConfirmedTrack, writeProposal } from "./storage";

const proposal = {
  tracks: [{ id: "technical-program-manager", name: "Technical Program Manager", field: "program-project-management", role: "technical-program-manager", keywords: [] }],
  location: { location_home: "Denver, CO", location_preferred: [], remote_ok: null },
};

afterEach(() => {
  window.sessionStorage.clear();
  window.localStorage.clear();
  vi.restoreAllMocks();
});

describe("coach storage", () => {
  it("round-trips the proposal per user, in sessionStorage", () => {
    writeProposal("u1", proposal);
    expect(readProposal("u1")).toEqual(proposal);
    expect(readProposal("u2")).toBeNull();
    expect(window.localStorage.length).toBe(0);
    clearProposal("u1");
    expect(readProposal("u1")).toBeNull();
  });

  it("stores no resume text: only tracks and location", () => {
    writeProposal("u1", { ...proposal, blocks: [{ content: "SECRET" }] } as never);
    const raw = window.sessionStorage.getItem(window.sessionStorage.key(0)!)!;
    expect(raw).not.toContain("SECRET");
  });

  it("round-trips the confirmed track per user, in localStorage", () => {
    writeConfirmedTrack("u1", "data-pm");
    expect(readConfirmedTrack("u1")).toBe("data-pm");
    expect(readConfirmedTrack("u2")).toBeNull();
  });

  it("treats corrupt or blocked storage as empty instead of throwing", () => {
    window.sessionStorage.setItem("rhapto.coach.proposal.u1", "{not json");
    expect(readProposal("u1")).toBeNull();
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(readProposal("u1")).toBeNull();
    expect(readConfirmedTrack("u1")).toBeNull();
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(() => writeProposal("u1", proposal)).not.toThrow();
    expect(() => writeConfirmedTrack("u1", "x")).not.toThrow();
  });
});
