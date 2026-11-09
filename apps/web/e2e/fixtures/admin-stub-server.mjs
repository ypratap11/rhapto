// A stand-in for the API, used only by playwright.admin.config.ts. Fictional data at example.com.
// Admin means: the request carries a Cf-Access-Jwt-Assertion whose payload says admin. No signature
// check; the real API does that.
import http from "node:http";

const PORT = Number(process.env.ADMIN_STUB_PORT ?? 8107);
const USER_ID = "00000000-0000-4000-8000-000000000001";
const NOW = Date.now();
const iso = (minutesAgo) => new Date(NOW - minutesAgo * 60_000).toISOString();

function isAdmin(req) {
  const value = req.headers["cf-access-jwt-assertion"];
  if (typeof value !== "string") return false;
  try {
    return JSON.parse(Buffer.from(value.split(".")[1], "base64url").toString("utf8")).admin === true;
  } catch {
    return false;
  }
}

const alerts = [
  { id: "budget", tone: "warn", title: "Free spend may reach the budget before the 1st", detail: "At the last three days' pace, $50.00 is reached in about 6 days." },
  { id: "duplicates", tone: "warn", title: "Possible duplicate accounts", detail: "ana.fictional@example.com and ana.fictional+work@example.com look like the same person." },
  { id: "failures", tone: "warn", title: "Failed runs jumped", detail: "9 failed today, against a daily average of 2 over the previous 7 days." },
  { id: "ready_to_ask", tone: "info", title: "People are asking for more resumes", detail: "7 people used all their free runs and asked for more. Ready to ask: 10 paying or 30 asking." },
  { id: "signin_limit", tone: "info", title: "Sign-in limit is getting close", detail: "41 of 50 accounts (estimate, counted from accounts)." },
];

const overview = {
  signups_total: 41,
  signups_today: 3,
  free_spend_month_usd: "38.40",
  budget_usd: 50,
  accounts: 41,
  account_cap: 50,
  want_more_users: 7,
  failed_7d: 12,
  alerts,
};

const users = [
  { id: USER_ID, email: "ana.fictional@example.com", runs_used: 3, runs_limit: 3, failed_count: 2, last_seen_at: iso(5), blocked: false },
  { id: "00000000-0000-4000-8000-000000000002", email: "a.very.long.fictional.address.for.wrapping@example.com", runs_used: 1, runs_limit: 3, failed_count: 0, last_seen_at: iso(300), blocked: false },
  { id: "00000000-0000-4000-8000-000000000003", email: "ben.fictional@example.com", runs_used: 0, runs_limit: 3, failed_count: 0, last_seen_at: iso(4000), blocked: true },
];

const categories = [
  ["blocked", "This account was blocked"],
  ["trial_limit", "The free runs were already used"],
  ["free_runs_paused", "Free runs are paused for everyone"],
  ["key_not_configured", "No AI key is set up"],
  ["key_rejected_shared", "The shared AI key was rejected"],
  ["key_rejected_own", "Their own AI key was rejected"],
  ["key_unreadable", "Their saved AI key could not be read"],
  ["provider_error", "The AI provider had an error"],
  ["malformed_output", "The AI answered in a shape we could not use"],
  ["over_budget", "The monthly budget was reached"],
  ["profile_problem", "Their profile has a problem"],
  ["render_failed", "The resume could not be built"],
  ["guardrail_failed", "A truthfulness check stopped the resume"],
  ["document_problem", "The resume document had a problem"],
  ["job_missing", "The job was removed"],
  ["no_resume", "No resume was uploaded"],
  ["did_not_finish", "The run never finished"],
  ["other", "Something else went wrong"],
];

const detail = {
  id: USER_ID,
  email: "ana.fictional@example.com",
  joined_at: iso(60 * 24 * 12),
  runs_used: 3,
  runs_limit: 3,
  free_spend_usd: "2.10",
  asked_for_more: true,
  blocked: false,
  failures: categories.slice(0, 6).map(([category, label], i) => ({ when: iso(30 + i * 90), type: "tailor_job", category, label })),
  suggested_reset_runs: 2,
  history: [
    { when: iso(60 * 24 * 2), actor_email: "owner@example.com", action: "reset_runs", before: { trial_runs_used: 3 }, after: { trial_runs_used: 1 } },
    { when: iso(60 * 24), actor_email: "owner@example.com", action: "unblock", before: { blocked: true }, after: { blocked: false } },
  ],
};

function send(res, status, body) {
  res.writeHead(status, { "content-type": status >= 400 ? "application/problem+json" : "application/json" });
  res.end(JSON.stringify(body));
}

const server = http.createServer((req, res) => {
  const path = new URL(req.url ?? "/", "http://stub").pathname;
  req.resume();
  if (path === "/healthz") return send(res, 200, { ok: true });
  if (path === "/api/v1/me") {
    return send(res, 200, { auth_mode: "access", email: isAdmin(req) ? "owner@example.com" : "someone@example.com", llm_configured: true, user_id: USER_ID });
  }
  if (path === "/api/v1/me/bootstrap") return send(res, 200, { seeded: false });
  if (path.startsWith("/api/v1/admin/")) {
    if (!isAdmin(req)) return send(res, 404, { title: "Not Found", status: 404 });
    if (path === "/api/v1/admin/session") return send(res, 200, { ok: true });
    if (path === "/api/v1/admin/overview") return send(res, 200, overview);
    if (path === "/api/v1/admin/users/search") return send(res, 200, { users, next_offset: null });
    if (path === `/api/v1/admin/users/${USER_ID}`) return send(res, 200, detail);
  }
  return send(res, 404, { title: "Not Found", status: 404 });
});

server.listen(PORT, "127.0.0.1");
