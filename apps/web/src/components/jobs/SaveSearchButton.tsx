"use client";

import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { useSaveSearch } from "@/lib/api/queries";
import type { SearchState } from "@/lib/search-state";

/** Hidden once the current query is already a saved search, and before there's anything worth
 * saving — an empty query would save "everything", which is not what the button promises. */
export function SaveSearchButton({ state, saved }: { state: SearchState; saved: boolean }) {
  const save = useSaveSearch();

  if (saved || !state.query.trim()) return null;

  async function onSave() {
    try {
      await save.mutateAsync(state);
      toast.success("Saved. New matches will show on your dashboard.");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not save this search");
    }
  }

  return (
    <Button type="button" variant="outline" onClick={onSave} disabled={save.isPending}>
      Save this search
    </Button>
  );
}
