import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { GuardrailsTab } from "./GuardrailsTab";

const putMutate = vi.fn();
const deleteMutate = vi.fn();
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useGuardrails: () => ({
    data: [
      { rule: "no-unverified-metrics", active: true, config: {} },
      { rule: "no-invented-entities", active: true, config: {} },
    ],
    isLoading: false,
    error: null,
  }),
  usePutGuardrail: () => ({ mutateAsync: putMutate, isPending: false }),
  useDeleteGuardrail: () => ({ mutateAsync: deleteMutate, isPending: false }),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function renderTab() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <GuardrailsTab />
    </QueryClientProvider>,
  );
}

describe("GuardrailsTab", () => {
  it("opens the guardrail editor as a centred dialog, not a sheet, with Save reachable", async () => {
    renderTab();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /edit no invented companies, schools or tools/i }));

    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeInTheDocument();
    expect(dialog.getAttribute("data-slot")).toBe("dialog-content");
    expect(dialog).not.toHaveAttribute("data-side");
    expect(screen.getByRole("button", { name: "Save" })).toBeVisible();
  });

  it("requires confirmation to turn off a rule, and cancel leaves it on", async () => {
    renderTab();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /edit no invented companies, schools or tools/i }));

    expect(screen.getByText(/turning this off allows companies, schools and tools that are not in your experience/i)).toBeInTheDocument();

    const active = screen.getByRole("switch", { name: /active/i });
    expect(active).toHaveAttribute("aria-checked", "true");
    await user.click(active);

    expect(screen.getByText(/turn off: no invented companies, schools or tools\?/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^cancel$/i }));

    expect(screen.queryByText(/turn off: no invented companies, schools or tools\?/i)).not.toBeInTheDocument();
    expect(screen.getByRole("switch", { name: /active/i })).toHaveAttribute("aria-checked", "true");
  });

  it("turns the rule off once the confirm dialog is accepted", async () => {
    renderTab();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /edit no invented companies, schools or tools/i }));
    await user.click(screen.getByRole("switch", { name: /active/i }));
    await user.click(screen.getByRole("button", { name: /^turn off$/i }));

    expect(screen.queryByText(/turn off: no invented companies, schools or tools\?/i)).not.toBeInTheDocument();
    expect(screen.getByRole("switch", { name: /active/i })).toHaveAttribute("aria-checked", "false");
  });

  it("shows the always-on rule as text, never as a switch, but keeps it editable", async () => {
    renderTab();
    const user = userEvent.setup();
    expect(screen.getByText("Always on")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /edit numbers must come from your resume file or a confirmed item/i }));
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
    expect(screen.getAllByText("Always on").length).toBeGreaterThan(1);
    expect(screen.getByRole("button", { name: "Save" })).toBeVisible();
  });
});
