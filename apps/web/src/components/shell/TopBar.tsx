"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { CircleQuestionMark, Settings } from "lucide-react";
import { FeedbackButton } from "@/components/feedback/FeedbackButton";
import { ThemeToggle } from "@/components/ui/theme-toggle";

const TABS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/jobs", label: "Jobs" },
  { href: "/resumes", label: "Resumes" },
  { href: "/pipeline", label: "Pipeline" },
  { href: "/profile", label: "Profile" },
] as const;

// Brick-red underline instead of a pill or a green bar (spec §8, "differentiators"): 2px, 6px below
// the label, painted with box-shadow so it does not move the text the way a border would.
const ACTIVE = "text-foreground shadow-[inset_0_-2px_0_0_var(--primary)] pb-1.5";

export function TopBar() {
  const pathname = usePathname();
  return (
    <header className="border-b border-border bg-surface">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-6 px-6">
        {/* The logo is a signed-in person's way back to their app, not to the explainer at "/" --
            sending them to the pitch instead would be the annoyance this route split must not
            create. */}
        <Link href="/dashboard" className="font-serif text-xl font-medium tracking-tight">
          Rhapto
        </Link>
        <nav aria-label="Primary" className="flex flex-1 items-center gap-5 text-sm">
          {TABS.map(({ href, label }) => {
            // No tab's href is a prefix of another tab's href (checked: /dashboard, /jobs,
            // /resumes, /pipeline, /profile), so a plain prefix match is unambiguous -- the old
            // `href === "/"` special case existed only because every path starts with "/".
            const active = pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={active ? ACTIVE : "pb-1.5 text-muted-foreground hover:text-foreground"}
              >
                {label}
              </Link>
            );
          })}
        </nav>
        <div className="flex items-center gap-1">
          {/* Deliberately outside the Primary nav: "About" is the pitch, not a place you work.
              Hidden below `sm` because the five primary tabs already overflow this bar at phone
              widths; a newcomer on a phone reaches /about from the TokenGate card instead. */}
          <Link
            href="/about"
            className="hidden px-1.5 text-sm text-muted-foreground hover:text-foreground sm:inline"
          >
            About
          </Link>
          <FeedbackButton />
          <ThemeToggle />
          <Link href="/settings" aria-label="Settings" title="Settings" className="rounded-control p-1.5 text-muted-foreground hover:text-foreground">
            <Settings className="size-4" aria-hidden />
            <span className="sr-only">Settings</span>
          </Link>
          <Link href="/settings#help" aria-label="Help" title="Help" className="rounded-control p-1.5 text-muted-foreground hover:text-foreground">
            <CircleQuestionMark className="size-4" aria-hidden />
            <span className="sr-only">Help</span>
          </Link>
        </div>
      </div>
    </header>
  );
}
