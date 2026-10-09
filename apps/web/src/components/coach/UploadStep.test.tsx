import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/client";
import { DOCX_MESSAGE } from "@/lib/coach/errors";
import { readProposal } from "@/lib/coach/storage";
import { UploadStep } from "./UploadStep";

const order: string[] = [];
const uploadMock = vi.fn();
const importMock = vi.fn();
const fire = vi.fn<(step: string) => Promise<void>>(async () => undefined);
vi.mock("@/lib/api/queries", () => ({
  useUploadResumeDocument: () => ({ mutateAsync: uploadMock }),
  useImportResume: () => ({ mutateAsync: importMock }),
}));
vi.mock("@/lib/coach/events", () => ({ fireCoachEvent: (step: string) => fire(step) }));

const DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
const docx = (name = "Maya_Chen_Resume.docx") => new File(["x"], name, { type: DOCX });
const proposal = {
  blocks: [],
  tracks: [{ id: "tpm", name: "Technical Program Manager", field: "program-project-management", role: "technical-program-manager", keywords: [] }],
  location: { location_home: "Denver, CO", location_preferred: [], remote_ok: null },
  dropped_periods: 0,
  metrics_to_confirm: 0,
};

function pick(file: File) {
  fireEvent.change(screen.getByLabelText(/choose your resume/i), { target: { files: [file] } });
}

beforeEach(() => {
  order.length = 0;
  uploadMock.mockReset().mockImplementation(async () => { order.push("upload"); return {}; });
  importMock.mockReset().mockImplementation(async () => { order.push("import"); return proposal; });
  fire.mockClear();
});
afterEach(() => window.sessionStorage.clear());

describe("UploadStep", () => {
  it("stores the document first, then imports, then reports both, and caches only tracks and location", async () => {
    const onDone = vi.fn();
    render(<UploadStep userId="u1" existingDocumentName={null} onDone={onDone} />);
    pick(docx());
    await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
    expect(order).toEqual(["upload", "import"]);
    expect(onDone).toHaveBeenCalledWith({
      filename: "Maya_Chen_Resume.docx",
      proposal: { tracks: proposal.tracks, location: proposal.location },
      importError: null,
    });
    expect(readProposal("u1")).toEqual({ tracks: proposal.tracks, location: proposal.location });
    expect(fire).toHaveBeenCalledWith("resume_in");
  });

  it("a_document_failure_stops_before_import: nothing has been spent, the Save-as sentence is shown", async () => {
    uploadMock.mockRejectedValueOnce(new ApiError(422, { title: "x", status: 422 }, "x"));
    const onDone = vi.fn();
    render(<UploadStep userId="u1" existingDocumentName={null} onDone={onDone} />);
    pick(docx());
    expect(await screen.findByRole("alert")).toHaveTextContent(DOCX_MESSAGE);
    expect(importMock).not.toHaveBeenCalled();
    expect(onDone).not.toHaveBeenCalled();
    expect(fire).not.toHaveBeenCalled();
    expect(screen.getByLabelText(/choose your resume/i)).not.toBeDisabled(); // can try again
  });

  it("when the import fails the document is already stored: report the plain error and carry on", async () => {
    importMock.mockRejectedValueOnce(new ApiError(422, { title: "x", status: 422 }, "x"));
    const onDone = vi.fn();
    render(<UploadStep userId="u1" existingDocumentName={null} onDone={onDone} />);
    pick(docx());
    await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
    expect(onDone.mock.calls[0]![0]).toMatchObject({
      proposal: null,
      importError: { message: "We couldn't read the roles in this resume", next: "role-picker" },
    });
    expect(readProposal("u1")).toBeNull();
    expect(fire).toHaveBeenCalledWith("resume_in"); // the resume did come in
  });

  it("the_upload_control_is_disabled_while_a_request_is_in_flight, and a second pick does nothing", async () => {
    let release: (v: unknown) => void = () => undefined;
    uploadMock.mockImplementationOnce(() => new Promise((resolve) => { release = resolve; }));
    render(<UploadStep userId="u1" existingDocumentName={null} onDone={vi.fn()} />);
    pick(docx());
    await waitFor(() => expect(screen.getByLabelText(/choose your resume/i)).toBeDisabled());
    expect(screen.getByRole("button", { name: /choose a file/i })).toBeDisabled();
    pick(docx("Again.docx"));
    expect(uploadMock).toHaveBeenCalledTimes(1);
    release({});
    await waitFor(() => expect(importMock).toHaveBeenCalledTimes(1));
  });

  it("rejects a PDF or an oversized file before any request", () => {
    render(<UploadStep userId="u1" existingDocumentName={null} onDone={vi.fn()} />);
    pick(new File(["x"], "cv.pdf", { type: "application/pdf" }));
    expect(screen.getByRole("alert")).toHaveTextContent(DOCX_MESSAGE);
    expect(uploadMock).not.toHaveBeenCalled();
  });

  it("says a re-upload replaces the resume on file", () => {
    render(<UploadStep userId="u1" existingDocumentName="Old_Resume.docx" onDone={vi.fn()} />);
    expect(screen.getByText(/Old_Resume\.docx/)).toBeInTheDocument();
    expect(screen.getByText(/replaces it/i)).toBeInTheDocument();
  });

  it("has the skip link", () => {
    render(<UploadStep userId="u1" existingDocumentName={null} onDone={vi.fn()} />);
    expect(screen.getByRole("link", { name: /skip to the full app/i })).toHaveAttribute("href", "/dashboard");
  });
});
