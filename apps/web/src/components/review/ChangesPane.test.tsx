import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ChangesPane } from "./ChangesPane";
import type { PackageOut } from "@/lib/api/queries";

const pkg = {
  id: "pkg-1",
  mode: "tune",
  edits: [
    { paragraph_id: "p-3", before: "Led the payments rewrite.", after: "Led the payments rewrite across four services.", reason: "the JD asks for payments platform scope" },
    { paragraph_id: "p-6", before: "Mentored juniors.", after: "Mentored three junior engineers.", reason: "the JD asks for mentoring" },
  ],
  source_document: {
    filename: "maya-chen-resume.docx",
    paragraphs: [
      { id: "p-1", text: "Maya Chen", role: "name", section: null },
      { id: "p-2", text: "Experience", role: "heading", section: "Experience" },
      { id: "p-3", text: "Led the payments rewrite.", role: "bullet", section: "Experience" },
      { id: "p-4", text: "   ", role: "other", section: "Experience" },
      { id: "p-5", text: "Summary", role: "heading", section: "Summary" },
      { id: "p-6", text: "Mentored juniors.", role: "summary", section: "Summary" },
    ],
    sections: [
      { heading: "Experience", paragraph_ids: ["p-2", "p-3", "p-4"] },
      { heading: "Summary", paragraph_ids: ["p-5", "p-6"] },
    ],
  },
} as unknown as PackageOut;

function violation(path: string): Set<string> {
  return new Set([path]);
}

describe("ChangesPane", () => {
  it("renders a card per edit with before text, the reason and a role chip", () => {
    render(<ChangesPane pkg={pkg} violationsByPath={new Set()} />);

    expect(screen.getByText("Led the payments rewrite.")).toBeInTheDocument();
    expect(screen.getByText("Mentored juniors.")).toBeInTheDocument();
    expect(screen.getByText(/payments platform scope/i)).toBeInTheDocument();
    expect(screen.getByText("bullet")).toBeInTheDocument();
    expect(screen.getByText("summary")).toBeInTheDocument();

    const afters = screen.getAllByLabelText("After");
    expect(afters).toHaveLength(2);
    expect(afters[0]).toHaveValue("Led the payments rewrite across four services.");
    expect(afters[1]).toHaveValue("Mentored three junior engineers.");
  });

  it("saves the full edited list with only the touched paragraph changed", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup({ delay: null });
    render(<ChangesPane pkg={pkg} violationsByPath={new Set()} onSave={onSave} />);

    const save = screen.getByRole("button", { name: /save as new version/i });
    expect(save).toBeDisabled();

    const afters = screen.getAllByLabelText("After");
    await user.clear(afters[1]!);
    await user.type(afters[1]!, "Mentored three junior engineers to promotion.");
    expect(save).toBeEnabled();
    await user.click(save);

    expect(onSave).toHaveBeenCalledWith([
      { paragraph_id: "p-3", after: "Led the payments rewrite across four services." },
      { paragraph_id: "p-6", after: "Mentored three junior engineers to promotion." },
    ]);
  });

  it("marks only the violating change card", () => {
    render(<ChangesPane pkg={pkg} violationsByPath={violation("edits[0]")} />);

    expect(document.getElementById("change-0")).toHaveAttribute("data-violation", "true");
    expect(document.getElementById("change-1")).toHaveAttribute("data-violation", "false");
  });

  it("shows the full document in order, skipping blank paragraphs and using the edited text", async () => {
    const user = userEvent.setup({ delay: null });
    render(<ChangesPane pkg={pkg} violationsByPath={new Set()} onSave={vi.fn()} />);

    const afters = screen.getAllByLabelText("After");
    await user.clear(afters[0]!);
    await user.type(afters[0]!, "Led the payments rewrite end to end.");

    const lines = screen.getByRole("list", { name: /full document/i }).querySelectorAll("li");
    expect([...lines].map((li) => li.textContent)).toEqual([
      "Maya Chen",
      "Experience",
      "Led the payments rewrite end to end.",
      "Summary",
      "Mentored three junior engineers.",
    ]);
  });
});
