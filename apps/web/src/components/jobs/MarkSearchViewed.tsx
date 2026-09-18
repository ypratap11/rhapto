"use client";

import { useEffect } from "react";
import { toast } from "sonner";
import { ApiError } from "@/lib/api/client";
import { useMarkSearchViewed } from "@/lib/api/queries";

/**
 * Opening a saved search's results (via the Dashboard rail's `?search_id=`) clears its "N new"
 * badge (spec §6). Split out of the Jobs page into its own component, mounted only while
 * `search_id` is present, so:
 *  - the real `useMarkSearchViewed` mutation — and the `useQueryClient` it needs — is never
 *    invoked on a plain `/jobs` visit (and so never needs a `QueryClientProvider` in a test that
 *    doesn't set `search_id`);
 *  - the mark-as-viewed behaviour, including its failure path, is unit-testable on its own.
 *
 * A failure here is silent by default (a badge count, not a page the user is looking at), so it
 * must not fail silently to the user too: without a toast, the "N new" badge stays wrong with no
 * signal anything went wrong.
 */
export function MarkSearchViewed({ searchId }: { searchId: string }) {
  const markViewed = useMarkSearchViewed();
  const { mutateAsync } = markViewed;

  useEffect(() => {
    void mutateAsync(searchId).catch((e: unknown) => {
      toast.error(e instanceof ApiError ? e.message : "Could not mark this search as viewed");
    });
  }, [searchId, mutateAsync]);

  return null;
}
