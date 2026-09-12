import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ResumeDocumentOut } from "@/lib/api/queries";
import { ResumeDocumentTab } from "./ResumeDocumentTab";

const uploadMutateAsync = vi.fn();
const deleteMutateAsync = vi.fn();
let resumeDocumentData: ResumeDocumentOut | null = null;

vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useResumeDocument: () => ({ data: resumeDocumentData, isLoading: false, error: null }),
  useUploadResumeDocument: () => ({ mutateAsync: uploadMutateAsync, isPending: false }),
  useDeleteResumeDocument: () => ({ mutateAsync: deleteMutateAsync, isPending: false }),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const doc: ResumeDocumentOut = {
  filename: "maya-chen-resume.docx",
  uploaded_at: "2026-09-10T12:00:00Z",
  document: {
    filename: "maya-chen-resume.docx",
    paragraphs: [
      { id: "p1", role: "heading", text: "Work Experience" },
      { id: "p2", role: "summary", text: "Product leader with 10 years of experience shipping B2B SaaS." },
      { id: "p3", role: "bullet", text: "Led the migration that cut checkout latency by 30%." },
    ],
    sections: [
      { heading: "Summary", paragraph_ids: ["p2"] },
      { heading: "Experience", paragraph_ids: ["p1", "p3"] },
    ],
  },
};

function renderTab() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <ResumeDocumentTab />
    </QueryClientProvider>,
  );
}

describe("ResumeDocumentTab", () => {
  beforeEach(() => {
    resumeDocumentData = null;
    uploadMutateAsync.mockReset();
    deleteMutateAsync.mockReset();
  });

  it("renders the upload zone when there is no document", () => {
    renderTab();
    expect(screen.getByText(/upload your resume \(\.docx\) to tailor it directly\. tune mode switches on automatically\./i)).toBeInTheDocument();
    expect(screen.getByLabelText("Resume document")).toBeInTheDocument();
  });

  it("renders the filename, section headings, and role chips when a document exists", () => {
    resumeDocumentData = doc;
    renderTab();
    expect(screen.getByText("maya-chen-resume.docx")).toBeInTheDocument();
    expect(screen.getByText("Summary")).toBeInTheDocument();
    expect(screen.getByText("Experience")).toBeInTheDocument();
    expect(screen.getByText("summary")).toBeInTheDocument();
    expect(screen.getByText("heading")).toBeInTheDocument();
  });

  it("sends the chosen file to the upload mutation", async () => {
    // A real change event on the file input, not a direct call to the handler: this is the only
    // test that proves the input is wired to the mutation at all.
    uploadMutateAsync.mockResolvedValue(undefined);
    renderTab();
    const user = userEvent.setup({ delay: null });
    const file = new File(["PK"], "maya-chen-resume.docx", {
      type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    });

    await user.upload(screen.getByLabelText("Resume document"), file);

    expect(uploadMutateAsync).toHaveBeenCalledTimes(1);
    const sent = uploadMutateAsync.mock.calls[0]?.[0] as unknown;
    expect(sent).toBeInstanceOf(File);
    expect((sent as File).name).toBe("maya-chen-resume.docx");
  });

  it("deletes the document after confirming", async () => {
    resumeDocumentData = doc;
    renderTab();
    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByRole("button", { name: /delete maya-chen-resume\.docx/i }));
    expect(screen.getByText(/delete maya-chen-resume\.docx\?/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^delete$/i }));
    expect(deleteMutateAsync).toHaveBeenCalled();
  });

  it("closes the dialog and shows the empty state once the delete resolves", async () => {
    resumeDocumentData = doc;
    // The component renders from `useResumeDocument()`, so the delete's effect on the UI is the
    // query going back to null -- which is what the mutation's onSuccess invalidation produces.
    deleteMutateAsync.mockImplementation(async () => {
      resumeDocumentData = null;
    });
    renderTab();
    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByRole("button", { name: /delete maya-chen-resume\.docx/i }));
    await user.click(screen.getByRole("button", { name: /^delete$/i }));

    expect(await screen.findByText(/upload your resume \(\.docx\)/i)).toBeInTheDocument();
    expect(screen.queryByText(/delete maya-chen-resume\.docx\?/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /delete maya-chen-resume\.docx/i })).not.toBeInTheDocument();
  });
});
