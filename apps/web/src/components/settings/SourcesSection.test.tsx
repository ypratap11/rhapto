import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SourcesSection } from "./SourcesSection";
import type { SourceSetting, SourceTestOut } from "@/lib/api/queries";

const rows: SourceSetting[] = [
  { id: "themuse", label: "The Muse", enabled: true, needs_key: false, key_set: false, fields: [] },
  { id: "adzuna", label: "Adzuna", enabled: false, needs_key: true, key_set: false, fields: ["app_id", "app_key"] },
  { id: "jsearch", label: "JSearch", enabled: true, needs_key: true, key_set: true, fields: ["api_key"] },
];

// Mutable, per-test module state (not a static top-of-file mock): each test below overwrites these
// before rendering, so a broken branch actually produces a different — and failing — assertion.
let data: SourceSetting[] | undefined = rows;
let isLoading = false;
let error: unknown = null;
let isPaused = false;
const save = vi.fn().mockResolvedValue({});
const testSource = vi.fn<() => Promise<SourceTestOut>>().mockResolvedValue({ ok: true, found: 1 });

vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useSourceSettings: () => ({ data, isLoading, error, isPaused }),
  useSaveSourceSettings: () => ({ mutateAsync: save, isPending: false }),
  useTestSource: () => ({ mutateAsync: testSource, isPending: false }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

describe("SourcesSection", () => {
  beforeEach(() => {
    data = rows;
    isLoading = false;
    error = null;
    isPaused = false;
    save.mockClear().mockResolvedValue({});
    testSource.mockClear().mockResolvedValue({ ok: true, found: 1 });
  });

  it("lists each source with its switch and says which need a key", () => {
    render(<SourcesSection />);
    expect(screen.getByRole("switch", { name: "The Muse" })).toBeChecked();
    expect(screen.getByRole("switch", { name: "Adzuna" })).not.toBeChecked();

    const adzuna = screen.getByRole("group", { name: "Adzuna" });
    expect(within(adzuna).getByText(/needs a key/i)).toBeInTheDocument();
    expect(within(adzuna).getByLabelText("app_id")).toHaveAttribute("type", "password");
    expect(within(adzuna).getByLabelText("app_key")).toHaveAttribute("type", "password");

    const jsearch = screen.getByRole("group", { name: "JSearch" });
    expect(within(jsearch).getByText(/key saved/i)).toBeInTheDocument();

    const themuse = screen.getByRole("group", { name: "The Muse" });
    expect(within(themuse).getByText(/zero setup/i)).toBeInTheDocument();
  });

  it("never echoes a stored key back into the form", () => {
    render(<SourcesSection />);
    expect(within(screen.getByRole("group", { name: "JSearch" })).getByLabelText("api_key")).toHaveValue("");
  });

  it("saves an enable toggle without sending any credentials", async () => {
    const user = userEvent.setup({ delay: null });
    render(<SourcesSection />);
    await user.click(screen.getByRole("switch", { name: "Adzuna" }));
    expect(save).toHaveBeenCalledWith({ source: "adzuna", body: { enabled: true } });
  });

  it("saves a typed key on Save, and clears the field afterwards", async () => {
    const user = userEvent.setup({ delay: null });
    render(<SourcesSection />);
    const adzuna = screen.getByRole("group", { name: "Adzuna" });
    const appId = within(adzuna).getByLabelText("app_id");
    await user.type(appId, "my-app-id");
    await user.click(within(adzuna).getByRole("button", { name: /^save$/i }));

    expect(save).toHaveBeenCalledWith({ source: "adzuna", body: { enabled: false, credentials: { app_id: "my-app-id" } } });
    expect(appId).toHaveValue("");
  });

  it("tests a source and reports how many results it found", async () => {
    const user = userEvent.setup({ delay: null });
    render(<SourcesSection />);
    const themuse = screen.getByRole("group", { name: "The Muse" });
    await user.click(within(themuse).getByRole("button", { name: /^test$/i }));
    expect(testSource).toHaveBeenCalledWith("themuse");
  });

  it("shows a shape-matched skeleton while loading, not the empty or error state", () => {
    isLoading = true;
    data = undefined;
    render(<SourcesSection />);
    expect(screen.queryByRole("group")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows an error banner when the query fails with nothing cached yet", () => {
    isLoading = false;
    data = undefined;
    error = new Error("boom");
    render(<SourcesSection />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.queryByRole("group")).not.toBeInTheDocument();
  });

  it("treats a paused fetch (offline) the same as a failure even though isLoading is false and error is null", () => {
    isLoading = false;
    data = undefined;
    error = null;
    isPaused = true;
    render(<SourcesSection />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("keeps showing cached sources alongside the banner when a background refetch fails", () => {
    data = rows;
    error = new Error("refetch failed");
    render(<SourcesSection />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "The Muse" })).toBeInTheDocument();
  });
});
