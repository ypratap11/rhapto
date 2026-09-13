# Multi-provider LLM support — design

Date: 2026-09-12. Status: approved in chat; plan to follow. Builds on main after tune-my-resume mode (4c3b684).
First of two specs for the open-source first-run experience; the second (resume-first onboarding, three-step
home, paste-a-job) depends on this one for "paste your key in the UI".

## 1. Goal

Any user can run Rhapto with the LLM key they already have (Anthropic, OpenAI, or Google Gemini), entered once in
the app's Settings page, with no file editing. Existing `.env` setups and the CLI keep working unchanged.

## 2. Non-goals

Provider-hosted embeddings (scoring keeps the local FastEmbed model); LiteLLM or any routing library; per-task or
per-job provider switching; multiple keys per provider; streaming.

## 3. Provider adapters and registry (`rhapto.engine.providers`)

The `LLMProvider` protocol is unchanged: `complete_structured(*, system: list[SystemBlock], messages: list[Message],
output_schema: type[T], max_tokens: int = 4096) -> StructuredResult[T]`.

Adapters:
- `anthropic.py` — existing, unchanged.
- `openai.py` — official `openai` SDK, chat completions with structured outputs (`response_format` = JSON schema
  from the Pydantic model, `strict: true`). System blocks are joined in order into one system message; the
  `cache` flag is ignored (OpenAI caches prefixes automatically). A refusal, a parse failure, or a schema
  mismatch raises `MalformedOutputError`. Usage maps `prompt_tokens`/`completion_tokens` (and
  `prompt_tokens_details.cached_tokens` into `cache_read_input_tokens`).
- `gemini.py` — official `google-genai` SDK, `generate_content` with `response_mime_type="application/json"` and
  `response_schema`. System blocks join into `system_instruction`. Because Gemini's schema dialect is narrower than
  Pydantic's JSON Schema, the adapter converts the schema with `schema_for_gemini(model)` (inlines `$ref`s, drops
  `additionalProperties`/`default`/`title`, turns `anyOf [X, null]` into a nullable `X`) and the tests assert the
  conversion succeeds for every engine schema (`JDExtract`, `ComposeOutput`, `TuneOutput`). Parse failures raise
  `MalformedOutputError`. Usage maps `prompt_token_count`/`candidates_token_count`/`cached_content_token_count`.

Errors: a new `ProviderAuthError(EngineError)` wraps 401/403 and quota/billing errors from any SDK with the
provider's message; rate limits keep the SDKs' built-in retries and otherwise surface as `EngineError`.

Registry (`registry.py`):

```
PROVIDERS = {
  "anthropic": ProviderInfo(label="Anthropic", models=["claude-opus-5", "claude-sonnet-5"], default="claude-sonnet-5", env_key="ANTHROPIC_API_KEY"),
  "openai":    ProviderInfo(label="OpenAI", models=["gpt-5", "gpt-5-mini"], default="gpt-5", env_key="OPENAI_API_KEY"),
  "gemini":    ProviderInfo(label="Google Gemini", models=["gemini-2.5-pro", "gemini-2.5-flash"], default="gemini-2.5-pro", env_key="GEMINI_API_KEY"),
}
def build_llm(provider: str, model: str, api_key: str) -> LLMProvider
```

Unknown provider ids raise `EngineError`; any model id is accepted ("other" in the UI passes straight through).
Dependencies added to `apps/api`: `openai>=1.60`, `google-genai>=1.0`. The engine still imports nothing from
config/profile/db/services/worker/api/cli.

## 4. Key storage

Table `llm_settings` (migration 0004): `user_id` (unique FK, cascade), `provider` String(20), `model` String(100),
`api_key_encrypted` Text, timestamps. Keys are encrypted with Fernet (`cryptography`) using `RHAPTO_SECRET_KEY`
from `.env`; `services/secrets.py` exposes `encrypt(text) -> str` / `decrypt(token) -> str` and raises a clear
error when the secret is missing or changed. When `RHAPTO_SECRET_KEY` is empty the key is derived from
`RHAPTO_API_TOKEN` (sha256, urlsafe base64) so existing setups need no new step; `.env.example` documents both.

API (`/api/v1/settings/llm`):
- `GET` → `{provider, model, key_set: bool, key_hint: str | null, source: "settings" | "env" | "none",
  providers: [{id, label, models, default}]}`. `key_hint` is the last four characters (`…4Qx2`); the raw key is
  never returned. `source: "env"` means no row exists and the environment provides the key.
- `PUT` body `{provider, model, api_key?: str}` → 200 with the same shape. Omitting `api_key` keeps the stored key
  when the provider is unchanged; switching provider without a key (and no env key for it) is a 422.
- `POST .../test` body `{provider, model, api_key?: str}` (key optional: falls back to the stored or env key) → runs
  one tiny structured call (`Ping{ok: bool}`) and returns `{ok: true, model}` or `{ok: false, error}` (200 either
  way).
- `DELETE` removes the row (falls back to env).

## 5. Runtime resolution

`services/llm.py`: `async def resolve_llm(session, user_id, settings) -> LLMProvider` — the stored row if present,
else the environment (`RHAPTO_LLM_PROVIDER`, default `anthropic`; `RHAPTO_LLM_MODEL`, default the provider's
default; the provider's env key), else raises `LLMNotConfiguredError("No LLM configured. Add a key in Settings.")`.
Providers are cached per process keyed by `(provider, model, sha256(key))` so clients are not rebuilt per task.

- Worker: `tailor_job` (the only task that calls the LLM; scoring is embedding-based) calls `resolve_llm` at
  task start; `ctx["llm"]` is removed. A `LLMNotConfiguredError` or `ProviderAuthError` fails the
  task with that message (no traceback) and the task event carries it.
- API: `POST /jobs/{id}/tailor` calls `resolve_llm` first and returns 409 `{"detail": "No LLM configured…",
  "code": "llm_not_configured"}` so the UI can link to Settings. `GET /me` gains `llm_configured: bool`.
- CLI: `rhapto tailor` and `rhapto score` gain `--provider` and `--model` (defaults from the environment as above);
  the CLI never reads the database. `build_providers` uses the registry.
- `AnthropicProvider` construction sites (`worker/main.py`, `cli/main.py`) are replaced by the registry.

## 6. Settings UI

The Settings page gains an **AI provider** section at the top. Three cards (Anthropic, OpenAI, Google Gemini); the
selected card expands to show: key field (`type=password`, placeholder shows `…4Qx2` when a key exists, label
"API key"), the curated model radio list with an **Other** option and text field, **Test connection**, **Save**.
A status line: "Using OpenAI · gpt-5 · key set" / "Using Anthropic from .env" / "No AI provider configured".
Test shows a green check with the model or the provider's error text inline. Save shows a toast and refreshes
`/me`.

Elsewhere: when `/me` reports `llm_configured: false`, the Jobs page's Next up panel and each Tailor button show a
"Set up your AI provider" link to Settings instead of starting a task; a 409 `llm_not_configured` from tailor
shows the same link in a toast.

## 7. Testing

- Adapters (mocked SDK clients): happy path parses into the schema; refusal/garbage → `MalformedOutputError`;
  401/403/quota → `ProviderAuthError`; usage mapping; system block joining; Gemini schema conversion for every
  engine schema and a round-trip parse of a sample `TuneOutput`.
- Registry: curated lists, defaults, unknown provider, "other" model id.
- Secrets: encrypt/decrypt round trip; wrong/missing secret → clear error.
- Settings API: PUT/GET never return the raw key, hint is last four; PUT without key keeps the key; provider switch
  without key → 422; DELETE falls back to env; test endpoint with a fake provider, both outcomes.
- Resolution: stored row wins over env; env fallback; none → `LLMNotConfiguredError`; cache keyed by key hash.
- Worker: saving a row changes the provider used by the next task (fake registry); not-configured fails the task
  cleanly. API: tailor returns 409 when not configured.
- Web: card selection, masked key, model list with Other, Test and Save flows, status line states, the
  "Set up your AI provider" prompt on Jobs.
- Existing golden/pipeline suites unchanged (fake provider).

## 8. Constraints carried over

Max 3 LLM calls per run; prompt-cached static blocks where the provider supports it; nothing submits; no personal
data or keys in the repo (`.env` gitignored; tests use fake keys); engine purity; import-linter contracts; TypeScript
strict.
