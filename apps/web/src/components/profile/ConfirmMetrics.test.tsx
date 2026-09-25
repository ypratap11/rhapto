import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Block } from "@/lib/api/queries";
import { ConfirmMetrics } from "./ConfirmMetrics";

const blocks: Block[] = [
  {
    id: "a",
    type: "achievement",
    org: null,
    role: null,
    period: null,
    content: "Cut costs 30%.",
    metric: "30%",
    verified: false,
    tags: [],
    attribution: null,
    concurrent: false,
    visibility: null,
  },
  {
    id: "b",
    type: "achievement",
    org: null,
    role: null,
    period: null,
    content: "Led team of 12.",
    metric: "12",
    verified: false,
    tags: [],
    attribution: null,
    concurrent: false,
    visibility: null,
  },
];

describe("ConfirmMetrics", () => {
  it("shows one number at a time with its sentence", () => {
    render(<ConfirmMetrics blocks={blocks} onConfirm={vi.fn()} onSkip={vi.fn()} onDone={vi.fn()} />);
    expect(screen.getByText(/Cut costs 30%/)).toBeInTheDocument();
    expect(screen.queryByText(/Led team of 12/)).not.toBeInTheDocument();
  });

  it("verifies only the block the user confirms", async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup({ delay: null });
    render(<ConfirmMetrics blocks={blocks} onConfirm={onConfirm} onSkip={vi.fn()} onDone={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /yes, .* accurate/i }));
    expect(onConfirm).toHaveBeenCalledWith("a");
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("leaves a skipped block unverified and moves on", async () => {
    const onSkip = vi.fn();
    const user = userEvent.setup({ delay: null });
    render(<ConfirmMetrics blocks={blocks} onConfirm={vi.fn()} onSkip={onSkip} onDone={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /skip/i }));
    expect(onSkip).toHaveBeenCalledWith("a");
    expect(screen.getByText(/Led team of 12/)).toBeInTheDocument();
  });

  it("explains what confirming buys", () => {
    render(<ConfirmMetrics blocks={blocks} onConfirm={vi.fn()} onSkip={vi.fn()} onDone={vi.fn()} />);
    expect(screen.getByText(/unconfirmed numbers are removed/i)).toBeInTheDocument();
  });
});
