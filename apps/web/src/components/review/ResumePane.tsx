"use client";

import { useState } from "react";
import type { Block, ResumeDocument } from "@/lib/api/queries";
import { isSameResume, removeBullet, updateBulletText } from "@/lib/resume-edit";
import { bulletPath, entryPath, summaryPath } from "@/lib/resume-paths";
import { Button } from "@/components/ui/button";
import { BulletRow } from "./BulletRow";

export function ResumePane({
  resume,
  blocks,
  selectedPath,
  onSelect,
  violationsByPath,
  onSave,
}: {
  resume: ResumeDocument;
  blocks: Map<string, Block>;
  selectedPath: string | null;
  onSelect: (path: string) => void;
  violationsByPath: Set<string>;
  onSave?: (resume: ResumeDocument) => Promise<void>;
}) {
  // The pane is keyed by package id from the page, so a new `resume` prop
  // always mounts a fresh instance here -- no effect needed to re-sync draft.
  const [draft, setDraft] = useState(resume);
  const [saving, setSaving] = useState(false);
  const editable = Boolean(onSave);
  const dirty = !isSameResume(draft, resume);

  function handleChange(path: string, text: string) {
    setDraft((d) => updateBulletText(d, path, text));
  }

  function handleRemove(path: string) {
    setDraft((d) => removeBullet(d, path));
  }

  async function handleSave() {
    if (!onSave) return;
    setSaving(true);
    try {
      await onSave(draft);
    } finally {
      setSaving(false);
    }
  }

  const h = draft.header;
  return (
    <article className="space-y-6 rounded-md border border-border bg-card p-6">
      <header>
        <h2 className="text-2xl">{h.name}</h2>
        <p className="text-sm text-muted-foreground">{[h.email, h.phone, h.location, ...h.links].filter(Boolean).join(" · ")}</p>
      </header>
      {draft.summary.length ? (
        <section>
          <h3 className="mb-2 font-sans text-xs font-semibold uppercase tracking-wide text-muted-foreground">Summary</h3>
          <ul className="space-y-1">
            {draft.summary.map((b, i) => (
              <BulletRow
                key={summaryPath(i)}
                path={summaryPath(i)}
                text={b.text}
                sourceBlockId={b.source_block_id}
                block={blocks.get(b.source_block_id) ?? null}
                selected={selectedPath === summaryPath(i)}
                hasViolation={violationsByPath.has(summaryPath(i))}
                onSelect={onSelect}
                editable={editable}
                onChange={handleChange}
                onRemove={handleRemove}
              />
            ))}
          </ul>
        </section>
      ) : null}
      {draft.sections.map((section, s) => (
        <section key={`${section.kind}-${s}`}>
          <h3 className="mb-2 font-sans text-xs font-semibold uppercase tracking-wide text-muted-foreground">{section.title || section.kind}</h3>
          <div className="space-y-4">
            {section.entries.map((entry, e) => {
              const ep = entryPath(s, e);
              const head = [entry.role ?? entry.title, entry.org, entry.period].filter(Boolean).join(" | ");
              return (
                <div key={ep} className={`rounded-md ${violationsByPath.has(ep) ? "ring-1 ring-amber-300" : ""}`}>
                  {head ? (
                    <button type="button" onClick={() => onSelect(ep)} className={`mb-1 text-left font-medium ${selectedPath === ep ? "text-accent" : ""}`}>
                      {head}
                    </button>
                  ) : null}
                  <ul className="space-y-1">
                    {entry.bullets.map((b, i) => (
                      <BulletRow
                        key={bulletPath(s, e, i)}
                        path={bulletPath(s, e, i)}
                        text={b.text}
                        sourceBlockId={b.source_block_id}
                        block={blocks.get(b.source_block_id) ?? null}
                        selected={selectedPath === bulletPath(s, e, i)}
                        hasViolation={violationsByPath.has(bulletPath(s, e, i))}
                        onSelect={onSelect}
                        editable={editable}
                        onChange={handleChange}
                        onRemove={handleRemove}
                      />
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
        </section>
      ))}
      {dirty ? (
        <div className="sticky bottom-4 flex items-center justify-between rounded-md border border-accent bg-card p-3 shadow-sm">
          <span className="text-sm">Unsaved edits. Saving re-runs the guardrails and creates a new version.</span>
          <div className="flex gap-2">
            <Button type="button" variant="outline" onClick={() => setDraft(resume)}>
              Discard
            </Button>
            <Button type="button" onClick={handleSave} disabled={saving}>
              {saving ? "Saving…" : "Save as new version"}
            </Button>
          </div>
        </div>
      ) : null}
    </article>
  );
}
