import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { PollNowButton } from "./PollNowButton";

const mutateAsync = vi.fn();
let isPending = false;
vi.mock("@/lib/api/queries", () => ({
  usePollNow: () => ({ mutateAsync, isPending }),
}));

vi.mock("./TaskProgress", async () => {
  const { useEffect } = await import("react");
  return {
    TaskProgress: ({ taskId, onFinished }: { taskId: string; onFinished: (state: { status: string }) => void }) => {
      useEffect(() => {
        onFinished({ status: "succeeded" });
      }, [onFinished]);
      return <div>progress:{taskId}</div>;
    },
  };
});

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
    expect(onFinished).toHaveBeenCalled();
  });
});
