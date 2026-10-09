"use client";

import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { useTaxonomy } from "@/lib/api/queries";
import { describeCoachError, type CoachError } from "@/lib/coach/errors";
import { fireCoachEvent } from "@/lib/coach/events";
import { searchRoles, useSaveCoachRole, type RoleSource } from "@/lib/coach/role";
import { clearProposal, writeConfirmedTrack, type CachedProposal } from "@/lib/coach/storage";
import { CoachErrorNote, CoachFrame, type TranscriptItem } from "./CoachFrame";

export type ConfirmedRole = { id: string; name: string };

export function RoleStep({
  userId,
  proposal,
  importError,
  transcript,
  onConfirmed,
  onPaste,
}: {
  userId: string;
  proposal: CachedProposal | null;
  importError: CoachError | null;
  transcript?: TranscriptItem[];
  onConfirmed: (role: ConfirmedRole) => void;
  onPaste?: () => void;
}) {
  const taxonomy = useTaxonomy();
  const { ready, isSaving, save } = useSaveCoachRole();
  const [other, setOther] = useState(false);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<CoachError | null>(null);
  const inFlight = useRef(false);
  const top = proposal?.tracks[0] ?? null;
  const alternatives = proposal?.tracks.slice(1) ?? [];
  const showPicker = other || top === null;
  const results = taxonomy.data ? searchRoles(taxonomy.data, query) : [];

  async function confirm(source: RoleSource) {
    if (inFlight.current || !ready) return;
    inFlight.current = true;
    setError(null);
    try {
      // One track and the location answers; no blocks (see useSaveCoachRole).
      const track = await save(source, proposal?.location ?? null);
      writeConfirmedTrack(userId, track.id);
      clearProposal(userId);
      void fireCoachEvent("role_confirmed");
      onConfirmed({ id: track.id, name: track.name });
    } catch (e) {
      setError(describeCoachError(e, "jobs"));
    } finally {
      inFlight.current = false;
    }
  }

  const title = top ? `Looks like you're aiming for: ${top.name}. Right?` : "What role are you aiming for?";
  return (
    <CoachFrame title={title} transcript={transcript}>
      <CoachErrorNote error={importError} />
      <CoachErrorNote error={error} />
      {top ? (
        <div className="flex flex-wrap gap-3">
          <Button type="button" size="lg" disabled={!ready || isSaving} onClick={() => void confirm({ kind: "proposed", track: top })}>
            Yes, that&apos;s right
          </Button>
          {!other ? (
            <Button type="button" size="lg" variant="outline" onClick={() => setOther(true)}>
              Something else
            </Button>
          ) : null}
        </div>
      ) : null}
      {showPicker ? (
        <div className="space-y-3">
          {alternatives.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {alternatives.map((t) => (
                <Button key={t.id} type="button" variant="outline" disabled={!ready || isSaving} onClick={() => void confirm({ kind: "proposed", track: t })}>
                  {t.name}
                </Button>
              ))}
            </div>
          ) : null}
          <div className="space-y-1">
            <label htmlFor="coach-role-search" className="text-sm font-medium">
              Search roles
            </label>
            <input
              id="coach-role-search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="e.g. product manager, data analyst"
              className="h-9 w-full rounded-control border border-border bg-background px-3 text-sm"
            />
          </div>
          {query.trim() && taxonomy.data ? (
            results.length > 0 ? (
              <ul aria-label="Matching roles" className="space-y-1">
                {results.map(({ field, role }) => (
                  <li key={role.id}>
                    <Button type="button" variant="ghost" className="h-auto w-full justify-start py-1.5" disabled={!ready || isSaving} onClick={() => void confirm({ kind: "taxonomy", field, role })}>
                      {role.name} <span className="ml-2 text-xs text-muted-foreground">{field.name}</span>
                    </Button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">No role matches that. Try a shorter word.</p>
            )
          ) : null}
        </div>
      ) : null}
      {onPaste ? (
        <p className="text-sm">
          <button type="button" className="text-primary underline underline-offset-4" onClick={onPaste}>
            Or paste a job you like
          </button>
        </p>
      ) : null}
    </CoachFrame>
  );
}
