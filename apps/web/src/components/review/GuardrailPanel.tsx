"use client";

import { StatusBadge } from "@/components/ui/StatusBadge";
import type { GuardrailReport } from "@/lib/api/queries";

export function GuardrailPanel({ report, onSelect }: { report: GuardrailReport; onSelect: (path: string) => void }) {
  return (
    <section aria-labelledby="guardrails-heading" className="space-y-3 rounded-md border border-border bg-card p-4">
      <div className="flex items-center justify-between">
        <h3 id="guardrails-heading" className="font-sans text-sm font-medium">
          Guardrails
        </h3>
        <StatusBadge tone={report.passed ? "green" : "amber"}>{report.passed ? "passed" : "blocked"}</StatusBadge>
      </div>
      {report.passed ? <p className="text-sm text-muted-foreground">All guardrails passed.</p> : null}
      {report.violations.length > 0 ? (
        <ul className="space-y-2">
          {report.violations.map((v, i) => (
            <li key={`${v.path}-${i}`}>
              <button type="button" onClick={() => onSelect(v.path)} className="w-full rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-left text-sm hover:bg-amber-100">
                <span className="font-mono text-xs text-amber-900">{v.rule}</span>
                <span className="block">{v.message}</span>
                <span className="block font-mono text-xs text-muted-foreground">{v.path}</span>
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
