"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import { ChevronDown, CircleQuestionMark, Settings } from "lucide-react";
import { FeedbackButton } from "@/components/feedback/FeedbackButton";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { SAME_ORIGIN_DEPLOYMENT } from "@/lib/api/client";

const TABS = [
  { href: "/start", label: "Tailor a resume" },
  { href: "/resumes", label: "My resumes" },
  { href: "/feedback", label: "Feedback" },
] as const;

// The screens the coach hides. Still reachable, one click away, for the people who want them.
const ADVANCED = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/jobs", label: "Jobs" },
  { href: "/pipeline", label: "Pipeline" },
  { href: "/profile", label: "Profile" },
] as const;

// Brick-red underline instead of a pill or a green bar (spec §8, "differentiators"): 2px, 6px below
// the label, painted with box-shadow so it does not move the text the way a border would.
const ACTIVE = "text-foreground shadow-[inset_0_-2px_0_0_var(--primary)] pb-1.5";

/** A disclosure, not a Base UI menu: no component here uses `ui/dropdown-menu` yet and nothing proves
 * it under jsdom. It lives in the trailing icon group rather than the scrolling <nav>, because an
 * absolutely positioned panel inside `overflow-x-auto` is clipped on phones. */
function AdvancedMenu({ pathname }: { pathname: string }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const panelId = useId();
  const active = ADVANCED.some(({ href }) => pathname.startsWith(href));

  useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent) => {
      if (root.current && !root.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        data-active={active ? "true" : undefined}
        onClick={() => setOpen((v) => !v)}
        className={`inline-flex items-center gap-1 rounded-control px-1.5 py-1 text-sm hover:text-foreground ${active ? "text-foreground" : "text-muted-foreground"}`}
      >
        Advanced
        <ChevronDown className="size-3.5" aria-hidden />
      </button>
      {open ? (
        <ul
          id={panelId}
          aria-label="Advanced"
          className="absolute right-0 top-full z-20 mt-1 min-w-40 rounded-card border border-border bg-surface p-1 shadow-card"
        >
          {ADVANCED.map(({ href, label }) => (
            <li key={href}>
              <Link
                href={href}
                aria-current={pathname.startsWith(href) ? "page" : undefined}
                className="block rounded-control px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted hover:text-foreground aria-[current=page]:text-foreground"
              >
                {label}
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export function TopBar() {
  const pathname = usePathname();
  return (
    <header className="border-b border-border bg-surface">
      {/* Below `md` the bar wraps into two rows: logo, Advanced and icons on top, the three tabs
          underneath in a row that scrolls sideways (PR #6). */}
      <div className="mx-auto flex min-h-14 max-w-6xl flex-wrap items-center justify-between gap-x-6 px-4 pt-2 sm:px-6 md:h-14 md:flex-nowrap md:pt-0">
        {/* Hosted: a signed-in person's way back is the coach, where the work starts. Token mode
            (self-hosted) has no coach audience yet and keeps the dashboard. */}
        <Link href={SAME_ORIGIN_DEPLOYMENT ? "/start" : "/dashboard"} className="font-serif text-xl font-medium tracking-tight">
          Rhapto
        </Link>
        <nav
          aria-label="Primary"
          className="order-last flex w-full items-center gap-4 overflow-x-auto whitespace-nowrap pt-2 text-sm md:order-none md:w-auto md:flex-1 md:gap-5 md:overflow-visible md:pt-0"
        >
          {TABS.map(({ href, label }) => {
            // No tab's href is a prefix of another's (/start, /resumes, /feedback), so a plain
            // prefix match is unambiguous.
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
          {/* keyed by path: navigating remounts it closed, with no setState-in-effect */}
          <AdvancedMenu key={pathname} pathname={pathname} />
          {/* Deliberately outside the Primary nav: "About" is the pitch, not a place you work.
              Hidden below `sm` to keep the top row short on phones. */}
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
