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

    expect(screen.getByText(/payments platform scope/i)).toBeInTheDocument();
    expect(screen.getByText("bullet")).toBeInTheDocument();
    expect(screen.getByText("summary")).toBeInTheDocument();

    // Edit 0 is a pure append (nothing removed), edit 1 replaces a word. The Before column only
    // ever shows removals, the After column (read view, since neither row is being edited) only
    // ever shows additions.
    const change0 = document.getElementById("change-0")!;
    expect(change0.querySelector('[data-slot="before-diff"] del')).toBeNull();
    expect(change0.querySelector('[data-slot="before-diff"] ins')).toBeNull();
    expect(change0.querySelector('[data-slot="after-preview"] ins')).toHaveTextContent("across four services");
    expect(change0.querySelector('[data-slot="after-preview"] del')).toBeNull();

    const change1 = document.getElementById("change-1")!;
    expect(change1.querySelector('[data-slot="before-diff"] del')).toHaveTextContent("juniors");
    expect(change1.querySelector('[data-slot="before-diff"] ins')).toBeNull();
    expect(change1.querySelector('[data-slot="after-preview"] ins')).toHaveTextContent("three junior engineers");
    expect(change1.querySelector('[data-slot="after-preview"] del')).toBeNull();

    const afters = screen.getAllByLabelText("After");
    expect(afters).toHaveLength(2);
    expect(afters[0]).toHaveValue("Led the payments rewrite across four services.");
    expect(afters[1]).toHaveValue("Mentored three junior engineers.");
  });

  it("renders a changed word inside <ins class=\"diff-add\"> and keeps a read-only After field out of tab order", () => {
    render(<ChangesPane pkg={pkg} violationsByPath={new Set()} />);

    const change1 = document.getElementById("change-1")!;
    const addedWord = change1.querySelector('[data-slot="after-preview"] ins.diff-add');
    expect(addedWord).toHaveTextContent("three junior engineers");

    const textarea = change1.querySelector('textarea[aria-invalid]')!;
    expect(textarea).toHaveAttribute("readonly");
    expect(textarea).toHaveAttribute("tabindex", "-1");
  });

  it("renders exactly one del (Before) and one ins (After) for a single replaced word", () => {
    const singleWordChange = {
      ...pkg,
      edits: [{ paragraph_id: "p-3", before: "Led the payments migration.", after: "Led the payments rewrite.", reason: "clarity" }],
    } as unknown as PackageOut;
    render(<ChangesPane pkg={singleWordChange} violationsByPath={new Set()} />);

    const card = document.getElementById("change-0")!;
    const before = card.querySelector('[data-slot="before-diff"]')!;
    const after = card.querySelector('[data-slot="after-preview"]')!;

    expect(before.querySelectorAll("del")).toHaveLength(1);
    expect(before.querySelector("del")).toHaveTextContent("migration");
    expect(before.querySelectorAll("ins")).toHaveLength(0);

    expect(after.querySelectorAll("ins")).toHaveLength(1);
    expect(after.querySelector("ins")).toHaveTextContent("rewrite");
    expect(after.querySelectorAll("del")).toHaveLength(0);

    // The whole document, front to back, has exactly one del and one ins.
    expect(card.querySelectorAll("del")).toHaveLength(1);
    expect(card.querySelectorAll("ins")).toHaveLength(1);
  });

  it("reveals the editable textarea when the After read view is clicked, and saves the typed text", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup({ delay: null });
    render(<ChangesPane pkg={pkg} violationsByPath={new Set()} onSave={onSave} />);

    const change1 = document.getElementById("change-1")!;
    const preview = change1.querySelector('[data-slot="after-preview"]');
    expect(preview).not.toBeNull();

    // Before any interaction, the After field is the (non-editable-looking) read view; the real
    // textarea underneath is not yet what's on screen.
    await user.click(preview!);

    // Clicking the read view hides it and focuses the real textarea.
    expect(change1.querySelector('[data-slot="after-preview"]')).toBeNull();

    const afters = screen.getAllByLabelText("After");
    await user.clear(afters[1]!);
    await user.type(afters[1]!, "Mentored three junior engineers to promotion.");
    await user.click(screen.getByRole("button", { name: /save as new version/i }));

    expect(onSave).toHaveBeenCalledWith([
      { paragraph_id: "p-3", after: "Led the payments rewrite across four services." },
      { paragraph_id: "p-6", after: "Mentored three junior engineers to promotion." },
    ]);
  });

  it("never shows the textarea for a non-editable change, even after clicking the read view", async () => {
    const user = userEvent.setup({ delay: null });
    render(<ChangesPane pkg={pkg} violationsByPath={new Set()} />);

    const change0 = document.getElementById("change-0")!;
    const preview = change0.querySelector('[data-slot="after-preview"]');
    expect(preview).not.toBeNull();
    expect(preview).toHaveAttribute("aria-hidden", "true");

    await user.click(preview!);

    // No onSave means no editing, so the click does nothing: the read view is still the one
    // showing (there is no editable textarea to hand off to).
    expect(change0.querySelector('[data-slot="after-preview"]')).not.toBeNull();
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
