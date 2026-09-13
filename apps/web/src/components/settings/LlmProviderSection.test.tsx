import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LlmProviderSection } from "./LlmProviderSection";
import type { LlmSettingsOut, LlmSettingsState, ProviderInfoOut } from "@/lib/api/queries";

const providers: ProviderInfoOut[] = [
  { id: "anthropic", label: "Anthropic", models: ["claude-opus-5", "claude-sonnet-5"], default: "claude-sonnet-5" },
  { id: "openai", label: "OpenAI", models: ["gpt-5", "gpt-5-mini"], default: "gpt-5" },
  { id: "gemini", label: "Google Gemini", models: ["gemini-2.5-pro", "gemini-2.5-flash"], default: "gemini-2.5-pro" },
];

const none: LlmSettingsOut = { provider: null, model: null, key_set: false, key_hint: null, source: "none", providers };

let state: LlmSettingsState | undefined = { kind: "ok", settings: none };
let isLoading = false;
let queryError: unknown = null;
const save = vi.fn();
const testConnection = vi.fn();
const remove = vi.fn();

vi.mock("@/lib/api/queries", () => ({
  useLlmSettings: () => ({ data: state, isLoading, error: queryError }),
  useSaveLlmSettings: () => ({ mutateAsync: save, isPending: false }),
  useTestLlm: () => ({ mutateAsync: testConnection, isPending: false }),
  useDeleteLlmSettings: () => ({ mutateAsync: remove, isPending: false }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function ok(over: Partial<LlmSettingsOut>): LlmSettingsState {
  return { kind: "ok", settings: { ...none, ...over } };
}

describe("LlmProviderSection", () => {
  beforeEach(() => {
    state = { kind: "ok", settings: none };
    isLoading = false;
    queryError = null;
    save.mockReset().mockResolvedValue(none);
    testConnection.mockReset();
    remove.mockReset().mockResolvedValue(undefined);
  });

  it("renders the status line for a stored provider, the environment, and nothing configured", () => {
    state = ok({ provider: "openai", model: "gpt-5", key_set: true, key_hint: "…1234", source: "settings" });
    const stored = render(<LlmProviderSection />);
    expect(screen.getByText("Using OpenAI · gpt-5 · key set")).toBeInTheDocument();
    stored.unmount();

    state = ok({ provider: "anthropic", model: "claude-sonnet-5", key_set: true, key_hint: "…1234", source: "env" });
    const fromEnv = render(<LlmProviderSection />);
    expect(screen.getByText("Using Anthropic from .env")).toBeInTheDocument();
    fromEnv.unmount();

    state = { kind: "ok", settings: none };
    render(<LlmProviderSection />);
    expect(screen.getByText("No AI provider configured")).toBeInTheDocument();
  });

  it("offers the three providers as radios and only expands the selected one", async () => {
    render(<LlmProviderSection />);
    const cards = screen.getAllByRole("radio", { name: /anthropic|openai|google gemini/i });
    expect(cards).toHaveLength(3);
    expect(cards.every((c) => c.getAttribute("aria-checked") === "false")).toBe(true);
    expect(screen.queryByLabelText("API key")).not.toBeInTheDocument();

    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByRole("radio", { name: "OpenAI" }));
    expect(screen.getByRole("radio", { name: "OpenAI" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByLabelText("API key")).toBeInTheDocument();
  });

  it("saves the selected provider, its default model and the typed key", async () => {
    render(<LlmProviderSection />);
    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByRole("radio", { name: "OpenAI" }));
    await user.type(screen.getByLabelText("API key"), "sk-test");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(save).toHaveBeenCalledWith({ provider: "openai", model: "gpt-5", api_key: "sk-test" });
  });

  it("sends the typed model id when Other is chosen", async () => {
    render(<LlmProviderSection />);
    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByRole("radio", { name: "OpenAI" }));
    await user.click(screen.getByRole("radio", { name: "Other" }));
    await user.type(screen.getByLabelText("Other model"), "gpt-6-preview");
    await user.type(screen.getByLabelText("API key"), "sk-test");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(save).toHaveBeenCalledWith({ provider: "openai", model: "gpt-6-preview", api_key: "sk-test" });
  });

  it("runs the test mutation and shows the provider's error text inline", async () => {
    testConnection.mockResolvedValue({ ok: false, error: "401 invalid x-api-key" });
    render(<LlmProviderSection />);
    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByRole("radio", { name: "Anthropic" }));
    await user.type(screen.getByLabelText("API key"), "sk-test");
    await user.click(screen.getByRole("button", { name: "Test connection" }));

    expect(testConnection).toHaveBeenCalledWith({ provider: "anthropic", model: "claude-sonnet-5", api_key: "sk-test" });
    expect(await screen.findByText(/401 invalid x-api-key/)).toBeInTheDocument();
  });

  it("reports a successful test with the model it reached, in a status region", async () => {
    testConnection.mockResolvedValue({ ok: true, model: "gpt-5" });
    render(<LlmProviderSection />);
    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByRole("radio", { name: "OpenAI" }));
    await user.type(screen.getByLabelText("API key"), "sk-test");
    await user.click(screen.getByRole("button", { name: "Test connection" }));

    expect(await screen.findByRole("status")).toHaveTextContent("gpt-5");
  });

  it("shows the masked hint as the key placeholder and never a key value", async () => {
    state = ok({ provider: "openai", model: "gpt-5", key_set: true, key_hint: "…1234", source: "settings" });
    render(<LlmProviderSection />);
    const key = screen.getByLabelText("API key");
    expect(key).toHaveValue("");
    expect(key).toHaveAttribute("type", "password");
    expect(key).toHaveAttribute("placeholder", "…1234");
  });

  it("keeps Save disabled until something changes", async () => {
    state = ok({ provider: "openai", model: "gpt-5", key_set: true, key_hint: "…1234", source: "settings" });
    render(<LlmProviderSection />);
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();

    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByRole("radio", { name: "gpt-5-mini" }));
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(save).toHaveBeenCalledWith({ provider: "openai", model: "gpt-5-mini" });
  });

  it("still renders the form, with the problem detail in an alert, when the stored key is unreadable", async () => {
    state = { kind: "unreadable", detail: "your stored API key could not be read; re-enter it" };
    render(<LlmProviderSection />);
    expect(screen.getByRole("alert")).toHaveTextContent("could not be read");
    expect(screen.getAllByRole("radio", { name: /anthropic|openai|google gemini/i })).toHaveLength(3);

    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByRole("radio", { name: "Anthropic" }));
    await user.type(screen.getByLabelText("API key"), "sk-test");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(save).toHaveBeenCalledWith({ provider: "anthropic", model: "claude-sonnet-5", api_key: "sk-test" });
  });

  it("surfaces a failed save in an alert", async () => {
    save.mockRejectedValue(new Error("an API key is required for OpenAI"));
    render(<LlmProviderSection />);
    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByRole("radio", { name: "OpenAI" }));
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("an API key is required for OpenAI");
  });
  it("confirms before removing the stored provider, and closes the dialog once it resolves", async () => {
    state = ok({ provider: "openai", model: "gpt-5", key_set: true, key_hint: "…1234", source: "settings" });
    render(<LlmProviderSection />);
    const user = userEvent.setup({ delay: null });

    await user.click(screen.getByRole("button", { name: "Remove the stored AI provider" }));
    expect(await screen.findByText("Remove the stored AI provider?")).toBeInTheDocument();
    // Opening the dialog must not be the destructive act.
    expect(remove).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Remove" }));
    expect(remove).toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByText("Remove the stored AI provider?")).not.toBeInTheDocument());
  });

  it("leaves the stored provider alone when the remove dialog is cancelled", async () => {
    state = ok({ provider: "openai", model: "gpt-5", key_set: true, key_hint: "…1234", source: "settings" });
    render(<LlmProviderSection />);
    const user = userEvent.setup({ delay: null });

    await user.click(screen.getByRole("button", { name: "Remove the stored AI provider" }));
    await user.click(await screen.findByRole("button", { name: "Cancel" }));

    await waitFor(() => expect(screen.queryByText("Remove the stored AI provider?")).not.toBeInTheDocument());
    expect(remove).not.toHaveBeenCalled();
  });

  it("offers no Remove when the provider comes from the environment", () => {
    state = ok({ provider: "anthropic", model: "claude-sonnet-5", key_set: true, key_hint: "…1234", source: "env" });
    render(<LlmProviderSection />);
    expect(screen.queryByRole("button", { name: /remove/i })).not.toBeInTheDocument();
  });

  it("surfaces a failed remove in an alert", async () => {
    state = ok({ provider: "openai", model: "gpt-5", key_set: true, key_hint: "…1234", source: "settings" });
    remove.mockRejectedValue(new Error("could not reach the API"));
    render(<LlmProviderSection />);
    const user = userEvent.setup({ delay: null });

    await user.click(screen.getByRole("button", { name: "Remove the stored AI provider" }));
    await user.click(await screen.findByRole("button", { name: "Remove" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("could not reach the API");
  });
});
