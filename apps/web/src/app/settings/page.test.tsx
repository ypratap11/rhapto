import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { toast } from "sonner";
import SettingsPage from "./page";
import { TokenGate } from "@/components/shell/TokenGate";
import { getSettings, setSettings } from "@/lib/api/client";

vi.mock("next/navigation", () => ({ usePathname: () => "/" }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// The AI provider, Job sources and Saved searches sections each have their own Save/Test/Edit
// buttons. Holding every one of their queries in the loading state keeps those button names
// unambiguous for most tests here (and keeps this suite off the network); each section has its own
// test file. `llmState` is mutable (reset in beforeEach) rather than a fixed loading shape, because
// LlmProviderSection renders nothing but a bare Skeleton while loading — no "AI provider" title —
// so the section-order test below needs it resolved to see that title at all.
let llmState: { data: unknown; isLoading: boolean; error: unknown } = { data: undefined, isLoading: true, error: null };
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useLlmSettings: () => llmState,
  useSaveLlmSettings: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useTestLlm: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteLlmSettings: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useSourceSettings: () => ({ data: undefined, isLoading: true, error: null, isPaused: false }),
  useSaveSourceSettings: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useTestSource: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useSavedSearches: () => ({ data: undefined, isLoading: true, error: null, isPaused: false }),
  useUpdateSavedSearch: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteSavedSearch: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUsageSummary: () => ({ data: undefined, isLoading: true, error: null }),
}));

afterEach(() => {
  window.localStorage.clear();
  vi.restoreAllMocks();
  llmState = { data: undefined, isLoading: true, error: null };
});

function renderPage() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <TokenGate>
        <p>secret content</p>
      </TokenGate>
      <SettingsPage />
    </QueryClientProvider>,
  );
}

describe("SettingsPage", () => {
  it("clears the stored token on Disconnect and the gate reappears", async () => {
    setSettings({ token: "tok", apiUrl: "http://localhost:8000" });
    renderPage();
    expect(screen.getByText("secret content")).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /disconnect/i }));

    expect(getSettings().token).toBe("");
    expect(screen.queryByText("secret content")).not.toBeInTheDocument();
    // `usePathname` is mocked to "/" here, and the gate answers the root with the landing page
    // rather than the Connect card -- so this is what "the gate is back" looks like at "/".
    expect(screen.getByText("Why not just ask a chatbot?")).toBeInTheDocument();
    expect(screen.getByLabelText(/bearer token/i)).toHaveValue("");
    expect(toast.success).toHaveBeenCalledWith("Disconnected");
  });

  it("rejects saving an API URL without a scheme, inline, without touching storage", async () => {
    renderPage();
    const user = userEvent.setup();
    const apiUrlInput = screen.getByLabelText(/api url/i);
    await user.clear(apiUrlInput);
    await user.type(apiUrlInput, "example.com");
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    expect(screen.getByText(/http:\/\/ or https:\/\//i)).toBeInTheDocument();
    expect(getSettings().apiUrl).not.toBe("example.com");
    expect(toast.success).not.toHaveBeenCalled();
  });

  it("toasts when the browser refuses to persist settings", async () => {
    renderPage();
    const setItemSpy = vi.spyOn(Object.getPrototypeOf(window.localStorage) as Storage, "setItem").mockImplementation(() => {
      throw new Error("quota exceeded");
    });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    expect(toast.error).toHaveBeenCalledWith("Could not save settings in this browser");
    setItemSpy.mockRestore();
  });

  it("shows every section, in order, with the Help section addressable as #help", () => {
    // Resolved (not loading), so LlmProviderSection renders its Card and "AI provider" title
    // instead of the bare loading Skeleton the other tests above rely on for button-name safety.
    llmState = { data: { kind: "ok", settings: { provider: null, model: null, key_set: false, key_hint: null, source: "none", providers: [] } }, isLoading: false, error: null };
    // A token, so TokenGate's own "Connect to your Rhapto API" card isn't in the tree competing
    // with the sections' card titles.
    setSettings({ token: "tok", apiUrl: "http://localhost:8000" });
    const { container } = renderPage();
    // Card titles only — the Help section's doc list legitimately repeats names like "Job sources"
    // and "Saved searches" in its body text, so a plain getByText(title) would be ambiguous.
    const cardTitles = Array.from(container.querySelectorAll('[data-slot="card-title"]')).map((el) => el.textContent);
    expect(cardTitles).toEqual(["AI provider", "Usage", "Job sources", "Saved searches", "Import and export", "API connection", "Help"]);

    const help = container.querySelector("#help");
    expect(help).not.toBeNull();
    expect(help).toHaveTextContent("Help");
  });
});
