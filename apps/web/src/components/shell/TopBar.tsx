"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import { ChevronDown, CircleQuestionMark, Menu, Settings } from "lucide-react";
import { accessRequestLink } from "@/components/landing/access";
import { primaryCta } from "@/components/landing/cta";
import { FeedbackButton } from "@/components/feedback/FeedbackButton";
import { Button, buttonVariants } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { SAME_ORIGIN_DEPLOYMENT } from "@/lib/api/client";
import { cn } from "cn";
import { useVisitorHeader } from "./TokenGate";

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

const MENU_LINK =
  "flex min-h-11 items-center rounded-control px-3 text-base text-muted-foreground hover:bg-muted hover:text-foreground aria-[current=page]:text-foreground";

/** The way in for a signed-out visitor. Hosted: an outline pill to the coach (Cloudflare Access asks them
 * to sign in there). Token mode: Settings, as the hero CTA. `prefetch={false}`: these routes are
 * protected and prefetching them from / makes the browser hit Cloudflare and log CORS errors. Absent on
 * /settings itself (no link to the page you are on). */
function EntryLink({ pathname, className, onClick }: { pathname: string; className?: string; onClick?: () => void }) {
  if (SAME_ORIGIN_DEPLOYMENT) {
    return (
      <Link href="/start" prefetch={false} onClick={onClick} className={cn(buttonVariants({ variant: "outline", size: "sm" }), className)}>
        Sign in
      </Link>
    );
  }
  const cta = primaryCta(false);
  if (pathname === cta.href) return null;
  return (
    <Link href={cta.href} prefetch={false} onClick={onClick} className={cn("text-sm font-medium text-foreground underline underline-offset-4", className)}>
      {cta.label}
    </Link>
  );
}

/** Below md the header is the logo (plus, in the app, the feedback button) and this button. A right-hand
 * sheet holds the items the desktop header shows for this page. Controlled: every item closes it in its own
 * onClick, because a hash link such as /settings#help does not change the pathname; the caller also keys
 * it by pathname so a back/forward navigation closes it too. Escape and an outside click are Base UI's. */
function MobileMenu({ pathname, visitor }: { pathname: string; visitor: boolean }) {
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);
  const access = accessRequestLink();
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger render={<Button variant="ghost" size="icon-sm" aria-label="Menu" aria-expanded={open} className="size-11 md:hidden" />}>
        <Menu aria-hidden />
      </SheetTrigger>
      <SheetContent side="right">
        <SheetHeader>
          <SheetTitle>Menu</SheetTitle>
        </SheetHeader>
        <ul className="flex flex-col gap-1 px-4 pb-4">
          {visitor ? (
            <>
              <li className="flex min-h-11 items-center px-3">
                <EntryLink pathname={pathname} onClick={close} />
              </li>
              {SAME_ORIGIN_DEPLOYMENT ? (
                <li>
                  <a
                    href={access.href}
                    target={access.external ? "_blank" : undefined}
                    rel={access.external ? "noreferrer" : undefined}
                    onClick={close}
                    className={MENU_LINK}
                  >
                    Request beta access
                  </a>
                </li>
              ) : null}
            </>
          ) : (
            <>
              {[...TABS, ...ADVANCED].map(({ href, label }) => (
                <li key={href}>
                  <Link href={href} onClick={close} aria-current={pathname.startsWith(href) ? "page" : undefined} className={MENU_LINK}>
                    {label}
                  </Link>
                </li>
              ))}
              <li>
                <Link href="/settings" onClick={close} className={MENU_LINK}>
                  Settings
                </Link>
              </li>
              <li>
                <Link href="/settings#help" onClick={close} className={MENU_LINK}>
                  Help
                </Link>
              </li>
            </>
          )}
          <li className="px-3 pt-2">
            <ThemeToggle className="size-11" />
          </li>
        </ul>
      </SheetContent>
    </Sheet>
  );
}

export function TopBar() {
  const pathname = usePathname();
  const visitor = useVisitorHeader();
  return (
    <header className="border-b border-border bg-surface">
      {/* One row at every width. Below md: the logo, the app's feedback button and the Menu button. From md
          the page's own items sit inline. Both variants are in the DOM and CSS picks one, so there is no
          viewport read in JS and nothing to mismatch on hydration. */}
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-x-6 px-4 sm:px-6">
        {/* Always the front door. Signed-in people reach the coach through the Tailor a resume tab. */}
        <Link href="/" className="inline-flex min-h-11 items-center font-serif text-xl font-medium tracking-tight">
          Rhapto
        </Link>
        {visitor ? (
          <div className="flex items-center gap-1">
            <div className="hidden items-center gap-3 md:flex">
              <ThemeToggle />
              <EntryLink pathname={pathname} />
            </div>
            <MobileMenu key={pathname} pathname={pathname} visitor />
          </div>
        ) : (
          <>
            <nav aria-label="Primary" className="hidden flex-1 items-center gap-5 whitespace-nowrap text-sm md:flex">
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
              <div className="hidden md:block">
                <AdvancedMenu key={pathname} pathname={pathname} />
              </div>
              <FeedbackButton />
              <div className="hidden items-center gap-1 md:flex">
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
              <MobileMenu key={pathname} pathname={pathname} visitor={false} />
            </div>
          </>
        )}
      </div>
    </header>
  );
}
