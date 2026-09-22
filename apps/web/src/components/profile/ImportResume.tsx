"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ApiError } from "@/lib/api/client";
import { useAnswers, useBases, usePutAnswers, usePutBlock, usePutTrack, type Block, type ResumeImportOut } from "@/lib/api/queries";
import { BLOCK_TYPES, joinList } from "@/lib/profile-forms";

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
 * caller (e.g. to know a proposal was accepted), not a gate on saving. `onDone` fires once the
 * whole flow, including guided metric confirmation (Task 4), is finished.
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

  const groups = BLOCK_TYPES.map((type) => ({ type, blocks: proposal.blocks.filter((b) => b.type === type) })).filter((g) => g.blocks.length > 0);

  async function handleAccept() {
    onConfirm(proposal);
    setSaving(true);
    try {
      const written = await Promise.all(proposal.blocks.map((b) => putBlock.mutateAsync(b)));

      // A proposed track never carries a resume base (the import proposal has no concept of one),
      // so fall back to whichever base already exists rather than inventing one; if the profile
      // has none yet, the track is still saved and the user assigns a base afterwards in the
      // Tracks tab, same as any track created with no base picked.
      const fallbackBase = bases.data?.[0]?.id ?? "";
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
        // PUT /profile/answers replaces the whole map (see LocationTab), so every other answer
        // key has to be preserved explicitly.
        await putAnswers.mutateAsync({
          ...(answers.data ?? {}),
          ...(location_home ? { location_home } : {}),
          ...(location_preferred.length > 0 ? { location_preferred: joinList(location_preferred) } : {}),
          ...(remote_ok ? { remote_ok } : {}),
        });
      }

      setSavedBlocks(written);
      toast.success(`Added ${written.length} blocks to your profile.`);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not save the imported profile");
    } finally {
      setSaving(false);
    }
  }

  if (savedBlocks) {
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
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={() => onCancel?.()} disabled={saving}>
          Cancel
        </Button>
        <Button onClick={() => void handleAccept()} disabled={saving}>
          Add {proposal.blocks.length} blocks to my profile
        </Button>
      </div>
    </div>
  );
}
