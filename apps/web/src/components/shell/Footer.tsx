"use client";

import Link from "next/link";
import { accessRequestLink } from "@/components/landing/access";
import { SAME_ORIGIN_DEPLOYMENT } from "@/lib/api/client";
import { GITHUB_URL } from "@/lib/links";
import { useVisitorHeader } from "./TokenGate";

const LINK = "inline-flex items-center text-muted-foreground underline-offset-4 hover:text-foreground hover:underline max-md:min-h-11";

/** One slim row on every page, mounted once in Shell. "Feedback" is a protected route, so it shows only
 * where the header shows the app (the same `useVisitorHeader` predicate): a visitor on / never sees it. */
export function Footer() {
  const visitor = useVisitorHeader();
  const access = accessRequestLink();
  return (
    <footer className="border-t border-border">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-center gap-x-6 gap-y-1 px-6 py-4 text-sm md:justify-between">
        <nav aria-label="Footer" className="flex flex-wrap items-center justify-center gap-x-6 gap-y-1">
          <a href={GITHUB_URL} target="_blank" rel="noreferrer" className={LINK}>
            Open source
          </a>
          {SAME_ORIGIN_DEPLOYMENT ? (
            <a href={access.href} target={access.external ? "_blank" : undefined} rel={access.external ? "noreferrer" : undefined} className={LINK}>
              Request beta access
            </a>
          ) : null}
          {visitor ? null : (
            <Link href="/feedback" className={LINK}>
              Feedback
            </Link>
          )}
        </nav>
        <p className="text-muted-foreground">© 2026 Rhapto</p>
      </div>
    </footer>
  );
}
