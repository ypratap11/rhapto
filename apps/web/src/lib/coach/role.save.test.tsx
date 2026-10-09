import { renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useSaveCoachRole, type RoleSource } from "./role";

const calls: string[] = [];
const loaded = { answers: { name: "Maya Chen" } as Record<string, string> | undefined, bases: [{ id: "executive" }] as { id: string }[] | undefined };
vi.mock("@/lib/api/queries", () => ({
  useAnswers: () => ({ data: loaded.answers }),
  useBases: () => ({ data: loaded.bases }),
  useTracks: () => existingTracks,
  usePutTrack: () => ({ isPending: false, mutateAsync: vi.fn(async (t: { id: string }) => { calls.push(`track:${t.id}`); }) }),
  usePutAnswers: () => ({ isPending: false, mutateAsync: vi.fn(async (a: Record<string, string>) => { calls.push(`answers:${Object.keys(a).sort().join(",")}`); }) }),
}));

const proposed: RoleSource = { kind: "proposed", track: { id: "tpm", name: "TPM", field: "f", role: "r", keywords: [] } };
const existingTracks: { data: { id: string; name: string; min_fit: number }[] | undefined } = { data: [] };

beforeEach(() => {
  calls.length = 0;
  loaded.answers = { name: "Maya Chen" };
  loaded.bases = [{ id: "executive" }];
  existingTracks.data = [];
});

describe("useSaveCoachRole", () => {
  it("writes the answers first, then the one track, and nothing else (no blocks)", async () => {
    const { result } = renderHook(() => useSaveCoachRole());
    expect(result.current.ready).toBe(true);
    const track = await result.current.save(proposed, { location_home: "Denver, CO", location_preferred: [], remote_ok: null });
    expect(calls).toEqual(["answers:location_home,name", "track:tpm"]);
    expect(track).toMatchObject({ id: "tpm", resume_base: "executive", min_fit: 60 });
  });

  it("does not overwrite a track the tester already has under that id (their keywords, min_fit and base survive)", async () => {
    existingTracks.data = [{ id: "tpm", name: "My TPM", min_fit: 72 }];
    const { result } = renderHook(() => useSaveCoachRole());
    const track = await result.current.save(proposed, { location_home: "Denver, CO", location_preferred: [], remote_ok: null });
    expect(calls).toEqual(["answers:location_home,name"]); // the answers still merge; no track PUT
    expect(track).toMatchObject({ id: "tpm", name: "My TPM", min_fit: 72 });
  });

  it("refuses to save until the existing tracks have loaded, so it cannot clobber one it has not seen", async () => {
    existingTracks.data = undefined;
    const { result } = renderHook(() => useSaveCoachRole());
    expect(result.current.ready).toBe(false);
    await expect(result.current.save(proposed, null)).rejects.toThrow("profile not loaded yet");
    expect(calls).toEqual([]);
  });

  it("skips the answers write when the import found no location", async () => {
    const { result } = renderHook(() => useSaveCoachRole());
    await result.current.save(proposed, null);
    expect(calls).toEqual(["track:tpm"]);
  });

  it("refuses to save, and writes nothing, before answers and bases have loaded", async () => {
    loaded.answers = undefined;
    const { result } = renderHook(() => useSaveCoachRole());
    expect(result.current.ready).toBe(false);
    await expect(result.current.save(proposed, null)).rejects.toThrow("profile not loaded yet");
    expect(calls).toEqual([]);
  });
});
