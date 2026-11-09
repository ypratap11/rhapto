import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import contract from "./contract.json";
import type { FailureOut, UserRowOut } from "./types";

type Models = Record<string, { properties?: Record<string, unknown>; $defs?: Record<string, { enum?: string[] }> }>;
const source = readFileSync(join(__dirname, "types.ts"), "utf8");

/** Every `Model.property` in the contract that the TypeScript source does not declare. */
function missing(models: Models, src: string): string[] {
  const out: string[] = [];
  for (const [model, def] of Object.entries(models)) {
    for (const prop of Object.keys(def.properties ?? {})) {
      if (!new RegExp(`\\b${prop}\\??:`).test(src)) out.push(`${model}.${prop}`);
    }
  }
  return out;
}

describe("admin types mirror the contract", () => {
  it("declares every property of every model", () => {
    expect(Object.keys(contract.models).length).toBeGreaterThan(5);
    expect(missing(contract.models as Models, source)).toEqual([]);
  });
  it("fails when the API adds a field the web type lacks", () => {
    const grown = structuredClone(contract.models) as Models;
    grown.UserRowOut!.properties!.brand_new_field = { type: "string" };
    expect(missing(grown, source)).toEqual(["UserRowOut.brand_new_field"]);
  });
  it("declares every failure category", () => {
    const cats = (contract.models as Models).FailureOut!.$defs!.FailureCategory!.enum!;
    expect(cats).toContain("did_not_finish");
    for (const c of cats) expect(source).toContain(`"${c}"`);
  });
  it("rejects a row missing a required field and an unknown category at compile time", () => {
    // @ts-expect-error failed_count is required
    const bad: UserRowOut = { id: "u", email: "e", runs_used: 0, runs_limit: null, last_seen_at: "t", blocked: false };
    // @ts-expect-error not a category
    const worse: FailureOut["category"] = "not_a_category";
    expect([bad, worse]).toHaveLength(2);
  });
});
