"use client";

import Link from "next/link";
import { useEffect } from "react";

export type Crumb = { label: string; href?: string };

/** The trail under the top bar, and the single source of the document title: spec §3 requires the
 * two to read the same. The title is written in an effect (not during render) because it is a DOM
 * side-effect, and Next's metadata API cannot see a client component's loaded data. */
export function Breadcrumbs({ items }: { items: Crumb[] }) {
  const title = items.map((i) => i.label).join(" › ");
  useEffect(() => {
    document.title = title;
  }, [title]);

  return (
    <nav aria-label="Breadcrumb" className="mb-4 text-sm text-muted-foreground">
      <ol className="flex flex-wrap items-center gap-1.5">
        {items.map((item, i) => (
          <li key={`${item.label}-${i}`} className="flex items-center gap-1.5">
            {i > 0 ? <span aria-hidden="true">›</span> : null}
            {item.href && i < items.length - 1 ? (
              <Link href={item.href} className="rounded-chip underline-offset-4 hover:text-foreground hover:underline">
                {item.label}
              </Link>
            ) : (
              <span aria-current="page" className="text-foreground">
                {item.label}
              </span>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}
