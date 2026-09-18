"use client";

import { StatusBadge } from "@/components/ui/StatusBadge";
import type { GuardrailReport } from "@/lib/api/queries";

export function GuardrailPanel({ report, onSelect }: { report: GuardrailReport; onSelect: (path: string) => void }) {
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
          {report.violations.map((v, i) => (
            <li key={`${v.path}-${i}`}>
              <button
                type="button"
                onClick={() => onSelect(v.path)}
                className="hover-lift w-full rounded-control border border-border border-l-4 border-l-destructive bg-surface px-3 py-2.5 text-left text-sm"
              >
                <span className="inline-flex items-center rounded-chip bg-destructive/10 px-2 py-0.5 font-mono text-xs font-medium text-destructive">{v.rule}</span>
                <span className="mt-1.5 block text-foreground">{v.message}</span>
                <span className="mt-0.5 block font-mono text-xs text-muted-foreground">{v.path}</span>
              </button>
            </li>
          ))}
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
