import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ACCESS_REQUEST_EMAIL, ACCESS_REQUEST_MAILTO } from "./access";
import { Landing } from "./Landing";

// `SAME_ORIGIN_DEPLOYMENT` is a `const` computed from an env var at module load, so a module mock is
// the only way to exercise both deployments -- the same pattern about/page.test.tsx and
// TokenGate.test.tsx use.
const sameOriginFlag = { value: false };
vi.mock("@/lib/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/client")>();
  return {
    ...actual,
    get SAME_ORIGIN_DEPLOYMENT() {
      return sameOriginFlag.value;
    },
  };
});

afterEach(() => {
  sameOriginFlag.value = false;
});

describe("Landing, the way in", () => {
  it("offers a stranger on the hosted instance both a sign-in and a way to ask for access", () => {
    sameOriginFlag.value = true;
    render(<Landing />);

    // The defect this fixes: the page told people to sign in and had no sign-in anywhere, and its
    // only CTA led to a Cloudflare Access prompt that refuses an address nobody has allowlisted.
    // Scoped to the hero rather than to the page, because that is where a stranger looks -- a
    // page-wide query passes on the footer pair alone, which is how a weaker version of this
    // assertion survived putting "Open your dashboard" back in the hero.
    // The hero is the first band on the page; the other two are the provenance demo and How it works.
    const hero = screen.getAllByTestId("hero-band")[0]!;
    expect(within(hero).getByRole("link", { name: /^sign in$/i })).toHaveAttribute(
      "href",
      "/dashboard",
    );
    expect(within(hero).getByRole("link", { name: /^request access$/i })).toHaveAttribute(
      "href",
      ACCESS_REQUEST_MAILTO,
    );
    expect(screen.queryByRole("link", { name: /open your dashboard/i })).toBeNull();

    // And again at the foot of the page, so someone who read the whole thing does not scroll back.
    const signIn = screen.getAllByRole("link", { name: /^sign in$/i });
    expect(signIn).toHaveLength(2);
    for (const link of signIn) expect(link).toHaveAttribute("href", "/dashboard");

    const request = screen.getAllByRole("link", { name: /^request access$/i });
    expect(request).toHaveLength(2);
    for (const link of request) expect(link).toHaveAttribute("href", ACCESS_REQUEST_MAILTO);
    // Spelled out rather than only compared to the constant: a typo'd or emptied address would
    // otherwise agree with itself and pass.
    expect(ACCESS_REQUEST_MAILTO).toBe(
      "mailto:hellorhapto@augaster.com?subject=Rhapto%20access%20request",
    );
    expect(ACCESS_REQUEST_EMAIL).toBe("hellorhapto@augaster.com");
  });

  it("says that access is invite-only, next to the buttons, instead of letting Cloudflare Access refuse people unexplained", () => {
    sameOriginFlag.value = true;
    render(<Landing />);
    const line = screen.getByText(/sign-in is an allowlist the maintainer keeps by hand/i);
    expect(line).toBeInTheDocument();
    // Nobody has committed to answering, so this line must not imply a turnaround.
    expect(line.textContent ?? "").not.toMatch(/reply|respond|get back|within \d|hour|business day/i);
  });

  it("offers a self-hoster neither sign-in nor request access, because they have nobody to ask", () => {
    render(<Landing />);
    expect(screen.getByRole("link", { name: /^get started$/i })).toHaveAttribute("href", "/settings");
    expect(screen.queryByRole("link", { name: /^sign in$/i })).toBeNull();
    expect(screen.queryByRole("link", { name: /request access/i })).toBeNull();
    // No mailto at all: nothing on a self-hosted page should mail the maintainer of someone else's
    // instance.
    expect(document.querySelectorAll('a[href^="mailto:"]')).toHaveLength(0);
  });

  it("tells step 1's reader how anyone gets invited, without weakening either deployment's half", () => {
    render(<Landing />);
    const steps = within(screen.getByRole("list", { name: /how it works/i })).getAllByRole(
      "listitem",
    );
    const first = steps[0]?.textContent ?? "";
    expect(first).toMatch(/Invites there are an allowlist the maintainer keeps by hand/i);
    // Both halves of the reviewed privacy claim survive: the self-hosting one and the hosted one.
    expect(first).toMatch(/nothing leaves your machine/i);
    expect(first).toMatch(/your data lives on that server, encrypted/i);
  });

  it("puts the animated journey inside How it works, above the five cards, and keeps both", () => {
    render(<Landing />);
    const journey = screen.getByRole("list", { name: /from asking for access to pressing send/i });
    expect(within(journey).getAllByRole("listitem")).toHaveLength(6);
    // The cards are still there and still five, so the titles pinned by the page tests stay put.
    expect(
      within(screen.getByRole("list", { name: /how it works/i })).getAllByRole("listitem"),
    ).toHaveLength(5);
    // Six beats beside five cards is a discrepancy a reader will notice, so the page explains it.
    expect(screen.getByText(/five steps rather than six/i)).toBeInTheDocument();
  });

  it("keeps the client boundary in the children, not in Landing", () => {
    // `Landing` is mounted at `/about` as a server component. A hook added directly to it fails at
    // build time, not in jsdom, so the only way a unit test can pin this constraint is to read the
    // modules: the interactivity must live behind its own "use client", as ProvenanceDemo already
    // does. Cheap, and it fails the moment someone reaches for `useState` in Landing.
    const dir = dirname(fileURLToPath(import.meta.url));
    const read = (name: string) => readFileSync(join(dir, name), "utf8");
    // Comments stripped first: Landing's own comments discuss `"use client"` and would otherwise
    // make this pass or fail on prose rather than on code.
    const code = read("Landing.tsx")
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/^[ \t]*\/\/.*$/gm, "");
    expect(code).not.toMatch(/"use client"/);
    expect(code).not.toMatch(/\buse[A-Z]\w*\(/);
    for (const child of ["JourneyWalkthrough.tsx", "ProvenanceDemo.tsx"]) {
      expect(read(child)).toMatch(/^"use client";/);
    }
  });
});
