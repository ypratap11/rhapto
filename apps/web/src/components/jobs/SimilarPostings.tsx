"use client";

import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useSimilarPostings } from "@/lib/api/queries";
import { SOURCE_LABEL } from "@/lib/fit";

/** "+N similar postings": the other copies of this posting that the list collapsed into one row.
 * Copies can come from different sources, so the label says "similar postings", not "locations".
 * Nothing is fetched until the person opens them. */
export function SimilarPostings({ ids }: { ids: string[] }) {
  const [open, setOpen] = useState(false);
  const query = useSimilarPostings(ids, open);
  const label = `+${ids.length} similar ${ids.length === 1 ? "posting" : "postings"}`;
  return (
    <div className="space-y-2">
      <Button variant="ghost" size="xs" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
        {label}
      </Button>
      {open ? (
        query.isError ? (
          <p className="text-xs text-fit-mid">Couldn&rsquo;t load the other postings.</p>
        ) : query.isLoading ? (
          <p className="text-xs text-muted-foreground">Loading&hellip;</p>
        ) : (
          <ul className="space-y-1 text-xs">
            {(query.data ?? []).map((copy) => (
              <li key={copy.id}>
                <Link href={`/jobs/${copy.id}`} className="underline-offset-4 hover:underline">
                  {copy.title ?? "Untitled role"}
                </Link>
                <span className="text-muted-foreground">
                  {" "}
                  &middot; {copy.location ?? "Location not listed"} &middot; {SOURCE_LABEL[copy.source] ?? copy.source}
                </span>
              </li>
            ))}
          </ul>
        )
      ) : null}
    </div>
  );
}
