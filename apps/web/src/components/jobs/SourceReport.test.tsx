import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SourceReport } from "./SourceReport";
import type { PerSource } from "@/lib/api/portal";

const base = { error: null, failed_boards: [], quota: null, state: "ok" as const };

function line(perSource: PerSource): string {
  const { container } = render(<SourceReport perSource={perSource} />);
  return container.textContent ?? "";
}

describe("SourceReport", () => {
  it("renders nothing without sources", () => {
    const { container } = render(<SourceReport perSource={{}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("ok: found and new counts", () => {
    expect(line({ greenhouse: { ...base, found: 182, new: 4 } })).toBe("Greenhouse 182 found · 4 new");
  });

  it("ok with quota: remaining requests are shown", () => {
    const text = line({
      jsearch: { ...base, found: 10, new: 4, quota: { limit: 200, remaining: 187, reset_at: null } },
    });
    expect(text).toBe("JSearch 10 found · 4 new · 187 of 200 requests left");
  });

  it("ok with a quota that lacks numbers adds nothing", () => {
    const text = line({ jsearch: { ...base, found: 1, new: 1, quota: { limit: null, remaining: null, reset_at: null } } });
    expect(text).toBe("JSearch 1 found · 1 new");
  });

  it("partial with one failed board", () => {
    const text = line({
      greenhouse: {
        ...base,
        state: "partial",
        found: 182,
        new: 4,
        failed_boards: [{ name: "coreweave", kind: "failed", message: "timed out after 30s" }],
      },
    });
    expect(text).toBe("Greenhouse 182 found · 4 new (1 board failed: coreweave timed out after 30s)");
  });

  it("partial with two failed boards", () => {
    const text = line({
      greenhouse: {
        ...base,
        state: "partial",
        found: 10,
        new: 2,
        failed_boards: [
          { name: "coreweave", kind: "failed", message: "timed out after 30s" },
          { name: "acme", kind: "failed", message: "returned HTTP 500" },
        ],
      },
    });
    expect(text).toBe("Greenhouse 10 found · 2 new (2 boards failed: coreweave timed out after 30s; acme returned HTTP 500)");
  });

  it("failed: label and error", () => {
    expect(line({ jooble: { ...base, state: "failed", found: 0, new: 0, error: "boom" } })).toBe("Jooble failed (boom)");
  });

  it("an old payload (error, no state) still reads as failed", () => {
    const old = { found: 0, new: 0, error: "boom" } as unknown as PerSource[string];
    expect(line({ jooble: old })).toBe("Jooble failed (boom)");
  });

  it("rate_limited: label prefix, never failed or API key", () => {
    const text = line({ adzuna: { ...base, state: "rate_limited", found: 0, new: 0, error: "rate-limited (quota used up, try again later)" } });
    expect(text).toBe("Adzuna rate-limited (quota used up, try again later)");
    expect(text).not.toMatch(/failed|API key/i);
  });

  it("unavailable: the vendor-blocked wording after the label", () => {
    const text = line({
      themuse: { ...base, state: "unavailable", found: 0, new: 0, error: "blocked by the vendor (bot protection), not available right now" },
    });
    expect(text).toBe("The Muse: blocked by the vendor (bot protection), not available right now");
    expect(text).not.toMatch(/HTTP 404/);
  });

  it("quota_exhausted: reset time in the user's locale", () => {
    const reset = "2026-12-01T00:00:00Z";
    const expected = new Date(reset).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
    const text = line({
      jsearch: {
        ...base,
        state: "quota_exhausted",
        found: 0,
        new: 0,
        error: "quota used up until 2026-12-01T00:00:00+00:00",
        quota: { limit: 200, remaining: 0, reset_at: reset },
      },
    });
    expect(text).toBe(`JSearch quota used up until ${expected}`);
    expect(text).not.toContain("+00:00");
  });

  it("quota_exhausted without a reset time falls back to the rate-limited wording", () => {
    const text = line({
      jsearch: { ...base, state: "quota_exhausted", found: 0, new: 0, error: "x", quota: { limit: 200, remaining: 0, reset_at: null } },
    });
    expect(text).toBe("JSearch rate-limited (quota used up, try again later)");
  });

  it("joins sources with a middle dot", () => {
    render(
      <SourceReport
        perSource={{
          greenhouse: { ...base, found: 3, new: 1 },
          jooble: { ...base, state: "failed", found: 0, new: 0, error: "boom" },
        }}
      />,
    );
    expect(screen.getByText("Greenhouse 3 found · 1 new · Jooble failed (boom)")).toBeInTheDocument();
  });
});
