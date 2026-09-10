"use client";

import type { Block, ResumeDocument } from "@/lib/api/queries";
import { bulletPath, entryPath, summaryPath } from "@/lib/resume-paths";
import { BulletRow } from "./BulletRow";

export function ResumePane({
  resume,
  blocks,
  selectedPath,
  onSelect,
  violationsByPath,
}: {
  resume: ResumeDocument;
  blocks: Map<string, Block>;
  selectedPath: string | null;
  onSelect: (path: string) => void;
  violationsByPath: Set<string>;
}) {
  const h = resume.header;
  return (
    <article className="space-y-6 rounded-md border border-border bg-card p-6">
      <header>
        <h2 className="text-2xl">{h.name}</h2>
        <p className="text-sm text-muted-foreground">{[h.email, h.phone, h.location, ...h.links].filter(Boolean).join(" · ")}</p>
      </header>
      {resume.summary.length ? (
        <section>
          <h3 className="mb-2 font-sans text-xs font-semibold uppercase tracking-wide text-muted-foreground">Summary</h3>
          <ul className="space-y-1">
            {resume.summary.map((b, i) => (
              <BulletRow
                key={summaryPath(i)}
                path={summaryPath(i)}
                text={b.text}
                sourceBlockId={b.source_block_id}
                block={blocks.get(b.source_block_id) ?? null}
                selected={selectedPath === summaryPath(i)}
                hasViolation={violationsByPath.has(summaryPath(i))}
                onSelect={onSelect}
              />
            ))}
          </ul>
        </section>
      ) : null}
      {resume.sections.map((section, s) => (
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
                      />
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
        </section>
      ))}
    </article>
  );
}
