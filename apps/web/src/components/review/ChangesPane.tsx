"use client";

import { diffWords } from "diff";
import { useId, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { DocumentSurface } from "@/components/ui/document-surface";
import { Label } from "@/components/ui/label";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Textarea } from "@/components/ui/textarea";
import type { DocParagraph, EditPatch, PackageOut } from "@/lib/api/queries";

/** Word-level diff of a change, `before` read against `after`, one side at a time: the
 * "before" side renders unchanged words plain plus removed words in `<del>` (what this used to
 * say); the "after" side renders unchanged words plain plus added words in `<ins>` (what it says
 * now). Each side only ever shows its own kind of change, so the two never need to sit in the
 * same node. */
function WordDiff({ before, after, side }: { before: string; after: string; side: "before" | "after" }) {
  const parts = useMemo(() => diffWords(before, after), [before, after]);
  const nodes: React.ReactNode[] = [];
  parts.forEach((part, i) => {
    if (side === "before" && part.added) return;
    if (side === "after" && part.removed) return;
    if (part.removed) nodes.push(<del key={`d${i}`} className="diff-del">{part.value}</del>);
    else if (part.added) nodes.push(<ins key={`i${i}`} className="diff-add">{part.value}</ins>);
    else nodes.push(<span key={`s${i}`}>{part.value}</span>);
  });
  return <>{nodes}</>;
}

/** The rewritten text of one paragraph, keyed by the paragraph the tune touched. */
type Draft = { paragraph_id: string; after: string };

function toDrafts(pkg: PackageOut): Draft[] {
  return pkg.edits.map((edit) => ({ paragraph_id: edit.paragraph_id, after: edit.after }));
}

export function ChangesPane({ pkg, violationsByPath, onSave }: { pkg: PackageOut; violationsByPath: Set<string>; onSave?: (edits: EditPatch[]) => Promise<void> }) {
  // Keying the body on the package id means a saved version (a new package) mounts a fresh
  // body with fresh drafts -- no effect syncing props into state.
  return <ChangesPaneBody key={pkg.id} pkg={pkg} violationsByPath={violationsByPath} onSave={onSave} />;
}

function ChangesPaneBody({ pkg, violationsByPath, onSave }: { pkg: PackageOut; violationsByPath: Set<string>; onSave?: (edits: EditPatch[]) => Promise<void> }) {
  const [drafts, setDrafts] = useState<Draft[]>(() => toDrafts(pkg));
  const [saving, setSaving] = useState(false);

  const paragraphs = useMemo(() => pkg.source_document?.paragraphs ?? [], [pkg.source_document]);
  const paragraphById = useMemo(() => new Map<string, DocParagraph>(paragraphs.map((p) => [p.id, p])), [paragraphs]);
  const sectionByParagraphId = useMemo(() => {
    const map = new Map<string, string>();
    for (const section of pkg.source_document?.sections ?? []) for (const id of section.paragraph_ids) map.set(id, section.heading);
    return map;
  }, [pkg.source_document]);
  const afterById = useMemo(() => new Map(drafts.map((d) => [d.paragraph_id, d.after])), [drafts]);

  const dirty = drafts.some((d, i) => d.after !== pkg.edits[i]?.after);
  const editable = Boolean(onSave);

  async function handleSave() {
    if (!onSave) return;
    setSaving(true);
    try {
      await onSave(drafts.map((d) => ({ paragraph_id: d.paragraph_id, after: d.after })));
    } finally {
      setSaving(false);
    }
  }

  return (
    <DocumentSurface className="space-y-6">
      {/* The heading id is the scroll target for a guardrail violation whose path is the whole
          `edits` list rather than one card, so it stays a stable, simple `changes`. */}
      <section aria-labelledby="changes" className="space-y-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="changes" className="font-sans text-sm font-medium">
            Changes
          </h2>
          <p className="text-xs text-muted-foreground">
            {pkg.edits.length} {pkg.edits.length === 1 ? "paragraph" : "paragraphs"} rewritten in {pkg.source_document?.filename ?? "your resume document"}
          </p>
        </div>
        {pkg.edits.length === 0 ? (
          <p className="text-sm text-muted-foreground">The tune left your document unchanged. Regenerate with feedback to push it harder.</p>
        ) : (
          <ol className="space-y-3">
            {pkg.edits.map((edit, i) => (
              <ChangeCard
                key={`${edit.paragraph_id}-${i}`}
                index={i}
                before={edit.before}
                reason={edit.reason}
                after={drafts[i]?.after ?? edit.after}
                originalAfter={edit.after}
                role={paragraphById.get(edit.paragraph_id)?.role ?? "unknown"}
                section={paragraphById.get(edit.paragraph_id)?.section ?? sectionByParagraphId.get(edit.paragraph_id) ?? null}
                hasViolation={violationsByPath.has(`edits[${i}]`)}
                editable={editable}
                onChange={(text) => setDrafts((list) => list.map((d, j) => (j === i ? { ...d, after: text } : d)))}
              />
            ))}
          </ol>
        )}
        {editable ? (
          <div className="flex items-center justify-between gap-3 border-t border-border pt-3">
            <span className="text-sm text-muted-foreground">{dirty ? "Unsaved edits. Saving re-runs the guardrails and creates a new version." : "Edit any rewrite above, then save a new version."}</span>
            <div className="flex gap-2">
              <Button type="button" variant="outline" onClick={() => setDrafts(toDrafts(pkg))} disabled={!dirty || saving}>
                Discard
              </Button>
              <Button type="button" onClick={handleSave} disabled={!dirty || saving}>
                {saving ? "Saving…" : "Save as new version"}
              </Button>
            </div>
          </div>
        ) : null}
      </section>
      {paragraphs.length ? (
        <section aria-labelledby="full-document-heading" className="space-y-2 border-t border-border pt-6">
          <h3 id="full-document-heading" className="font-sans text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Full document
          </h3>
          <ul aria-labelledby="full-document-heading" className="space-y-1.5 text-sm">
            {paragraphs
              .filter((p) => p.text.trim())
              .map((p) => {
                const edited = afterById.get(p.id);
                return (
                  <li
                    key={p.id}
                    className={`whitespace-pre-wrap ${edited === undefined ? "border-l-2 border-transparent pl-3" : "border-l-2 border-primary/50 bg-primary/5 pl-3"} ${p.role === "heading" ? "font-sans text-xs font-semibold uppercase tracking-wide text-muted-foreground" : ""}`}
                  >
                    {edited ?? p.text}
                  </li>
                );
              })}
          </ul>
        </section>
      ) : null}
    </DocumentSurface>
  );
}

function ChangeCard({
  index,
  before,
  after,
  originalAfter,
  reason,
  role,
  section,
  hasViolation,
  editable,
  onChange,
}: {
  index: number;
  before: string;
  after: string;
  originalAfter: string;
  reason: string;
  role: string;
  section: string | null;
  hasViolation: boolean;
  editable: boolean;
  onChange: (text: string) => void;
}) {
  const afterId = useId();
  const [focused, setFocused] = useState(false);
  // Once this row has actually been edited, keep the textarea up rather than snapping back to
  // the (now stale) read view on blur.
  const touched = after !== originalAfter;
  const showTextarea = editable && (focused || touched);

  return (
    <li
      id={`change-${index}`}
      data-violation={hasViolation ? "true" : "false"}
      className={`space-y-3 rounded-control border p-3 ${hasViolation ? "border-destructive/60 bg-destructive/5" : "border-border"}`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge tone="muted">{role}</StatusBadge>
        {section ? <span className="text-xs text-muted-foreground">{section}</span> : null}
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <p className="font-sans text-xs font-semibold uppercase tracking-wide text-muted-foreground">Before</p>
          <p data-slot="before-diff" className="whitespace-pre-wrap text-sm text-muted-foreground">
            {before ? <WordDiff before={before} after={after} side="before" /> : "(this paragraph is not in the stored document)"}
          </p>
        </div>
        <div className="space-y-1">
          <Label htmlFor={afterId}>After</Label>
          {!showTextarea ? (
            <div
              data-slot="after-preview"
              aria-hidden="true"
              onClick={editable ? () => document.getElementById(afterId)?.focus() : undefined}
              className={`min-h-16 whitespace-pre-wrap rounded-lg border border-input px-2.5 py-2 text-sm text-foreground ${editable ? "cursor-text hover:border-primary/50" : ""}`}
            >
              {before ? <WordDiff before={before} after={after} side="after" /> : after}
            </div>
          ) : null}
          <Textarea
            id={afterId}
            value={after}
            rows={3}
            readOnly={!editable}
            // A read-only pane is not something to tab into: the sr-only mirror of the preview would
            // otherwise put an unreachable-looking stop between every change card.
            tabIndex={editable ? undefined : -1}
            aria-invalid={hasViolation}
            onChange={(e) => onChange(e.target.value)}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            className={showTextarea ? "" : "sr-only"}
          />
        </div>
      </div>
      <p className="text-xs text-muted-foreground">{reason}</p>
    </li>
  );
}
