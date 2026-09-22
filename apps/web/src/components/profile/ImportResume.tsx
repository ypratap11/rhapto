"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ApiError } from "@/lib/api/client";
import { useAnswers, useBases, usePutAnswers, usePutBlock, usePutTrack, type Block, type ResumeImportOut } from "@/lib/api/queries";
import { BLOCK_TYPES, joinList } from "@/lib/profile-forms";
import { ConfirmMetrics } from "./ConfirmMetrics";

/**
 * The resume_base a proposed track falls back to when the profile has no bases yet (the
 * fresh-install path). Must be a valid `ResumeBase.id`/`Track.id` slug (`^[a-z0-9][a-z0-9-]*$`):
 * `synthesize_bases` (apps/api/src/rhapto/profile/loader.py) builds one `ResumeBase` per distinct
 * `track.resume_base` the first time the profile is loaded with no bases in the database, so any
 * fixed valid slug here becomes a real, resolvable base for tailoring, export and the rescore
 * worker — an empty string is the one value that cannot, because `ResumeBase.id` rejects it.
 */
const DEFAULT_RESUME_BASE_ID = "imported-default";

const BLOCK_TYPE_LABEL: Record<(typeof BLOCK_TYPES)[number], string> = {
  achievement: "Achievements",
  role: "Roles",
  project: "Projects",
  skill: "Skills",
  credential: "Credentials",
};

/**
 * One tile of the review screen's summary row: counts of proposed blocks, dropped periods and
 * metrics to confirm. Same stat-tile contract as Settings' Usage section (dataviz: sentence-case
 * label, Sans value in the font's default proportional figures — `tabular-nums` is reserved for
 * table columns, not a standalone tile value).
 */
function ImportStatTile({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-xl font-medium text-foreground">{value}</p>
    </div>
  );
}

function ImportedBlockRow({ block }: { block: Block }) {
  return (
    <li className="space-y-1 rounded-md border border-border bg-surface p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-sm font-medium">{block.role ?? block.org ?? block.id}</p>
          {block.org && block.role ? <p className="text-xs text-muted-foreground">{block.org}</p> : null}
        </div>
        {block.period ? <span className="text-xs text-muted-foreground">{block.period}</span> : <StatusBadge tone="muted">no date</StatusBadge>}
      </div>
      <p className="text-sm">{block.content}</p>
      {block.metric ? (
        <p className="text-xs text-muted-foreground">
          Claims <span className="font-medium text-foreground">{block.metric}</span> — unverified, so it is stripped from generated resumes until confirmed.
        </p>
      ) : null}
    </li>
  );
}

/**
 * Upload-and-review screen for Spec §6 Screen 2: the resume-import proposal. Nothing here is
 * persisted until the user clicks "Add N blocks to my profile" — the endpoint that produced
 * `proposal` is read-only, and this component is the only place that turns it into real writes,
 * through the same `usePutBlock`/`usePutTrack`/`usePutAnswers` hooks the profile tabs use.
 *
 * `onConfirm` fires as soon as the user accepts, before the writes resolve — it is a hook for the
 * caller (e.g. to know a proposal was accepted), not a gate on saving. Once the blocks are
 * written, any saved block that carries a `metric` is walked one at a time by `ConfirmMetrics`
 * (spec §6): every imported block starts `verified: false`, so its number is stripped from
 * generated resumes until the user asserts it themselves. `onDone` fires once that guided
 * confirmation (or, when nothing needs confirming, the plain save) is finished.
 */
export function ImportResume({
  proposal,
  onConfirm,
  onCancel,
  onDone,
}: {
  proposal: ResumeImportOut;
  onConfirm: (proposal: ResumeImportOut) => void;
  onCancel?: () => void;
  onDone?: () => void;
}) {
  const answers = useAnswers();
  const bases = useBases();
  const putBlock = usePutBlock();
  const putTrack = usePutTrack();
  const putAnswers = usePutAnswers();
  const [saving, setSaving] = useState(false);
  const [savedBlocks, setSavedBlocks] = useState<Block[] | null>(null);
  const [metricsDone, setMetricsDone] = useState(false);

  const groups = BLOCK_TYPES.map((type) => ({ type, blocks: proposal.blocks.filter((b) => b.type === type) })).filter((g) => g.blocks.length > 0);

  // `handleAccept` merges `answers.data` (to preserve every other answer key — PUT replaces the
  // whole map, see LocationTab) and reads `bases.data` to pick a track's resume base, so accepting
  // before either query has resolved, or after either has errored, must not be possible: an
  // unresolved `useAnswers()` would PUT a map containing only the two or three location keys this
  // component knows about, wiping notice period, salary and everything else, and an unresolved
  // `useBases()` would fall back to inventing a resume base. This mirrors the guard
  // `LocationTab.tsx` already applies to the same `useAnswers()` query.
  const answersReady = !answers.isLoading && answers.data !== undefined;
  const basesReady = !bases.isLoading && bases.data !== undefined;
  const notReady = !answersReady || !basesReady;

  async function handleAccept() {
    // Re-read (rather than trust the `notReady` computed above) so TypeScript narrows `data` to
    // defined within this closure, and so a stale click (e.g. a query that errored between render
    // and click) is still caught here, not just by the disabled button.
    const answersData = answers.data;
    const basesData = bases.data;
    if (answers.isLoading || answersData === undefined || bases.isLoading || basesData === undefined) {
      return;
    }
    onConfirm(proposal);
    setSaving(true);
    // Blocks are written first and their result is kept even if a later step fails: `PUT` is an
    // upsert, so every write here is safely retryable, and a track or answers failure after the
    // blocks landed must not be reported as though nothing was saved (finding 3) — the block
    // library really does exist now, and `ConfirmMetrics` still needs to run over it.
    let written: Block[] = [];
    try {
      written = await Promise.all(proposal.blocks.map((b) => putBlock.mutateAsync(b)));
      setSavedBlocks(written);

      // A proposed track never carries a resume base (the import proposal has no concept of one).
      // If the profile already has bases, fall back to whichever exists rather than inventing one
      // — the user assigns a real base afterwards in the Tracks tab, same as any track created
      // with no base picked. If it has none yet (the fresh-install path), an empty string is not
      // an option: `ResumeBase.id` rejects it, so `synthesize_bases` would crash constructing the
      // implied base the moment anything re-loads the profile (tailoring, export, the rescore
      // worker `put_track` enqueues below). `DEFAULT_RESUME_BASE_ID` is a valid slug instead, which
      // `synthesize_bases` turns into a real, resolvable base.
      const fallbackBase = basesData.length > 0 ? basesData[0]!.id : DEFAULT_RESUME_BASE_ID;
      await Promise.all(
        proposal.tracks.map((t) =>
          putTrack.mutateAsync({
            id: t.id,
            name: t.name,
            description: null,
            keywords: t.keywords ?? [],
            resume_base: fallbackBase,
            min_fit: 50,
            field: t.field,
            role: t.role,
          }),
        ),
      );

      const { location_home, remote_ok } = proposal.location;
      const location_preferred = proposal.location.location_preferred ?? [];
      if (location_home || location_preferred.length > 0 || remote_ok) {
        await putAnswers.mutateAsync({
          ...answersData,
          ...(location_home ? { location_home } : {}),
          ...(location_preferred.length > 0 ? { location_preferred: joinList(location_preferred) } : {}),
          ...(remote_ok ? { remote_ok } : {}),
        });
      }

      toast.success(`Added ${written.length} blocks to your profile.`);
    } catch (e) {
      if (written.length > 0) {
        // Blocks are already saved (savedBlocks is set above) — say so, and that retrying is
        // safe, rather than the old blanket "could not save" that read as a total failure.
        const reason = e instanceof ApiError ? e.message : "an unexpected error";
        toast.error(
          `Saved ${written.length} block${written.length === 1 ? "" : "s"} to your profile, but could not finish the import (${reason}). It is safe to try again.`,
        );
      } else {
        toast.error(e instanceof ApiError ? e.message : "Could not save the imported profile");
      }
    } finally {
      setSaving(false);
    }
  }

  async function verifyMetric(id: string) {
    const block = savedBlocks?.find((b) => b.id === id);
    if (!block) return;
    try {
      const updated = await putBlock.mutateAsync({ ...block, verified: true });
      setSavedBlocks((current) => current?.map((b) => (b.id === id ? updated : b)) ?? current);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : `Could not verify ${id}`);
    }
  }

  if (savedBlocks) {
    const withMetric = savedBlocks.filter((b) => b.metric);
    if (withMetric.length > 0 && !metricsDone) {
      return (
        <ConfirmMetrics
          blocks={withMetric}
          onConfirm={(id) => void verifyMetric(id)}
          onSkip={() => undefined}
          onDone={() => setMetricsDone(true)}
        />
      );
    }
    return (
      <div className="space-y-3">
        <p className="text-sm text-foreground">Added {savedBlocks.length} blocks to your profile.</p>
        <div className="flex justify-end">
          <Button onClick={() => onDone?.()}>Done</Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">Nothing is saved yet — review this first.</p>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        <ImportStatTile label="Blocks proposed" value={proposal.blocks.length} />
        <ImportStatTile label="Dropped periods" value={proposal.dropped_periods} />
        <ImportStatTile label="Metrics to confirm" value={proposal.metrics_to_confirm} />
      </div>
      {proposal.dropped_periods > 0 ? (
        <p className="text-sm text-muted-foreground">
          {proposal.dropped_periods} block{proposal.dropped_periods === 1 ? "" : "s"} had no date Rhapto could read — add{" "}
          {proposal.dropped_periods === 1 ? "it" : "them"} later.
        </p>
      ) : null}
      <div className="space-y-4">
        {groups.map((g) => (
          <div key={g.type} className="space-y-2">
            <h3 className="text-sm font-medium text-foreground">{BLOCK_TYPE_LABEL[g.type]}</h3>
            <ul className="space-y-2">
              {g.blocks.map((b) => (
                <ImportedBlockRow key={b.id} block={b} />
              ))}
            </ul>
          </div>
        ))}
      </div>
      {proposal.tracks.length > 0 ? (
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-foreground">Proposed tracks</h3>
          <ul className="flex flex-wrap gap-2">
            {proposal.tracks.map((t) => (
              <li key={t.id}>
                <StatusBadge tone="neutral">{t.name}</StatusBadge>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {proposal.location.location_home ? <p className="text-sm text-muted-foreground">Home location: {proposal.location.location_home}</p> : null}
      {notReady ? (
        <p className="text-xs text-muted-foreground">Loading the rest of your profile before this can be saved safely&hellip;</p>
      ) : null}
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={() => onCancel?.()} disabled={saving}>
          Cancel
        </Button>
        <Button onClick={() => void handleAccept()} disabled={saving || notReady}>
          Add {proposal.blocks.length} blocks to my profile
        </Button>
      </div>
    </div>
  );
}
