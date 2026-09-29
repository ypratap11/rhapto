import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { PollNowButton } from "./PollNowButton";

const mutateAsync = vi.fn();
let isPending = false;
vi.mock("@/lib/api/queries", () => ({
  usePollNow: () => ({ mutateAsync, isPending }),
}));

// The fake finishes only when told to. Finishing on mount raced the assertion below: PollNowButton
// clears the progress line the moment the task finishes, so "progress:t1" could vanish before
// findByText saw it (green on one CI run, red on the next).
vi.mock("./TaskProgress", () => ({
  TaskProgress: ({ taskId, onFinished }: { taskId: string; onFinished: (state: { status: string }) => void }) => (
    <div>
      progress:{taskId}
      <button type="button" onClick={() => onFinished({ status: "succeeded" })}>
        finish task
      </button>
    </div>
  ),
}));

describe("PollNowButton", () => {
  it("disables while pending, then starts polling and reports the task id and finish", async () => {
    const onFinished = vi.fn();
    const { rerender } = render(<PollNowButton onFinished={onFinished} />);

    isPending = true;
    rerender(<PollNowButton onFinished={onFinished} />);
    expect(screen.getByRole("button", { name: /poll now/i })).toBeDisabled();

    isPending = false;
    mutateAsync.mockResolvedValueOnce({ id: "t1", status: "queued" });
    rerender(<PollNowButton onFinished={onFinished} />);
    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByRole("button", { name: /poll now/i }));

    expect(await screen.findByText("progress:t1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /poll now/i })).toBeDisabled();
    expect(onFinished).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "finish task" }));

    expect(onFinished).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("progress:t1")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /poll now/i })).toBeEnabled();
  });
});
