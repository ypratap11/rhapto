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
    data: [{ rule: "no-unverified-metrics", active: true, config: {} }],
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
  it("requires confirmation to turn off no-unverified-metrics, and cancel leaves it on", async () => {
    renderTab();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /edit no-unverified-metrics/i }));

    expect(screen.getByText(/turning this off allows numbers that no verified block supports/i)).toBeInTheDocument();

    const active = screen.getByRole("switch", { name: /active/i });
    expect(active).toHaveAttribute("aria-checked", "true");
    await user.click(active);

    expect(screen.getByText(/turn off no-unverified-metrics\?/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^cancel$/i }));

    expect(screen.queryByText(/turn off no-unverified-metrics\?/i)).not.toBeInTheDocument();
    expect(screen.getByRole("switch", { name: /active/i })).toHaveAttribute("aria-checked", "true");
  });

  it("turns the rule off once the confirm dialog is accepted", async () => {
    renderTab();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /edit no-unverified-metrics/i }));
    await user.click(screen.getByRole("switch", { name: /active/i }));
    await user.click(screen.getByRole("button", { name: /^turn off$/i }));

    expect(screen.queryByText(/turn off no-unverified-metrics\?/i)).not.toBeInTheDocument();
    expect(screen.getByRole("switch", { name: /active/i })).toHaveAttribute("aria-checked", "false");
  });
});
