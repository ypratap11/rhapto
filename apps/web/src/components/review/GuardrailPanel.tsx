"use client";

import Link from "next/link";
import { Check } from "lucide-react";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { GuardrailReport } from "@/lib/api/queries";

/**
 * A `completeness` violation names a block that is ABSENT from the document, so its `path` is
 * `selection.block_ids['<id>']`: it addresses no node, and a click on it would do nothing on the
 * review page. Only this prefix is treated as node-less. Every other path stays a button --
 * `sections[..]`, `summary[..]`, `cover_note`, and a tune-mode `edits[..]`, which the review
 * page's `scrollToChange` and the job page's `?path=` link both depend on.
 *
 * A node-less row never gets a button. Where the panel sits away from the document (the job page),
 * the caller passes `nodelessHref` and the row gets a plain link to the resume page instead.
 */
const NODELESS_PATH_PREFIX = "selection.";

const FIX_CLASS =
  "inline-flex min-h-11 shrink-0 items-center rounded-full border border-border px-4 text-sm font-medium hover:bg-muted";

type Violation = GuardrailReport["violations"][number];

/**
 * `checks` (what each rule that ran promises) and `remedies` (what to do about a failure) are keyed
 * by rule id and come from the API; no sentence is written here. A rule missing from either map
 * still renders: a check line falls back to "Checked: <rule id>", and a violation with no remedy
 * shows the engine's message instead, so a historical report is never blanked out.
 */
export function GuardrailPanel({
  report,
  checks = {},
  remedies = {},
  onSelect,
  nodelessHref,
}: {
  report: GuardrailReport;
  checks?: Record<string, string>;
  remedies?: Record<string, string>;
  onSelect: (path: string) => void;
  nodelessHref?: string;
}) {
  const ruleIds = [...new Set(report.rules_run)];
  const errors = report.violations.filter((v) => v.severity === "error");
  const warnings = report.violations.filter((v) => v.severity !== "error");

  function line(v: Violation): string {
    return remedies[v.rule] ?? v.message;
  }

  // A control is only drawn for a row with a node to go to (or a link target); only those take a
  // number. Rows whose computed label repeats get "(n of m)" so each control is named uniquely.
  const hasControl = (v: Violation) => !v.path.startsWith(NODELESS_PATH_PREFIX) || Boolean(nodelessHref);
  const labelTotals = new Map<string, number>();
  for (const v of [...(report.passed ? [] : errors), ...warnings]) {
    if (hasControl(v)) labelTotals.set(`Fix: ${line(v)}`, (labelTotals.get(`Fix: ${line(v)}`) ?? 0) + 1);
  }
  const labelSeen = new Map<string, number>();
  function fixLabel(v: Violation): string {
    const base = `Fix: ${line(v)}`;
    const total = labelTotals.get(base) ?? 1;
    if (total < 2) return base;
    const n = (labelSeen.get(base) ?? 0) + 1;
    labelSeen.set(base, n);
    return `${base} (${n} of ${total})`;
  }

  function fixControl(v: Violation) {
    if (!hasControl(v)) return null;
    const label = fixLabel(v);
    if (!v.path.startsWith(NODELESS_PATH_PREFIX)) {
      return (
        <button type="button" aria-label={label} onClick={() => onSelect(v.path)} className={FIX_CLASS}>
          Fix
        </button>
      );
    }
    if (nodelessHref) {
      return (
        <Link href={nodelessHref} aria-label={label} className={FIX_CLASS}>
          Fix
        </Link>
      );
    }
    return null;
  }

  function violationList(items: Violation[], accent: string) {
    return (
      <ul className="space-y-2">
        {items.map((v, i) => (
          <li
            key={`${v.path}-${i}`}
            className={`flex flex-wrap items-center justify-between gap-3 rounded-control border border-border border-l-4 bg-surface px-3 py-2.5 text-sm ${accent}`}
          >
            <span className="min-w-0 flex-1">{line(v)}</span>
            {fixControl(v)}
          </li>
        ))}
      </ul>
    );
  }

  return (
    <section aria-labelledby="guardrails-heading" className="space-y-3 rounded-card border border-border bg-surface p-4 shadow-card">
      <div className="flex items-center justify-between">
        <h3 id="guardrails-heading" className="font-sans text-sm font-medium">
          Truth check
        </h3>
        <StatusBadge tone={report.passed ? "high" : "mid"}>{report.passed ? "Passed" : "Needs attention"}</StatusBadge>
      </div>
      {report.passed ? (
        <ul aria-label="What was checked" className="space-y-1.5">
          {ruleIds.map((id) => (
            <li key={id} className="flex items-start gap-2 text-sm text-muted-foreground">
              <Check className="mt-0.5 size-4 shrink-0 text-fit-high" aria-hidden />
              <span>{checks[id] ?? `Checked: ${id.replaceAll("-", " ")}`}</span>
            </li>
          ))}
        </ul>
      ) : (
        <>
          <p className="text-sm">Rhapto held this resume back because some lines did not pass the truth check.</p>
          {errors.length > 0 ? violationList(errors, "border-l-destructive") : null}
        </>
      )}
      {warnings.length > 0 ? (
        <div className="space-y-2">
          <p className="text-xs font-medium text-muted-foreground">Heads up</p>
          {violationList(warnings, "border-l-fit-mid")}
        </div>
      ) : null}
      <details className="text-xs text-muted-foreground">
        <summary className="flex min-h-11 cursor-pointer items-center">Details</summary>
        <div className="space-y-3 pb-2">
          <p>
            Checks that ran:{" "}
            {ruleIds.map((r) => (
              <span key={r} className="mr-2 font-mono">
                {r}
              </span>
            ))}
          </p>
          {report.violations.map((v, i) => (
            <div key={`${v.path}-${i}`} className="space-y-0.5">
              <p className="flex flex-wrap items-center gap-1.5">
                <span className="font-mono font-medium">{v.rule}</span>
                <span>{v.severity}</span>
                {v.block_id ? <span className="font-mono">{v.block_id}</span> : null}
              </p>
              <p className="text-foreground">{v.message}</p>
              <p className="font-mono">{v.path}</p>
            </div>
          ))}
        </div>
      </details>
    </section>
  );
}
