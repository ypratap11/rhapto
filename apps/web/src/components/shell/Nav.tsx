"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Columns3, ListChecks, Package, Settings, UserRound } from "lucide-react";

const ITEMS = [
  { href: "/", label: "Jobs", icon: ListChecks },
  { href: "/packages", label: "Packages", icon: Package },
  { href: "/pipeline", label: "Pipeline", icon: Columns3 },
  { href: "/profile", label: "Profile", icon: UserRound },
] as const;

const LINK_CLASS = (active: boolean) =>
  `flex items-center gap-2 rounded-md px-3 py-2 text-sm ${active ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground"}`;

export function Nav() {
  const pathname = usePathname();
  return (
    <nav aria-label="Primary" className="flex items-center gap-1">
      {ITEMS.map(({ href, label, icon: Icon }) => {
        const active = href === "/" ? pathname === "/" || pathname.startsWith("/jobs") : pathname.startsWith(href);
        return (
          <Link key={href} href={href} aria-current={active ? "page" : undefined} className={LINK_CLASS(active)}>
            <Icon className="size-4" aria-hidden />
            {label}
          </Link>
        );
      })}
      <Link
        href="/settings"
        aria-label="Settings"
        aria-current={pathname.startsWith("/settings") ? "page" : undefined}
        className={LINK_CLASS(pathname.startsWith("/settings"))}
      >
        <Settings className="size-4" aria-hidden />
      </Link>
    </nav>
  );
}
