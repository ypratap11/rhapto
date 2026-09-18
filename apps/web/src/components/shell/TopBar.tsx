"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { CircleQuestionMark, Settings } from "lucide-react";
import { ThemeToggle } from "@/components/ui/theme-toggle";

const TABS = [
  { href: "/", label: "Dashboard" },
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
        <Link href="/" className="font-serif text-xl font-medium tracking-tight">
          Rhapto
        </Link>
        <nav aria-label="Primary" className="flex flex-1 items-center gap-5 text-sm">
          {TABS.map(({ href, label }) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
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
          <ThemeToggle />
          <Link href="/settings#help" aria-label="Help" title="Help" className="rounded-control p-1.5 text-muted-foreground hover:text-foreground">
            <CircleQuestionMark className="size-4" aria-hidden />
            <span className="sr-only">Help</span>
          </Link>
          <Link href="/settings" aria-label="Settings" title="Settings" className="rounded-control p-1.5 text-muted-foreground hover:text-foreground">
            <Settings className="size-4" aria-hidden />
            <span className="sr-only">Settings</span>
          </Link>
        </div>
      </div>
    </header>
  );
}
