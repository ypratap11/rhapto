import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import contract from "./contract.json";
import { ADMIN_ROUTES } from "./queries";

const key = (r: { method: string; path: string }) => `${r.method} ${r.path}`;

describe("admin routes", () => {
  it("admin routes in queries.ts equal the routes in contract.json", () => {
    const ours = Object.values(ADMIN_ROUTES).map(key).sort();
    const theirs = contract.routes.map(key).sort();
    expect(theirs.length).toBeGreaterThan(5);
    expect(ours).toEqual(theirs);
  });
  it("queries.ts writes /admin/ only inside ADMIN_ROUTES", () => {
    const src = readFileSync(join(__dirname, "queries.ts"), "utf8");
    const start = src.indexOf("export const ADMIN_ROUTES");
    const end = src.indexOf("} as const", start);
    expect(start).toBeGreaterThanOrEqual(0);
    expect(end).toBeGreaterThan(start);
    const outside = src.slice(0, start) + src.slice(end);
    expect(outside).not.toContain("/admin/");
  });
});
