import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/client";
import { PasteJob } from "./PasteJob";

const create = vi.fn();
vi.mock("@/lib/api/queries", () => ({ useCreateJob: () => ({ mutateAsync: create }) }));

const JD = "ExampleCo is hiring a Data Platform Program Manager to lead our Snowflake migration across teams. ".repeat(2);

beforeEach(() => create.mockReset());

describe("PasteJob", () => {
  it("will not send a description that is too short, and says so", async () => {
    render(<PasteJob onJob={vi.fn()} onCancel={vi.fn()} />);
    const user = userEvent.setup({ delay: null });
    await user.type(screen.getByLabelText(/job description/i), "too short");
    await user.click(screen.getByRole("button", { name: /use this job/i }));
    expect(screen.getByRole("alert")).toHaveTextContent(/at least 50 characters/i);
    expect(create).not.toHaveBeenCalled();
  });

  it("creates the job and hands its id on", async () => {
    create.mockResolvedValueOnce({ id: "job-1" });
    const onJob = vi.fn(async () => undefined);
    render(<PasteJob onJob={onJob} onCancel={vi.fn()} />);
    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByLabelText(/job description/i));
    await user.paste(JD);
    await user.click(screen.getByRole("button", { name: /use this job/i }));
    await waitFor(() => expect(onJob).toHaveBeenCalledWith("job-1"));
    expect(create).toHaveBeenCalledWith({ jd_text: JD.trim() }); // the component sends the trimmed text
  });

  it("a job already added (409) is reused, not an error", async () => {
    create.mockRejectedValueOnce(new ApiError(409, { title: "Conflict", status: 409, existing_job_id: "job-0" }, "x"));
    const onJob = vi.fn(async () => undefined);
    render(<PasteJob onJob={onJob} onCancel={vi.fn()} />);
    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByLabelText(/job description/i));
    await user.paste(JD);
    await user.click(screen.getByRole("button", { name: /use this job/i }));
    await waitFor(() => expect(onJob).toHaveBeenCalledWith("job-0"));
  });

  it("a double click creates one job", async () => {
    let release: (v: unknown) => void = () => undefined;
    create.mockImplementationOnce(() => new Promise((resolve) => { release = resolve; }));
    render(<PasteJob onJob={vi.fn(async () => undefined)} onCancel={vi.fn()} />);
    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByLabelText(/job description/i));
    await user.paste(JD);
    await user.dblClick(screen.getByRole("button", { name: /use this job/i }));
    expect(create).toHaveBeenCalledTimes(1);
    release({ id: "job-1" });
  });

  it("shows an error handed down by the parent (a refused start)", () => {
    render(<PasteJob error={{ message: "Rhapto isn't set up to tailor yet", next: "feedback" }} onJob={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Rhapto isn't set up to tailor yet");
  });

  it("Cancel goes back", async () => {
    const onCancel = vi.fn();
    render(<PasteJob onJob={vi.fn()} onCancel={onCancel} />);
    await userEvent.setup({ delay: null }).click(screen.getByRole("button", { name: /cancel/i }));
    expect(onCancel).toHaveBeenCalled();
  });
});
