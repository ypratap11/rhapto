"use client";

import { Search } from "lucide-react";
import Link from "next/link";
import { Button, buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { applicableWiden, clearAllFilters, FILTER_LABEL, hasActiveFilters, WIDEN, type JobsEmptyReason } from "@/lib/jobs-empty";
import type { FitFilter, SearchState } from "@/lib/search-state";

/** A list of names as a person would read it. */
function joinNames(names: readonly string[]): string {
  if (names.length === 0) return "";
  if (names.length === 1) return names[0]!;
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

/**
 * The blamed filter's value as a person would recognise it.
 *
 * `filter_value` is rendered by the filter's own registry entry, which is the right thing on the
 * server — one definition, and no display concern leaking into the query layer. But two of those
 * values are identifiers: `search_id` renders a UUID and `field` renders a taxonomy id. The response
 * already carries `search_name` and `field_name` for exactly this, so a sentence reading
 * "(saved search: 3f2a1b8c-…)" was using the wrong field, not missing one.
 *
 * Still never a literal: every branch returns something the API sent.
 */
function displayValue(reason: JobsEmptyReason): string | null {
  if (reason.filter_id === "search_id") return reason.search_name ?? reason.filter_value ?? null;
  if (reason.filter_id === "field") return reason.field_name ?? reason.filter_value ?? null;
  return reason.filter_value ?? null;
}

/**
 * Why this grid is empty, and the one click that would change it.
 *
 * Every sentence here is built from values the API sent -- `field_name` and `user_field_names` come
 * from the taxonomy and the user's own tracks, `search_location` from the saved search. No field name
 * and no place name is written into this file, which is both a product rule (nothing personal, nothing
 * invented) and what makes the tests meaningful: an assertion about a string that is a literal in the
 * same file proves nothing about whether the condition was detected.
 *
 * There is deliberately no suggested alternative location and no asserted cause for a search that has
 * never matched. Nothing in this codebase distinguishes an unrecognised location from a narrow query
 * from an empty market -- `poll_runs` records `found = 0, error = NULL` for all of them -- and there
 * is no gazetteer to draw an alternative from. "Try 'X'" would be a guess presented as a diagnosis,
 * which is the same failure as the silence it replaces.
 */
export function EmptyJobsExplanation({
  reason,
  loading = false,
  fitHiddenCount = null,
  state,
  onChange,
  onClearSavedSearch,
}: {
  reason: JobsEmptyReason | null | undefined;
  loading?: boolean;
  /**
   * How many jobs the API returned that the CLIENT's own `fit` filter then hid. Set only in that
   * case, and it is drawn from `passesFit`'s actual output (`rawJobs.length` vs `jobs.length`) rather
   * than from a second implementation of it: each filter is explained by the layer that applies it.
   */
  fitHiddenCount?: number | null;
  state: SearchState;
  onChange: (next: SearchState) => void;
  onClearSavedSearch: () => void;
}) {
  if (fitHiddenCount !== null && fitHiddenCount > 0) {
    return (
      <Explanation
        title={`${plural(fitHiddenCount, "job")} hidden by the fit filter`}
        description={`Nothing scores ${state.fit} or above right now. The filter is applied in this page, not by the search.`}
        action={
          <Button size="sm" variant="outline" onClick={() => onChange({ ...state, fit: "all" satisfies FitFilter })}>
            Show any fit
          </Button>
        }
      />
    );
  }

  if (loading) {
    return <Skeleton className="h-32 w-full rounded-card" data-testid="empty-reason-loading" />;
  }

  if (!reason) {
    // No diagnosis available (it was never asked for, or the call failed). The old copy, which at
    // least does not claim a cause it does not have.
    return <EmptyState icon={Search} title="No jobs yet" description="Search above, or let your saved searches fill this in." />;
  }

  if (reason.cause === "no_jobs") {
    return (
      <Explanation
        title="No jobs yet"
        description="Rhapto has not found anything for this account. Check that a job source can run and that a search is active, then poll."
        action={
          <Link href="/settings" className={buttonVariants({ size: "sm", variant: "outline" })}>
            Open Settings
          </Link>
        }
      />
    );
  }

  if (reason.cause === "field_without_tracks") {
    const owned = joinNames(reason.user_field_names);
    return (
      <Explanation
        title={reason.field_name ? `You have no tracks in ${reason.field_name}` : "You have no tracks in that field"}
        description={
          owned
            ? `Your tracks are in ${owned}. This filter cannot match anything until you add a track in that field.`
            : "You have no tracks at all yet, so no field can match."
        }
        action={
          <div className="flex flex-wrap gap-2">
            {widenButton(reason, state, onChange, onClearSavedSearch, "field")}
            <Link href="/profile?card=tracks" className={buttonVariants({ size: "sm", variant: "outline" })}>
              Edit tracks
            </Link>
          </div>
        }
      />
    );
  }

  // A saved search that has run and never returned anything is a different thing to say than
  // "this filter excluded everything", so it is checked before the generic filter branch.
  //
  // Gated on `search_id` being blamed OR nothing being blamed at all. The second half matters: when
  // the rest of the corpus is excluded too, the cause is `combination` and `filter_id` is null, so a
  // check on `filter_id === "search_id"` alone went quiet in exactly the compound case — even though
  // the run history is already sitting in the response. It deliberately does NOT fire when some
  // OTHER filter is blamed with a positive `would_match`: that blame is more specific and more
  // actionable, and overriding it would bury a one-click fix.
  if (
    (reason.filter_id === "search_id" || reason.cause === "combination") &&
    reason.search_runs != null &&
    !reason.search_ever_found
  ) {
    const runs = reason.search_runs;
    const name = reason.search_name ?? "This search";
    const where = reason.search_location ? ` for ${reason.search_location}` : "";
    return (
      <Explanation
        title={
          runs === 0
            ? `${name} has not run yet`
            : `${name} has run ${plural(runs, "time")} and never returned a job`
        }
        // Stated as a fact, with no cause attached: an unrecognised location, a query that is too
        // narrow, a source with no coverage and an empty market all look identical from here.
        description={
          runs === 0
            ? `It will be included in the next poll${where}.`
            : `It has been asking${where}. Widening the keywords or the location may help; so may checking that a source can run.`
        }
        action={
          <div className="flex flex-wrap gap-2">
            <Link href="/settings" className={buttonVariants({ size: "sm", variant: "outline" })}>
              Edit this search
            </Link>
            {widenButton(reason, state, onChange, onClearSavedSearch, "search_id")}
          </div>
        }
      />
    );
  }

  if (reason.cause === "filter" && reason.filter_id) {
    const label = FILTER_LABEL[reason.filter_id];
    const value = displayValue(reason);
    const found = reason.would_match ?? 0;
    return (
      <Explanation
        title={`The ${label} filter excluded everything`}
        description={`${plural(found, "job")} would show without it${value ? ` (${label}: ${value})` : ""}.`}
        action={widenButton(reason, state, onChange, onClearSavedSearch, reason.filter_id)}
      />
    );
  }

  if (reason.cause === "combination") {
    const hiddenWiden = applicableWiden("hidden");
    return (
      <Explanation
        title="No job matches all of these filters together"
        // TRUE BY CONSTRUCTION, which the previous wording was not. `combination` is returned when
        // every leave-one-out count is zero — removing any single filter still leaves nothing. The
        // old sentence ("each filter on its own leaves something") asserted the exact opposite of
        // the condition it was rendered for, and the advice that followed it — widen them one at a
        // time — could not work.
        description={`You have ${plural(reason.total, "job")}, and none matches all of these filters. Removing any single one of them still leaves nothing, so there is no one filter to widen.`}
        action={
          <div className="flex flex-wrap gap-2">
            {/* Labelled by what it DOES, not by what it achieves. Clearing the filters cannot be
                promised to fill the grid — for a corpus that is entirely hidden it provably does
                not — so the copy above no longer promises it. */}
            {hasActiveFilters(state) ? (
              <Button size="sm" variant="outline" onClick={() => onChange(clearAllFilters(state))}>
                Clear these filters
              </Button>
            ) : null}
            {/* The hidden switch is a MODE, not a filter that can be absent: `clearAllFilters`
                cannot express "hidden and not hidden", so clearing it only ever picks one side. That
                is why the toggle is offered separately — it is the one control that reaches a corpus
                the cleared filters still cannot show.
                Offered only when the API says flipping it would actually reveal rows. Under
                `combination` every leave-one-out count is 0, so the toggle is normally absent; it
                appears in the one case that is not covered by that — `hidden` narrowing a corpus the
                other filters also exclude. Gated on the count rather than on a guess, because the
                client cannot know otherwise. */}
            {hiddenWiden && (reason.would_match_without.hidden ?? 0) > 0 ? (
              <Button size="sm" variant="outline" onClick={() => onChange(hiddenWiden.apply(state))}>
                {hiddenWiden.label(state)}
              </Button>
            ) : null}
          </div>
        }
      />
    );
  }

  // `nothing_matched`: the diagnosis was asked about a result that is not actually empty. Not an
  // error, and not something to dress up as one.
  return <EmptyState icon={Search} title="No jobs yet" description="Search above, or let your saved searches fill this in." />;
}

function widenButton(
  reason: JobsEmptyReason,
  state: SearchState,
  onChange: (next: SearchState) => void,
  onClearSavedSearch: () => void,
  id: keyof typeof WIDEN,
) {
  const widen = WIDEN[id];
  if (!widen.apply) return null;
  const apply = widen.apply;
  return (
    <Button
      size="sm"
      onClick={() => {
        if (widen.clearsSavedSearch) onClearSavedSearch();
        else onChange(apply(state));
      }}
    >
      {widen.label(state)}
    </Button>
  );
}

function Explanation({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div
      className="flex flex-col items-center gap-2 rounded-card border border-border bg-surface px-6 py-10 text-center"
      data-testid="empty-jobs-explanation"
    >
      <Search aria-hidden="true" className="size-6 text-muted-foreground" />
      <p className="font-sans text-base font-semibold">{title}</p>
      <p className="max-w-prose text-sm text-muted-foreground">{description}</p>
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}
