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

afterEach(() => {
  window.localStorage.clear();
  vi.restoreAllMocks();
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
    expect(screen.getByText(/connect to your rhapto api/i)).toBeInTheDocument();
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
});
