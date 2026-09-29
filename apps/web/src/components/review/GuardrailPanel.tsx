"use client";

import Link from "next/link";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { GuardrailReport } from "@/lib/api/queries";

/**
 * A `completeness` violation names a block that is ABSENT from the document, so its `path` is
 * `selection.block_ids['<id>']`: it addresses no node, and a click on it would do nothing on the
 * review page. Only this prefix is treated as node-less. Every other path stays a button --
 * `sections[..]`, `summary[..]`, `cover_note`, and a tune-mode `edits[..]`, which the review
 * page's `scrollToChange` and the job page's `?path=` link both depend on.
 *
 * A node-less row is never a button. Where the panel sits away from the document (the job page),
 * the caller passes `nodelessHref` and the row becomes a plain link to the package page instead.
 */
const NODELESS_PATH_PREFIX = "selection.";

/**
 * `remedies` is keyed by rule id and comes from `PackageOut.guardrail_remedies`.
 *
 * It is optional, and a rule missing from it is rendered WITHOUT a remedy line rather than with a
 * blank one or not at all. That fallback is the point: a rule added server-side before this map knew
 * about it, or a historical report naming a rule this build dropped, must still show its id, its
 * message and its bullet. A bare `remedies[v.rule]` lookup rendered into the row would have blanked
 * exactly those cases out — the ones a user most needs to see.
 */
export function GuardrailPanel({
  report,
  remedies = {},
  onSelect,
  nodelessHref,
}: {
  report: GuardrailReport;
  remedies?: Record<string, string>;
  onSelect: (path: string) => void;
  nodelessHref?: string;
}) {
  return (
    <section aria-labelledby="guardrails-heading" className="space-y-3 rounded-card border border-border bg-surface p-4 shadow-card">
      <div className="flex items-center justify-between">
        <h3 id="guardrails-heading" className="font-sans text-sm font-medium">
          Guardrails
        </h3>
        <StatusBadge tone={report.passed ? "high" : "mid"}>{report.passed ? "passed" : "blocked"}</StatusBadge>
      </div>
      {report.passed ? <p className="text-sm text-muted-foreground">All guardrails passed.</p> : null}
      {report.violations.length > 0 ? (
        <ul className="space-y-2">
          {report.violations.map((v, i) => {
            // A warning does not block the package, so it must not be dressed as the thing that did.
            const isError = v.severity === "error";
            const remedy = remedies[v.rule];
            const hasNode = !v.path.startsWith(NODELESS_PATH_PREFIX);
            const rowClass = `w-full rounded-control border border-border border-l-4 bg-surface px-3 py-2.5 text-left text-sm ${
              isError ? "border-l-destructive" : "border-l-fit-mid"
            }`;
            const body = (
              <>
                <span className="flex flex-wrap items-center gap-1.5">
                  <span
                    className={`inline-flex items-center rounded-chip px-2 py-0.5 font-mono text-xs font-medium ${
                      isError ? "bg-destructive/10 text-destructive" : "bg-fit-mid/10 text-fit-mid"
                    }`}
                  >
                    {v.rule}
                  </span>
                  <span className="text-xs text-muted-foreground">{v.severity}</span>
                  {/* Which block the bullet came from: the path says where it is in the document,
                      `block_id` says what to go and edit in the library. */}
                  {v.block_id ? <span className="font-mono text-xs text-muted-foreground">{v.block_id}</span> : null}
                </span>
                <span className="mt-1.5 block text-foreground">{v.message}</span>
                <span className="mt-0.5 block font-mono text-xs text-muted-foreground">{v.path}</span>
                {remedy ? <span className="mt-1.5 block text-xs text-muted-foreground">{remedy}</span> : null}
              </>
            );
            let row;
            if (hasNode) {
              row = (
                <button type="button" onClick={() => onSelect(v.path)} className={`hover-lift ${rowClass}`}>
                  {body}
                </button>
              );
            } else if (nodelessHref) {
              row = (
                <Link href={nodelessHref} className={`hover-lift block ${rowClass}`}>
                  {body}
                </Link>
              );
            } else {
              row = <div className={rowClass}>{body}</div>;
            }
            return <li key={`${v.path}-${i}`}>{row}</li>;
          })}
        </ul>
      ) : null}
      <p className="text-xs text-muted-foreground">
        Rules run:{" "}
        {report.rules_run.map((r) => (
          <span key={r} className="mr-2 font-mono">
            {r}
          </span>
        ))}
      </p>
    </section>
  );
}
