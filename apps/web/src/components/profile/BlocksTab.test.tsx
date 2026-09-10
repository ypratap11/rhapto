import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { BlocksTab } from "./BlocksTab";

const putMutate = vi.fn();
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useBlocks: () => ({
    data: [
      { id: "acme-migration", type: "achievement", org: "Acme Analytics", role: null, period: "2023", verified: true, metric: "18%", content: "Owned it.", tags: ["migration"], attribution: null, concurrent: false, visibility: null },
    ],
    isLoading: false,
    error: null,
  }),
  usePutBlock: () => ({ mutateAsync: putMutate, isPending: false }),
  useDeleteBlock: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

describe("BlocksTab", () => {
  it("lists blocks and opens the editor prefilled", async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <BlocksTab />
      </QueryClientProvider>,
    );
    expect(screen.getByText("acme-migration")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: /edit acme-migration/i }));
    expect(screen.getByLabelText(/^content/i)).toHaveValue("Owned it.");
    expect(screen.getByLabelText(/^verified/i)).toBeChecked();
  });
});
