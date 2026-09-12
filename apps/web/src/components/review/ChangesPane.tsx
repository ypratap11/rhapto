"use client";

import { useId, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Textarea } from "@/components/ui/textarea";
import type { DocParagraph, EditPatch, PackageOut } from "@/lib/api/queries";

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
    <div className="space-y-4">
      <section aria-labelledby="changes-heading" className="space-y-4 rounded-md border border-border bg-card p-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="changes-heading" className="font-sans text-sm font-medium">
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
        <section aria-labelledby="full-document-heading" className="space-y-2 rounded-md border border-border bg-card p-4">
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
                    className={`whitespace-pre-wrap ${edited === undefined ? "border-l-2 border-transparent pl-3" : "border-l-2 border-amber-400 bg-amber-50/50 pl-3"} ${p.role === "heading" ? "font-sans text-xs font-semibold uppercase tracking-wide text-muted-foreground" : ""}`}
                  >
                    {edited ?? p.text}
                  </li>
                );
              })}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

function ChangeCard({
  index,
  before,
  after,
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
  reason: string;
  role: string;
  section: string | null;
  hasViolation: boolean;
  editable: boolean;
  onChange: (text: string) => void;
}) {
  const afterId = useId();
  return (
    <li
      id={`change-${index}`}
      data-violation={hasViolation ? "true" : "false"}
      className={`space-y-2 rounded-md border p-3 ${hasViolation ? "border-red-400 bg-red-50/40" : "border-border"}`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge tone="zinc">{role}</StatusBadge>
        {section ? <span className="text-xs text-muted-foreground">{section}</span> : null}
      </div>
      <div className="space-y-1">
        <p className="font-sans text-xs font-semibold uppercase tracking-wide text-muted-foreground">Before</p>
        <p className="whitespace-pre-wrap text-sm text-muted-foreground">{before || "(this paragraph is not in the stored document)"}</p>
      </div>
      <div className="space-y-1">
        <Label htmlFor={afterId}>After</Label>
        <Textarea id={afterId} value={after} rows={3} readOnly={!editable} onChange={(e) => onChange(e.target.value)} />
      </div>
      <p className="text-xs text-muted-foreground">{reason}</p>
    </li>
  );
}
