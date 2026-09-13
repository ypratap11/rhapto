# Multi-Provider LLM Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user run Rhapto with an Anthropic, OpenAI, or Google Gemini key entered once in Settings, stored encrypted, resolved per task by the worker, with `.env` and the CLI still working.

**Architecture:** Two new adapters beside the Anthropic one implement the unchanged `LLMProvider` protocol; a registry maps provider id + model + key to an adapter. A per-user `llm_settings` row holds the encrypted key; `services/llm.resolve_llm` picks stored row → environment → error, and the worker's tailor task calls it at start. A settings router and a Settings-page section expose it; `/me` reports whether an LLM is configured so the Jobs page can point to Settings.

**Tech Stack:** Python 3.12, `openai` SDK, `google-genai` SDK, `cryptography` (Fernet), FastAPI, SQLAlchemy/Alembic, arq; Next 16 / React 19 / TanStack Query / vitest.

**Spec:** `docs/superpowers/specs/2026-09-12-llm-providers-design.md`

## Global Constraints

- Product rules (CLAUDE.md): nothing submits; max 3 LLM calls per run (unchanged, the budget lives in the pipeline); no personal data or real keys anywhere in the repo (tests use `sk-test`-style fakes); secrets via `.env`.
- Import-linter: `rhapto.engine` imports none of config/profile/db/services/worker/api/cli (the registry and adapters are engine code and take plain strings); `services` never import worker/api/cli.
- The `LLMProvider` protocol is unchanged: `complete_structured(*, system, messages, output_schema, max_tokens=4096) -> StructuredResult[T]`. Adapters raise `MalformedOutputError` for output that does not fit the schema and `ProviderAuthError` for 401/403/quota; other SDK errors surface as `EngineError`.
- Registry contents (verbatim): anthropic → models `["claude-opus-5", "claude-sonnet-5"]`, default `claude-sonnet-5`, env key `ANTHROPIC_API_KEY`; openai → `["gpt-5", "gpt-5-mini"]`, default `gpt-5`, env key `OPENAI_API_KEY`; gemini → `["gemini-2.5-pro", "gemini-2.5-flash"]`, default `gemini-2.5-pro`, env key `GEMINI_API_KEY`. Labels: "Anthropic", "OpenAI", "Google Gemini".
- Encryption secret: `RHAPTO_SECRET_KEY` from `.env`; when empty, derive the Fernet key from `RHAPTO_API_TOKEN` (`base64.urlsafe_b64encode(sha256(token).digest())`) so no new setup step is required; when both are empty, `services/secrets` raises `SecretsError("set RHAPTO_SECRET_KEY in .env")`. (Ruling: the spec said the secret is generated like the API token; the API token is documented, not generated, so derivation is the zero-setup path.)
- Errors the API returns: tailor with no LLM → 409 `{"detail": "No LLM configured. Add a key in Settings.", "code": "llm_not_configured"}`; PUT switching provider without a key and no env key → 422.
- The raw key never leaves the server: responses carry `key_set` and `key_hint` (last four characters prefixed with `…`) only. Keys are never logged.
- Checks before every commit — Python (from `apps/api`): `uv run ruff check src tests`, `uv run ruff format src tests`, `uv run mypy src`, `uv run lint-imports`, `uv run pytest -q --deselect tests/unit/test_enqueue_arq.py -p no:cacheprovider` in the foreground (10-minute timeout; one pytest at a time). Web (from `apps/web`): `pnpm test`, `pnpm typecheck`, `pnpm lint` (one accepted warning in `TaskProgress.tsx`), `pnpm build`.
- Generated files never hand-edited: `packages/schemas/openapi.json`, `apps/web/src/lib/api/schema.d.ts` via `bash scripts/codegen.sh` from the repo root; commit them with the API change.
- Commit messages end with the two attribution lines given in the session.

## File Structure

```
apps/api/src/rhapto/engine/providers/errors.py      NEW ProviderAuthError
apps/api/src/rhapto/engine/providers/openai.py      NEW OpenAIProvider
apps/api/src/rhapto/engine/providers/gemini.py      NEW GeminiProvider, schema_for_gemini
apps/api/src/rhapto/engine/providers/registry.py    NEW ProviderInfo, PROVIDERS, build_llm
apps/api/src/rhapto/engine/providers/anthropic.py   map 401/403 → ProviderAuthError (only change)
apps/api/src/rhapto/config.py                       + rhapto_llm_provider, openai_api_key, gemini_api_key, rhapto_secret_key
apps/api/src/rhapto/services/secrets.py             NEW encrypt/decrypt/SecretsError
apps/api/src/rhapto/services/llm.py                 NEW resolve_llm, LLMNotConfiguredError, env_llm_config, provider cache
apps/api/alembic/versions/0004_llm_settings.py      NEW llm_settings
apps/api/src/rhapto/db/models.py                    + LlmSettingsRow
apps/api/src/rhapto/db/repositories/llm_settings.py NEW get/upsert/delete
apps/api/src/rhapto/api/schemas.py                  + LlmSettingsOut, LlmSettingsIn, LlmTestOut, ProviderInfoOut; MeOut.llm_configured
apps/api/src/rhapto/api/routers/settings.py         NEW /settings/llm GET/PUT/DELETE, /settings/llm/test POST
apps/api/src/rhapto/api/routers/tailor.py           409 when not configured
apps/api/src/rhapto/api/routers/meta.py             llm_configured
apps/api/src/rhapto/worker/tasks.py                 tailor_job resolves the LLM per task
apps/api/src/rhapto/worker/main.py                  drop ctx["llm"]
apps/api/src/rhapto/cli/main.py                     --provider/--model via registry
apps/web/src/components/settings/LlmProviderSection.tsx   NEW
apps/web/src/app/settings/page.tsx                  section at top
apps/web/src/lib/api/queries.ts                     useLlmSettings, useSaveLlmSettings, useTestLlm, useDeleteLlmSettings
apps/web/src/components/queue/{TailorButton,NextUp}.tsx   "Set up your AI provider" prompt
README.md, .env.example, docker-compose.yml         env passthrough and docs
```

---

### Task 1: Engine: OpenAI and Gemini adapters, ProviderAuthError, registry

**Files:**
- Create: `engine/providers/errors.py`, `engine/providers/openai.py`, `engine/providers/gemini.py`, `engine/providers/registry.py`; tests `tests/unit/test_provider_openai.py`, `tests/unit/test_provider_gemini.py`, `tests/unit/test_provider_registry.py`
- Modify: `engine/providers/anthropic.py` (wrap `anthropic.AuthenticationError`/`PermissionDeniedError` → `ProviderAuthError`; add a test in the existing anthropic test file), `apps/api/pyproject.toml` (`openai>=1.60`, `google-genai>=1.0`), `uv lock`.

**Interfaces:**
- `errors.py`: `class ProviderAuthError(EngineError)` with `.provider: str` and the SDK's message.
- `openai.py`: `class OpenAIProvider: __init__(self, model: str, api_key: str | None = None, client: Any | None = None)`; `complete_structured` builds `messages=[{"role":"system","content": "\n\n".join(b.text for b in system)}, *user/assistant]`, calls `client.chat.completions.parse(model=..., messages=..., response_format=output_schema, max_tokens=...)` (the SDK's Pydantic-native path; `strict` is implied); `choice.message.refusal` or `parsed is None` → `MalformedOutputError`; `openai.AuthenticationError`/`PermissionDeniedError`/`RateLimitError` with a quota message → `ProviderAuthError`; usage → `TokenUsage(input_tokens=prompt_tokens, output_tokens=completion_tokens, cache_read_input_tokens=prompt_tokens_details.cached_tokens or 0)`.
- `gemini.py`: `def schema_for_gemini(model: type[BaseModel]) -> dict[str, Any]` (inline `$defs`/`$ref`, drop `title`/`default`/`additionalProperties`, `anyOf:[X,{type:null}]` → `X` + `nullable: true`, keep `enum`, `items`, `properties`, `required`); `class GeminiProvider: __init__(self, model, api_key=None, client=None)`; `complete_structured` calls `client.aio.models.generate_content(model=..., contents=[...user/assistant turns...], config={"system_instruction": joined, "response_mime_type": "application/json", "response_schema": schema_for_gemini(output_schema), "max_output_tokens": max_tokens})`; `output_schema.model_validate_json(response.text)` with `ValidationError`/`ValueError` → `MalformedOutputError`; `google.genai.errors.ClientError` with status 401/403/429-quota → `ProviderAuthError`; usage from `response.usage_metadata` (`prompt_token_count`, `candidates_token_count`, `cached_content_token_count`).
- `registry.py`: `@dataclass(frozen=True) class ProviderInfo(id, label, models: tuple[str, ...], default: str, env_key: str)`; `PROVIDERS: dict[str, ProviderInfo]` per Global Constraints; `def build_llm(provider: str, model: str, api_key: str) -> LLMProvider` (unknown id → `EngineError(f"unknown provider {provider!r}")`); `def provider_ids() -> list[str]`.

- [ ] **Step 1: Failing tests.** OpenAI: with a fake client whose `chat.completions.parse` returns an object with `choices[0].message.parsed = JDExtract(...)`, `.refusal=None`, and `usage`, `complete_structured` returns the value and usage; `refusal="..."` → `MalformedOutputError`; raising `openai.AuthenticationError` → `ProviderAuthError` with `.provider == "openai"`; the system message equals the joined blocks. Gemini: `schema_for_gemini(JDExtract)`, `(ComposeOutput)`, `(TuneOutput)` contain no `$ref`/`$defs`/`additionalProperties`/`title` keys anywhere (walk recursively) and nullable fields carry `nullable: True`; a fake client returning `.text` = a valid `TuneOutput` JSON parses; garbage text → `MalformedOutputError`; `ClientError(403)` → `ProviderAuthError`. Registry: `build_llm("openai","gpt-5","k")` is an `OpenAIProvider` with `.model == "gpt-5"`; `build_llm("nope",...)` raises `EngineError`; every `PROVIDERS[p].default in PROVIDERS[p].models`; "other" model ids pass through unchanged. Anthropic: `anthropic.AuthenticationError` → `ProviderAuthError`.
- [ ] **Step 2: Run to verify failure** (`uv run pytest tests/unit/test_provider_*.py -q`).
- [ ] **Step 3: Implement** per Interfaces. Add the two SDK dependencies with `uv add openai>=1.60 google-genai>=1.0` (commit `uv.lock`). Type stubs: both SDKs ship types; if mypy complains about `google.genai`, add a targeted `[[tool.mypy.overrides]]` `ignore_missing_imports` for `google.*` only.
- [ ] **Step 4: Checks and commit** (`feat(engine): OpenAI and Gemini providers behind a registry`).

---

### Task 2: Secrets, `llm_settings` storage, and `resolve_llm`

**Files:**
- Create: `services/secrets.py`, `services/llm.py`, `alembic/versions/0004_llm_settings.py`, `db/repositories/llm_settings.py`; tests `tests/unit/test_secrets.py`, `tests/unit/test_resolve_llm.py`, `tests/db/test_llm_settings_repo.py` (follow the existing db test layout)
- Modify: `config.py`, `db/models.py`.

**Interfaces:**
- `config.py` `Settings` gains `rhapto_llm_provider: str = "anthropic"`, `openai_api_key: str = ""`, `gemini_api_key: str = ""`, `rhapto_secret_key: str = ""` (existing `anthropic_api_key`, `rhapto_llm_model` stay; `rhapto_llm_model` default becomes `""` meaning "the provider's default").
- `secrets.py`: `class SecretsError(Exception)`; `def fernet_for(settings: Settings) -> Fernet` (Global Constraints derivation); `def encrypt(settings, text: str) -> str`; `def decrypt(settings, token: str) -> str` (`InvalidToken` → `SecretsError("stored key cannot be decrypted; RHAPTO_SECRET_KEY changed")`).
- Migration `0004`: `llm_settings(id uuid pk, user_id uuid unique fk users cascade, provider varchar(20) not null, model varchar(100) not null, api_key_encrypted text not null, created_at, updated_at)`; downgrade drops it.
- `db/models.py`: `LlmSettingsRow` (`__tablename__ = "llm_settings"`).
- `repositories/llm_settings.py`: `get_llm_settings(session, user_id) -> LlmSettingsRow | None`, `upsert_llm_settings(session, user_id, *, provider, model, api_key_encrypted) -> LlmSettingsRow`, `delete_llm_settings(session, user_id) -> bool`.
- `services/llm.py`: `class LLMNotConfiguredError(Exception)` (message "No LLM configured. Add a key in Settings."); `@dataclass(frozen=True) class LlmConfig(provider, model, api_key, source: Literal["settings","env"])`; `def env_llm_config(settings) -> LlmConfig | None` (provider = `settings.rhapto_llm_provider`, must be in `PROVIDERS`; key = the provider's env key read from the matching settings field; model = `settings.rhapto_llm_model or PROVIDERS[p].default`; `None` when the key is empty); `async def stored_llm_config(session, settings, user_id) -> LlmConfig | None` (decrypts); `async def resolve_llm_config(session, settings, user_id) -> LlmConfig` (stored → env → raise); `def llm_for(config: LlmConfig) -> LLMProvider` (per-process `dict` cache keyed by `(provider, model, sha256(api_key).hexdigest())`, values from `build_llm`); `async def resolve_llm(session, settings, user_id) -> LLMProvider`.

- [ ] **Step 1: Failing tests.** Secrets: round trip; different secret → `SecretsError`; both env values empty → `SecretsError`; derivation from the API token is deterministic. Resolve (unit, with a fake session/repo via monkeypatching `stored_llm_config`): stored row wins; env fallback with default model when `rhapto_llm_model` is empty; env provider not in registry → `LLMNotConfiguredError`; no key anywhere → `LLMNotConfiguredError`; `llm_for` returns the same object for the same config and a different one when the key changes. Repo (db test): upsert twice updates the single row; delete returns True then False.
- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement**; `uv run alembic upgrade head` against the dev database and check `downgrade -1` then `upgrade head` again.
- [ ] **Step 4: Checks and commit** (`feat(services): encrypted llm_settings and per-user LLM resolution`).

---

### Task 3: API settings router, tailor 409, `/me`, worker and CLI resolution

**Files:**
- Create: `api/routers/settings.py`; tests `tests/api/test_llm_settings_api.py`
- Modify: `api/schemas.py`, `api/app.py` (router registration; find the file that includes routers), `api/routers/tailor.py`, `api/routers/meta.py`, `worker/tasks.py`, `worker/main.py`, `cli/main.py`, `tests/api/conftest.py` (`worker_ctx` gains `"llm_resolver"`), `tests/api/test_tailor_api.py`, `tests/unit/test_worker_tasks.py`, `tests/unit/test_cli.py`; regenerate `openapi.json` + `schema.d.ts`.

**Interfaces:**
- Schemas: `ProviderInfoOut(id, label, models: list[str], default: str)`; `LlmSettingsOut(provider: str | None, model: str | None, key_set: bool, key_hint: str | None, source: Literal["settings","env","none"], providers: list[ProviderInfoOut])`; `LlmSettingsIn(provider: str, model: str, api_key: str | None = None)`; `LlmTestIn` = same shape; `LlmTestOut(ok: bool, model: str | None = None, error: str | None = None)`; `MeOut.llm_configured: bool`.
- Router `/api/v1/settings/llm`: `GET` (stored row → source `settings`, hint from the decrypted key's last four; else env config → source `env`, hint from the env key; else `none` with provider/model `None`); `PUT` (validate provider in registry; key precedence: body key → stored key if provider unchanged → env key for that provider → 422 "an API key is required for <label>"; store encrypted; return GET shape); `DELETE` → 204; `POST /test` (key precedence as PUT; build via `build_llm`, run `complete_structured(system=[SystemBlock(text="Reply with ok=true.")], messages=[Message(role="user", content="ping")], output_schema=Ping, max_tokens=64)` where `class Ping(BaseModel): ok: bool`; `ProviderAuthError`/`EngineError`/SDK exceptions → `LlmTestOut(ok=False, error=str(exc)[:300])`). The test endpoint is injectable: the router uses `state.llm_factory` (defaults to `build_llm`) so tests can substitute a fake.
- Worker: `tailor_job` gets the provider with `resolver = ctx.get("llm_resolver") or resolve_llm; llm = await resolver(session, settings, user_id)` at task start (settings via `get_settings()` as elsewhere in tasks); `LLMNotConfiguredError` and `ProviderAuthError` fail the task with `str(exc)` as the task error (same path as other failures, no traceback). `worker/main.py` no longer sets `ctx["llm"]`; `tests/api/conftest.py` `worker_ctx` replaces `"llm": fake_llm` with `"llm_resolver": <async fn returning fake_llm>`.
- Tailor endpoint: before enqueueing, `await resolve_llm_config(...)`; on `LLMNotConfiguredError` raise `HTTPException(409, detail=...)` with the JSON body per Global Constraints (use a small custom response or `HTTPException(detail={"detail": ..., "code": "llm_not_configured"})` shaped to match the existing Problem handler — check how the web `ApiError` reads `detail`).
- `/me`: `llm_configured = (await resolve_llm_config(...)) succeeded`.
- CLI: `tailor` and `score` gain `--provider` (default `settings.rhapto_llm_provider`) and `--model` (default provider default); `build_providers(settings, provider, model)` uses `env_llm_config`-style lookup with the registry and errors "`<ENV_KEY>` is not set; put it in .env" when the key is empty.

- [ ] **Step 1: Failing tests.** API: GET with nothing → `source none`, `key_set False`, three providers listed; PUT `{provider: "openai", model: "gpt-5", api_key: "sk-test-1234"}` → `key_set True`, `key_hint "…1234"`, response contains no `sk-test`; PUT again without a key keeps it; PUT switching to `gemini` without a key → 422; DELETE → 204 then GET `none`; POST test with a fake factory returning a scripted `Ping(ok=True)` → `{ok: true, model}`, and with a factory raising `ProviderAuthError("bad key")` → `{ok: false, error: "bad key"}`; `/me` `llm_configured` false → true after PUT. Tailor: with `api_settings.anthropic_api_key = ""` and no row → 409 with `code llm_not_configured`; with a row → task enqueued and the worker used the resolver (assert the fake was called). Worker unit: resolver raising `LLMNotConfiguredError` → task failed with that message. CLI: `--provider openai` without `OPENAI_API_KEY` exits 1 with the message; with a fake `build_providers` patched as today the tune/blocks tests still pass.
- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement**; `bash scripts/codegen.sh`.
- [ ] **Step 4: Checks and commit** (`feat(api): LLM settings endpoints, per-task provider resolution, CLI provider flags`).

---

### Task 4: Web: Settings AI provider section and "set up your provider" prompts

**Files:**
- Create: `components/settings/LlmProviderSection.tsx` + test
- Modify: `lib/api/queries.ts` (`useLlmSettings`, `useSaveLlmSettings`, `useTestLlm`, `useDeleteLlmSettings`, `MeOut` already regenerated), `app/settings/page.tsx` (section first), `components/queue/TailorButton.tsx` and `NextUp.tsx` (+ tests): when `useMe().data?.llm_configured === false` render a link "Set up your AI provider" to `/settings` instead of the Tailor button; on a 409 with `code llm_not_configured` from tailor, toast with the same link.

**Interfaces:** `LlmProviderSection` renders three selectable cards (`role="radio"`, labels Anthropic / OpenAI / Google Gemini); the selected card shows `input[type=password]` labelled "API key" (placeholder `…1234` when `key_set`), a radio list of the curated models plus "Other" with a text input, buttons "Test connection" and "Save"; a status line per spec §6 ("Using OpenAI · gpt-5 · key set", "Using Anthropic from .env", "No AI provider configured"); test result inline (`role="status"`), errors in `role="alert"`; Save disabled until something changed; after Save, invalidate `["me"]` and the settings key.

- [ ] **Step 1: Failing tests.** Section: renders status from the mocked GET; selecting OpenAI and typing a key then Save calls the save mutation with `{provider:"openai", model:"gpt-5", api_key:"sk-test"}`; choosing "Other" sends the typed model id; Test calls the test mutation and shows the returned error text; a masked hint is shown and the key input is empty. TailorButton/NextUp: with `llm_configured false` the link renders and no tailor mutation exists.
- [ ] **Step 2: Run to verify failure** (`npx vitest run <files>`).
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Web checks and commit** (`feat(web): AI provider settings and setup prompts`).

---

### Task 5: Docs, env, compose, end-to-end

**Files:** `README.md` (Setup: "Add your AI key in Settings" replaces the ANTHROPIC_API_KEY-first instruction; a table of supported providers; `.env` still works), `.env.example` (`RHAPTO_LLM_PROVIDER`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `RHAPTO_SECRET_KEY` with the generation one-liner, all optional), `docker-compose.yml` (pass the new variables to api and worker), `scripts/smoke-api.sh` (accept any provider key).

- [ ] **Step 1:** Make the edits; `docker compose config` validates; `git grep -n "ANTHROPIC_API_KEY" README.md` shows only the fallback mention.
- [ ] **Step 2:** Rebuild `api`, `worker`, `web` one at a time; `docker compose up -d`; through the API: GET settings → `source env` (the user's `.env` still has an Anthropic key), PUT a provider + key, POST test, tailor one job and confirm the task succeeds; DELETE to return to env. Never paste a real key into a commit, log, or ledger.
- [ ] **Step 3: Commit** (`docs: provider setup via Settings; env and compose passthrough`).

---

## Self-review notes

- Spec coverage: §3 adapters/registry (T1), §4 storage + API (T2, T3), §5 resolution worker/API/CLI (T2, T3), §6 UI (T4), §7 tests (each task), env/docs (T5).
- Type consistency: `LlmConfig`, `resolve_llm`, `resolve_llm_config`, `llm_for`, `build_llm`, `ProviderAuthError`, `LLMNotConfiguredError`, `LlmSettingsOut/In`, `LlmTestOut`, `MeOut.llm_configured` are named identically across tasks; the worker's `ctx["llm_resolver"]` seam is defined in T3 and used by the test fixture there.
- Ruling recorded in Global Constraints: secret derivation from the API token when `RHAPTO_SECRET_KEY` is empty.
