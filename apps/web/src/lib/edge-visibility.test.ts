import { readdirSync, existsSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import visibility from "./edge-visibility.json";

/**
 * Cloudflare Access protects this app by listing path prefixes, not by claiming the whole hostname —
 * that inversion is what allows `/` to be public at all (docs/runbook-public-landing.md). The cost of
 * it is that **a route nobody listed is public by default**, and nothing about adding a page would
 * otherwise say so. A reviewer can't catch it either: the mistake is an absence, in a different
 * system, in a dashboard.
 *
 * So this test derives the route list from the filesystem and fails when a route is in neither list.
 * It cannot verify Cloudflare itself — `scripts/check-access-boundary.sh` does that against the live
 * site — but it does guarantee that the omission is impossible to make quietly.
 */

const APP_DIR = join(import.meta.dirname, "..", "app");

/** Top-level URL segments that App Router actually serves, read from the filesystem. */
function topLevelRoutes(): string[] {
  const found = new Set<string>();
  if (existsSync(join(APP_DIR, "page.tsx"))) found.add("/");

  for (const entry of readdirSync(APP_DIR, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue;
    // Route groups `(name)` do not appear in the URL, and private folders `_name` are not routed.
    if (entry.name.startsWith("(") || entry.name.startsWith("_")) continue;
    // A directory is a route only if it, or something beneath it, serves a page or a route handler.
    if (servesSomething(join(APP_DIR, entry.name))) found.add(`/${entry.name}`);
  }
  return [...found].sort();
}

function servesSomething(dir: string): boolean {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.isFile() && /^(page|route)\.(tsx?|jsx?)$/.test(entry.name)) return true;
    if (entry.isDirectory() && servesSomething(join(dir, entry.name))) return true;
  }
  return false;
}

describe("edge visibility", () => {
  const routes = topLevelRoutes();
  const publicAtEdge = new Set(visibility.publicAtEdge);
  const protectedAtEdge = new Set(visibility.protectedAtEdge);

  it("finds the routes this app actually serves", () => {
    // A guard on the guard: if the derivation silently returned nothing, every assertion below would
    // pass vacuously and this file would be decoration.
    expect(routes.length).toBeGreaterThan(5);
    expect(routes).toContain("/");
    expect(routes).toContain("/dashboard");
  });

  it("classifies every route as public or protected at the edge", () => {
    const unclassified = routes.filter((r) => !publicAtEdge.has(r) && !protectedAtEdge.has(r));
    expect(
      unclassified,
      `These routes are in neither list in edge-visibility.json, which means Cloudflare Access is ` +
        `NOT protecting them and they are reachable by anyone: ${unclassified.join(", ")}. ` +
        `Add each to protectedAtEdge, and add rhapto.augaster.com<route> to the destinations of the ` +
        `Cloudflare application holding the Email Policy. Then run scripts/check-access-boundary.sh.`,
    ).toEqual([]);
  });

  it("never lists a route as both public and protected", () => {
    const both = [...publicAtEdge].filter((r) => protectedAtEdge.has(r));
    expect(both, `listed as both public and protected: ${both.join(", ")}`).toEqual([]);
  });

  it("does not claim to protect a route that no longer exists", () => {
    // A stale entry is harmless at the edge but misleads the next person reading the list, and makes
    // the Cloudflare destinations and this file drift apart.
    const stale = [...protectedAtEdge, ...publicAtEdge].filter((r) => !routes.includes(r));
    expect(stale, `declared but not served by the app: ${stale.join(", ")}`).toEqual([]);
  });

  it("keeps /settings protected at the edge even though TokenGate treats it as public", () => {
    // The two senses of "public" are different and conflating them was a review finding. /settings is
    // reachable in-app without a session so a self-hoster can enter their API details; it must never
    // be reachable from the internet without one.
    expect(protectedAtEdge.has("/settings")).toBe(true);
    expect(publicAtEdge.has("/settings")).toBe(false);
  });
});
