// Hand-written mirror of apps/api admin_schemas.py. Admin routes are not in the public OpenAPI
// document, so these are not generated; types.test.ts fails when the API adds a field that is missing here.

export type AlertTone = "warn" | "info";

export type AlertOut = { id: string; tone: AlertTone; title: string; detail: string };

export type OverviewOut = {
  signups_total: number;
  signups_today: number;
  /** Decimal string, e.g. "18.40". */
  free_spend_month_usd: string;
  budget_usd: number | null;
  accounts: number;
  account_cap: number;
  want_more_users: number;
  failed_7d: number;
  alerts: AlertOut[];
};

export type UserSearchIn = { q?: string; offset?: number };

export type UserRowOut = {
  id: string;
  email: string;
  runs_used: number;
  runs_limit: number | null;
  /** Failed runs in the last 7 days. */
  failed_count: number;
  last_seen_at: string;
  blocked: boolean;
};

export type UserSearchOut = { users: UserRowOut[]; next_offset: number | null };

export type FailureCategory =
  | "blocked"
  | "trial_limit"
  | "free_runs_paused"
  | "key_not_configured"
  | "key_rejected_shared"
  | "key_rejected_own"
  | "key_unreadable"
  | "provider_error"
  | "malformed_output"
  | "over_budget"
  | "profile_problem"
  | "render_failed"
  | "guardrail_failed"
  | "document_problem"
  | "job_missing"
  | "no_resume"
  | "did_not_finish"
  | "other";

export type FailureOut = { when: string; type: string; category: FailureCategory; label: string };

export type ActionOut = {
  when: string;
  actor_email: string;
  action: string;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
};

export type UserDetailOut = {
  id: string;
  email: string;
  joined_at: string;
  runs_used: number;
  runs_limit: number | null;
  free_spend_usd: string;
  asked_for_more: boolean;
  blocked: boolean;
  failures: FailureOut[];
  suggested_reset_runs: number | null;
  history: ActionOut[];
};

export type ResetIn = { to: number };

export type ActionResultOut = { changed: boolean; runs_used: number | null; blocked: boolean | null };

export type AdminSessionOut = { ok: boolean };
