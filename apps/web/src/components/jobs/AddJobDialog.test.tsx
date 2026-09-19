import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AddJobDialog } from "./AddJobDialog";
import { ApiError } from "@/lib/api/client";

const mutateAsync = vi.fn();
vi.mock("@/lib/api/queries", () => ({ useCreateJob: () => ({ mutateAsync, isPending: false }) }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

afterEach(() => {
  mutateAsync.mockReset();
});

function renderDialog(onOpenChange: (open: boolean) => void = () => undefined) {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <AddJobDialog open onOpenChange={onOpenChange} />
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

  it('closes the dialog when "Show it" is clicked after a 409 duplicate', async () => {
    mutateAsync.mockRejectedValueOnce(new ApiError(409, { title: "Conflict", status: 409, existing_job_id: "j9" }, "Conflict"));
    const onOpenChange = vi.fn();
    renderDialog(onOpenChange);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/job description/i), "x".repeat(60));
    await user.click(screen.getByRole("button", { name: /add job/i }));
    await user.click(await screen.findByRole("button", { name: /show it/i }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("resets every field (not just text/url) when the dialog is reopened", async () => {
    mutateAsync.mockResolvedValueOnce({ id: "j1" });
    const client = new QueryClient();
    const onOpenChange = vi.fn();
    const { rerender } = render(
      <QueryClientProvider client={client}>
        <AddJobDialog open onOpenChange={onOpenChange} />
      </QueryClientProvider>,
    );
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/job description/i), "x".repeat(60));
    await user.type(screen.getByLabelText(/company/i), "ExampleCo");
    await user.type(screen.getByLabelText(/title/i), "PM");
    await user.type(screen.getByLabelText(/location/i), "Remote");
    await user.click(screen.getByRole("button", { name: /add job/i }));
    expect(onOpenChange).toHaveBeenCalledWith(false);

    // The parent closes the dialog, then reopens it later.
    rerender(
      <QueryClientProvider client={client}>
        <AddJobDialog open={false} onOpenChange={onOpenChange} />
      </QueryClientProvider>,
    );
    rerender(
      <QueryClientProvider client={client}>
        <AddJobDialog open onOpenChange={onOpenChange} />
      </QueryClientProvider>,
    );

    expect(screen.getByLabelText(/job description/i)).toHaveValue("");
    expect(screen.getByLabelText(/company/i)).toHaveValue("");
    expect(screen.getByLabelText(/title/i)).toHaveValue("");
    expect(screen.getByLabelText(/location/i)).toHaveValue("");
  });
});
