import { existsSync, readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

// Tailoring in these specs must not call a real provider. Run the stack with
// RHAPTO_LLM_PROVIDER=fake, which portal-backend registers in
// apps/api/src/rhapto/engine/providers/registry.py against
// rhapto.engine.providers.fake.FakeLLMProvider. If that entry is missing, the tailor specs will
// fail at the Tailor button with a provider error — skip them with test.skip() and say why,
// rather than pointing the suite at a paid API.
//
// A second, unrelated hazard lives in the *profile*, not the provider: `POST
// /profile/resume-document` (the file behind Profile > Resume template, and the default for
// "tune" mode) is a separate resource from blocks.yaml/tracks.yaml/etc. and is **not** touched by
// the profile.example re-import below. On a long-lived dev stack it can still hold a real,
// previously-uploaded resume (name, email, phone, employer). Every spec in this suite therefore
// either (a) explicitly picks "Build from blocks" in the Tailor button's Mode select rather than
// letting a resume document default it to "tune", or (b) only ever tailors after
// profile.spec.ts has replaced the document with e2e/fixtures/resume-template.docx (the fictional
// "Maya Chen" fixture also used by apps/api's own tests, see apps/api/tests/helpers_docx.py). Never
// read `profile/` (the real, gitignored profile) here or anywhere else in this suite — only
// `profile.example/`.

const REPO_ROOT = resolve(__dirname, "../../..");
const PROFILE_EXAMPLE_DIR = resolve(REPO_ROOT, "profile.example");

function readEnvFile(path: string): Record<string, string> {
  if (!existsSync(path)) return {};
  const env: Record<string, string> = {};
  for (const line of readFileSync(path, "utf8").split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq === -1) continue;
    env[trimmed.slice(0, eq).trim()] = trimmed.slice(eq + 1).trim();
  }
  return env;
}

export default async function globalSetup(): Promise<void> {
  const fileEnv = readEnvFile(resolve(REPO_ROOT, ".env"));
  const token = process.env.RHAPTO_API_TOKEN ?? fileEnv.RHAPTO_API_TOKEN ?? "";
  const apiUrl = process.env.RHAPTO_PUBLIC_API_URL ?? fileEnv.RHAPTO_PUBLIC_API_URL ?? "http://localhost:8000";
  // Propagate to the worker processes Playwright spawns after globalSetup returns: fixtures.ts and
  // every spec read these two from process.env, and there is no other channel to hand them values
  // computed here (or read from a .env file two directories up from apps/web/e2e).
  process.env.RHAPTO_API_TOKEN = token;
  process.env.RHAPTO_PUBLIC_API_URL = apiUrl;

  if (!token) {
    throw new Error(
      "RHAPTO_API_TOKEN is empty (checked the environment and the repo root's .env). Set it before running `pnpm e2e`.",
    );
  }
  const auth = { Authorization: `Bearer ${token}` };

  // Seed the stack with profile.example, exactly the way scripts/smoke-api.sh does: multipart
  // POST with every profile.example/*.yaml file. DESTRUCTIVE — replaces whatever profile is
  // currently loaded — which is the point: the specs and the screenshot script must run against
  // known, fictional data, never whatever a prior manual session left behind.
  const files = readdirSync(PROFILE_EXAMPLE_DIR).filter((f) => f.endsWith(".yaml"));
  if (files.length === 0) {
    throw new Error(`No *.yaml files found under ${PROFILE_EXAMPLE_DIR}`);
  }
  const form = new FormData();
  for (const f of files) {
    const buf = readFileSync(resolve(PROFILE_EXAMPLE_DIR, f));
    form.append("files", new Blob([buf]), f);
  }
  const importUrl = `${apiUrl}/api/v1/profile/import`;
  const importRes = await fetch(importUrl, { method: "POST", headers: auth, body: form });
  if (!importRes.ok) {
    throw new Error(
      `profile.example import failed: POST ${importUrl} -> ${importRes.status} ${await importRes.text()}`,
    );
  }

  // Fail loudly with the URL and status if the stack is not up, so a missing `docker compose up
  // -d` (or a stopped api/db/redis container) never looks like a UI bug three specs later.
  const meUrl = `${apiUrl}/api/v1/me`;
  const meRes = await fetch(meUrl, { headers: auth });
  if (!meRes.ok) {
    throw new Error(
      `Stack not reachable/healthy: GET ${meUrl} -> ${meRes.status} ${await meRes.text()}. ` +
        "Run `docker compose up -d` (db, redis, api, worker) from the repo root before `pnpm e2e`.",
    );
  }
  const me = (await meRes.json()) as { email?: string };
  const expectedEmail = fileEnv.RHAPTO_USER_EMAIL;
  if (expectedEmail && me.email !== expectedEmail) {
    throw new Error(
      `GET ${meUrl} returned email ${String(me.email)}, expected ${expectedEmail} (.env's ` +
        "RHAPTO_USER_EMAIL). The profile.example import above should have made these match — refusing to " +
        "run the suite against a profile that might not be profile.example.",
    );
  }

  // The comment at the top of this file has said it since the first version of this suite: tailoring
  // here must not call a real provider. Until now nothing actually checked that — a stack running its
  // default (real) provider would silently tailor through the real Anthropic API on every `pnpm e2e`
  // run: real latency, real cost, and non-deterministic output the specs' assertions were never
  // written to tolerate. Fail loudly, before a single spec runs, instead of leaving that to be
  // noticed in a bill or a flaky assertion.
  const llmUrl = `${apiUrl}/api/v1/settings/llm`;
  const llmRes = await fetch(llmUrl, { headers: auth });
  if (!llmRes.ok) {
    throw new Error(`GET ${llmUrl} -> ${llmRes.status} ${await llmRes.text()}`);
  }
  const llm = (await llmRes.json()) as { provider?: string | null };
  if (llm.provider !== "fake") {
    throw new Error(
      `GET ${llmUrl} reports provider ${JSON.stringify(llm.provider)}, not "fake". This suite must never tailor ` +
        "through a real LLM provider (real latency, real cost, non-deterministic output). Run the stack with " +
        "RHAPTO_LLM_PROVIDER=fake, e.g. `docker compose -f docker-compose.yml -f docker-compose.e2e.yml up -d` " +
        "from the repo root, before `pnpm e2e`.",
    );
  }

  // Saved searches are not reset by the profile import above (they are their own table, not part
  // of profile.example's YAML files) and jobs.spec.ts's "Save this search" step hides its button
  // once a search with the same name already exists — so a search left over from a previous run
  // would make that step silently untestable instead of failing. Clear the slate here rather than
  // widen the spec's own assertions to tolerate stale state.
  const searchesUrl = `${apiUrl}/api/v1/searches`;
  const searchesRes = await fetch(searchesUrl, { headers: auth });
  if (searchesRes.ok) {
    const searches = (await searchesRes.json()) as { id: string }[];
    for (const s of searches) {
      await fetch(`${searchesUrl}/${s.id}`, { method: "DELETE", headers: auth });
    }
  }
}
