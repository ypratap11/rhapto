"use client";

import { useState } from "react";
import { toast } from "sonner";
import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/client";
import { useBases, usePutTrack, useTaxonomy, useTaxonomySuggestions, type TaxonomyField, type TaxonomyRole } from "@/lib/api/queries";
import { suggestedRoles, trackFromRole } from "@/lib/taxonomy";
import { cn } from "cn";

function ChipButton({ onClick, disabled, children }: { onClick: () => void; disabled: boolean; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="rounded-chip border border-primary/30 bg-primary/10 px-2.5 py-1 text-sm font-medium text-primary transition-colors hover:bg-primary/20 disabled:pointer-events-none disabled:opacity-50"
    >
      {children}
    </button>
  );
}

function FieldButton({ pressed, onClick, children }: { pressed: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={cn(
        "w-full rounded-chip border px-2.5 py-1.5 text-left text-sm font-medium transition-colors",
        pressed ? "border-primary bg-primary text-primary-foreground" : "border-border bg-surface text-foreground hover:bg-surface-muted",
      )}
    >
      {children}
    </button>
  );
}

function RoleButton({ onClick, disabled, children }: { onClick: () => void; disabled: boolean; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="w-full rounded-chip border border-border bg-surface px-2.5 py-1.5 text-left text-sm font-medium transition-colors hover:bg-surface-muted disabled:pointer-events-none disabled:opacity-50"
    >
      {children}
    </button>
  );
}

/**
 * Spec §5: the two-level field → role picker that creates a track from the taxonomy, with the
 * uploaded resume's suggestions offered as one-tap chips.
 *
 * `selectedFieldId` starts `null` and the effective field is derived each render as
 * `selectedFieldId ?? fields[0]?.id` — never synced from the taxonomy query with an effect, so
 * there is nothing to point at a field that has vanished from a later fetch.
 */
export function FieldPicker({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const taxonomy = useTaxonomy();
  const suggestions = useTaxonomySuggestions();
  const bases = useBases();
  const putTrack = usePutTrack();
  const [selectedFieldId, setSelectedFieldId] = useState<string | null>(null);

  const fields = taxonomy.data?.fields ?? [];
  const effectiveFieldId = selectedFieldId ?? fields[0]?.id ?? null;
  const selectedField = fields.find((f) => f.id === effectiveFieldId) ?? null;

  const suggested = taxonomy.data && suggestions.data ? suggestedRoles(suggestions.data, taxonomy.data) : [];
  const suggestedIds = new Set(suggested.map((s) => s.role.id));
  // A role already offered as a suggestion chip is left out of the roles column — one actionable
  // button per role, not two with the same name.
  const roles = (selectedField?.roles ?? []).filter((r) => !suggestedIds.has(r.id));

  const hasIssue = Boolean(taxonomy.error) || taxonomy.isPaused;
  const nothingToShow = !taxonomy.data && hasIssue;

  // Suggestions have their own loading/failed/stale-cache states, independent of taxonomy's (they
  // come from separate queries with different staleTimes): a loading suggestions call must show a
  // skeleton, not silently render the same empty chip row a genuinely-suggestion-less resume would —
  // that would be indistinguishable from "nothing matched."
  const suggestionsHasIssue = Boolean(suggestions.error) || suggestions.isPaused;
  const suggestionsNothingToShow = !suggestions.data && suggestionsHasIssue;

  async function pick(field: TaxonomyField, role: TaxonomyRole) {
    try {
      await putTrack.mutateAsync(trackFromRole(field, role, bases.data?.[0]?.id ?? "default"));
      toast.success(`Added the ${role.name} track`);
      onOpenChange(false);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not create the track");
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl space-y-4">
        <DialogHeader>
          <DialogTitle>Pick a field and role</DialogTitle>
        </DialogHeader>
        {taxonomy.isLoading ? (
          <div className="grid grid-cols-2 gap-4" aria-hidden="true">
            <Skeleton className="h-48 w-full" />
            <Skeleton className="h-48 w-full" />
          </div>
        ) : nothingToShow ? (
          <ApiErrorBanner error={taxonomy.error ?? "Can't reach Rhapto's API."} />
        ) : (
          <>
            {hasIssue ? <ApiErrorBanner error={taxonomy.error ?? "Can't reach Rhapto's API."} /> : null}
            {suggestions.isLoading ? (
              <div className="flex flex-wrap gap-1.5" aria-hidden="true">
                <Skeleton className="h-7 w-32 rounded-chip" />
                <Skeleton className="h-7 w-40 rounded-chip" />
              </div>
            ) : suggestionsNothingToShow ? (
              <p className="text-xs text-fit-mid">Couldn&rsquo;t load suggestions from your resume.</p>
            ) : suggested.length > 0 ? (
              <div role="group" aria-label="Suggested from your resume" className="flex flex-wrap items-center gap-1.5">
                {suggested.map(({ field, role }) => (
                  <ChipButton key={role.id} onClick={() => pick(field, role)} disabled={putTrack.isPending}>
                    {role.name}
                  </ChipButton>
                ))}
                {suggestionsHasIssue ? <span className="text-xs text-fit-mid">(couldn&rsquo;t refresh)</span> : null}
              </div>
            ) : null}
            {fields.length === 0 ? (
              <p className="text-sm text-muted-foreground">No fields configured yet.</p>
            ) : (
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5" role="group" aria-label="Fields">
                  {fields.map((field) => (
                    <FieldButton key={field.id} pressed={field.id === effectiveFieldId} onClick={() => setSelectedFieldId(field.id)}>
                      {field.name}
                    </FieldButton>
                  ))}
                </div>
                <div className="space-y-1.5" role="group" aria-label="Roles">
                  {roles.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No more roles in this field.</p>
                  ) : (
                    roles.map((role) => (
                      <RoleButton key={role.id} onClick={() => selectedField && pick(selectedField, role)} disabled={putTrack.isPending}>
                        {role.name}
                      </RoleButton>
                    ))
                  )}
                </div>
              </div>
            )}
          </>
        )}
        <p className="text-xs text-muted-foreground">Tracks stay editable — name, keywords and the fit threshold — in the Tracks card.</p>
      </DialogContent>
    </Dialog>
  );
}
