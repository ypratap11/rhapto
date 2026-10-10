"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { type RefObject, useEffect, useId, useRef, useState } from "react";
import { Menu, Plus, User } from "lucide-react";
import { accessRequestLink } from "@/components/landing/access";
import { primaryCta } from "@/components/landing/cta";
import { type FeedbackTarget, QuickFeedbackDialog } from "@/components/feedback/QuickFeedbackDialog";
import { Button, buttonVariants } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { ThemeMenuItem, ThemeToggle } from "@/components/ui/theme-toggle";
import { SAME_ORIGIN_DEPLOYMENT } from "@/lib/api/client";
import { useMe } from "@/lib/api/queries";
import { areaForPath, contextForPath, FEEDBACK_HIDDEN_ROUTES } from "@/lib/feedback";
import { cn } from "cn";
import { useSignedIn, useVisitorHeader } from "./TokenGate";

export const TABS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/resumes", label: "My resumes" },
] as const;

/** Which tab a page belongs to. Jobs are reached from the Dashboard; a tailored resume belongs to My
 * resumes. The coach, Profile and Settings light neither. */
export function activeTab(pathname: string): string | null {
  if (pathname.startsWith("/resumes") || pathname.includes("/packages/")) return "/resumes";
  if (pathname.startsWith("/dashboard") || pathname.startsWith("/jobs")) return "/dashboard";
  return null;
}

const ACCOUNT_LINKS = [
  { href: "/profile", label: "Your profile" },
  { href: "/settings", label: "Settings" },
  { href: "/settings#help", label: "Help" },
] as const;

/** Cloudflare Access serves this on every protected hostname. A plain anchor on purpose: it is not a
 * Next route, so no router, no prefetch. Hosted mode only; token mode has no sign-out. */
const SIGN_OUT_HREF = "/cdn-cgi/access/logout";

// Brick-red underline instead of a pill or a green bar (spec §8, "differentiators"): 2px, 6px below
// the label, painted with box-shadow so it does not move the text the way a border would.
const ACTIVE = "text-foreground shadow-[inset_0_-2px_0_0_var(--primary)] pb-1.5";
const ROW = "flex min-h-11 w-full items-center rounded-control px-3 text-sm text-muted-foreground hover:bg-muted hover:text-foreground";
const MENU_LINK =
  "flex min-h-11 items-center rounded-control px-3 text-base text-muted-foreground hover:bg-muted hover:text-foreground aria-[current=page]:text-foreground";

/** A disclosure, not `role=menu` (that promises arrow-key roving nobody builds). The caller keys it by
 * pathname so navigating remounts it closed. */
function AccountMenu({
  initial,
  canFeedback,
  onFeedback,
  trigger,
}: {
  initial: string | null;
  canFeedback: boolean;
  onFeedback: () => void;
  trigger: RefObject<HTMLButtonElement | null>;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const panelId = useId();

  useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent) => {
      if (root.current && !root.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        trigger.current?.focus();
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, trigger]);

  return (
    <div
      ref={root}
      className="relative hidden md:block"
      onBlur={(e) => {
        // Tabbing out closes it; focus moving within it does not. Safari and Firefox on macOS do not focus a
        // button on click, so relatedTarget is null then: only a known target outside the panel closes it
        // (outside clicks and Escape have their own handlers).
        const next = e.relatedTarget as Node | null;
        if (open && next && !root.current?.contains(next)) setOpen(false);
      }}
    >
      <button
        ref={trigger}
        type="button"
        aria-label="Account"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
        className="inline-flex size-11 items-center justify-center rounded-full"
      >
        <span className="inline-flex size-9 items-center justify-center rounded-full border border-border bg-surface-muted text-sm font-medium text-foreground hover:bg-muted">
          {initial ?? <User className="size-4" aria-hidden />}
        </span>
      </button>
      {open ? (
        <ul id={panelId} aria-label="Account" className="absolute right-0 top-full z-20 mt-1 w-56 rounded-card border border-border bg-surface p-1 shadow-card">
          {ACCOUNT_LINKS.map(({ href, label }) => (
            <li key={href}>
              <Link href={href} onClick={() => setOpen(false)} className={ROW}>
                {label}
              </Link>
            </li>
          ))}
          {canFeedback ? (
            <li>
              <button
                type="button"
                className={cn(ROW, "text-left")}
                onClick={() => {
                  setOpen(false);
                  onFeedback();
                }}
              >
                Send feedback
              </button>
            </li>
          ) : null}
          <li>
            <ThemeMenuItem className={cn(ROW, "text-left")} />
          </li>
          {SAME_ORIGIN_DEPLOYMENT ? (
            <li>
              <a href={SIGN_OUT_HREF} className={ROW}>
                Sign out
              </a>
            </li>
          ) : null}
        </ul>
      ) : null}
    </div>
  );
}

/** The way in for a signed-out visitor. Hosted: an outline pill to the Dashboard (Cloudflare Access asks
 * them to sign in there). Token mode: Settings, as the hero CTA. `prefetch={false}`: these routes are
 * protected and prefetching them from / makes the browser hit Cloudflare and log CORS errors. Absent on
 * /settings itself (no link to the page you are on). */
function EntryLink({ pathname, className, onClick }: { pathname: string; className?: string; onClick?: () => void }) {
  if (SAME_ORIGIN_DEPLOYMENT) {
    return (
      <Link href="/dashboard" prefetch={false} onClick={onClick} className={cn(buttonVariants({ variant: "outline", size: "sm" }), className)}>
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

/** Below md the header is the logo (plus, in the app, the + button) and this button. A right-hand
 * sheet holds the items the desktop header shows for this page. Controlled: every item closes it in its own
 * onClick, because a hash link such as /settings#help does not change the pathname; the caller also keys
 * it by pathname so a back/forward navigation closes it too. Escape and an outside click are Base UI's. */
function MobileMenu({
  pathname,
  visitor,
  canFeedback,
  onFeedback,
  trigger,
}: {
  pathname: string;
  visitor: boolean;
  canFeedback: boolean;
  onFeedback: () => void;
  trigger?: RefObject<HTMLButtonElement | null>;
}) {
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);
  const access = accessRequestLink();
  // EntryLink renders nothing on /settings in token mode; skip its row too so no blank 44px line shows.
  const showEntry = SAME_ORIGIN_DEPLOYMENT || pathname !== primaryCta(false).href;
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger render={<Button ref={trigger} variant="ghost" size="icon-sm" aria-label="Menu" aria-expanded={open} className="size-11 md:hidden" />}>
        <Menu aria-hidden />
      </SheetTrigger>
      <SheetContent side="right">
        <SheetHeader>
          <SheetTitle>Menu</SheetTitle>
        </SheetHeader>
        <ul className="flex flex-col gap-1 px-4 pb-4">
          {visitor ? (
            <>
              {showEntry ? (
                <li className="px-3">
                  <EntryLink pathname={pathname} onClick={close} className="min-h-11 inline-flex items-center" />
                </li>
              ) : null}
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
              {TABS.map(({ href, label }) => (
                <li key={href}>
                  <Link href={href} onClick={close} aria-current={activeTab(pathname) === href ? "page" : undefined} className={MENU_LINK}>
                    {label}
                  </Link>
                </li>
              ))}
              <li role="presentation" className="px-3 pb-1 pt-4 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Account
              </li>
              {ACCOUNT_LINKS.map(({ href, label }) => (
                <li key={href}>
                  <Link href={href} onClick={close} className={MENU_LINK}>
                    {label}
                  </Link>
                </li>
              ))}
              {canFeedback ? (
                <li>
                  <button
                    type="button"
                    className={cn(MENU_LINK, "w-full text-left")}
                    onClick={() => {
                      close();
                      onFeedback();
                    }}
                  >
                    Send feedback
                  </button>
                </li>
              ) : null}
              <li>
                <ThemeMenuItem className={cn(MENU_LINK, "w-full text-left")} />
              </li>
              {SAME_ORIGIN_DEPLOYMENT ? (
                <li>
                  <a href={SIGN_OUT_HREF} className={MENU_LINK}>
                    Sign out
                  </a>
                </li>
              ) : null}
            </>
          )}
          {visitor ? (
            <li className="px-3 pt-2">
              <ThemeToggle className="size-11" />
            </li>
          ) : null}
        </ul>
      </SheetContent>
    </Sheet>
  );
}

export function TopBar() {
  const pathname = usePathname();
  const visitor = useVisitorHeader();
  const [feedback, setFeedback] = useState<FeedbackTarget | null>(null);
  const accountRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLButtonElement>(null);
  // Signed in AND /me succeeded. Someone who passes Cloudflare but is not on the allowlist gets a 403
  // from /me and must not be offered a feedback form whose POST is refused.
  const signedIn = useSignedIn();
  const me = useMe({ enabled: signedIn });
  const initial = me.data?.email?.trim().charAt(0).toUpperCase() || null;
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  const canFeedback = signedIn && me.isSuccess && !FEEDBACK_HIDDEN_ROUTES.has(path);
  // Area and context are fixed at open time, so navigating while the dialog is open cannot retag it.
  const openFeedback = () => setFeedback({ area: areaForPath(pathname), ...contextForPath(pathname) });
  const current = activeTab(pathname);
  return (
    <header className="border-b border-border bg-surface">
      {/* One row at every width. Below md: the logo, the + and the Menu button. From md the page's own
          items sit inline. Both variants are in the DOM and CSS picks one, so there is no viewport read
          in JS and nothing to mismatch on hydration. */}
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-x-6 px-4 sm:px-6">
        <Link href={visitor ? "/" : "/dashboard"} className="inline-flex min-h-11 items-center font-serif text-xl font-medium tracking-tight">
          Rhapto
        </Link>
        {visitor ? (
          <div className="flex items-center gap-1">
            <div className="hidden items-center gap-3 md:flex">
              <ThemeToggle />
              <EntryLink pathname={pathname} />
            </div>
            <MobileMenu key={`menu-${pathname}`} pathname={pathname} visitor canFeedback={false} onFeedback={openFeedback} />
          </div>
        ) : (
          <>
            <nav aria-label="Primary" className="hidden flex-1 items-center gap-5 whitespace-nowrap text-sm md:flex">
              {TABS.map(({ href, label }) => (
                <Link
                  key={href}
                  href={href}
                  aria-current={current === href ? "page" : undefined}
                  className={current === href ? ACTIVE : "pb-1.5 text-muted-foreground hover:text-foreground"}
                >
                  {label}
                </Link>
              ))}
            </nav>
            <div className="flex items-center gap-2">
              <Link href="/start" className={cn(buttonVariants({ size: "lg" }), "hidden md:inline-flex")}>
                <Plus aria-hidden /> Tailor a resume
              </Link>
              <Link href="/start" aria-label="Tailor a resume" className={cn(buttonVariants({ size: "icon" }), "size-11 md:hidden")}>
                <Plus aria-hidden />
              </Link>
              <AccountMenu key={`account-${pathname}`} initial={initial} canFeedback={canFeedback} onFeedback={openFeedback} trigger={accountRef} />
              <MobileMenu key={`menu-${pathname}`} pathname={pathname} visitor={false} canFeedback={canFeedback} onFeedback={openFeedback} trigger={menuRef} />
            </div>
          </>
        )}
      </div>
      {/* Once, outside both menus: a dialog rendered inside either would unmount the moment the menu closed. */}
      {feedback ? (
        <QuickFeedbackDialog
          open
          onOpenChange={(next) => {
            if (next) return;
            setFeedback(null);
            // The item that opened the dialog went with its menu, so hand focus to whichever trigger is on screen.
            requestAnimationFrame(() => {
              // Focusing a display:none trigger is a no-op, so whichever one is on screen takes it.
              accountRef.current?.focus();
              if (document.activeElement !== accountRef.current) menuRef.current?.focus();
            });
          }}
          target={feedback}
        />
      ) : null}
    </header>
  );
}
