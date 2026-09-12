import { afterEach, describe, expect, it, vi } from "vitest";
import { readSkipped, skipJob, unskipAll } from "./skipped";

afterEach(() => {
  window.localStorage.clear();
  vi.restoreAllMocks();
});

describe("skipped", () => {
  it("skips a job and reads it back", () => {
    skipJob("a");
    expect(readSkipped()).toEqual(["a"]);
  });

  it("does not duplicate a job skipped twice", () => {
    skipJob("a");
    skipJob("a");
    expect(readSkipped()).toEqual(["a"]);
  });

  it("empties the list on unskipAll", () => {
    skipJob("a");
    skipJob("b");
    unskipAll();
    expect(readSkipped()).toEqual([]);
  });

  it("returns an empty list when localStorage throws", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(readSkipped()).toEqual([]);
  });
});
