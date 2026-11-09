import type { ReactNode } from "react";
import type { OverviewOut } from "@/lib/admin/types";

function percent(part: number, whole: number): string {
  if (!(whole > 0) || !Number.isFinite(part)) return "0%";
  const p = Math.min(100, Math.max(0, (part / whole) * 100));
  return `${Math.round(p * 10) / 10}%`;
}

function Bar({ width, testId }: { width: string; testId?: string }) {
  return (
    <div className="h-2 overflow-hidden rounded-full bg-surface-muted" aria-hidden="true">
      <div data-testid={testId} className="h-full rounded-full bg-fit-high" style={{ width }} />
    </div>
  );
}

function Tile({ label, value, testId, children }: { label: string; value: string; testId: string; children?: ReactNode }) {
  return (
    <div className="flex min-h-11 flex-col gap-1.5 rounded-2xl border border-border bg-surface px-[18px] py-4">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span data-testid={testId} className="font-heading text-[28px] leading-none font-semibold tabular-nums text-foreground">
        {value}
      </span>
      {children}
    </div>
  );
}

const hint = "text-[0.8rem] text-muted-foreground";

export function OverviewTiles({ overview: o }: { overview: OverviewOut }) {
  const spend = Number(o.free_spend_month_usd);
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
      <Tile label="Sign-ups" value={String(o.signups_total)} testId="value-signups">
        <span className={hint}>+{o.signups_today} today</span>
      </Tile>
      <Tile label="Free spend this month" value={`$${o.free_spend_month_usd}`} testId="value-spend">
        {o.budget_usd === null ? (
          <span className={hint}>no budget set</span>
        ) : (
          <>
            <Bar width={percent(spend, o.budget_usd)} testId="spend-bar" />
            <span className={hint}>of ${o.budget_usd}</span>
          </>
        )}
      </Tile>
      <Tile label="Sign-in limit" value={`${o.accounts} / ${o.account_cap}`} testId="value-limit">
        <Bar width={percent(o.accounts, o.account_cap)} />
        <span className={hint}>estimate, counted from accounts</span>
      </Tile>
      <Tile label="Want more resumes" value={String(o.want_more_users)} testId="value-more">
        <span className={hint}>people asked</span>
      </Tile>
      <Tile label="Failed runs, last 7 days" value={String(o.failed_7d)} testId="value-failed">
        <span className={hint}>across all users</span>
      </Tile>
    </div>
  );
}
