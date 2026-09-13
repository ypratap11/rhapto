"use client";

import { useId, useState } from "react";
import { toast } from "sonner";
import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/client";
import {
  useDeleteLlmSettings,
  useLlmSettings,
  useSaveLlmSettings,
  useTestLlm,
  type LlmSettingsOut,
  type LlmTestOut,
  type ProviderInfoOut,
} from "@/lib/api/queries";

/** Sentinel for the "Other" model radio: the model id then comes from the free-text field. */
const OTHER = "__other__";

/**
 * The provider list normally comes from `GET /settings/llm`. That call answers 409
 * `llm_key_unreadable` when the stored key cannot be decrypted, and in exactly that state the
 * section still has to offer a form so the user can re-enter a key — with no list to render it
 * from. This mirrors apps/api's provider registry for that one case; a successful GET always wins.
 */
const FALLBACK_PROVIDERS: ProviderInfoOut[] = [
  { id: "anthropic", label: "Anthropic", models: ["claude-opus-5", "claude-sonnet-5"], default: "claude-sonnet-5" },
  { id: "openai", label: "OpenAI", models: ["gpt-5", "gpt-5-mini"], default: "gpt-5" },
  { id: "gemini", label: "Google Gemini", models: ["gemini-2.5-pro", "gemini-2.5-flash"], default: "gemini-2.5-pro" },
];

/** The form's unsaved state. `model === OTHER` means the id is in `other`. `apiKey` starts empty, always. */
type Draft = { provider: string; model: string; other: string; apiKey: string };

function draftFor(provider: string, model: string | null, providers: ProviderInfoOut[]): Draft {
  const info = providers.find((p) => p.id === provider);
  const resolved = model ?? info?.default ?? "";
  const curated = info?.models.includes(resolved) ?? false;
  return { provider, model: curated ? resolved : OTHER, other: curated ? "" : resolved, apiKey: "" };
}

function statusLine(settings: LlmSettingsOut, providers: ProviderInfoOut[]): string {
  if (settings.source === "none" || settings.provider === null) return "No AI provider configured";
  const label = providers.find((p) => p.id === settings.provider)?.label ?? settings.provider;
  if (settings.source === "env") return `Using ${label} from .env`;
  return `Using ${label} · ${settings.model} · key set`;
}

function message(e: unknown, fallback: string): string {
  if (e instanceof ApiError) return e.problem?.detail ?? e.message;
  return e instanceof Error ? e.message : fallback;
}

export function LlmProviderSection() {
  const llm = useLlmSettings();
  const save = useSaveLlmSettings();
  const probe = useTestLlm();
  const remove = useDeleteLlmSettings();
  const keyId = useId();
  const otherId = useId();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [result, setResult] = useState<LlmTestOut | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  if (llm.isLoading) return <Skeleton className="h-48 w-full" />;
  if (llm.error) return <ApiErrorBanner error={llm.error} />;

  const state = llm.data;
  const settings = state?.kind === "ok" ? state.settings : null;
  const unreadable = state?.kind === "unreadable" ? state.detail : null;
  const providers = settings && settings.providers.length > 0 ? settings.providers : FALLBACK_PROVIDERS;

  // Unsaved edits win; otherwise the form mirrors whatever the server says is configured. Derived
  // on render rather than synced into state by an effect.
  const current = draft ?? (settings?.provider ? draftFor(settings.provider, settings.model, providers) : null);
  const selected = providers.find((p) => p.id === current?.provider) ?? null;
  const model = current === null ? "" : current.model === OTHER ? current.other.trim() : current.model;
  // Only the provider the key actually belongs to may advertise its hint.
  const hint = settings?.key_set && settings.provider === current?.provider ? settings.key_hint : null;
  const changed =
    current !== null &&
    (current.apiKey.trim().length > 0 || current.provider !== (settings?.provider ?? null) || model !== (settings?.model ?? ""));

  function body() {
    const key = current?.apiKey.trim() ?? "";
    return { provider: current?.provider ?? "", model, ...(key ? { api_key: key } : {}) };
  }

  function selectProvider(id: string) {
    if (current?.provider === id) return;
    setResult(null);
    setFailure(null);
    // Coming back to the stored provider restores its stored model; anything else starts at its default.
    setDraft(draftFor(id, settings?.provider === id ? settings.model : null, providers));
  }

  function update(patch: Partial<Draft>) {
    if (current === null) return;
    // A previous probe no longer describes what is in the form.
    setResult(null);
    setDraft({ ...current, ...patch });
  }

  async function runTest() {
    setFailure(null);
    setResult(null);
    try {
      setResult(await probe.mutateAsync(body()));
    } catch (e) {
      setFailure(message(e, "Could not reach the API"));
    }
  }

  async function onSave() {
    setFailure(null);
    try {
      await save.mutateAsync(body());
      // Drop the draft so the form re-derives from the refreshed settings (and forgets the key).
      setDraft(null);
      setResult(null);
      toast.success("AI provider saved");
    } catch (e) {
      setFailure(message(e, "Could not save the AI provider"));
    }
  }

  async function onRemove() {
    setFailure(null);
    try {
      await remove.mutateAsync();
      setDraft(null);
      setResult(null);
      toast.success("Removed the stored AI provider");
    } catch (e) {
      setFailure(message(e, "Could not remove the AI provider"));
    }
  }

  // One alert node for every way this section can be unhappy: an unreadable stored key, a failed
  // request, and a probe the provider rejected.
  const alerts = [unreadable, failure, result && !result.ok ? (result.error ?? "The provider rejected the request.") : null].filter(
    (m): m is string => typeof m === "string" && m.length > 0,
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>AI provider</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {settings ? <p className="text-sm text-muted-foreground">{statusLine(settings, providers)}</p> : null}
        {alerts.length > 0 ? (
          <div role="alert" className="space-y-1 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm">
            {alerts.map((m) => (
              <p key={m}>{m}</p>
            ))}
          </div>
        ) : null}
        <div role="radiogroup" aria-label="Provider" className="grid gap-2 sm:grid-cols-3">
          {providers.map((p) => {
            const isSelected = current?.provider === p.id;
            return (
              <button
                key={p.id}
                type="button"
                role="radio"
                aria-checked={isSelected}
                aria-label={p.label}
                onClick={() => selectProvider(p.id)}
                className={`rounded-lg border px-3 py-2 text-left text-sm transition-colors ${
                  isSelected ? "border-primary bg-muted" : "border-border hover:bg-muted/50"
                }`}
              >
                <span className="block font-medium">{p.label}</span>
                <span className="block text-xs text-muted-foreground">{p.default}</span>
              </button>
            );
          })}
        </div>
        {current !== null ? (
          <div className="space-y-4 rounded-lg border border-border p-3">
            <div className="space-y-1">
              <Label htmlFor={keyId}>API key</Label>
              <Input
                id={keyId}
                type="password"
                autoComplete="off"
                value={current.apiKey}
                placeholder={hint ?? "Paste your API key"}
                onChange={(e) => update({ apiKey: e.target.value })}
              />
              <p className="text-xs text-muted-foreground">
                Stored encrypted on the server. It is never sent back to the browser — only its last four characters.
              </p>
            </div>
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium">Model</legend>
              {(selected?.models ?? []).map((m) => (
                <label key={m} className="flex items-center gap-2 text-sm">
                  <input type="radio" name={`${keyId}-model`} value={m} checked={current.model === m} onChange={() => update({ model: m })} />
                  {m}
                </label>
              ))}
              <label className="flex items-center gap-2 text-sm">
                <input type="radio" name={`${keyId}-model`} value={OTHER} checked={current.model === OTHER} onChange={() => update({ model: OTHER })} />
                Other
              </label>
              {current.model === OTHER ? (
                <div className="space-y-1">
                  <Label htmlFor={otherId}>Other model</Label>
                  <Input id={otherId} value={current.other} placeholder="Model id" onChange={(e) => update({ other: e.target.value })} />
                </div>
              ) : null}
            </fieldset>
            {result?.ok ? (
              <p role="status" className="text-sm text-green-700">
                ✓ Connected · {result.model ?? model}
              </p>
            ) : null}
            <div className="flex flex-wrap gap-2">
              <Button onClick={onSave} disabled={!changed || model.length === 0 || save.isPending}>
                Save
              </Button>
              <Button variant="outline" onClick={runTest} disabled={model.length === 0 || probe.isPending}>
                Test connection
              </Button>
              {settings?.source === "settings" ? (
                <Button variant="destructive" onClick={onRemove} disabled={remove.isPending}>
                  Remove
                </Button>
              ) : null}
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
