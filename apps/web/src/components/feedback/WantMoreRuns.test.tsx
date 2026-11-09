import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { WANT_MORE_RUNS_TEXT, WantMoreRuns } from "./WantMoreRuns";

const mutateAsync = vi.fn();
vi.mock("@/lib/api/queries", () => ({ useSubmitFeedback: () => ({ mutateAsync, isPending: false }) }));

beforeEach(() => mutateAsync.mockReset());

it("records the request as quick feedback on the given page, then thanks without promising runs", async () => {
  mutateAsync.mockResolvedValueOnce({});
  render(<WantMoreRuns area="job_detail" />);
  await userEvent.click(screen.getByRole("button", { name: "Want more resumes? Tell us" }));
  expect(mutateAsync).toHaveBeenCalledWith({ form: "quick", page_area: "job_detail", answers: { kind: "idea", text: WANT_MORE_RUNS_TEXT } });
  expect(await screen.findByRole("status")).toHaveTextContent("We've noted that you'd like more");
  expect(screen.queryByRole("button")).toBeNull();
});

it("keeps the button and says so when the send fails", async () => {
  mutateAsync.mockRejectedValueOnce(new Error("network"));
  render(<WantMoreRuns area="coach" />);
  await userEvent.click(screen.getByRole("button"));
  expect(await screen.findByRole("alert")).toHaveTextContent("didn't send");
  expect(screen.getByRole("button")).toBeEnabled();
});
