import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AddJobDialog } from "./AddJobDialog";

const mutateAsync = vi.fn();
vi.mock("@/lib/api/queries", () => ({ useCreateJob: () => ({ mutateAsync, isPending: false }) }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

function renderDialog() {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <AddJobDialog open onOpenChange={() => undefined} />
    </QueryClientProvider>,
  );
}

describe("AddJobDialog", () => {
  it("requires at least 50 characters of pasted text", async () => {
    renderDialog();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/job description/i), "too short");
    await user.click(screen.getByRole("button", { name: /add job/i }));
    expect(screen.getByText(/at least 50 characters/i)).toBeInTheDocument();
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it("submits pasted text with optional company and title", async () => {
    mutateAsync.mockResolvedValueOnce({ id: "j1" });
    renderDialog();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/job description/i), "x".repeat(60));
    await user.type(screen.getByLabelText(/company/i), "ExampleCo");
    await user.click(screen.getByRole("button", { name: /add job/i }));
    expect(mutateAsync).toHaveBeenCalledWith({ jd_text: "x".repeat(60), company: "ExampleCo", title: null, location: null, url: null });
  });
});
