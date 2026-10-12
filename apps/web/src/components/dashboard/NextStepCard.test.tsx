import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { JobOut } from "@/lib/api/queries";
import type { TailorStarter } from "@/lib/coach/useStartTailor";
import { NextStepCard } from "./NextStepCard";

const idle = (over: Partial<TailorStarter> = {}): TailorStarter => ({ start: vi.fn(), pickedId: null, error: null, failedJobId: null, ...over });
const job = { id: "j1", company: "Acme", title: "Program Manager" } as unknown as JobOut;

describe("NextStepCard", () => {
  it("review: names the company, role and fit, and links to the resume page", () => {
    render(
      <NextStepCard
        step={{ kind: "review", draft: { id: "p1", job_id: "j9", company: "Rigetti", title: "Senior TPM", best_fit: 78 } }}
        starter={idle()}
        onOpenApplication={vi.fn()}
      />,
    );
    expect(screen.getByText("Review your Rigetti resume")).toBeInTheDocument();
    expect(screen.getByText("Senior TPM · fit 78")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Review it" })).toHaveAttribute("href", "/jobs/j9/packages/p1");
  });

  it("review: leaves out fit when there is none", () => {
    render(
      <NextStepCard step={{ kind: "review", draft: { id: "p1", job_id: "j9", company: "Rigetti", title: "Senior TPM", best_fit: null } }} starter={idle()} onOpenApplication={vi.fn()} />,
    );
    expect(screen.getByText("Senior TPM")).toBeInTheDocument();
  });

  it("review list: a plain link to the To review tab", () => {
    render(<NextStepCard step={{ kind: "review-list" }} starter={idle()} onOpenApplication={vi.fn()} />);
    expect(screen.getByRole("link", { name: "Review them" })).toHaveAttribute("href", "/resumes?tab=review");
  });

  it("follow-up: opens that application", async () => {
    const user = userEvent.setup({ delay: null });
    const open = vi.fn();
    render(<NextStepCard step={{ kind: "followup", applicationId: "a1", company: "Sunrun", title: "PM" }} starter={idle()} onOpenApplication={open} />);
    expect(screen.getByText("Follow up with Sunrun")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Update status" }));
    expect(open).toHaveBeenCalledWith("a1");
  });

  it("tailor: starts through the shared starter and shows Starting while it runs", async () => {
    const user = userEvent.setup({ delay: null });
    const starter = idle();
    const { rerender } = render(<NextStepCard step={{ kind: "tailor", job }} starter={starter} onOpenApplication={vi.fn()} />);
    expect(screen.getByText("Tailor a resume for Acme")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Tailor a resume for Acme" }));
    expect(starter.start).toHaveBeenCalledWith(job);
    rerender(<NextStepCard step={{ kind: "tailor", job }} starter={idle({ pickedId: "j1" })} onOpenApplication={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Tailor a resume for Acme" })).toBeDisabled();
    expect(screen.getByRole("button")).toHaveTextContent("Starting…");
  });

  it("tailor: shows the error only for its own job", () => {
    const error = { message: "Could not start", next: "retry" } as never;
    const { rerender } = render(<NextStepCard step={{ kind: "tailor", job }} starter={idle({ error, failedJobId: "j1" })} onOpenApplication={vi.fn()} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Could not start");
    rerender(<NextStepCard step={{ kind: "tailor", job }} starter={idle({ error, failedJobId: "other" })} onOpenApplication={vi.fn()} />);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows a placeholder while loading and nothing when there is no step", () => {
    const { container, rerender } = render(<NextStepCard step={{ kind: "loading" }} starter={idle()} onOpenApplication={vi.fn()} />);
    expect(container.querySelector('[data-slot="skeleton"]')).not.toBeNull();
    expect(screen.queryByRole("link")).toBeNull();
    rerender(<NextStepCard step={null} starter={idle()} onOpenApplication={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("uses 44px phone-height actions", () => {
    render(<NextStepCard step={{ kind: "review-list" }} starter={idle()} onOpenApplication={vi.fn()} />);
    expect(screen.getByRole("link").className).toContain("max-md:min-h-11");
  });
});
